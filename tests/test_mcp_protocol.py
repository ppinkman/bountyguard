import asyncio
import os
from pathlib import Path
import sys
import unittest

from mcp import Client,StdioServerParameters
from bountyguard.mcp_server import Backend


class MCPTests(unittest.TestCase):
    def test_backend_rejects_non_loopback_destinations(self):
        for base in ['https://evil.test','http://127.0.0.1.evil.test','http://localhost/path','http://user:password@localhost']:
            with self.assertRaises(ValueError):Backend(base)

    def test_stdio_lists_tools_and_refuses_unapproved_mutation(self):
        async def scenario():
            env=os.environ.copy();env.pop('GITHUB_TOKEN',None);env.pop('NEAR_AI_API_KEY',None)
            env['BOUNTYGUARD_MCP_ALLOW_WRITES']='0';env['BOUNTYGUARD_MCP_ALLOW_MODEL']='0'
            params=StdioServerParameters(command=sys.executable,args=['-m','bountyguard.mcp_server'],cwd=str(Path(__file__).resolve().parents[1]),env=env)
            async with Client(params) as client:
                tools=await client.list_tools();self.assertEqual(len(tools.tools),5)
                names={t.name for t in tools.tools};self.assertNotIn('fund',names);self.assertNotIn('pay',names)
                rejected=await client.call_tool('request_claim',{'bounty_id':'0'*32});self.assertTrue(rejected.is_error)
        asyncio.run(scenario())


if __name__=='__main__':unittest.main()
