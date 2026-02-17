"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables with MCP_ prefix.
"""
from pathlib import Path
from typing import List

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MCP_",
        case_sensitive=False,
        extra="ignore"
    )

    # Server Configuration
    server_name: str = "mcp-cicd-server"
    transport: str = "stdio"

    # Directories
    workspace_dir: Path = Path("./workspace")
    deployment_dir: Path = Path("./deployments")
    log_dir: Path = Path("./logs")

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # Port Configuration
    port_range_start: int = 8000
    port_range_end: int = 9000

    # Container Limits
    container_memory_limit: str = "512m"
    health_check_timeout: int = 30

    # Git Configuration
    allowed_git_hosts: List[str] = ["github.com", "gitlab.com"]

    # Optional GitHub Token
    github_token: SecretStr | None = None

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of {valid_levels}")
        return v_upper

    @field_validator("port_range_start", "port_range_end")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port is in valid range."""
        if not 1024 <= v <= 65535:
            raise ValueError("Port must be between 1024 and 65535")
        return v

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for directory in [self.workspace_dir, self.deployment_dir, self.log_dir]:
            directory.mkdir(parents=True, exist_ok=True)


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings singleton instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
