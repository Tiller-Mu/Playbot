"""录制控制API - 支持开始/暂停/继续/停止录制，页面捕获，覆盖率分析"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.database import Project, TestPage, get_db
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


@router.api_route("/{project_id}/start", methods=["GET", "POST"])
async def start_recording(project_id: str, db: AsyncSession = Depends(get_db)):
    """开始/继续录制 - 支持GET/POST以便调试"""
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
        print(f"[录制路由] 准备启动浏览器，项目: {project.name}, URL: {base_url}", flush=True)
        try:
            session.start(base_url=base_url)
            session.launch_browser()
            print(f"[录制路由] 浏览器启动命令已发出", flush=True)
        except Exception as e:
            print(f"[录制路由] ❌ 启动失败: {str(e)}", flush=True)
            raise HTTPException(500, f"启动录制失败: {str(e)}")
        
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
    
    # 获取项目信息
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(404, "项目不存在")

    # 同步录制到的页面到数据库
    print(f"[录制API] 正在同步 {len(session.discovered_pages)} 个发现的页面到数据库...", flush=True)
    for route_pattern, page_data in session.discovered_pages.items():
        # 1. 寻找现有记录（包括带/不带斜杠的情况）
        existing_page = None
        search_patterns = [route_pattern]
        alt_pattern = route_pattern[:-1] if route_pattern.endswith('/') and len(route_pattern) > 1 else route_pattern + '/'
        search_patterns.append(alt_pattern)
        
        page_result = await db.execute(
            select(TestPage).where(
                TestPage.project_id == project_id,
                TestPage.full_path.in_(search_patterns)
            )
        )
        existing_page = page_result.scalar_one_or_none()
        
        # 2. 寻找具有源码路径的静态页面（供继承信息使用）
        static_page_result = await db.execute(
            select(TestPage).where(
                TestPage.project_id == project_id,
                TestPage.full_path.in_(search_patterns),
                TestPage.file_path != None
            )
        )
        static_page = static_page_result.scalar_one_or_none()

        if existing_page:
            # 状态更新
            existing_page.is_captured = True
            # 如果现有记录缺失关键信息，则从静态页面补全
            if static_page:
                if not existing_page.file_path:
                    existing_page.file_path = static_page.file_path
                if not existing_page.component_name:
                    existing_page.component_name = static_page.component_name
                if not existing_page.imported_components:
                    existing_page.imported_components = static_page.imported_components
            print(f"[录制API] 状态同步成功: {existing_page.full_path} (ID: {existing_page.id})", flush=True)
        else:
            # 仅当完全找不到记录时才创建新记录
            new_page = TestPage(
                project_id=project_id,
                name=route_pattern,
                path=route_pattern.split('/')[-1] or '/',
                full_path=route_pattern,
                is_leaf=True,
                is_captured=True,
                file_path=static_page.file_path if static_page else None,
                component_name=static_page.component_name if static_page else None,
                imported_components=static_page.imported_components if static_page else None,
                description=f"通过录制自动发现的页面: {route_pattern}"
            )
            db.add(new_page)
            print(f"[录制API] 创建新页面记录: {route_pattern}", flush=True)
    
    await db.commit()
    
    repo_path = project.repo_path or f"workspace/repos/{project_id}"
    
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
    
    # 动态计算实时时长
    current_duration = session.total_duration
    if session.status == 'recording' and session.start_time:
        import time
        current_duration += (time.time() - session.start_time)
    
    return {
        "status": session.status,
        "discovered_count": len(session.discovered_pages),
        "discovered_pages": list(session.discovered_pages.keys()),
        "duration": current_duration
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
