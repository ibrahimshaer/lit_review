import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = sys.executable  # the interpreter running this test
SRV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

async def main():
    params = StdioServerParameters(command=PY, args=[SRV])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as sess:
            init = await sess.initialize()
            print("server:", init.serverInfo.name, init.serverInfo.version)
            tools = await sess.list_tools()
            for t in tools.tools:
                print(" tool:", t.name, "| params:", list(t.inputSchema.get("properties", {}).keys()))
            res = await sess.call_tool("list_categories", {})
            print("list_categories ->", len(res.structuredContent or {}), "keys, isError =", res.isError)
            res = await sess.call_tool("get_paper", {"arxiv_id": "not an id"})
            print("bad id -> isError =", res.isError, "|", res.content[0].text[:80])
asyncio.run(main())
