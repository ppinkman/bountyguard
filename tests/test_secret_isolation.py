import base64
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile, ZipInfo

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from bountyguard.identity import b58decode, nep413_digest
from bountyguard.near import make_key
from bountyguard.sandbox import DockerTests, IsolationError, scan_edits
from tools.agent_client import call_tool
from tools.agent_wallet import DemoError, signature
from tools.agent_workspace import unpack


FAKE_SECRET = "canary-should-never-be-copied"
IMAGE = "sha256:" + "a" * 64


class IsolationTests(unittest.TestCase):
    def test_container_has_only_checkout_mount_and_no_host_credentials(self):
        with patch("shutil.which", return_value="/trusted/docker"), patch.dict(os.environ, {
            "GITHUB_TOKEN": FAKE_SECRET, "BOUNTYGUARD_CODING_API_KEY": FAKE_SECRET,
            "BOUNTYGUARD_AGENT_SEED": FAKE_SECRET, "HTTPS_PROXY": FAKE_SECRET,
        }):
            tests = DockerTests(IMAGE)
        argv = tests.command("unit-test", tests.TEST, Path.cwd() / "snapshot")
        self.assertEqual(argv.count("--mount"), 1)
        for flag in ("--read-only", "--network=none", "--pull=never", "--cap-drop=ALL", "--user=65534:65534"):
            self.assertIn(flag, argv)
        self.assertTrue(argv[argv.index("--mount") + 1].endswith("target=/work,readonly"))
        self.assertNotIn(FAKE_SECRET, repr((argv, tests.env)))
        self.assertNotIn("docker.sock", repr(argv))

    def test_patch_rejects_token_private_key_or_protected_path(self):
        path = "tools/agent_client.py"
        original = {path: "answer = 1\n"}
        for target, content in [
            (path, 'token = "' + FAKE_SECRET + '"\n'),
            (path, 'token = "ed25519:' + "D" * 88 + '"\n'),
            (path, 'token = "github_pat_abcdef"\n'),
            (".github/workflows/ci.yml", "job: malicious\n"),
            ("tools/../tests/test_foo.py", "assert False\n"),
        ]:
            with self.subTest(target=target), self.assertRaises(IsolationError):
                scan_edits({**original, target: "old"}, {target: content}, (FAKE_SECRET,))
        self.assertEqual(scan_edits(original, {path: "answer = 2\n"}, (FAKE_SECRET,)),
                         {path: "answer = 2\n"})

    def test_checkout_rejects_symlink_and_traversal(self):
        for name, mode in [("root/../key", stat.S_IFREG), ("root/tools/sneaky", stat.S_IFLNK),
                           ("root/tools/NUL.py", stat.S_IFREG), ("root/tools/.GIT/data", stat.S_IFREG)]:
            archive = io.BytesIO()
            entry = ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (mode | 0o644) << 16
            with ZipFile(archive, "w") as target:
                target.writestr(entry, FAKE_SECRET)
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(DemoError):
                    unpack(archive.getvalue(), Path(directory))
                self.assertEqual(list(Path(directory).iterdir()), [])

    @unittest.skipUnless(os.getenv("BOUNTYGUARD_TEST_IMAGE"), "set trusted Docker image ID to run a real isolation probe")
    def test_container_canary_cannot_read_key_or_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            tests_dir = checkout / "tests"
            tests_dir.mkdir(parents=True)
            key_file = root / "agent-seed.json"
            key_file.write_text(FAKE_SECRET, encoding="utf-8")
            probe = (
                "import os, pathlib, unittest\n"
                "class TestProbe(unittest.TestCase):\n"
                "    def test_host_key(self):\n"
                "        self.assertNotIn('BOUNTYGUARD_AGENT_SEED', os.environ)\n"
                "        self.assertFalse(pathlib.Path('/work/agent-seed.json').exists())\n"
                "        self.assertFalse(pathlib.Path('/var/run/docker.sock').exists())\n"
                f"        self.assertFalse(pathlib.Path({key_file.as_posix()!r}).exists())\n"
            )
            (tests_dir / "test_probe.py").write_text(probe, encoding="utf-8")
            with patch.dict(os.environ, {"BOUNTYGUARD_AGENT_SEED": FAKE_SECRET}):
                runner = DockerTests(os.environ["BOUNTYGUARD_TEST_IMAGE"])
                self.assertTrue(runner.test(checkout))

    def test_claimant_signature_covers_bounty_and_testnet_identity(self):
        bounty = {"id": "a" * 32, "repo": "owner/repo", "repo_id": 5, "issue_number": 7, "terms_hash": "terms"}
        key = make_key()
        now = int(time.time())
        context = {"application": "BountyGuard", "version": 1, "network": "testnet",
                   "bounty_id": bounty["id"], "repo": "owner/repo", "repo_id": 5, "issue_number": 7,
                   "github_user_id": 22, "near_account_id": "agent.testnet", "purpose": "claimant",
                   "terms_hash": "terms", "challenge_id": "challenge", "expires_at": now + 299}
        nonce = bytes(32)
        challenge = {"id": "challenge", "message": json.dumps(context), "recipient": "bountyguard.local",
                     "nonce": base64.b64encode(nonce).decode()}
        proof = signature(challenge, bounty, 22, "agent.testnet", key["seed"], now=now)
        public = Ed25519PublicKey.from_public_bytes(b58decode(proof["public_key"].split(":")[1]))
        public.verify(base64.b64decode(proof["signature"]), nep413_digest(challenge["message"], nonce, challenge["recipient"]))
        with self.assertRaises(DemoError):
            signature(challenge, bounty, 23, "agent.testnet", key["seed"], now=now)
        with self.assertRaises(DemoError):
            signature(challenge, bounty, 22, "agent.testnet", key["seed"], now=now + 300)


class MCPIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_child_inherits_only_the_explicit_actor_credential(self):
        result = Mock(is_error=False, structured_content={"state": "DRAFT"})
        client = Mock()
        client.call_tool = unittest.mock.AsyncMock(return_value=result)
        context = unittest.mock.MagicMock()
        context.__aenter__.return_value = client
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": FAKE_SECRET, "BOUNTYGUARD_AGENT_SEED": FAKE_SECRET,
            "NEAR_AI_API_KEY": FAKE_SECRET, "BOUNTYGUARD_CODING_API_KEY": FAKE_SECRET,
            "BOUNTYGUARD_MAINTAINER_GITHUB_TOKEN": FAKE_SECRET,
        }), patch("tools.agent_client.Client", return_value=context) as spawn:
            await call_tool("get_bounty", {"bounty_id": "a" * 32})
            await call_tool("request_claim", {"bounty_id": "a" * 32}, token="actor-token", allow_writes=True)
        read, write = [item.args[0].env for item in spawn.call_args_list]
        self.assertNotIn("GITHUB_TOKEN", read)
        self.assertEqual(write["GITHUB_TOKEN"], "actor-token")
        self.assertNotIn(FAKE_SECRET, repr((read, write)))
