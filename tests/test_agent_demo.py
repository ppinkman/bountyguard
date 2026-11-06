import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tools.agent_demo import Demo, DemoError, Journal, main, payment
from tools.agent_workspace import Repository
from tools.maintainer_settle import settle

BOUNTY = "a" * 32
HEAD = "b" * 40
PR = "https://github.com/ppinkman/bountyguard/pull/100"
REWARD = str(5 * 10**21)
CLAIM = {"id": "claim", "actor_id": 42, "near_account_id": "agent.testnet"}
CONFIG = {"bounty_id": BOUNTY, "terms_hash": "terms", "actor_id": 42,
          "account": "agent.testnet", "files": ["tools/agent_client.py"], "requests": 2}


class DemoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.path = Path(root.name) / "run.json"
        self.journal = Journal(self.path, CONFIG)
        capture = redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        self.bounty = {
            "id": BOUNTY, "terms_hash": "terms", "network": "testnet", "repo": "ppinkman/bountyguard",
            "repo_id": 9, "issue_url": "https://github.com/ppinkman/bountyguard/issues/99", "issue_hash": "issue",
            "creator_id": 7, "maintainer_account": "maintainer.testnet", "deadline": int(time.time()) + 100,
            "state": "DRAFT", "claims": [], "issue": {"body": "Fix me."},
            "source_paths": ["tools/"], "amount": "0.005", "amount_yocto": REWARD,
            "ci": {"workflow_id": 321}, "assigned_terms_hash": "assigned",
        }
        self.calls = []
        self.remote_head = None
        self.pr = None
        self.repo = Mock()
        self.repo.base = "main"
        self.repo.base_commit.return_value = {"sha": "c" * 40, "branch": "main", "tree": "d" * 40}
        self.repo.commit.return_value = HEAD
        self.repo.branch_head.side_effect = lambda: self.remote_head
        self.repo.create_branch.side_effect = self.branch
        self.repo.pr.side_effect = lambda head: self.pr
        self.repo.create_pr.side_effect = self.open_pr
        self.repo.ci.return_value = {"passed": True, "run_id": 123}
        self.wallet = Mock()
        self.model = Mock()
        self.model.propose.return_value = ({"tools/agent_client.py": "def value():\n    return 2\n"}, {"model": "fixture"})
        self.tests = Mock()
        self.tests.test.return_value = True

    def fund(self):
        self.bounty.update(state="FUNDED", claim=CLAIM, funding_receipt={"fixture": True})

    def paid(self):
        self.bounty.update(state="PAID", merge_evidence={"merge_commit_sha": "e" * 40},
                           payment_receipt={"transaction_hash": "A" * 44, "contract": "escrow.testnet",
                                            "network": "testnet", "final_execution_status": "FINAL",
                                            "status": {"SuccessValue": "dHJ1ZQ=="}})

    def branch(self, head):
        self.remote_head = head

    def open_pr(self):
        self.pr = {"html_url": PR}

    async def mcp(self, name, **args):
        self.calls.append((name, args))
        if name == "request_claim":
            self.bounty["claims"] = [CLAIM]
            self.fund()
            return CLAIM
        if name == "submit_pull_request":
            self.bounty.update(state="PR_SUBMITTED", pr_url=args["pr_url"])
        if name == "review_pull_request":
            self.bounty.update(state="READY_TO_MERGE", review={"head_sha": HEAD, "verdict": "PASS",
                               "ci": {"passed": True, "run_id": 123, "run_attempt": 1},
                               "report_hash": "report", "delivery_hash": "delivery"})
            self.paid()
        return deepcopy(self.bounty)

    def checkout(self, repo, sha, workspace):
        (workspace / "tools").mkdir()
        (workspace / "tools/agent_client.py").write_text("def value():\n    return 1\n", encoding="utf-8")

    def demo(self, seconds=5, mcp=None):
        return Demo(CONFIG, self.journal, mcp or self.mcp, self.repo, self.wallet, self.model,
                    self.tests, self.checkout, seconds=seconds, poll=0.001, secrets=("fixture-token-1234",))

    async def test_completed_flow_and_repeat_read_receipt_without_new_writes(self):
        result = await self.demo().run()
        self.assertEqual(result["head_sha"], HEAD)
        self.assertEqual([name for name, _ in self.calls if name != "get_bounty"],
                         ["request_claim", "submit_pull_request", "review_pull_request"])
        self.journal = Journal(self.path, CONFIG)
        self.assertEqual(await self.demo().run(), result)
        self.repo.create_pr.assert_called_once()
        self.model.propose.assert_called_once()
        evidence = json.loads(next(self.path.parent.glob("agent-demo-*.json")).read_text())
        self.assertEqual(evidence["pr_url"], PR)
        self.assertNotIn("return 2", json.dumps(evidence))
        self.assertNotIn("fixture-token-1234", self.path.read_text())

    async def test_ambiguous_claim_is_reconciled(self):
        async def lost_claim(name, **args):
            result = await self.mcp(name, **args)
            if name == "request_claim":
                raise TimeoutError()
            return result

        with self.assertRaisesRegex(DemoError, "MCP call failed"):
            await self.demo(mcp=lost_claim).run()
        self.journal = Journal(self.path, CONFIG)
        await self.demo().run()
        self.wallet.assert_called_once()
        self.assertEqual(sum(name == "request_claim" for name, _ in self.calls), 1)

    async def test_ambiguous_pr_is_reconciled(self):
        def lost_response():
            self.open_pr()
            raise TimeoutError()

        self.repo.create_pr.side_effect = lost_response
        with self.assertRaises(TimeoutError):
            await self.demo().run()
        self.journal = Journal(self.path, CONFIG)
        await self.demo().run()
        self.repo.create_pr.assert_called_once()
        self.model.propose.assert_called_once()

    async def test_uncertain_model_is_not_replayed(self):
        self.model.propose.side_effect = DemoError("model timeout")
        with self.assertRaisesRegex(DemoError, "model timeout"):
            await self.demo().run()
        self.journal = Journal(self.path, CONFIG)
        with self.assertRaisesRegex(DemoError, "uncertain"):
            await self.demo().run()
        self.model.propose.assert_called_once()
        self.repo.create_branch.assert_not_called()

    async def test_local_failures_are_bounded_and_never_publish(self):
        self.tests.test.return_value = False
        with self.assertRaisesRegex(DemoError, "request limit"):
            await self.demo().run()
        self.assertEqual(self.model.propose.call_count, 2)
        self.repo.commit.assert_not_called()
        self.repo.create_pr.assert_not_called()

    async def test_test_environment_required_before_claim(self):
        self.tests.check.side_effect = DemoError("Docker unavailable")
        with self.assertRaisesRegex(DemoError, "Docker unavailable"):
            await self.demo().run()
        self.wallet.assert_not_called()
        self.assertEqual([name for name, _ in self.calls], ["get_bounty"])

    async def test_green_ci_with_no_pr_link_stops_before_model_review(self):
        self.repo.ci.return_value = {"passed": False, "association_missing": True, "run_id": 123}
        with self.assertRaisesRegex(DemoError, "without the required PR/base link"):
            await self.demo().run()
        self.assertFalse(any(name == "review_pull_request" for name, _ in self.calls))
        self.assertIn("ci_association_missing", self.path.read_text())

    async def test_wait_for_assignment_has_deadline_and_resumes(self):
        async def waiting(name, **args):
            if name == "request_claim":
                self.bounty["claims"] = [CLAIM]
                return CLAIM
            return await self.mcp(name, **args)

        with self.assertRaisesRegex(DemoError, "timed out"):
            await self.demo(seconds=0.05, mcp=waiting).run()
        self.model.propose.assert_not_called()
        self.journal = Journal(self.path, CONFIG)
        self.fund()
        await self.demo().run()
        self.wallet.assert_called_once()

    async def test_dry_run_only_reads_without_creating_a_checkpoint(self):
        args = Mock(execute=False, bounty_id=BOUNTY, repo=self.bounty["repo"], max_yocto=int(REWARD))
        with patch("tools.agent_demo.call_tool", AsyncMock(return_value=self.bounty)) as tool:
            await main(args)
        tool.assert_awaited_once_with("get_bounty", {"bounty_id": BOUNTY})
        self.assertFalse(self.path.exists())

    async def test_payment_for_other_revision_is_refused(self):
        self.fund()
        await self.mcp("review_pull_request")
        with self.assertRaisesRegex(DemoError, "No final"):
            payment(self.bounty, "c" * 40)

    async def test_maintainer_confirmation_is_required(self):
        await self.demo().run()
        self.bounty.update(state="READY_TO_MERGE", pr_number=100)
        api = Mock()
        api.login.return_value = {"id": 7}
        api.call.return_value = self.bounty
        github = Mock()
        github.request.return_value = {"merged": True, "head": {"sha": HEAD}}
        with self.assertRaisesRegex(DemoError, "not requested"):
            settle(api, github, BOUNTY, HEAD, "maintainer-token", confirm=lambda _: "no")
        api.call.assert_called_once_with("bounties/" + BOUNTY)


class GitHubFixtureTests(unittest.TestCase):
    def test_create_ref_only_in_verified_agent_fork(self):
        github = Mock()
        github.me.return_value = {"id": 42}
        github.repo.side_effect = [
            {"id": 9, "default_branch": "main", "private": False},
            {"id": 10, "parent": {"id": 9}, "owner": {"id": 42}, "fork": True,
             "permissions": {"push": True}, "private": False},
        ]
        repo = Repository(github, {"repo": "ppinkman/bountyguard", "repo_id": 9, "id": BOUNTY}, "machine")
        repo.preflight(open_issue=False)
        repo.create_branch(HEAD)
        github.request.assert_called_once_with("/repos/machine/bountyguard/git/refs",
                                                {"ref": "refs/heads/bountyguard-" + BOUNTY, "sha": HEAD})
