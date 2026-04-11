import asyncio
import logging
import os
import shutil
from pathlib import Path

from git import Repo, GitCommandError, InvalidGitRepositoryError

from app.core.config import settings

logger = logging.getLogger(__name__)


async def clone_repo(git_url: str, branch: str = "main", project_id: str = "") -> str:
    """Clone or update a git repository. Returns the local repo path."""
    repo_dir = settings.repos_dir / project_id
    
    def _operate():
        # 情况1: 目录不存在，直接 clone
        if not repo_dir.exists():
            logger.info(f"目录不存在，开始克隆: {git_url} -> {repo_dir}")
            logger.debug(f"分支: {branch}, depth: 1")
            Repo.clone_from(git_url, str(repo_dir), branch=branch, depth=1)
            logger.info("克隆完成")
            return
        
        # 目录存在，检查是否是有效的 git 仓库
        try:
            repo = Repo(repo_dir)
            
            # 情况2: 是有效的 git 仓库，fetch + checkout + reset
            logger.info(f"检测到已存在的仓库，执行更新: {repo_dir}")
            
            # 确保远程 origin 存在
            if 'origin' not in [r.name for r in repo.remotes]:
                logger.debug(f"创建远程 origin: {git_url}")
                repo.create_remote('origin', git_url)
            else:
                logger.debug(f"更新远程 origin URL: {git_url}")
                repo.remotes.origin.set_url(git_url)
            
            # Fetch 最新代码
            logger.debug("正在 fetch 远程更新...")
            repo.remotes.origin.fetch()
            
            # 检查分支是否存在
            branch_names = [h.name for h in repo.heads]
            target_branch = branch if branch in branch_names else 'main'
            
            if target_branch not in branch_names:
                # 分支不存在，尝试从远程创建
                logger.debug(f"本地分支 {target_branch} 不存在，从远程创建")
                repo.git.checkout('-b', target_branch, f'origin/{target_branch}')
            else:
                # 切换到目标分支
                logger.debug(f"切换到分支: {target_branch}")
                repo.git.checkout(target_branch)
            
            # Reset 到远程最新状态
            logger.debug("重置到远程最新状态...")
            repo.git.reset('--hard', f'origin/{target_branch}')
            
            # Pull 确保最新
            logger.debug("拉取最新代码...")
            repo.remotes.origin.pull(target_branch)
            
            logger.info("仓库更新完成")
            
        except InvalidGitRepositoryError:
            # 情况3: 目录存在但不是 git 仓库，删除后重新 clone
            logger.warning(f"目录存在但不是有效的 git 仓库，清理后重新克隆")
            try:
                _force_remove_dir(repo_dir)
            except Exception as remove_err:
                logger.error(f"删除目录失败: {repo_dir}", exc_info=True)
                raise Exception(
                    f"与 Git 仓库同名的目录被占用，且无法删除: {repo_dir}\n"
                    f"错误详情: {remove_err}\n"
                    f"请检查是否有其他程序正在占用该目录，或手动删除后重试"
                )
            
            logger.info(f"开始克隆: {git_url} -> {repo_dir}")
            Repo.clone_from(git_url, str(repo_dir), branch=branch, depth=1)
            logger.info("克隆完成")
            
        except Exception as e:
            # 情况4: 其他错误，尝试删除后重新 clone
            logger.error(f"仓库操作失败: {e}，尝试清理后重新克隆", exc_info=True)
            try:
                _force_remove_dir(repo_dir)
                logger.info(f"开始克隆: {git_url} -> {repo_dir}")
                Repo.clone_from(git_url, str(repo_dir), branch=branch, depth=1)
                logger.info("克隆完成")
            except Exception as remove_err:
                logger.error(f"删除目录失败: {repo_dir}", exc_info=True)
                raise Exception(
                    f"与 Git 仓库同名的目录被占用，且无法删除: {repo_dir}\n"
                    f"错误详情: {remove_err}\n"
                    f"请检查是否有其他程序正在占用该目录，或手动删除后重试"
                )
            except Exception as clone_err:
                logger.error(f"重新克隆失败: {clone_err}", exc_info=True)
                raise Exception(f"Git 操作失败: {clone_err}")

    try:
        await asyncio.to_thread(_operate)
        return str(repo_dir)
    except Exception as e:
        raise Exception(f"Git 操作失败: {str(e)}")


def _force_remove_dir(path: Path):
    """强制删除目录，处理 Windows 文件锁定问题"""
    import stat
    
    def remove_readonly(func, path, excinfo):
        """清除只读属性后重试"""
        os.chmod(path, stat.S_IWRITE)
        func(path)
    
    logger.debug(f"尝试删除目录: {path}")
    try:
        # 先尝试正常删除
        shutil.rmtree(path, onerror=remove_readonly)
        logger.debug(f"目录删除成功: {path}")
    except Exception as e:
        logger.error(f"删除目录失败: {path}", exc_info=True)
        raise


async def pull_repo(repo_path: str, branch: str = "main") -> None:
    """Pull latest changes for an existing repo."""
    def _pull():
        repo = Repo(repo_path)
        origin = repo.remotes.origin
        origin.pull(branch)

    await asyncio.to_thread(_pull)
