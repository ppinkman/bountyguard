"""Read-only GitHub connector. No arbitrary URLs, PR execution or GitHub writes."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .domain import GuardError, github_url
from .python_changes import implementation_changed


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GuardError("Upstream redirect requires explicit repository revalidation.")


def opener():
    handlers = [NoRedirect()]
    if os.getenv("BOUNTYGUARD_DIRECT_NETWORK") == "1":
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


class GitHub:
    def __init__(self, token=None):
        self.token = token or None

    def request(self, path, body=None):
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise GuardError("Invalid GitHub API path.")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "BountyGuard/0.1"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = json.dumps(body).encode() if body is not None else None
        if data:
            headers["Content-Type"] = "application/json"
        try:
            with opener().open(urllib.request.Request("https://api.github.com" + path, data=data, headers=headers), timeout=20) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise GuardError("GitHub response exceeds the supported evidence limit.")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise GuardError("GitHub returned HTTP " + str(exc.code) + "; check access and rate limits.", 502) from None
        except (OSError, ValueError):
            raise GuardError("GitHub evidence is unavailable. No acceptance or payment was authorized.", 502) from None

    def me(self):
        actor = self.request("/user")
        if not isinstance(actor.get("id"), int) or not actor.get("login"):
            raise GuardError("GitHub identity could not be verified.", 401)
        return {"id": actor["id"], "login": actor["login"]}

    def repo(self, repo):
        return self.request("/repos/" + repo)

    def issue(self, repo, number):
        result = self.request(f"/repos/{repo}/issues/{number}")
        if "pull_request" in result:
            raise GuardError("Choose an Issue, not a pull request.", 422)
        return result

    def file(self, repo, path, ref):
        result = self.request(f"/repos/{repo}/contents/{urllib.parse.quote(path, safe='/')}?ref={urllib.parse.quote(ref, safe='')}")
        if result.get("type") != "file" or result.get("encoding") != "base64" or result.get("size", 999999) > 100_000:
            raise GuardError("The selected source must be an ordinary, bounded repository file.")
        content = base64.b64decode(result["content"], validate=False)
        return {"sha": result["sha"], "content": content.decode("utf-8")}

    def workflow(self, repo, path):
        return self.request(f"/repos/{repo}/actions/workflows/{urllib.parse.quote(path.rsplit('/',1)[-1])}")

    def pages(self, path, key=None, max_items=100):
        collected = []
        for page in range(1, max_items // 100 + 2):
            separator = "&" if "?" in path else "?"
            result = self.request(path + separator + f"per_page=100&page={page}")
            batch = result[key] if key else result
            collected.extend(batch)
            if len(collected) > max_items:
                raise GuardError("Evidence exceeds the supported size; manual review is required.")
            if len(batch) < 100:
                if key and result.get("total_count", len(collected)) > len(collected):
                    raise GuardError("GitHub returned incomplete evidence.")
                return collected
        raise GuardError("Evidence pagination did not finish.")

    def closes_issue(self, repo, pr_number, issue_number):
        if not self.token:
            raise GuardError("Authenticated GitHub access is required to verify Issue linkage.")
        owner, name = repo.split("/")
        result = self.request("/graphql", {"query": "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){closingIssuesReferences(first:100){nodes{number repository{databaseId}} pageInfo{hasNextPage}}}}}", "variables": {"owner": owner, "name": name, "number": pr_number}})
        try:
            references = result["data"]["repository"]["pullRequest"]["closingIssuesReferences"]
            if result.get("errors") or references["pageInfo"]["hasNextPage"]:
                raise KeyError()
            return references["nodes"]
        except (KeyError, TypeError):
            raise GuardError("GitHub could not establish complete closing-Issue linkage.") from None

    def pr_snapshot(self, repo, number):
        pr = self.request(f"/repos/{repo}/pulls/{number}")
        files = self.pages(f"/repos/{repo}/pulls/{number}/files", max_items=40)
        if len(files) != pr["changed_files"]:
            raise GuardError("PR file evidence is incomplete.")
        patches = []
        for file in files:
            if not file.get("patch") or len(file["patch"].encode()) > 24_000:
                raise GuardError("Binary, missing or oversized patches require manual review.")
            added = sum(line.startswith("+") for line in file["patch"].splitlines())
            removed = sum(line.startswith("-") for line in file["patch"].splitlines())
            if added != file["additions"] or removed != file["deletions"]:
                raise GuardError("Patch line counts do not match GitHub's file metadata; incomplete evidence cannot pass.")
            patches.append({key: file.get(key) for key in ("filename", "previous_filename", "status", "sha", "patch", "additions", "deletions")})
        if len(json.dumps(patches).encode()) > 48_000:
            raise GuardError("PR exceeds the bounded review size.")
        after = self.request(f"/repos/{repo}/pulls/{number}")
        if after["head"]["sha"] != pr["head"]["sha"] or after["base"]["sha"] != pr["base"]["sha"]:
            raise GuardError("PR changed while collecting evidence. Recheck its new revision.")
        source_bytes = 0
        for file in patches:
            if not file["filename"].endswith(".py"):
                continue
            before = "" if file["status"] == "added" else self.file(repo, file.get("previous_filename") or file["filename"], pr["base"]["sha"])["content"]
            after = "" if file["status"] == "removed" else self.file(pr["head"]["repo"]["full_name"], file["filename"], pr["head"]["sha"])["content"]
            source_bytes += len(before.encode("utf-8")) + len(after.encode("utf-8"))
            if source_bytes > 400_000:
                raise GuardError("Combined Python source exceeds the review budget.")
            file["implementation_changed"] = implementation_changed(before, after)
        return pr, sorted(patches, key=lambda item: item["filename"])

    def ci_evidence(self, repo, pr, policy, accepted=None):
        head = pr["head"]["sha"]
        path = f"/repos/{repo}/actions/workflows/{policy['workflow_id']}/runs?event=pull_request&head_sha={head}"
        runs = self.pages(path, "workflow_runs", max_items=100)
        candidates = [r for r in runs if r["workflow_id"] == policy["workflow_id"] and r["head_sha"] == head and r["event"] == "pull_request" and r.get("path") == policy["workflow_path"]]
        if not candidates:
            return {"passed": False, "reason": "No matching trusted pull_request workflow run.", "runs": []}
        run = max(candidates, key=lambda r: r["id"])
        associated = any(p["number"] == pr["number"] and p["head"]["sha"] == head and p["base"]["sha"] == pr["base"]["sha"] for p in run.get("pull_requests", []))
        jobs = self.pages(f"/repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest", "jobs", max_items=100)
        checks = []
        for name in policy["required_checks"]:
            matches = [j for j in jobs if j["name"] == name]
            if len(matches) != 1:
                return {"passed": False, "reason": "Required check missing or ambiguous: " + name, "run_id": run["id"]}
            job = matches[0]
            check_id = job.get("check_run_url", "").rsplit("/", 1)[-1]
            if not check_id.isdigit():
                raise GuardError("Missing check-run binding.")
            check = self.request(f"/repos/{repo}/check-runs/{check_id}")
            checks.append({"name": name, "job_id": job["id"], "check_run_id": int(check_id), "app_id": check.get("app", {}).get("id"), "app_slug": check.get("app", {}).get("slug"), "suite_id": check.get("check_suite", {}).get("id"), "tested_sha": check.get("head_sha"), "status": check["status"], "conclusion": check.get("conclusion"), "job_passed": job["status"] == "completed" and job.get("conclusion") == "success"})
        association_source = "live PR head/base association"
        if not associated and pr.get("merged") and accepted:
            # GitHub clears run.pull_requests after merge. Only the exact
            # previously accepted run/attempt/checks may retain its association.
            # The settlement caller separately verifies merge parent ancestry.
            associated = bool(accepted.get("passed") and accepted.get("run_id") == run["id"] and accepted.get("run_attempt") == run.get("run_attempt") and accepted.get("head_sha") == head and accepted.get("base_sha") == pr["base"]["sha"] and accepted.get("checks") == checks)
            association_source = "pinned pre-merge association; matching immutable run/attempt/checks"
        passed = associated and run["status"] == "completed" and run.get("conclusion") == "success" and all(c["job_passed"] and c["app_id"] == policy["app_id"] and c["app_slug"] == "github-actions" and c["suite_id"] == run["check_suite_id"] and c["status"] == "completed" and c["conclusion"] == "success" for c in checks)
        # check-run head_sha may be a GitHub-generated merge commit. The workflow
        # run, suite, job and PR head/base association must all agree instead.
        return {"passed": passed, "reason": "Trusted workflow evidence passed." if passed else "Workflow/commit association or required checks did not pass.", "association_source": association_source, "run_id": run["id"], "run_attempt": run.get("run_attempt"), "head_sha": head, "base_sha": pr["base"]["sha"], "checks": checks}
