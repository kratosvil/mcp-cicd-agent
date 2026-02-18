"""
Unit tests for utils/git_utils.py

Tests URL validation, workspace management, and metadata extraction.
Git clone operations are mocked to avoid network calls.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_cicd.exceptions import GitOperationError
from mcp_cicd.utils.git_utils import (
    validate_git_url,
    WorkspaceManager,
    extract_commit_metadata,
)


# ── validate_git_url ────────────────────────────────────────────────────────

class TestValidateGitUrl:
    ALLOWED = ["github.com", "gitlab.com"]

    def test_https_github_allowed(self):
        validate_git_url("https://github.com/user/repo.git", self.ALLOWED)

    def test_https_gitlab_allowed(self):
        validate_git_url("https://gitlab.com/user/repo.git", self.ALLOWED)

    def test_git_at_github_allowed(self):
        validate_git_url("git@github.com:user/repo.git", self.ALLOWED)

    def test_disallowed_host_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("https://bitbucket.org/user/repo.git", self.ALLOWED)

    def test_semicolon_injection_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("https://github.com/user/repo.git;rm -rf /", self.ALLOWED)

    def test_pipe_injection_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("https://github.com/user/repo.git|cat /etc/passwd", self.ALLOWED)

    def test_backtick_injection_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("https://github.com/user/repo.git`id`", self.ALLOWED)

    def test_dollar_sign_injection_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("https://github.com/user/repo.git$(whoami)", self.ALLOWED)

    def test_no_https_prefix_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("ftp://github.com/user/repo.git", self.ALLOWED)

    def test_file_scheme_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url("file:///tmp/repo", self.ALLOWED)

    def test_empty_allowed_hosts_denies_all(self):
        # When allowed_hosts is non-empty, any host not in the list is denied
        with pytest.raises(GitOperationError):
            validate_git_url("https://github.com/user/repo.git", ["example.com"])

    def test_ampersand_in_url_raises(self):
        with pytest.raises(GitOperationError):
            validate_git_url(
                "https://github.com/user/repo.git&curl evil.com",
                self.ALLOWED
            )


# ── WorkspaceManager ────────────────────────────────────────────────────────

class TestWorkspaceManager:
    def test_sanitize_repo_name_github_https(self, tmp_path):
        wm = WorkspaceManager(tmp_path)
        name = wm.sanitize_repo_name("https://github.com/user/my-repo.git")
        assert name == "my-repo"

    def test_sanitize_repo_name_with_uppercase(self, tmp_path):
        wm = WorkspaceManager(tmp_path)
        name = wm.sanitize_repo_name("https://github.com/user/MyRepo.git")
        assert name == "myrepo"

    def test_sanitize_repo_name_with_underscores(self, tmp_path):
        wm = WorkspaceManager(tmp_path)
        name = wm.sanitize_repo_name("https://github.com/user/my_project.git")
        # underscores should be replaced with hyphens per sanitize logic
        assert name == "my-project"

    def test_get_path_structure(self, tmp_path):
        wm = WorkspaceManager(tmp_path)
        path = wm.get_path("https://github.com/user/repo.git", "abc123def456")
        assert "repo" in str(path)
        assert "abc123def456" in str(path)

    def test_get_path_uses_12_char_sha(self, tmp_path):
        wm = WorkspaceManager(tmp_path)
        full_sha = "a" * 40
        path = wm.get_path("https://github.com/user/repo.git", full_sha)
        # path should contain first 12 chars of sha
        assert "a" * 12 in str(path)

    def test_create_makes_directory(self, tmp_path):
        wm = WorkspaceManager(tmp_path)
        sha = "deadbeef1234cafebabe5678"
        created = wm.create("https://github.com/user/repo.git", sha)
        assert created.exists()
        assert created.is_dir()

    def test_base_dir_created_on_init(self, tmp_path):
        new_dir = tmp_path / "workspaces"
        assert not new_dir.exists()
        WorkspaceManager(new_dir)
        assert new_dir.exists()


# ── extract_commit_metadata ─────────────────────────────────────────────────

class TestExtractCommitMetadata:
    def _make_mock_repo(self, sha="abc1234567890abcdef1234567890abcdef123456",
                        author="Test User", message="Test commit",
                        branch_name="main"):
        """Build a minimal mock GitPython Repo object."""
        from datetime import datetime, timezone

        commit = MagicMock()
        commit.hexsha = sha
        commit.author.name = author
        commit.message = message
        commit.committed_datetime = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)

        repo = MagicMock()
        repo.head.commit = commit
        repo.active_branch.name = branch_name

        return repo

    def test_extracts_full_sha(self):
        sha = "a" * 40
        repo = self._make_mock_repo(sha=sha)
        meta = extract_commit_metadata(repo)
        assert meta.full_sha == sha

    def test_extracts_short_sha(self):
        sha = "abc1234567890" + "0" * 27
        repo = self._make_mock_repo(sha=sha)
        meta = extract_commit_metadata(repo)
        assert meta.short_sha == sha[:7]

    def test_extracts_author(self):
        repo = self._make_mock_repo(author="Jane Doe")
        meta = extract_commit_metadata(repo)
        assert meta.author == "Jane Doe"

    def test_extracts_message_stripped(self):
        repo = self._make_mock_repo(message="  My commit message  \n")
        meta = extract_commit_metadata(repo)
        assert meta.message == "My commit message"

    def test_extracts_branch(self):
        repo = self._make_mock_repo(branch_name="feature/test")
        meta = extract_commit_metadata(repo)
        assert meta.branch == "feature/test"

    def test_detached_head_uses_detached_string(self):
        repo = self._make_mock_repo()
        repo.active_branch.name  # make accessing raise TypeError
        repo.active_branch = MagicMock()
        type(repo.active_branch).name = property(
            lambda self: (_ for _ in ()).throw(TypeError("detached HEAD"))
        )
        meta = extract_commit_metadata(repo)
        assert meta.branch == "detached"
