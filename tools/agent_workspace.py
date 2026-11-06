"""Read a pinned public checkout and publish only approved, tested Python changes."""
from io import BytesIO
import json
from pathlib import Path
import re
import stat
from zipfile import ZipFile

import httpx2

from bountyguard.domain import digest, issue_context
from bountyguard.github import GitHub
from bountyguard.sandbox import safe_path
from tools.agent_wallet import DemoError

SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+")


class Repository:
    def __init__(self, github, bounty, login):
        self.github = github
        self.bounty = bounty
        self.repo = bounty["repo"]
        if not REPO.fullmatch(self.repo) or not re.fullmatch(r"[A-Za-z0-9-]+", login):
            raise DemoError("Invalid GitHub repository or agent login.")
        self.fork = login + "/" + self.repo.split("/")[1]
        self.branch = "bountyguard-" + bounty["id"]
        self.upstream = "/repos/" + self.repo
        self.fork_api = "/repos/" + self.fork

    def preflight(self, *, open_issue=True):
        upstream = self.github.repo(self.repo)
        fork = self.github.repo(self.fork)
        if (upstream["id"] != self.bounty["repo_id"] or upstream.get("private")
                or fork.get("private") or not fork.get("fork")
                or fork.get("parent", {}).get("id") != upstream["id"]
                or fork["owner"]["id"] != self.github.me()["id"]
                or not fork.get("permissions", {}).get("push")):
            raise DemoError("Prepare a writable public fork owned by the machine account first.")
        branch = upstream["default_branch"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", branch) or branch in (".", "..", self.branch):
            raise DemoError("Unsupported default branch.")
        self.base = branch
        if open_issue:
            issue = self.github.issue(self.repo, self.bounty["issue_number"])
            if issue["state"] != "open" or digest(issue_context(issue, upstream["id"])) != self.bounty["issue_hash"]:
                raise DemoError("GitHub Issue is closed or differs from the agreed terms.")

    def base_commit(self):
        commit = self.github.request(self.upstream + "/commits/" + self.base)
        if not SHA.fullmatch(commit["sha"]) or not SHA.fullmatch(commit["commit"]["tree"]["sha"]):
            raise DemoError("GitHub did not return a valid base revision.")
        fork_commit = self.github.request(self.fork_api + "/git/commits/" + commit["sha"])
        if fork_commit["sha"] != commit["sha"]:
            raise DemoError("Sync the Agent fork with the upstream revision first.")
        return {"sha": commit["sha"], "tree": commit["commit"]["tree"]["sha"], "branch": self.base}

    def pr(self, head):
        query = httpx2.QueryParams({"state": "all", "head": self.fork.split("/")[0] + ":" + self.branch,
                                   "base": self.base})
        results = self.github.pages(self.upstream + "/pulls?" + str(query), max_items=10)
        if not results:
            return None
        if len(results) != 1:
            raise DemoError("More than one PR matches the dedicated branch.")
        pr = self.github.request(self.upstream + "/pulls/" + str(results[0]["number"]))
        if (pr["head"]["sha"] != head or pr["head"]["ref"] != self.branch
                or (pr["head"].get("repo") or {}).get("full_name", "").lower() != self.fork.lower()
                or pr["base"]["repo"]["id"] != self.bounty["repo_id"]
                or pr["base"]["ref"] != self.base or pr["user"]["id"] != self.github.me()["id"]
                or (pr["state"] != "open" and not pr["merged"])):
            raise DemoError("Existing PR differs from the approved actor, branch or tested revision.")
        return pr

    def create_pr(self):
        return self.github.request(self.upstream + "/pulls", {
            "title": f"Fix bounty issue #{self.bounty['issue_number']}",
            "body": f"Closes #{self.bounty['issue_number']}\n\nSubmitted by the BountyGuard demo agent after isolated Python tests.",
            "head": self.fork.split("/")[0] + ":" + self.branch, "base": self.base,
            "maintainer_can_modify": False,
        })

    def commit(self, base, changes):
        tree = self.github.request(self.fork_api + "/git/trees", {
            "base_tree": base["tree"],
            "tree": [{"path": path, "mode": "100644", "type": "blob", "content": content}
                     for path, content in sorted(changes.items())],
        })
        if not SHA.fullmatch(tree["sha"]):
            raise DemoError("GitHub returned an invalid tree.")
        commit = self.github.request(self.fork_api + "/git/commits", {
            "message": f"Fix issue #{self.bounty['issue_number']}", "tree": tree["sha"], "parents": [base["sha"]],
        })
        if not SHA.fullmatch(commit["sha"]):
            raise DemoError("GitHub returned an invalid commit.")
        return commit["sha"]

    def branch_head(self):
        refs = self.github.request(self.fork_api + "/git/matching-refs/heads/" + self.branch)
        matches = [ref["object"]["sha"] for ref in refs if ref["ref"] == "refs/heads/" + self.branch]
        return matches[0] if matches else None

    def create_branch(self, head):
        self.github.request(self.fork_api + "/git/refs", {"ref": "refs/heads/" + self.branch, "sha": head})

    def ci(self, pr):
        return self.github.ci_evidence(self.repo, pr, self.bounty["ci"])


def snapshot(repo, sha, directory):
    if not REPO.fullmatch(repo) or not SHA.fullmatch(sha):
        raise DemoError("Invalid checkout coordinates.")
    with httpx2.Client(trust_env=False, timeout=30) as client:
        with client.stream("GET", f"https://codeload.github.com/{repo}/zip/{sha}") as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 8_000_000:
                    raise DemoError("Repository archive exceeds the demo limit.")
    unpack(data, directory)


def unpack(data, directory):
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 400 or sum(entry.file_size for entry in entries) > 16_000_000:
            raise DemoError("Unsupported archive size.")
        root = entries[0].filename.split("/")[0]
        files = set()
        for entry in entries:
            top, _, relative = entry.filename.partition("/")
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (top != root or (relative and not safe_path(relative.rstrip("/")))
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise DemoError("Unsupported archive path or file type.")
            if entry.is_dir():
                continue
            if not relative or relative.lower() in files:
                raise DemoError("Archive contains an invalid or duplicate file.")
            files.add(relative.lower())
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(archive.read(entry))
