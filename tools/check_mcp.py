"""Exercise the real stdio protocol; read-only and explicitly denied write only."""
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

ROOT=Path(__file__).resolve().parents[1]


async def main():
    env=os.environ.copy()
    for name in ('GITHUB_TOKEN','NEAR_AI_API_KEY'):
        env.pop(name,None)
    env['BOUNTYGUARD_MCP_ALLOW_WRITES']='0';env['BOUNTYGUARD_MCP_ALLOW_MODEL']='0'
    params=StdioServerParameters(command=sys.executable,args=['-m','bountyguard.mcp_server'],cwd=str(ROOT),env=env)
    async with Client(params) as client:
        tools=await client.list_tools()
        names=sorted(tool.name for tool in tools.tools)
        expected=sorted(['list_bounties','get_bounty','request_claim','submit_pull_request','review_pull_request'])
        if names!=expected:raise RuntimeError('Unexpected MCP tools.')
        read=await client.call_tool('list_bounties',{})
        denied=await client.call_tool('request_claim',{'bounty_id':'0'*32})
        if read.is_error or not denied.is_error:raise RuntimeError('Read/write capability boundary failed.')
        print(json.dumps({'tools':names,'read_succeeded':True,'write_without_operator_permission_refused':True,'funding_tools_exposed':False}))


if __name__=='__main__':asyncio.run(main())
