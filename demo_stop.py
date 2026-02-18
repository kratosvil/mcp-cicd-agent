"""Para y elimina el contenedor hello-world-demo via MCP."""
import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_cicd"], env=None
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "stop_deployment", {"container_name": "hello-world-demo"}
            )
            data = json.loads(result.content[0].text)
            print(f"\n  [OK] {data['message']}")
            print(f"  status = {data['status']}\n")


if __name__ == "__main__":
    asyncio.run(main())
