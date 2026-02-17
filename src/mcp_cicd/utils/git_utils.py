# Este archivo maneja todas las operaciones de Git: clonado, checkout, extracción de metadata.

"""
Git operations utilities using GitPython.

Handles repository cloning, checkout, and metadata extraction.
"""
import re  # Expresiones regulares para validación de URLs y nombres
from dataclasses import dataclass  # Crear clases de datos simples
from datetime import datetime  # Manejo de fechas y timestamps
from pathlib import Path  # Manejo moderno de rutas de archivos
from typing import Optional  # Type hints para valores opcionales

from git import Repo, GitCommandError  # GitPython - wrapper de comandos git
from git.exc import InvalidGitRepositoryError  # Excepción cuando el directorio no es repo git

from ..exceptions import CloneError, CheckoutError, GitOperationError  # Excepciones personalizadas
from .logging import get_logger  # Logger estructurado

logger = get_logger(__name__)


@dataclass
class CommitMetadata:
    """Git commit metadata extracted from repository."""
    full_sha: str  # SHA completo del commit (40 caracteres)
    short_sha: str  # SHA corto (7 caracteres)
    branch: str  # Nombre de la rama o "detached" si no está en una rama
    author: str  # Nombre del autor del commit
    message: str  # Mensaje del commit
    timestamp: datetime  # Fecha y hora del commit


