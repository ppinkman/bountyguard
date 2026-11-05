"""Call BountyGuard through real MCP stdio; never loads a wallet or model key."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def run(args):
    names = {"get": "get_bounty", "claim": "request_claim", "submit": "submit_pull_request", "review": "review_pull_request", "receipt": "get_bounty"}
    arguments = {"bounty_id": args.bounty_id}
    if args.command == "submit":
        if not args.pr_url:
            raise SystemExit("submit requires --pr-url for an existing PR.")
        arguments["pr_url"] = args.pr_url
    if args.command == "review":
        arguments["use_model"] = args.use_model
    if args.command in {"claim", "submit", "review"} and not args.allow_writes:
        raise SystemExit("This action requires --allow-writes and GITHUB_TOKEN in the process environment.")
    if args.use_model and not args.allow_model:
        raise SystemExit("Model use requires --allow-model as well as --use-model.")
    # Only the GitHub actor's credential is needed by this MCP child. In
    # particular, it receives no model provider or development signing key.
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PYTHONUTF8", "GITHUB_TOKEN"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["BOUNTYGUARD_MCP_ALLOW_WRITES"] = "1" if args.allow_writes else "0"
    env["BOUNTYGUARD_MCP_ALLOW_MODEL"] = "1" if args.allow_model else "0"
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "bountyguard.mcp_server"], cwd=str(ROOT), env=env)
    async with Client(parameters) as client:
        result = await client.call_tool(names[args.command], arguments)
    if result.is_error:
        raise SystemExit("MCP refused the action: " + str(result.content))
    body = result.structured_content
    if body is None:
        body = json.loads(next(block.text for block in result.content if block.type == "text"))
    record = {"transport": "MCP stdio", "tool": names[args.command], "arguments": arguments, "at": int(time.time()), "result": body}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.command == "receipt" and body.get("state") != "PAID":
        raise SystemExit("No paid receipt yet. Current state: " + body.get("state", "unknown"))
    print(json.dumps({"tool": names[args.command], "bounty_id": body.get("bounty_id", body.get("id")), "state": body.get("state"), "claim_id": body.get("id") if args.command == "claim" else None, "payment_receipt": body.get("payment_receipt"), "output": str(args.output) if args.output else None}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["get", "claim", "submit", "review", "receipt"])
    parser.add_argument("bounty_id")
    parser.add_argument("--pr-url")
    parser.add_argument("--allow-writes", action="store_true")
    parser.add_argument("--use-model", action="store_true")
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--output", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__": main()
