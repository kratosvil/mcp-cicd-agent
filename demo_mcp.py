"""
Demo en vivo del MCP CI/CD Agent.
Despliega un contenedor Hello World en localhost:8080 via protocolo MCP real.
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).parent
FIXTURE_PATH = str(PROJECT_ROOT / "tests" / "fixtures" / "simple-app")
IMAGE_TAG = "hello-world-mcp:v1"
CONTAINER_NAME = "hello-world-demo"
HOST_PORT = 8080
CONTAINER_PORT = 8000


def banner(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def ok(msg):
    print(f"  [OK] {msg}")


def info(msg):
    print(f"  --> {msg}")


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_cicd"],
        env=None,
    )

    print("\n" + "="*55)
    print("  MCP CI/CD AGENT — Demo Hello World en localhost:8080")
    print("="*55)
    print(f"  Servidor: python -m mcp_cicd (stdio transport)")
    print(f"  Fixture:  {FIXTURE_PATH}")
    print(f"  Target:   http://localhost:{HOST_PORT}")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            # ── Conexión al servidor MCP ──────────────────────────────────
            banner("CONECTANDO AL SERVIDOR MCP")
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            ok(f"Servidor MCP iniciado correctamente")
            ok(f"Herramientas registradas ({len(tool_names)}): {', '.join(tool_names)}")

            # ── PASO 1: detect_project_type ───────────────────────────────
            banner("PASO 1 — detect_project_type")
            info(f"Analizando: {FIXTURE_PATH}")
            result = await session.call_tool(
                "detect_project_type",
                {"repo_path": FIXTURE_PATH},
            )
            if result.isError:
                print(f"  [ERROR] {result.content[0].text}")
                return
            data = json.loads(result.content[0].text)
            ok(f"project_type    = {data['project_type']}")
            ok(f"dockerfile_path = {data['dockerfile_path']}")
            ok(f"exposed_ports   = {data['exposed_ports']}")

            # ── PASO 2: build_image ───────────────────────────────────────
            banner("PASO 2 — build_image")
            info(f"Construyendo imagen: {IMAGE_TAG}")
            result = await session.call_tool(
                "build_image",
                {
                    "path": FIXTURE_PATH,
                    "image_tag": IMAGE_TAG,
                    "dockerfile": "Dockerfile",
                },
            )
            if result.isError:
                print(f"  [ERROR] {result.content[0].text}")
                return
            data = json.loads(result.content[0].text)
            ok(f"image_id   = {data['image_id'][:19]}...")
            ok(f"image_tag  = {data['image_tag']}")
            ok(f"build_time = {data['build_time']}s")
            ok(f"size_mb    = {data['size_mb']} MB")
            info(f"Ultimas lineas del build:")
            for line in data["build_logs"][-5:]:
                print(f"             {line}")

            # ── PASO 3: deploy_container ──────────────────────────────────
            banner("PASO 3 — deploy_container")
            info(f"Desplegando '{CONTAINER_NAME}' en puerto {HOST_PORT}...")
            result = await session.call_tool(
                "deploy_container",
                {
                    "image_tag": IMAGE_TAG,
                    "container_name": CONTAINER_NAME,
                    "host_port": HOST_PORT,
                    "container_port": CONTAINER_PORT,
                },
            )
            if result.isError:
                print(f"  [ERROR] {result.content[0].text}")
                return
            data = json.loads(result.content[0].text)
            ok(f"container_id   = {data['container_id'][:19]}...")
            ok(f"container_name = {data['container_name']}")
            ok(f"host_port      = {data['host_port']}")
            ok(f"url            = {data['url']}")
            ok(f"status         = {data['status']}")
            service_url = data["url"]

            # ── PASO 4: healthcheck ───────────────────────────────────────
            banner("PASO 4 — healthcheck")
            health_url = f"{service_url}/health"
            info(f"Verificando: {health_url}")
            result = await session.call_tool(
                "healthcheck",
                {"url": health_url, "timeout": 30},
            )
            if result.isError:
                print(f"  [ERROR] {result.content[0].text}")
                return
            data = json.loads(result.content[0].text)
            ok(f"healthy         = {data['healthy']}")
            ok(f"response_code   = {data['response_code']}")
            ok(f"attempts        = {data['attempts']}")
            ok(f"elapsed_seconds = {data['elapsed_seconds']}s")

            # ── PASO 5: get_logs ──────────────────────────────────────────
            banner("PASO 5 — get_logs")
            result = await session.call_tool(
                "get_logs",
                {"container_name": CONTAINER_NAME, "tail": 10},
            )
            if result.isError:
                print(f"  [ERROR] {result.content[0].text}")
                return
            data = json.loads(result.content[0].text)
            ok(f"lines_returned = {data['lines_returned']}")
            print(f"\n  --- Logs del contenedor ---")
            for line in data["logs"].strip().splitlines():
                print(f"  {line}")

            # ── RESUMEN FINAL ─────────────────────────────────────────────
            banner("SERVICIO CORRIENDO")
            print(f"\n  Tu app Hello World esta en:")
            print(f"\n    http://localhost:{HOST_PORT}/        -> 'Hello from MCP CI/CD Test App!'")
            print(f"    http://localhost:{HOST_PORT}/health   -> 'OK'")
            print(f"\n  Para probarlo desde terminal:")
            print(f"    curl http://localhost:{HOST_PORT}/")
            print(f"    curl http://localhost:{HOST_PORT}/health")
            print(f"\n  Para detenerlo, ejecuta:")
            print(f"    python demo_stop.py")
            print()


if __name__ == "__main__":
    asyncio.run(main())
