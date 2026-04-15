"""录制控制API - 支持开始/暂停/继续/停止录制，页面捕获，覆盖率分析"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.database import Project, get_db
from app.services.recording_session import RecordingSession
from app.services.coverage_analyzer import CoverageAnalyzer
from app.services.playwright_mcp import PlaywrightMCPService

router = APIRouter(prefix="/api/recording", tags=["recording"])

logger = logging.getLogger(__name__)

# 全局会话管理器（内存存储，后续可改为Redis）
_sessions = {}


def _get_session(project_id: str) -> RecordingSession:
    """获取或创建录制会话"""
    if project_id not in _sessions:
        session = RecordingSession(project_id)
        # 尝试加载之前的会话
        session.load()
        _sessions[project_id] = session
    return _sessions[project_id]


@router.post("/{project_id}/start")
async def start_recording(project_id: str, db: AsyncSession = Depends(get_db)):
    """开始/继续录制"""
    # 验证项目存在
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在，无法开始录制")
    
    session = _get_session(project_id)
    
    # 根据当前状态决定是开始还是继续
    if session.status == 'paused':
        session.resume()
        return {
            "message": "继续录制",
            "status": "recording",
            "discovered_count": len(session.discovered_pages)
        }
    elif session.status in ['idle', 'completed']:
        if session.status == 'completed':
            # 清除旧会话，开始新录制
            session.clear()
        
        # 启动浏览器
        base_url = project.base_url
        session.start(base_url=base_url)
        session.launch_browser()
        
        return {
            "message": "开始录制，浏览器窗口已打开",
            "status": "recording",
            "discovered_count": 0
        }
    else:
        return {
            "message": "已在录制中",
            "status": session.status,
            "discovered_count": len(session.discovered_pages)
        }


@router.post("/{project_id}/pause")
async def pause_recording(project_id: str):
    """暂停录制"""
    session = _get_session(project_id)
    
    if session.status != 'recording':
        raise HTTPException(400, f"当前状态为 {session.status}，无法暂停")
    
    session.pause()
    return {
        "message": "录制已暂停",
        "status": "paused",
        "discovered_count": len(session.discovered_pages)
    }


@router.post("/{project_id}/stop")
async def stop_recording(project_id: str, db: AsyncSession = Depends(get_db)):
    """停止录制并分析覆盖率"""
    session = _get_session(project_id)
    
    if session.status not in ['recording', 'paused']:
        raise HTTPException(400, f"当前状态为 {session.status}，无法停止")
    
    session.stop()
    
    # 获取项目信息（如果不存在，使用降级策略）
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    repo_path = None
    if project:
        repo_path = project.repo_path or f"workspace/repos/{project_id}"
        logger.info(f"[录制API] 使用项目repo_path: {repo_path}")
    else:
        logger.warning(f"[录制API] 项目不存在: {project_id}，使用降级策略")
        # 尝试从session文件目录推断
        repo_path = f"workspace/repos/{project_id}"
    
    # 分析覆盖率
    analyzer = CoverageAnalyzer()
    report = analyzer.analyze(session, repo_path)
    
    return {
        "message": "录制完成",
        "status": "completed",
        "report": report
    }


@router.get("/{project_id}/status")
async def get_recording_status(project_id: str):
    """获取录制状态"""
    session = _get_session(project_id)
    
    return {
        "status": session.status,
        "discovered_count": len(session.discovered_pages),
        "discovered_pages": list(session.discovered_pages.keys()),
        "duration": session.total_duration
    }


@router.post("/{project_id}/capture")
async def capture_page(project_id: str, url: str, db: AsyncSession = Depends(get_db)):
    """捕获页面DOM（录制时调用）"""
    session = _get_session(project_id)
    
    if session.status != 'recording':
        raise HTTPException(400, f"录制未开始，当前状态: {session.status}")
    
    # 获取项目信息
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(404, "项目不存在")
    
    # 构建完整URL
    if not url.startswith('http'):
        base_url = project.base_url.rstrip('/')
        url = f"{base_url}{url}"
    
    try:
        # 使用Playwright获取DOM
        mcp = PlaywrightMCPService(project_id=project_id, headless=True)
        dom_data = await mcp.analyze_page(url, timeout=30000)
        
        if not dom_data:
            raise HTTPException(500, "DOM获取失败，页面可能无法访问")
        
        # 添加到会话
        session.add_page(url, dom_data)
        
        return {
            "message": "页面已记录",
            "route_pattern": session._normalize_url(url),
            "total_discovered": len(session.discovered_pages)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[录制API] 捕获页面失败: {e}", exc_info=True)
        raise HTTPException(500, f"DOM捕获失败: {str(e)}")


@router.delete("/{project_id}/session")
async def clear_session(project_id: str):
    """清除录制会话"""
    if project_id in _sessions:
        _sessions[project_id].clear()
        del _sessions[project_id]
        return {"message": "会话已清除"}
    return {"message": "会话不存在"}
