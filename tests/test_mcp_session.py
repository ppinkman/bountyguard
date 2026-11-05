import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from mcp.server.mcpserver.exceptions import ToolError
from bountyguard.mcp_server import Backend


class ScriptedAPI:
    def __init__(self, steps):
        self.steps, self.calls = list(steps), []

    def open(self, request, timeout):
        self.calls.append({"url": request.full_url, "body": request.data, "authorization": request.get_header("Authorization")})
        if not self.steps:
            raise AssertionError("Unexpected extra HTTP request.")
        step = self.steps.pop(0)
        if isinstance(step, int):
            raise urllib.error.HTTPError(request.full_url, step, "scripted API refusal", {}, io.BytesIO(b'{"detail":"request refused"}'))
        if isinstance(step, Exception):
            raise step
        return io.BytesIO(json.dumps(step).encode())


class MCPSessionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"GITHUB_TOKEN": "unit-actor-token", "BOUNTYGUARD_MCP_ALLOW_WRITES": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.backend = Backend()
        self.backend.session = "old-unit-session"
        self.path = "/api/bounties/" + "a" * 32 + "/claim"

    def test_expired_session_refreshes_once_and_repeats_the_same_request(self):
        api = ScriptedAPI([401, {"session": "fresh-unit-session"}, {"id": "original-claim"}])
        self.backend.opener = api
        self.assertEqual(self.backend.call(self.path, {}), {"id": "original-claim"})
        self.assertEqual([call["url"] for call in api.calls], [self.backend.base+self.path, self.backend.base+"/api/session", self.backend.base+self.path])
        self.assertEqual(api.calls[0]["body"], api.calls[2]["body"])
        self.assertEqual(api.calls[0]["authorization"], "Bearer old-unit-session")
        self.assertIsNone(api.calls[1]["authorization"])
        self.assertEqual(api.calls[2]["authorization"], "Bearer fresh-unit-session")

    def test_a_second_401_stops_and_discards_the_failed_session(self):
        api = ScriptedAPI([401, {"session": "fresh-unit-session"}, 401])
        self.backend.opener = api
        with self.assertRaises(ToolError): self.backend.call(self.path, {})
        self.assertEqual(len(api.calls), 3)
        self.assertIsNone(self.backend.session)

    def test_failed_refresh_does_not_loop_or_repeat_the_mutation(self):
        api = ScriptedAPI([401, 401])
        self.backend.opener = api
        with self.assertRaises(ToolError): self.backend.call(self.path, {})
        self.assertEqual(len(api.calls), 2)
        self.assertIsNone(self.backend.session)

    def test_other_http_failures_are_not_retried(self):
        for status in (403, 409, 429, 502):
            with self.subTest(status=status):
                api = ScriptedAPI([status]); self.backend.opener = api
                with self.assertRaises(ToolError): self.backend.call(self.path, {})
                self.assertEqual(len(api.calls), 1)

    def test_unknown_transport_outcome_is_not_retried(self):
        api = ScriptedAPI([urllib.error.URLError("unit transport failure")])
        self.backend.opener = api
        with self.assertRaises(urllib.error.URLError): self.backend.call(self.path, {})
        self.assertEqual(len(api.calls), 1)

    def test_invalid_initial_login_is_not_retried(self):
        self.backend.session = None
        api = ScriptedAPI([401]); self.backend.opener = api
        with self.assertRaises(ToolError): self.backend.call(self.path, {})
        self.assertEqual(len(api.calls), 1)

    def test_disabled_writes_cannot_start_a_refresh(self):
        api = ScriptedAPI([]); self.backend.opener = api
        with patch.dict(os.environ, {"BOUNTYGUARD_MCP_ALLOW_WRITES": "0"}):
            with self.assertRaises(ToolError): self.backend.call(self.path, {})
        self.assertEqual(api.calls, [])


if __name__ == "__main__": unittest.main()
