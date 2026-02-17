"""
State management for deployment records.

Handles atomic JSON file operations and deployment history tracking.
"""
import json  # Serialización y deserialización de JSON
import os  # Operaciones del sistema operativo (rutas, archivos)
import tempfile  # Creación de archivos temporales
from datetime import datetime  # Manejo de fechas y timestamps
from pathlib import Path  # Manejo moderno de rutas de archivos
from typing import Optional, List, Dict, Any  # Type hints para tipos opcionales y colecciones

from ..models.deployment import DeploymentRecord, DeploymentStatus  # Modelo Pydantic de deployment
from ..exceptions import ConfigurationError  # Excepción personalizada para errores de config
from .logging import get_logger  # Logger estructurado

logger = get_logger(__name__)


class StateManager:
    """Manages deployment state persistence with atomic writes."""

    def __init__(self, deployment_dir: Path):
        """
        Initialize state manager.

        Args:
            deployment_dir: Directory for storing deployment JSON files
        """
        self.deployment_dir = deployment_dir
        self.deployment_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.deployment_dir / "index.json"
        self._ensure_index()

    def _ensure_index(self) -> None:
        """Create index file if it doesn't exist."""
        if not self.index_file.exists():
            self._atomic_write_json(self.index_file, {"deployments": []})

    def _atomic_write_json(self, filepath: Path, data: Dict[str, Any]) -> None:
        """
        Write JSON file atomically using temp file + rename.

        Args:
            filepath: Target file path
            data: Data to serialize as JSON
        """
        dir_path = filepath.parent
        dir_path.mkdir(parents=True, exist_ok=True)

        # Create temp file in same directory (required for atomic rename)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(dir_path),
            prefix=".tmp_",
            suffix=".json"
        )

        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

            # Atomic rename (POSIX guarantees atomicity)
            os.replace(tmp_path, str(filepath))

        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise ConfigurationError(
                f"Failed to write {filepath}: {e}",
                context={"filepath": str(filepath)}
            )

    def save(self, record: DeploymentRecord) -> None:
        """
        Save deployment record to individual JSON file and update index.

        Args:
            record: Deployment record to save
        """
        # Save individual deployment file
        deployment_file = self.deployment_dir / f"{record.deployment_id}.json"
        data = record.model_dump(mode='json')
        self._atomic_write_json(deployment_file, data)

        # Update index
        self._update_index(record.deployment_id, record.status, record.repo_url)

        logger.info(
            "deployment_saved",
            deployment_id=record.deployment_id,
            status=record.status,
            repo_url=record.repo_url
        )

    def _update_index(self, deployment_id: str, status: str, repo_url: str) -> None:
        """Update index with deployment metadata."""
        index = self._read_json(self.index_file)

        # Remove existing entry if present
        index["deployments"] = [
            d for d in index["deployments"]
            if d["deployment_id"] != deployment_id
        ]

        # Add new entry
        index["deployments"].append({
            "deployment_id": deployment_id,
            "status": status,
            "repo_url": repo_url,
            "updated_at": datetime.utcnow().isoformat()
        })

        self._atomic_write_json(self.index_file, index)

    def load(self, deployment_id: str) -> Optional[DeploymentRecord]:
        """
        Load deployment record by ID.

        Args:
            deployment_id: Deployment ID to load

        Returns:
            DeploymentRecord if found, None otherwise
        """
        deployment_file = self.deployment_dir / f"{deployment_id}.json"

        if not deployment_file.exists():
            logger.warning("deployment_not_found", deployment_id=deployment_id)
            return None

        data = self._read_json(deployment_file)
        return DeploymentRecord(**data)

    def _read_json(self, filepath: Path) -> Dict[str, Any]:
        """Read and parse JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to read {filepath}: {e}",
                context={"filepath": str(filepath)}
            )

    def find_latest_successful(
        self,
        repo_url: str,
        exclude: Optional[str] = None
    ) -> Optional[DeploymentRecord]:
        """
        Find the most recent successful deployment for a repository.

        Args:
            repo_url: Repository URL to search for
            exclude: Optional deployment ID to exclude from search

        Returns:
            Latest successful DeploymentRecord or None
        """
        index = self._read_json(self.index_file)

        # Filter for successful deployments of this repo
        candidates = [
            d for d in index["deployments"]
            if d["repo_url"] == repo_url
            and d["status"] == DeploymentStatus.RUNNING.value
            and d["deployment_id"] != exclude
        ]

        if not candidates:
            return None

        # Sort by updated_at descending and take first
        candidates.sort(key=lambda x: x["updated_at"], reverse=True)
        latest_id = candidates[0]["deployment_id"]

        return self.load(latest_id)

    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all deployments from index.

        Returns:
            List of deployment metadata dicts
        """
        index = self._read_json(self.index_file)
        return index["deployments"]
