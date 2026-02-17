# Este archivo permite ejecutar el servidor MCP como módulo Python usando: python -m mcp_cicd

"""
Entry point for running MCP CI/CD Agent as a Python module.

Usage:
    python -m mcp_cicd
"""

from .server import main

if __name__ == "__main__":
    main()
