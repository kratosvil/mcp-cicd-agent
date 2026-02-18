# MCP CI/CD Agent - Usage Guide

Complete guide for using the MCP CI/CD Agent to automate Docker deployments.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Available Tools](#available-tools)
- [Workflow Examples](#workflow-examples)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- Python 3.10 or higher
- Docker Desktop (running)
- Git

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/kratosvil/mcp-cicd-agent.git
cd mcp-cicd-agent
```

2. **Create virtual environment:**
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows PowerShell
# or
source .venv/bin/activate   # Linux/Mac
```

3. **Install dependencies:**
```bash
pip install -e .
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your settings
```

---

## Configuration

The server is configured via environment variables in `.env`:
```env
# Server Configuration
MCP_SERVER_NAME=mcp-cicd-server
MCP_TRANSPORT=stdio

# Directories
MCP_WORKSPACE_DIR=./workspace
MCP_DEPLOYMENT_DIR=./deployments
MCP_LOG_DIR=./logs

# Logging
MCP_LOG_LEVEL=INFO         # DEBUG, INFO, WARNING, ERROR
MCP_LOG_JSON=true          # true for JSON logs, false for console

# Port Configuration
MCP_PORT_RANGE_START=8000
MCP_PORT_RANGE_END=9000

# Container Settings
MCP_CONTAINER_MEMORY_LIMIT=512m
MCP_HEALTH_CHECK_TIMEOUT=30

# Git Security
MCP_ALLOWED_GIT_HOSTS=github.com,gitlab.com

# Optional: GitHub Token for private repos
# MCP_GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
```

---

## Running the Server

### Standalone Mode
```bash
python -m mcp_cicd
```

### As Installed Command
```bash
mcp-cicd
```

### With Claude Desktop

Add to Claude Desktop configuration (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "cicd-agent": {
      "command": "C:\\MCP\\MCP-Despliegues\\mcp-cicd-agent\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_cicd"],
      "cwd": "C:\\MCP\\MCP-Despliegues\\mcp-cicd-agent"
    }
  }
}
```

---

## Available Tools

### 1. `prepare_repo`

Clone or update a Git repository.

**Parameters:**
- `repo_url` (string, required): Git repository URL
- `branch` (string, optional): Branch/tag/commit (default: "main")
- `target_dir` (string, optional): Custom workspace path

**Returns:**
```json
{
  "workspace_path": "/path/to/workspace",
  "commit_sha": "a1b2c3d4...",
  "short_sha": "a1b2c3d",
  "branch": "main",
  "author": "Developer Name",
  "message": "Commit message",
  "timestamp": "2026-02-18T15:00:00Z"
}
```

---

### 2. `detect_project_type`

Detect project type from repository files.

**Parameters:**
- `repo_path` (string, required): Path to repository

**Returns:**
```json
{
  "project_type": "docker",
  "dockerfile_path": "Dockerfile",
  "compose_file": null,
  "exposed_ports": [8000, 8080],
  "details": {
    "has_docker": true,
    "has_compose": false
  }
}
```

**Detected Types:**
- `docker-compose` - Has docker-compose.yml
- `docker` - Has Dockerfile
- `nodejs` - Has package.json
- `python` - Has requirements.txt/pyproject.toml
- `go` - Has go.mod
- `rust` - Has Cargo.toml
- `unknown` - No recognized markers

---

### 3. `build_image`

Build Docker image from Dockerfile.

**Parameters:**
- `path` (string, required): Build context directory
- `image_tag` (string, required): Image tag (e.g., "myapp:v1.0")
- `dockerfile` (string, optional): Dockerfile name (default: "Dockerfile")
- `build_args` (dict, optional): Build arguments

**Returns:**
```json
{
  "image_id": "sha256:abc123...",
  "image_tag": "myapp:v1.0",
  "build_logs": ["Step 1/5 : FROM python:3.10", ...],
  "build_time": 45.23,
  "size_bytes": 524288000,
  "size_mb": 500.0
}
```

---

### 4. `deploy_container`

Deploy container from image.

**Parameters:**
- `image_tag` (string, required): Image to deploy
- `container_name` (string, required): Unique container name
- `host_port` (int, optional): Host port (auto-assigned if not specified)
- `container_port` (int, optional): Container port (default: 8000)
- `env_vars` (dict, optional): Environment variables

**Returns:**
```json
{
  "container_id": "def456...",
  "container_name": "myapp-a1b2c3d-p8080",
  "host_port": 8080,
  "container_port": 8000,
  "url": "http://localhost:8080",
  "status": "running"
}
```

---

### 5. `healthcheck`

Validate service availability.

**Parameters:**
- `url` (string, required): URL to check
- `timeout` (int, optional): Max seconds to wait (default: 30)
- `interval` (float, optional): Initial retry interval (default: 2.0)
- `backoff` (float, optional): Backoff multiplier (default: 1.5)
- `expected_status` (int, optional): Expected HTTP code (default: 200)

**Returns:**
```json
{
  "healthy": true,
  "url": "http://localhost:8080",
  "response_code": 200,
  "attempts": 3,
  "elapsed_seconds": 5.2,
  "message": "Service healthy after 3 attempt(s) in 5.2s"
}
```

---

### 6. `get_logs`

Retrieve container logs.

**Parameters:**
- `container_name` (string, required): Container name
- `tail` (int, optional): Number of lines (default: 100, max: 1000)

**Returns:**
```json
{
  "container_name": "myapp-a1b2c3d-p8080",
  "logs": "2026-02-18T15:00:00Z Starting server...\n...",
  "lines_returned": 100
}
```

---

### 7. `stop_deployment`

Stop and remove container.

**Parameters:**
- `container_name` (string, required): Container to stop

**Returns:**
```json
{
  "container_name": "myapp-a1b2c3d-p8080",
  "status": "stopped",
  "message": "Container stopped and removed successfully"
}
```

---

### 8. `rollback`

Rollback to previous successful deployment.

**Parameters:**
- `deployment_id` (string, optional): Failed deployment ID
- `repo_url` (string, optional): Repository URL (alternative)

**Returns:**
```json
{
  "rollback_deployment_id": "dep-20260218-rollback-a1b2c3d",
  "original_deployment_id": "dep-20260218-xyz789",
  "previous_deployment_id": "dep-20260217-abc123",
  "container_name": "myapp-rollback-a1b2c3d-p8080",
  "host_port": 8080,
  "url": "http://localhost:8080",
  "commit_sha": "a1b2c3d4...",
  "message": "Rolled back to deployment dep-20260217-abc123 (commit a1b2c3d)"
}
```

---

## Workflow Examples

### Example 1: Complete Deployment
```
Deploy the app from https://github.com/myuser/myapp on port 8080
```

**MCP will execute:**
1. `prepare_repo` - Clone repository
2. `detect_project_type` - Find Dockerfile
3. `build_image` - Build Docker image
4. `deploy_container` - Deploy on port 8080
5. `healthcheck` - Verify service is running

---

### Example 2: Rollback Failed Deployment
```
The deployment failed, rollback to the previous working version
```

**MCP will execute:**
1. `rollback` - Find last successful deployment
2. `stop_deployment` - Stop failed container
3. `deploy_container` - Redeploy previous image
4. `healthcheck` - Verify rollback succeeded

---

### Example 3: Check Container Logs
```
Show me the last 50 lines of logs from container myapp-abc123-p8080
```

**MCP will execute:**
1. `get_logs` - Retrieve logs with tail=50

---

## Troubleshooting

### Server won't start

**Error:** `ModuleNotFoundError: No module named 'mcp_cicd'`

**Solution:**
```bash
pip install -e .
```

---

### Port conflicts

**Error:** `PortConflictError: Port 8080 is already in use`

**Solution:**
- Let the tool auto-assign a port (don't specify `host_port`)
- Or stop the conflicting container
- Or specify a different port

---

### Docker daemon not accessible

**Error:** `Failed to connect to Docker daemon`

**Solution:**
- Start Docker Desktop
- Verify with: `docker ps`

---

### Git clone fails

**Error:** `Git host example.com not in allowed list`

**Solution:**
Add the host to `.env`:
```env
MCP_ALLOWED_GIT_HOSTS=github.com,gitlab.com,example.com
```

---

### Build fails

**Check build logs in the response:**
```json
{
  "build_logs": ["ERROR: Failed to fetch package X", ...]
}
```

**Common fixes:**
- Fix Dockerfile syntax
- Check base image availability
- Verify build context path

---

## Advanced Usage

### Custom Dockerfile Location
```
Build image from src/backend/Dockerfile
```
```json
{
  "path": "/path/to/workspace",
  "image_tag": "myapp:v1.0",
  "dockerfile": "src/backend/Dockerfile"
}
```

---

### Environment Variables
```
Deploy with DATABASE_URL=postgres://localhost/db
```
```json
{
  "image_tag": "myapp:v1.0",
  "container_name": "myapp-prod",
  "env_vars": {
    "DATABASE_URL": "postgres://localhost/db",
    "ENVIRONMENT": "production"
  }
}
```

---

## Security Notes

- Containers run as **non-root user (UID 1000)**
- Ports bind to **localhost only (127.0.0.1)**
- Memory limited to **512MB** (configurable)
- Git URLs validated against allowlist
- No privilege escalation allowed

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/kratosvil/mcp-cicd-agent/issues
- Documentation: See README.md
