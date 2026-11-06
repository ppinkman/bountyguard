"""Run one explicitly approved BountyGuard bounty as a separate GitHub actor."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import tempfile
import time

from bountyguard.domain import GuardError, testnet_account
from bountyguard.github import GitHub
from bountyguard.sandbox import DockerTests, IsolationError, editable, scan_edits
from tools.agent_client import ROOT, call_tool
from tools.agent_coding import CodingModel
from tools.agent_wallet import DemoError, LocalAPI, bind, checked_id
from tools.agent_workspace import Repository, SHA, snapshot

DATA = ROOT / "data" / "agent"
TERMINAL = {"REFUNDED", "REVISION_CHANGED", "SETTLEMENT_ATTENTION"}
TX = re.compile(r"[1-9A-HJ-NP-Za-km-z]{43,44}")


class Journal:
    def __init__(self, path, config):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"config": config, "events": []}
        if self.data["config"] != config:
            raise DemoError("Resume with the original identity, terms, files, image and model limits.")

    def save(self, event, *, evidence=None, **fields):
        self.data.update(fields)
        record = {"at": int(time.time()), "event": event, **(evidence or {})}
        self.data["events"].append(record)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        print(json.dumps(record), flush=True)


def payment(bounty, head):
    receipt = bounty.get("payment_receipt") or {}
    report = bounty.get("review") or {}
    tx = receipt.get("transaction_hash", "")
    if (bounty["state"] != "PAID" or not TX.fullmatch(tx) or receipt.get("network") != "testnet"
            or receipt.get("final_execution_status") != "FINAL" or "SuccessValue" not in (receipt.get("status") or {})
            or report.get("head_sha") != head
            or report.get("verdict") != "PASS" or not report.get("ci", {}).get("passed")):
        raise DemoError("No final testnet payment receipt for this Agent revision.")
    testnet_account(receipt["contract"])
    return {"contract": receipt["contract"], "transaction_hash": tx, "head_sha": head,
            "report_hash": report["report_hash"], "delivery_hash": report["delivery_hash"],
            "ci_run_id": report["ci"]["run_id"], "merge_sha": bounty["merge_evidence"]["merge_commit_sha"]}


class Demo:
    def __init__(self, config, journal, mcp, repo, bind_wallet, model, tests,
                 checkout=snapshot, *, seconds=1800, poll=12, secrets=()):
        self.config, self.journal = config, journal
        self.mcp, self.repo, self.bind_wallet = mcp, repo, bind_wallet
        self.model, self.tests, self.checkout = model, tests, checkout
        self.deadline, self.poll = time.monotonic() + seconds, poll
        self.secrets = secrets

    @property
    def state(self):
        return self.journal.data

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise DemoError("Run timed out. Resume the same bounty to continue from its checkpoint.")

    async def tool(self, name, **args):
        self.check_time()
        try:
            result = await self.mcp(name, bounty_id=self.config["bounty_id"], **args)
        except Exception:
            raise DemoError("MCP call failed. Check the bounty before resuming; no raw response was logged.") from None
        self.journal.save("mcp", evidence={"tool": name, "state": result.get("state")})
        return result

    async def current(self):
        bounty = await self.tool("get_bounty")
        if (bounty["id"] != self.config["bounty_id"] or bounty["terms_hash"] != self.config["terms_hash"]
                or bounty["network"] != "testnet" or bounty["creator_id"] == self.config["actor_id"]):
            raise DemoError("Bounty terms, network or role changed.")
        if bounty["state"] in TERMINAL or (bounty["state"] != "PAID" and bounty["deadline"] <= time.time()):
            raise DemoError("Bounty expired or needs maintainer attention.")
        if bounty["state"] != "DRAFT" and not self.owns(bounty.get("claim") or {}):
            raise DemoError("The funded claim belongs to a different identity or wallet.")
        return bounty

    def owns(self, claim):
        return claim.get("actor_id") == self.config["actor_id"] and claim.get("near_account_id") == self.config["account"]

    async def wait(self, condition):
        while True:
            bounty = await self.current()
            result = condition(bounty)
            if result is not None:
                return result
            self.check_time()
            await asyncio.sleep(min(self.poll, max(0, self.deadline - time.monotonic())))

    async def claim(self, bounty):
        if bounty["state"] == "DRAFT" and not any(self.owns(claim) for claim in bounty.get("claims", [])):
            self.check_time()
            self.bind_wallet(bounty)
            self.journal.save("claim_intent")
            claim = await self.tool("request_claim")
            if not self.owns(claim):
                raise DemoError("Claim result does not match the Agent identity.")
            self.journal.save("claim_requested", evidence={"claim_id": claim["id"]})
        return await self.wait(lambda current: current if current.get("funding_receipt") else None)

    def prepare(self, bounty):
        if "head" in self.state:
            return self.state["head"]
        base = self.state["base"]
        if base["branch"] != self.repo.base:
            raise DemoError("The repository default branch changed.")
        with tempfile.TemporaryDirectory(prefix="bountyguard-", dir=self.journal.path.parent) as temp:
            workspace = Path(temp)
            self.checkout(bounty["repo"], base["sha"], workspace)
            original = {name: (workspace / name).read_text(encoding="utf-8") if (workspace / name).is_file() else None
                        for name in self.config["files"]}
            if any(name.startswith("tests/") and text is not None for name, text in original.items()):
                raise DemoError("The demo can add a regression test but cannot modify existing tests.")
            if not any(text is not None and any(name.startswith(p) for p in bounty["source_paths"])
                       for name, text in original.items()):
                raise DemoError("Allow at least one existing Python file under an agreed source path.")
            while "tested_edits" not in self.state:
                self.check_time()
                if self.state.get("coding_pending"):
                    raise DemoError("Original coding request is uncertain. Automatic replay is disabled.")
                if "candidate" not in self.state:
                    count = self.state.get("requests", 0)
                    if count >= self.config["requests"]:
                        raise DemoError("Local tests or candidate validation failed within the coding request limit.")
                    self.journal.save("coding_intent", evidence={"request": count + 1},
                                      requests=count + 1, coding_pending=True)
                    edits, evidence = self.model.propose(bounty["issue"], original, retry=count > 0)
                    edits = scan_edits(original, edits, self.secrets)
                    if not any(any(name.startswith(p) for p in bounty["source_paths"]) for name in edits):
                        raise DemoError("Candidate lacks a change under an agreed source path.")
                    self.journal.save("coding_response", evidence=evidence, candidate=edits, coding_pending=False)
                edits = scan_edits(original, self.state["candidate"], self.secrets)
                for name, content in edits.items():
                    path = workspace / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content.encode("utf-8"))
                self.check_time()
                passed = self.tests.test(workspace)
                if passed:
                    self.journal.save("isolated_tests_passed", tested_edits=edits)
                else:
                    for name in edits:
                        path = workspace / name
                        if original[name] is None:
                            path.unlink()
                        else:
                            path.write_bytes(original[name].encode("utf-8"))
                    self.state.pop("candidate")
                    self.journal.save("isolated_tests_failed")
            edits = scan_edits(original, self.state["tested_edits"], self.secrets)
            self.check_time()
            head = self.repo.commit(base, edits)
            self.journal.save("commit_prepared", evidence={"head_sha": head}, head=head)
        return head

    def publish(self, head):
        self.check_time()
        existing = self.repo.branch_head()
        if existing is None:
            self.journal.save("create_branch_intent", evidence={"head_sha": head})
            self.repo.create_branch(head)
            existing = self.repo.branch_head()
        if existing != head:
            raise DemoError("The dedicated fork branch does not point at the tested commit.")
        pr = self.repo.pr(head)
        if pr is None:
            self.check_time()
            if self.state.get("pr_intent"):
                raise DemoError("Original PR creation is uncertain. Inspect GitHub, then resume once it is visible.")
            self.journal.save("create_pr_intent", pr_intent=True)
            self.repo.create_pr()
            pr = self.repo.pr(head)
        if pr is None:
            raise DemoError("PR is not visible yet. Resume after GitHub shows it.")
        self.journal.save("pr_observed", evidence={"pr_url": pr["html_url"], "head_sha": head})
        return pr["html_url"]

    async def run(self):
        bounty = await self.current()
        head = self.state.get("head")
        if bounty["state"] != "PAID":
            self.repo.preflight(open_issue=bounty["state"] in {"DRAFT", "ASSIGNED", "FUNDING_UNCERTAIN", "FUNDED"})
            if not head:
                self.tests.check()
                if "base" not in self.state:
                    base = self.repo.base_commit()
                    self.journal.save("base_pinned", evidence={"base_sha": base["sha"]}, base=base)
            bounty = await self.claim(bounty)
            if bounty["state"] in {"FUNDED", "PR_SUBMITTED", "REVIEW_REQUIRED"}:
                head = self.prepare(bounty)
                url = self.publish(head)
                if not bounty.get("pr_url"):
                    await self.tool("submit_pull_request", pr_url=url)
                elif bounty["pr_url"] != url:
                    raise DemoError("Another PR was already submitted for this bounty.")

                def trusted_ci(current):
                    if current["state"] in {"READY_TO_MERGE", "PAID"}:
                        return current
                    self.check_time()
                    ci = self.repo.ci(self.repo.pr(head))
                    if ci["passed"]:
                        self.journal.save("trusted_ci_passed", evidence={"ci_run_id": ci["run_id"], "head_sha": head})
                        return current
                    if ci.get("association_missing"):
                        self.journal.save("ci_association_missing", evidence={"ci_run_id": ci["run_id"], "head_sha": head})
                        raise DemoError("GitHub reported passing CI without the required PR/base link. Review was not requested.")
                    if not self.state.get("ci_wait"):
                        self.journal.save("waiting_for_trusted_ci", ci_wait=True)

                bounty = await self.wait(trusted_ci)
                if bounty["state"] not in {"READY_TO_MERGE", "PAID"}:
                    if self.state.get("review_intent"):
                        raise DemoError("Review was already requested. Check the existing result before taking further action.")
                    self.journal.save("review_intent", review_intent=True)
                    bounty = await self.tool("review_pull_request", use_model=True)
                if bounty["state"] not in {"READY_TO_MERGE", "PAID"}:
                    raise DemoError("Review did not clear the PR for merge.")
            if (bounty.get("review") or {}).get("head_sha") != head or not head:
                raise DemoError("Reviewed revision does not match the Agent's tested commit.")
            bounty = await self.wait(lambda current: current if current["state"] == "PAID" else None)
        result = payment(bounty, head)
        self.journal.save("paid_receipt", evidence=result)
        evidence = {
            "schema": "bountyguard/agent-demo/v1", **result,
            "bounty_id": bounty["id"], "repo_id": bounty["repo_id"],
            "issue_url": bounty["issue_url"], "issue_hash": bounty["issue_hash"],
            "pr_url": bounty["pr_url"], "assigned_terms_hash": bounty["assigned_terms_hash"],
            "amount_yocto": bounty["amount_yocto"], "actor_id": bounty["claim"]["actor_id"],
            "claimant": bounty["claim"]["near_account_id"], "maintainer": bounty["maintainer_account"],
            "maintainer_id": bounty["creator_id"], "workflow_id": bounty["ci"]["workflow_id"],
            "run_attempt": bounty["review"]["ci"]["run_attempt"],
            "events": self.state["events"],
        }
        date = time.strftime("%Y-%m-%d", time.gmtime())
        path = self.journal.path.with_name(f"agent-demo-{date}-{bounty['id'][:8]}.json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        print("Review before publishing: " + str(path))
        return result


def validate_bounty(bounty, identifier, repo, max_yocto):
    if (bounty["id"] != identifier or bounty["network"] != "testnet" or bounty["repo"].lower() != repo.lower()
            or not 0 < int(bounty["amount_yocto"]) <= max_yocto):
        raise DemoError("Bounty does not match the selected repository, testnet or reward limit.")


async def main(args):
    identifier = checked_id(args.bounty_id)
    if not args.execute:
        bounty = await call_tool("get_bounty", {"bounty_id": identifier})
        validate_bounty(bounty, identifier, args.repo, args.max_yocto)
        plan = {key: bounty[key] for key in ("id", "state", "issue", "amount", "deadline", "source_paths")}
        plan["mode"] = "read-only"
        plan["steps"] = ["bind and claim", "wait for assignment and funding", "test a candidate in Docker",
                         "open a fork PR", "wait for trusted CI and review", "read the testnet receipt"]
        print(json.dumps(plan, indent=2))
        return
    if (not args.login or not args.account or not args.image or not args.allow_file
            or len(set(args.allow_file)) != len(args.allow_file) or len(args.allow_file) > 4
            or not all(editable(name) for name in args.allow_file)):
        raise DemoError("Execution requires the machine login, testnet account, image and one to four approved Python paths.")
    account = testnet_account(args.account)
    token = os.environ.get("BOUNTYGUARD_AGENT_GITHUB_TOKEN")
    coding_key = os.environ.get("BOUNTYGUARD_CODING_API_KEY")
    if not token or token in (os.getenv("GITHUB_TOKEN"), os.getenv("BOUNTYGUARD_MAINTAINER_GITHUB_TOKEN")):
        raise DemoError("Configure only the machine account's explicit GitHub credential in the Agent environment.")
    if any(os.environ.get(key) for key in ("GITHUB_TOKEN", "GH_TOKEN", "NEAR_AI_API_KEY",
                                          "BOUNTYGUARD_MAINTAINER_GITHUB_TOKEN", "BOUNTYGUARD_VAULT")):
        raise DemoError("Use a separate Agent shell without maintainer or reviewer credentials.")
    github = GitHub(token)
    actor = github.me()
    if actor["login"].lower() != args.login.lower():
        raise DemoError("GitHub token does not belong to the configured machine login.")
    async def mcp(name, **kwargs):
        return await call_tool(name, kwargs, token=token if name != "get_bounty" else None,
                               allow_writes=name != "get_bounty", allow_model=name == "review_pull_request")

    bounty = await mcp("get_bounty", bounty_id=identifier)
    validate_bounty(bounty, identifier, args.repo, args.max_yocto)
    config = {"bounty_id": identifier, "terms_hash": bounty["terms_hash"], "actor_id": actor["id"],
              "login": actor["login"], "account": account, "repo": bounty["repo"], "files": sorted(args.allow_file),
              "requests": args.requests, "model": args.model, "max_tokens": args.max_tokens, "image": args.image}
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = DATA / (identifier + ".lock")
    try:
        lock.mkdir()
    except FileExistsError:
        raise DemoError("This bounty is already running or has a stale lock. See the recovery instructions.") from None
    api = LocalAPI()
    try:
        journal = Journal(DATA / (identifier + ".json"), config)
        repo = Repository(github, bounty, actor["login"])
        # This closure is the only step that opens the key file.
        def bind_wallet(current):
            if api.login(token)["id"] != actor["id"]:
                raise DemoError("GitHub and local API actor IDs differ.")
            bind(api, current, actor["id"], account, args.key_file)

        model = CodingModel(coding_key, args.model, args.max_tokens)
        tests = DockerTests(args.image) if not journal.data.get("head") else None
        await Demo(config, journal, mcp, repo, bind_wallet, model, tests, seconds=args.timeout,
                   secrets=(token, coding_key, os.getenv("BOUNTYGUARD_AGENT_SEED"))).run()
    finally:
        api.close()
        lock.rmdir()


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bounty_id")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read and print terms only (the default)")
    mode.add_argument("--execute", action="store_true", help="Permit claim, model calls and fork PR for this bounty")
    parser.add_argument("--repo", default="ppinkman/bountyguard")
    parser.add_argument("--max-yocto", type=int, default=5 * 10**21)
    parser.add_argument("--login")
    parser.add_argument("--account")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--image")
    parser.add_argument("--allow-file", action="append")
    parser.add_argument("--model", default="Qwen/Qwen3.6-35B-A3B-FP8")
    parser.add_argument("--requests", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if not 256 <= args.max_tokens <= 6000 or not 1 <= args.timeout <= 7200:
        parser.error("Use 256-6000 output tokens and a 1-7200 second polling deadline.")
    try:
        asyncio.run(main(args))
    except (DemoError, IsolationError) as exc:
        parser.exit(1, str(exc) + "\n")
    except (GuardError, OSError, ValueError, KeyError, TypeError, RuntimeError, ExceptionGroup):
        parser.exit(1, "Agent stopped on an upstream or local state error. Check the checkpoint before resuming.\n")


if __name__ == "__main__":
    cli()
