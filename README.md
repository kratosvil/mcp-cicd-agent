# MCP CI/CD Agent

**Production-grade Model Context Protocol server for automated Docker deployments**

## Overview

This MCP server automates the complete CI/CD pipeline for containerized applications:
- Clone Git repositories
- Detect project type (Dockerfile, docker-compose)
- Build Docker images with log capture
- Deploy containers with port management
- Health check validation
- Deployment state tracking
- Rollback capabilities

## Architecture

Built using:
- **FastMCP** framework for tool registration
- **Docker SDK** for container orchestration
- **GitPython** for repository automation
- **Structured logging** with JSON output
- **Atomic state management** via JSON files

## Project Structure
```
mcp-cicd-agent/
├── src/mcp_cicd/          # Main application code
│   ├── tools/             # MCP tool implementations
│   ├── models/            # Pydantic data models
│   ├── utils/             # Docker, Git, state helpers
│   └── config/            # Configuration management
├── tests/                 # Unit and integration tests
├── workspace/             # Git clone target (gitignored)
├── deployments/           # Deployment state files (gitignored)
└── logs/                  # Application logs (gitignored)
```

## MCP Tools

The server exposes 8 tools for complete deployment automation:

1. **prepare_repo** - Clone/update Git repository
2. **detect_project_type** - Identify Dockerfile vs docker-compose
3. **build_image** - Build Docker image with log streaming
4. **deploy_container** - Deploy with port conflict resolution
5. **healthcheck** - Validate service availability
6. **get_logs** - Retrieve container logs
7. **stop_deployment** - Stop and remove container
8. **rollback** - Restore previous successful deployment

## Design Principles

- **Local-first**: All operations run on local Docker daemon
- **Deterministic**: Sequential pipeline execution, no hidden state
- **Observable**: Structured logs, JSON state files, atomic writes
- **Secure**: Localhost-only binding, non-root containers, resource limits
- **Reproducible**: Version-pinned dependencies, isolated workspaces

## Status

🚧 **Under Development** - Following senior DevOps practices for production readiness

## Author

Built by Kratosvil - DevOps Engineer specializing in AWS, Terraform, Kubernetes, and AI integration
