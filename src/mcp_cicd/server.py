# Este es el servidor principal MCP que inicializa la configuración, logging,
# registra las 8 herramientas y ejecuta el servidor FastMCP.

"""
MCP CI/CD Agent Server.

Main entry point for the MCP server that orchestrates deployment automation.
Registers all 8 tools and handles server lifecycle.
"""
from mcp.server.fastmcp import FastMCP  # Framework FastMCP para crear servidor MCP

from .config.settings import get_settings  # Singleton de configuración
from .utils.logging import setup_logging, get_logger  # Sistema de logging estructurado

# Import tool registration functions
from .tools.repo_tools import register_repo_tools  # Herramientas de repositorio (prepare_repo, detect_project_type)
from .tools.docker_tools import register_docker_tools  # Herramientas Docker (build_image, deploy_container, get_logs)
from .tools.lifecycle_tools import register_lifecycle_tools  # Herramientas de lifecycle (stop_deployment, rollback)
from .tools.health_tools import register_health_tools  # Herramienta de health (healthcheck)

# Initialize settings
settings = get_settings()

# Ensure required directories exist
settings.ensure_directories()

# Setup structured logging
setup_logging(
    level=settings.log_level,
    json_logs=settings.log_json,
    log_dir=settings.log_dir
)

logger = get_logger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name=settings.server_name,
    json_response=True  # Return JSON responses for better parsing
)

logger.info(
    "mcp_server_initializing",
    server_name=settings.server_name,
    transport=settings.transport,
    log_level=settings.log_level
)

# Register all MCP tools
logger.info("registering_mcp_tools")

register_repo_tools(mcp)
logger.info("repo_tools_registered", tools=["prepare_repo", "detect_project_type"])

register_docker_tools(mcp)
logger.info("docker_tools_registered", tools=["build_image", "deploy_container", "get_logs"])

register_lifecycle_tools(mcp)
logger.info("lifecycle_tools_registered", tools=["stop_deployment", "rollback"])

register_health_tools(mcp)
logger.info("health_tools_registered", tools=["healthcheck"])

logger.info(
    "mcp_server_ready",
    total_tools=8,
    tools=[
        "prepare_repo",
        "detect_project_type",
        "build_image",
        "deploy_container",
        "healthcheck",
        "get_logs",
        "stop_deployment",
        "rollback"
    ]
)


def main():
    """
    Main entry point for running the MCP server.

    Can be invoked via:
    - python -m mcp_cicd.server
    - Direct execution if __name__ == "__main__"
    """
    logger.info("starting_mcp_server", transport=settings.transport)

    try:
        # Run the MCP server with configured transport
        mcp.run(transport=settings.transport)
    except KeyboardInterrupt:
        logger.info("mcp_server_shutdown", reason="keyboard_interrupt")
    except Exception as e:
        logger.error("mcp_server_error", error=str(e))
        raise


if __name__ == "__main__":
    main()
