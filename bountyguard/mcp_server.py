"""MCP tools use the same local API and verified GitHub actor as the web UI."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ToolError("Backend redirects are refused.")


class Backend:
    def __init__(self, base="http://127.0.0.1:8766"):
        parsed = urlsplit(base)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("MCP backend must be an ordinary loopback HTTP origin.")
        self.base = base.rstrip("/"); self.session = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, path, body=None, _retry_auth=True):
        if not path.startswith("/api/") or ".." in path or "?" in path:
            raise ToolError("Invalid API path.")
        headers = {"Content-Type": "application/json"}
        if body is not None and path != "/api/session":
            if os.getenv("BOUNTYGUARD_MCP_ALLOW_WRITES") != "1":
                raise ToolError("MCP writes are disabled. Explicit operator permission is required.")
            if not self.session:
                token = os.getenv("GITHUB_TOKEN")
                if not token:
                    raise ToolError("Configure the claimant's GitHub token in the MCP process environment.")
                self.session = self.call("/api/session", {"token": token})["session"]
            headers["Authorization"] = "Bearer " + self.session
        try:
            request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
            with self.opener.open(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc).get("detail", "Request refused.")
            except ValueError:
                detail = "Request refused."
            finally:
                exc.close()
            if exc.code == 401 and "Authorization" in headers:
                # This API checks authentication before any bounty mutation.
                # Only an explicit unauthenticated response permits one replay;
                # unknown transport outcomes and other failures are not retried.
                self.session = None
                if _retry_auth:
                    return self.call(path, body, _retry_auth=False)
            raise ToolError("BountyGuard: " + str(detail)) from None


def create_server(backend=None):
    backend = backend or Backend()
    server = MCPServer("BountyGuard", instructions="Read exact assigned bounty terms and revision evidence. Complete verified identity binding before claiming. Funding and settlement are not exposed by this adapter.")

    def identifier(value):
        if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            raise ToolError("Use an exact bounty ID.")
        return value

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def list_bounties() -> list[dict[str, Any]]:
        """List stored bounties and current acceptance states. Read-only."""
        return backend.call("/api/bounties")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def get_bounty(bounty_id: str) -> dict[str, Any]:
        """Read the exact terms, assigned recipient, revision and review evidence."""
        return backend.call("/api/bounties/" + identifier(bounty_id))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def request_claim(bounty_id: str) -> dict[str, Any]:
        """Request assignment after completing GitHub + NEP-413 binding in the UI. Does not fund."""
        return backend.call("/api/bounties/" + identifier(bounty_id) + "/claim", {})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def submit_pull_request(bounty_id: str, pr_url: str) -> dict[str, Any]:
        """Submit an existing GitHub PR as the assigned, authenticated author. Does not create a PR."""
        return backend.call("/api/bounties/" + identifier(bounty_id) + "/pr", {"pr_url": pr_url})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    def review_pull_request(bounty_id: str, use_model: bool = False) -> dict[str, Any]:
        """Verify the current revision. Model use needs an explicit process-level credit permission. Never pays."""
        if use_model and os.getenv("BOUNTYGUARD_MCP_ALLOW_MODEL") != "1":
            raise ToolError("MCP model credit spending is disabled.")
        return backend.call("/api/bounties/" + identifier(bounty_id) + "/review", {"allow_model": use_model})

    # Funding/payment are intentionally not MCP tools in this first release.
    # Existing maintainer authorization remains necessary in the web/API flow.
    return server


if __name__ == "__main__":
    create_server().run()
