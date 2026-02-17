# Este archivo marca el paquete mcp_cicd y expone la versión del proyecto.

"""
MCP CI/CD Agent - Production-grade deployment automation via Model Context Protocol.

Exposes 8 MCP tools for complete Docker deployment workflows.
"""

__version__ = "0.1.0"
__author__ = "Kratosvil"
__description__ = "MCP server for automated Docker CI/CD deployments"

# Expose main components for easier imports
from .server import mcp, main

__all__ = ["mcp", "main", "__version__"]
