"""录制控制API - 支持开始/暂停/继续/停止录制，页面捕获，覆盖率分析"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from fastapi.responses import HTMLResponse
import re
import os

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
            
        # 开发者环境：启动全新录制前，强制清空之前的页面树数据（利用手工联级删除规避 SQLite FK Constraint）
        from sqlalchemy import delete
        from app.models.database import TestPage, TestCase, ExecutionDetail, ActionTrace
        
        # 1. 级联清理当前工程下所有测试用例的执行明细
        await db.execute(
            delete(ExecutionDetail).where(
                ExecutionDetail.test_case_id.in_(
                    select(TestCase.id).where(TestCase.project_id == project_id)
                )
            )
        )
        
        # 2. 清理当前工程下挂载的所有 TestCase
        await db.execute(delete(TestCase).where(TestCase.project_id == project_id))
        
        # 3. 清理当前工程下的所有录制轨迹 ActionTrace
        await db.execute(delete(ActionTrace).where(ActionTrace.project_id == project_id))
        
        # 3. 最后安全清空 TestPage 页面树
        await db.execute(delete(TestPage).where(TestPage.project_id == project_id))
        
        await db.commit()
        print(f"[录制路由] 已清空项目 {project_id} 下的历史页面树，保证测试数据纯净易分析。", flush=True)
        
        # 启动浏览器
        base_url = project.base_url
        print(f"[录制路由] 准备启动浏览器，项目: {project.name}, URL: {base_url}", flush=True)
        try:
            session.start(base_url=base_url)
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

    # 预先获取所有具有静态分析数据的页面（用于正则匹配）
    static_pages_result = await db.execute(
        select(TestPage).where(
            TestPage.project_id == project_id,
            TestPage.file_path != None
        )
    )
    all_static_pages = static_pages_result.scalars().all()

    # 同步录制到的页面到数据库 (即使是跨页也做扫描发现)
    action_history = getattr(session, 'action_history', [])
    unique_routes_dict = {}
    route_action_counts = {}
    for action in action_history:
        url = action.get('url', '')
        if url:
            route = getattr(session, '_normalize_url', lambda u: u)(url)
            if route not in unique_routes_dict:
                unique_routes_dict[route] = True
            route_action_counts[route] = route_action_counts.get(route, 0) + 1

    print(f"[录制API] 发现 {len(unique_routes_dict)} 个页面关联，正在同步页面节点...", flush=True)

    anchor_route = None
    if route_action_counts:
        # 按照产生的动作交互数量降序排序，选出最具代表性的页面作为主体节点
        anchor_route = sorted(route_action_counts.keys(), key=lambda r: route_action_counts[r], reverse=True)[0]

    # 先将 action_history 按 route 分组
    route_actions = {}
    if action_history:
        for action in action_history:
            url = action.get('url', '')
            if url:
                route = getattr(session, '_normalize_url', lambda u: u)(url)
                if route not in route_actions:
                    route_actions[route] = []
                route_actions[route].append(action)

    page_nodes = {}
    for route_pattern in unique_routes_dict.keys():
        # 提取当前路由的活跃组件，辅助匹配
        active_comps_for_route = set()
        for act in route_actions.get(route_pattern, []):
            if act.get('raw_data', {}).get('action') == 'active_components':
                active_comps_for_route.update(act.get('raw_data', {}).get('value', []))
                
        # 1. 寻找现有记录（精确匹配）
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
        
        # 2. 寻找具有源码路径的静态页面（动态路由正则匹配或组件名匹配）
        static_page = None
        for sp in all_static_pages:
            sp_path = sp.full_path
            if sp_path in search_patterns:
                static_page = sp
                break
            
            import re
            pattern = re.sub(r':[^/]+', r'[^/]+', sp_path)
            pattern = re.sub(r'\[[^/]+\]', r'[^/]+', pattern)
            if pattern != sp_path:
                regex = f"^{pattern}/?$"
                if re.match(regex, route_pattern):
                    static_page = sp
                    break
                    
        # 3. 增强匹配：如果正则也没匹配上，但该页面渲染的活跃组件名与某个静态页面名吻合，则认为是同一个页面
        if not static_page and active_comps_for_route:
            for sp in all_static_pages:
                if sp.name in active_comps_for_route:
                    static_page = sp
                    break

        page_node = None
        if existing_page:
            existing_page.is_captured = True
            page_node = existing_page
        elif static_page:
            # 核心修复：如果找到了对应的静态页面，直接挂载到该节点，而不是创建新页面
            static_page.is_captured = True
            page_node = static_page
        else:
            new_page = TestPage(
                project_id=project_id,
                name=route_pattern,
                path=route_pattern.split('/')[-1] or '/',
                full_path=route_pattern,
                is_leaf=True,
                is_captured=True,
                description=f"通过录制自动发现跨页用例关联的页面: {route_pattern}"
            )
            db.add(new_page)
            # Flush 之后获取 ID
            await db.flush()
            page_node = new_page
            
        page_nodes[route_pattern] = page_node
            
    # -- 核心变动：将行为归一化并分发到各个对应页面的 ActionTrace --
    if action_history:
        from app.services.action_normalizer import ActionNormalizer
        from app.models.semantic_ir import IntentPlan
        from app.models.database import ActionTrace
        from datetime import datetime
                
        for route_pattern, actions in route_actions.items():
            if route_pattern not in page_nodes:
                continue
                
            page_node = page_nodes[route_pattern]
            normalized_steps = ActionNormalizer.normalize(actions)
            
            # 提取活跃组件计算覆盖率
            active_comps = set()
            for act in actions:
                if act.get('raw_data', {}).get('action') == 'active_components':
                    active_comps.update(act.get('raw_data', {}).get('value', []))
                    
            # 核心修复：即使用户没有进行实质交互（normalized_steps为空），只要页面被渲染了（有活跃组件），也应该保存一条访问轨迹
            if not normalized_steps and not active_comps:
                continue
            
            # 计算漏测覆盖率
            imported_comps = []
            if page_node and page_node.imported_components:
                import json
                try: imported_comps = json.loads(page_node.imported_components)
                except: pass
            
            missed_comps = list(set(imported_comps) - active_comps)
            
            intent_plan = IntentPlan(
                intent=f"页面操作录制（自动归一化）",
                steps=normalized_steps,
                assertions=[],  # 留待下一阶段由 LLM 补全
                recorded_components=list(active_comps),
                missed_components=missed_comps
            )
            
            # 将结构化的 Semantic IR 转为 JSON 存入 ActionTrace 的 trace_data 字段
            semantic_json = intent_plan.model_dump_json(indent=2)
            
            new_trace = ActionTrace(
                project_id=project_id,
                page_id=page_node.id,

                title=f"录制轨迹 {datetime.now().strftime('%m-%d %H:%M')}",
                description=f"已由 Action Normalizer 转化为 Semantic IR。本页面操作覆盖了 {len(active_comps)} 个组件。",
                trace_data=semantic_json
            )
            db.add(new_trace)
            print(f"[录制API] 页面 {route_pattern} 已成功提取 {len(normalized_steps)} 步行为并存入独立的 ActionTrace 轨迹！发现遗漏组件: {missed_comps}", flush=True)

    await db.commit()
    
    repo_path = project.repo_path or f"workspace/repos/{project_id}"
    
    # 分析覆盖率
    analyzer = CoverageAnalyzer()
    report = analyzer.analyze(session, repo_path)
    
    # 清空会话历史，防止下次重启录制时堆积重复的历史数据
    session.action_history = []
    session.save()
    
    return {
        "message": "录制完成",
        "status": "completed",
        "report": report
    }



@router.get("/{project_id}/status")
async def get_recording_status(project_id: str):
    """获取录制状态"""
    session = _get_session(project_id)
    
    current_duration = session.total_duration
    if session.status == 'recording' and session.start_time:
        import time
        current_duration += (time.time() - session.start_time)
    
    action_history = getattr(session, 'action_history', [])
        
    return {
        "status": session.status,
        "action_count": len(action_history),
        "actions": action_history,
        "duration": current_duration
    }


@router.get("/{project_id}/pages/{page_id}/snapshot", response_class=HTMLResponse)
async def get_page_snapshot(project_id: str, page_id: str):
    """获取保存的原生页面DOM快照渲染"""
    snapshot_dir = f"workspace/snapshots/{project_id}"
    html_path = os.path.join(snapshot_dir, f"{page_id}.html")
    
    if not os.path.exists(html_path):
        return HTMLResponse(
            content=f"<html><body style='font-family:sans-serif;text-align:center;color:#999;margin-top:20%'>DOM 结构不存在或尚未生成，请确保页面已经被正常抓取并停止录制。</body></html>", 
            status_code=404
        )
        
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    # 改用 style 注入，因为 iframe 设置了 sandbox 会禁用 script
    inject_style = "<style>body { pointer-events: none !important; user-select: none !important; }</style>"
    if "</head>" in html_content:
        html_content = html_content.replace("</head>", f"{inject_style}</head>")
    elif "</body>" in html_content:
        html_content = html_content.replace("</body>", f"{inject_style}</body>")
    else:
        html_content += inject_style
        
    return HTMLResponse(content=html_content)


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
