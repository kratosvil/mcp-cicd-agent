"""
Custom exception hierarchy for MCP CI/CD Agent.

Each exception carries a context dict for structured logging.
"""


class MCPCICDError(Exception):
    """Base exception for all MCP CI/CD errors."""

    def __init__(self, message: str, context: dict = None):
        self.context = context or {}
        super().__init__(message)


class GitOperationError(MCPCICDError):
    """Base exception for Git-related operations."""
    pass


class CloneError(GitOperationError):
    """Raised when git clone fails."""
    pass


class CheckoutError(GitOperationError):
    """Raised when git checkout fails."""
    pass


class DockerOperationError(MCPCICDError):
    """Base exception for Docker-related operations."""
    pass


class BuildError(DockerOperationError):
    """Raised when Docker image build fails."""
    pass


class ContainerStartError(DockerOperationError):
    """Raised when container fails to start."""
    pass


class PortConflictError(DockerOperationError):
    """Raised when requested port is already in use."""
    pass


class HealthCheckError(DockerOperationError):
    """Raised when health check fails after timeout."""
    pass


class PipelineError(MCPCICDError):
    """Base exception for pipeline orchestration errors."""
    pass


class RollbackError(PipelineError):
    """Raised when rollback operation fails."""
    pass


class ConfigurationError(MCPCICDError):
    """Raised when configuration is invalid."""
    pass


class ValidationError(MCPCICDError):
    """Raised when input validation fails."""
    pass
