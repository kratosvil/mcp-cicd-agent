"""
MCP Protocol tests — verifies the server starts correctly and exposes all 8 tools.

Uses the official MCP Python client SDK (stdio_client + ClientSession) to connect
to the server as a subprocess and issue real MCP protocol calls.

Run with:
    pytest tests/test_mcp_server.py -v -s
"""
import sys
from pathlib import Path

import pytest

EXPECTED_TOOLS = {
    "prepare_repo",
    "detect_project_type",
    "build_image",
    "deploy_container",
    "healthcheck",
    "get_logs",
    "stop_deployment",
    "rollback",
}

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.mark.asyncio
async def test_mcp_server_starts_and_registers_all_tools():
    """
    Start the MCP server as a subprocess via stdio transport and verify:
    1. Server initializes without error.
    2. All 8 tools are registered and listed.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_cicd"],
        env=None,  # inherit parent environment (includes venv and .env location)
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # ── Initialize ─────────────────────────────────────────────────
            init_result = await session.initialize()
            assert init_result is not None, "Server did not return initialize result"

            # ── List tools ─────────────────────────────────────────────────
            tools_result = await session.list_tools()
            assert tools_result is not None
            assert len(tools_result.tools) > 0

            registered_names = {tool.name for tool in tools_result.tools}

            # ── Assert all 8 tools present ─────────────────────────────────
            missing = EXPECTED_TOOLS - registered_names
            assert not missing, (
                f"Missing tools in MCP server: {missing}\n"
                f"Registered tools: {registered_names}"
            )

            assert len(registered_names) == 8, (
                f"Expected exactly 8 tools, got {len(registered_names)}: {registered_names}"
            )


@pytest.mark.asyncio
async def test_mcp_tools_have_descriptions():
    """Verify each tool has a non-empty description."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_cicd"],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()

            for tool in tools_result.tools:
                assert tool.description, (
                    f"Tool '{tool.name}' has no description"
                )
                assert len(tool.description) > 10, (
                    f"Tool '{tool.name}' description too short: '{tool.description}'"
                )


@pytest.mark.asyncio
async def test_mcp_tools_have_input_schemas():
    """Verify each tool exposes an inputSchema."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_cicd"],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()

            for tool in tools_result.tools:
                assert tool.inputSchema is not None, (
                    f"Tool '{tool.name}' has no inputSchema"
                )


@pytest.mark.asyncio
async def test_mcp_detect_project_type_via_protocol(fixture_app_path):
    """
    Call detect_project_type through the MCP protocol and verify
    it returns project_type='docker' for the fixture app.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_cicd"],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "detect_project_type",
                arguments={"repo_path": str(fixture_app_path)},
            )

            assert result is not None
            assert not result.isError, f"Tool returned error: {result.content}"

            # Parse the text content (JSON response)
            import json
            content_text = result.content[0].text
            data = json.loads(content_text)

            assert data["project_type"] == "docker"
            assert data["dockerfile_path"] == "Dockerfile"
            assert 8000 in data["exposed_ports"]
