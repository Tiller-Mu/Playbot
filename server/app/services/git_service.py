import asyncio
import os
import shutil
from pathlib import Path

from git import Repo, GitCommandError

from app.core.config import settings


async def clone_repo(git_url: str, branch: str = "main", project_id: str = "") -> str:
    """Clone a git repository. Returns the local repo path."""
    repo_dir = settings.repos_dir / project_id
    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    def _clone():
        Repo.clone_from(git_url, str(repo_dir), branch=branch, depth=1)

    await asyncio.to_thread(_clone)
    return str(repo_dir)


async def pull_repo(repo_path: str, branch: str = "main") -> None:
    """Pull latest changes for an existing repo."""
    def _pull():
        repo = Repo(repo_path)
        origin = repo.remotes.origin
        origin.pull(branch)

    await asyncio.to_thread(_pull)
