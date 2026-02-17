"""
Pydantic models for deployment state management.

Defines the schema for deployment records stored as JSON.
"""
from datetime import datetime  # Manejo de fechas y timestamps
from enum import Enum  # Crear enumeraciones con valores fijos
from typing import Optional, List  # Type hints para tipos opcionales y listas

from pydantic import BaseModel, Field  # BaseModel: clase base para modelos, Field: validación de campos


class DeploymentStatus(str, Enum):
    """Valid deployment status values (finite state machine)."""
    PENDING = "pending"
    CLONING = "cloning"
    BUILDING = "building"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"
    ROLLED_BACK = "rolled_back"


class StepStatus(str, Enum):
    """Valid step execution status values."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DeploymentStep(BaseModel):
    """Individual step in the deployment pipeline."""
    name: str = Field(..., description="Step name (clone, detect, build, deploy, healthcheck)")
    status: StepStatus = Field(..., description="Step execution status")
    duration_seconds: float = Field(..., description="Step execution time in seconds")
    error: Optional[str] = Field(None, description="Error message if step failed")


class HealthCheckResult(BaseModel):
    """Health check validation result."""
    status: str = Field(..., description="healthy or unhealthy")
    url: str = Field(..., description="URL that was checked")
    response_code: Optional[int] = Field(None, description="HTTP response code if successful")
    retries: int = Field(..., description="Number of attempts made")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class DeploymentRecord(BaseModel):
    """Complete deployment state record."""

    # Identity
    deployment_id: str = Field(..., description="Unique deployment identifier")

    # Repository info
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field(..., description="Git branch/tag/commit ref")
    commit_sha: str = Field(..., description="Full commit SHA")

    # Project detection
    project_type: str = Field(..., description="Detected project type (docker, docker-compose, etc)")

    # Docker artifacts
    image_name: str = Field(..., description="Docker image name")
    image_tag: str = Field(..., description="Docker image tag")
    image_id: Optional[str] = Field(None, description="Docker image ID (sha256:...)")

    # Container info
    container_name: str = Field(..., description="Container name")
    container_id: Optional[str] = Field(None, description="Docker container ID")
    host_port: int = Field(..., description="Host port mapping")
    container_port: int = Field(..., description="Container internal port")

    # Status
    status: DeploymentStatus = Field(..., description="Current deployment status")

    # Timestamps
    created_at: datetime = Field(..., description="Deployment creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Deployment start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Deployment completion timestamp")

    # Logs and errors
    build_logs_path: Optional[str] = Field(None, description="Path to build logs file")
    error: Optional[str] = Field(None, description="Error message if failed")

    # Rollback tracking
    rollback_from: Optional[str] = Field(None, description="Deployment ID this rolled back from")

    # Pipeline steps
    steps: List[DeploymentStep] = Field(default_factory=list, description="Executed pipeline steps")

    # Health check
    healthcheck: Optional[HealthCheckResult] = Field(None, description="Health check result")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True  # Store enums as their string values in JSON
        json_encoders = {
            datetime: lambda v: v.isoformat()  # Serialize datetime as ISO format
        }
