# MCP CI/CD Agent

MCP server that lets LLM agents run complete Docker CI/CD pipelines — from Git clone to live container.

<div align="center">

![MCP](https://img.shields.io/badge/MCP-Server-6366f1)
![Python](https://img.shields.io/badge/Python-3.10+-22c55e)
![Docker](https://img.shields.io/badge/Docker-Required-0ea5e9)
![Tests](https://img.shields.io/badge/Tests-101%20passed-22c55e)
![License](https://img.shields.io/badge/License-MIT-a855f7)

**Give Claude a Git repo URL — it clones, builds, deploys, and validates the container for you**

</div>

---

## What It Does

You point Claude at a repository. Claude runs the full pipeline autonomously through the Model Context Protocol.

```
"Deploy the latest version of my API from github.com/myorg/myapi"
```

```
  User ──► Claude AI ──► MCP Server ──► Docker ──► Running Container
 (prompt)  (orchestrates)  (8 tools)    (build)    (localhost:8080)
```

## Features

- **Full pipeline in one conversation** — clone, detect, build, deploy, validate, rollback
- **8 MCP tools** — each step is an explicit, observable tool call
- **Port conflict resolution** — finds an available port automatically
- **Deployment state tracking** — JSON state files enable rollback to any previous deployment
- **Secure by default** — localhost-only binding, `no-new-privileges`, 512 MB memory cap
- **Structured logging** — JSON logs for every operation, easy to pipe to any log aggregator
- **101 unit tests** — full coverage of validation, Git, Docker, and settings layers

## Quick Start

### Prerequisites

- Python 3.10+
- Docker 20.10+ (daemon running)
- [Claude Desktop](https://claude.ai/download)

### Install

```bash
git clone https://github.com/kratosvil/mcp-cicd-agent.git
cd mcp-cicd-agent
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -e .
```

### Configure Claude Desktop

Add to your Claude Desktop config file:

| OS | Path |
|----|------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "cicd-agent": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "mcp_cicd"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

> **Windows example**
> ```json
> "command": "C:\\Users\\you\\mcp-cicd-agent\\.venv\\Scripts\\python.exe"
> ```

Restart Claude Desktop, then try:

```
"Clone https://github.com/myorg/myapi and deploy it"
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `prepare_repo` | Clone or update a Git repository into an isolated workspace |
| `detect_project_type` | Identify Dockerfile vs docker-compose and exposed port |
| `build_image` | Build a Docker image with full log capture |
| `deploy_container` | Deploy container with automatic port conflict resolution |
| `healthcheck` | Poll HTTP endpoint until service is healthy or timeout |
| `get_logs` | Retrieve the last N lines of container stdout/stderr |
| `stop_deployment` | Stop and remove a running container |
| `rollback` | Redeploy the last successful deployment for a given name |

## Architecture

```
Claude Desktop
     │
     │  MCP Protocol (JSON-RPC 2.0 via stdio)
     ▼
┌──────────────────────────────────┐
│  MCP CI/CD Server (FastMCP)      │
│                                  │
│  repo_tools   ──► GitPython      │
│  docker_tools ──► Docker SDK     │
│  health_tools ──► httpx          │
│  lifecycle_tools ──► state mgr   │
└──────┬───────────────────────────┘
       │
       ▼
   Docker Engine
   ├── Image build (Dockerfile)
   └── Container run
          └── 127.0.0.1:<port>  (localhost only)
```

- **Protocol**: JSON-RPC 2.0 over stdio
- **State**: Atomic JSON files in `deployments/` (gitignored)
- **Workspaces**: Isolated per-commit directories in `workspace/` (gitignored)
- **Security**: `no-new-privileges:true`, `mem_limit=512m`, `127.0.0.1` binding only

## Testing

```bash
# Run all 101 unit tests
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=src/mcp_cicd --cov-report=term-missing

# Run integration tests (requires Docker daemon)
pytest tests/integration/ -v

# Run a specific group
pytest tests/unit/ -v -k "TestValidateGitUrl"
pytest tests/unit/ -v -k "TestDockerUtils"
```

Unit tests use mocked Docker and Git calls — no running Docker instance needed.

## Project Structure

```
mcp-cicd-agent/
├── src/mcp_cicd/
│   ├── tools/             # MCP tool implementations (8 tools)
│   │   ├── repo_tools.py
│   │   ├── docker_tools.py
│   │   ├── health_tools.py
│   │   └── lifecycle_tools.py
│   ├── models/            # Pydantic data models
│   ├── utils/             # Docker, Git, validation, state helpers
│   └── config/            # Settings via pydantic-settings + .env
├── tests/
│   ├── unit/              # 101 unit tests (mocked)
│   ├── integration/       # End-to-end pipeline tests (Docker required)
│   └── fixtures/          # Test app (simple Python HTTP server)
├── workspace/             # Git clone target (gitignored)
├── deployments/           # Deployment state JSON files (gitignored)
└── logs/                  # Application logs (gitignored)
```

## Configuration

All settings can be overridden via environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | `None` | Personal access token for private repos |
| `MCP_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MCP_PORT_RANGE_START` | `8000` | Start of auto-assigned port range |
| `MCP_PORT_RANGE_END` | `9000` | End of auto-assigned port range |
| `MCP_ALLOWED_GIT_HOSTS` | `["github.com","gitlab.com"]` | JSON list of allowed Git hosts |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Client | Claude Desktop |
| Protocol | MCP (stdio, JSON-RPC 2.0) |
| Backend | Python 3.10+ / FastMCP |
| Container | Docker SDK for Python |
| Git | GitPython |
| HTTP | httpx (async health checks) |
| Validation | Pydantic v2 + pydantic-settings |
| Testing | pytest / pytest-asyncio |

## License

MIT