class WorkspaceManager:
    """Manages isolated workspace directories for repository clones."""

    def __init__(self, base_dir: Path):
        """
        Initialize workspace manager.

        Args:
            base_dir: Base directory for all workspaces
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def sanitize_repo_name(self, repo_url: str) -> str:
        """
        Extract and sanitize repository name from URL.

        Args:
            repo_url: Git repository URL

        Returns:
            Sanitized repository name
        """
        # Extract last part of URL and remove .git extension
        name = repo_url.rstrip('/').split('/')[-1]
        name = name.replace('.git', '')

        # Replace invalid characters with hyphens
        name = re.sub(r'[^a-z0-9-]', '-', name.lower())

        return name

    def get_path(self, repo_url: str, commit_sha: str) -> Path:
        """
        Get workspace path for a repository and commit.

        Args:
            repo_url: Repository URL
            commit_sha: Commit SHA (will use first 12 chars)

        Returns:
            Path to workspace directory
        """
        repo_name = self.sanitize_repo_name(repo_url)
        sha_short = commit_sha[:12]
        return self.base_dir / repo_name / sha_short

    def create(self, repo_url: str, commit_sha: str) -> Path:
        """
        Create workspace directory.

        Args:
            repo_url: Repository URL
            commit_sha: Commit SHA

        Returns:
            Created workspace path
        """
        path = self.get_path(repo_url, commit_sha)
        path.mkdir(parents=True, exist_ok=True)
        logger.info("workspace_created", path=str(path))
        return path


def validate_git_url(url: str, allowed_hosts: list[str]) -> None:
    """
    Validate Git URL against allowed hosts.

    Args:
        url: Git repository URL
        allowed_hosts: List of allowed hostnames (e.g., ['github.com'])

    Raises:
        GitOperationError: If URL is invalid or not from allowed host
    """
    # Basic URL validation
    if not url.startswith(('https://', 'http://', 'git@')):
        raise GitOperationError(
            "Git URL must start with https://, http://, or git@",
            context={"url": url}
        )

    # Check for dangerous characters (command injection prevention)
    dangerous_chars = [';', '|', '&', '$', '`']
    if any(char in url for char in dangerous_chars):
        raise GitOperationError(
            "Git URL contains dangerous characters",
            context={"url": url}
        )

    # Extract hostname
    if url.startswith('git@'):
        # git@github.com:user/repo.git
        match = re.search(r'git@([^:]+):', url)
    else:
        # https://github.com/user/repo.git
        match = re.search(r'https?://([^/]+)/', url)

    if not match:
        raise GitOperationError(
            "Could not extract hostname from Git URL",
            context={"url": url}
        )

    hostname = match.group(1)

    # Check against allowlist
    if hostname not in allowed_hosts:
        raise GitOperationError(
            f"Git host {hostname} not in allowed list",
            context={"hostname": hostname, "allowed": allowed_hosts}
        )


def clone_or_update_repo(
    repo_url: str,
    target_path: Path,
    branch: str = "main"
) -> Repo:
    """
    Clone repository or update if already exists.

    Args:
        repo_url: Git repository URL
        target_path: Local path to clone into
        branch: Branch/tag/commit to checkout

    Returns:
        Git repository object

    Raises:
        CloneError: If clone/update fails
    """
    try:
        # Check if directory already exists and is a git repo
        if target_path.exists() and (target_path / '.git').exists():
            logger.info("updating_existing_repo", path=str(target_path))
            repo = Repo(target_path)

            # Fetch latest changes
            origin = repo.remotes.origin
            origin.fetch()

        else:
            logger.info(
                "cloning_repository",
                url=repo_url,
                path=str(target_path)
            )
            repo = Repo.clone_from(
                repo_url,
                target_path,
                branch=branch,
                depth=1  # Shallow clone for speed
            )

        return repo

    except GitCommandError as e:
        raise CloneError(
            f"Failed to clone repository: {e}",
            context={"url": repo_url, "path": str(target_path), "error": str(e)}
        )
    except InvalidGitRepositoryError as e:
        raise CloneError(
            f"Invalid git repository: {e}",
            context={"path": str(target_path), "error": str(e)}
        )


def checkout_ref(repo: Repo, ref: str) -> None:
    """
    Checkout a specific branch, tag, or commit.

    Args:
        repo: Git repository object
        ref: Branch name, tag, or commit SHA

    Raises:
        CheckoutError: If checkout fails
    """
    try:
        logger.info("checking_out_ref", ref=ref)

        # Try to checkout the ref
        repo.git.checkout(ref)

        logger.info("checkout_successful", ref=ref)

    except GitCommandError as e:
        raise CheckoutError(
            f"Failed to checkout {ref}: {e}",
            context={"ref": ref, "error": str(e)}
        )


def extract_commit_metadata(repo: Repo) -> CommitMetadata:
    """
    Extract metadata from current commit.

    Args:
        repo: Git repository object

    Returns:
        CommitMetadata with commit information
    """
    commit = repo.head.commit

    # Handle detached HEAD state (happens when checking out tags or SHAs)
    try:
        branch = repo.active_branch.name
    except TypeError:
        # In detached HEAD state
        branch = "detached"

    metadata = CommitMetadata(
        full_sha=commit.hexsha,
        short_sha=commit.hexsha[:7],
        branch=branch,
        author=commit.author.name,
        message=commit.message.strip(),
        timestamp=commit.committed_datetime
    )

    logger.info(
        "commit_metadata_extracted",
        sha=metadata.short_sha,
        branch=metadata.branch,
        author=metadata.author
    )

    return metadata


def prepare_repository(
    repo_url: str,
    workspace_manager: WorkspaceManager,
    branch: str = "main",
    allowed_hosts: list[str] = None
) -> tuple[Path, CommitMetadata]:
    """
    Complete repository preparation workflow.

    Args:
        repo_url: Git repository URL
        workspace_manager: Workspace manager instance
        branch: Branch/tag/commit to checkout
        allowed_hosts: Optional list of allowed Git hosts

    Returns:
        Tuple of (workspace_path, commit_metadata)

    Raises:
        GitOperationError: If any step fails
    """
    # Validate URL if allowed hosts specified
    if allowed_hosts:
        validate_git_url(repo_url, allowed_hosts)

    # Clone or update repository to temporary location first
    temp_path = workspace_manager.base_dir / "temp_clone"
    repo = clone_or_update_repo(repo_url, temp_path, branch)

    # Checkout specific ref if needed
    if branch != "main":
        checkout_ref(repo, branch)

    # Extract commit metadata
    metadata = extract_commit_metadata(repo)

    # Create final workspace with commit SHA
    final_path = workspace_manager.create(repo_url, metadata.full_sha)

    # Move repository to final location if different
    if temp_path != final_path:
        import shutil
        if final_path.exists():
            shutil.rmtree(final_path)
        shutil.move(str(temp_path), str(final_path))

    logger.info(
        "repository_prepared",
        repo_url=repo_url,
        workspace=str(final_path),
        commit=metadata.short_sha
    )

    return final_path, metadata
