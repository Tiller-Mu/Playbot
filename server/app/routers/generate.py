from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import json
import logging

from app.models.database import Project, TestPage, get_db
from app.schemas.schemas import MCPGenerateRequest
from app.services.component_analyzer import analyze_components
from app.core.websocket import ws_manager
from app.services.mcp_log_service import mcp_log_service

router = APIRouter(prefix="/api/generate", tags=["generate"])
logger = logging.getLogger(__name__)


@router.post("/mcp/discover", response_model=dict)
async def mcp_discover_pages(data: MCPGenerateRequest, db: AsyncSession = Depends(get_db)):
    """
    MCP 页面嗅探 - 仅静态分析发现页面路由树
    
    流程：
    1. 静态分析发现组件和页面路由
    2. 将页面写入页面树（无LLM分析）
    3. 后续可点击单页进行LLM分析
    """
    print(f"[MCP-API] mcp_discover_pages 被调用, project_id={data.project_id}", flush=True)
    
    project = await db.get(Project, data.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.repo_path:
        raise HTTPException(400, "请先拉取项目代码")
    if not project.base_url:
        raise HTTPException(400, "请先配置项目 base_url")

    project_id = data.project_id
    
    async def send_log(level: str, message: str, log_data: dict = None):
        """异步发送WebSocket日志"""
        log_entry = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "data": log_data
        }
        print(f"[MCP-LOG] Broadcasting to mcp_{project_id}: {message[:50]}...", flush=True)
        await ws_manager.broadcast(log_entry, channel=f"mcp_{project_id}")
        mcp_log_service.log(project_id, level, message, log_data)

    try:
        # 清空旧的页面树数据
        await send_log("info", f"🗑️ 清空旧的页面数据...")
        from sqlalchemy import delete
        await db.execute(
            delete(TestPage).where(TestPage.project_id == data.project_id)
        )
        await db.commit()
        await send_log("info", f"✓ 旧数据已清空")
        
        # 开始会话
        await send_log("info", f"🚀 开始页面嗅探，项目: {project.name}")
        await send_log("info", f"📂 项目路径: {project.repo_path}")
        
        # Step 1: 静态组件分析
        await send_log("info", f"📊 Step 1/2: 开始静态组件分析...")
        components_info = await analyze_components(project.repo_path)
        
        component_count = len(components_info.get('components', []))
        page_count = len(components_info.get('page_components', []))
        common_count = len(components_info.get('common_components', []))
        
        await send_log("success", 
            f"✓ 静态分析完成: 共 {component_count} 个组件 "
            f"({page_count} 个页面组件, {common_count} 个普通组件)",
            {
                "framework": components_info.get('framework', '未知'),
                "entry_points": components_info.get('entry_points', [])
            }
        )

        # Step 2: 构建页面树并写入数据库
        await send_log("info", f"💾 Step 2/2: 构建页面树...")
        
        page_components = components_info.get('page_components', [])
        
        # 收集所有需要的文件夹路径
        folder_paths = set()  # {folder_path: folder_name}
        folder_name_map = {}  # folder_path -> folder_name
        
        for pc in page_components:
            route = pc.get('route', '')
            if route == '/':
                continue
            parts = route.strip('/').split('/')
            for i in range(len(parts) - 1):
                fp = '/' + '/'.join(parts[:i+1])
                folder_paths.add(fp)
                folder_name_map[fp] = parts[i]
        
        # 先flush页面节点获取ID，再创建文件夹，最后设置parent_id
        # 第一步：创建所有文件夹节点
        folder_id_map = {}  # folder_path -> id (str)
        
        for fp in sorted(folder_paths):  # 按路径排序，确保父文件夹先创建
            folder = TestPage(
                project_id=data.project_id,
                name=folder_name_map[fp],
                path=folder_name_map[fp],
                full_path=fp,
                is_leaf=False,
                component_name='[]',
                description=""
            )
            db.add(folder)
            await db.flush()  # flush获取ID
            folder_id_map[fp] = folder.id
            await send_log("info", f"📁 文件夹: {fp}")
        
        # 第二步：创建所有页面节点，直接设置parent_id
        created_pages = []
        
        for pc in page_components:
            route = pc.get('route', '')
            file_path = pc.get('file_path', '')
            
            # 页面名：优先用路由最后一段，避免多个index重复
            if route and route != '/':
                route_parts = route.strip('/').split('/')
                page_name = route_parts[-1] if route_parts[-1] != 'index' else (route_parts[-2] if len(route_parts) > 1 else 'index')
            else:
                page_name = pc.get('name', route)
            
            parts = route.strip('/').split('/') if route != '/' else ['']
            
            # 确定parent_id
            parent_id = None
            if len(parts) > 1:
                parent_path = '/' + '/'.join(parts[:-1])
                parent_id = folder_id_map.get(parent_path)
            
            # 存储组件信息和文件路径
            page_info = {
                'file_path': file_path,
            }
            test_page = TestPage(
                project_id=data.project_id,
                name=page_name,
                path=file_path or route,  # 存储实际文件路径
                full_path=route,
                is_leaf=True,
                parent_id=parent_id,
                component_name=json.dumps(page_info, ensure_ascii=False),
                description=""
            )
            db.add(test_page)
            await db.flush()  # flush获取ID
            created_pages.append(test_page)
            await send_log("info", f"📄 页面: {route}")
        
        # 第三步：设置文件夹的parent_id
        for fp, fid in folder_id_map.items():
            parts = fp.strip('/').split('/')
            if len(parts) > 1:
                parent_path = '/' + '/'.join(parts[:-1])
                parent_id = folder_id_map.get(parent_path)
                if parent_id:
                    # 用update语句直接更新，避免ORM关系加载
                    await db.execute(
                        TestPage.__table__.update()
                        .where(TestPage.id == fid)
                        .values(parent_id=parent_id)
                    )
        
        await db.commit()
        
        created_pages = list(created_pages)
        
        await send_log("success", f"✓ 页面嗅探完成: 发现 {len(created_pages)} 个页面")
        await send_log("info", f"💡 提示：点击页面树中的页面，可进行LLM详细分析")

        return {
            "message": f"成功发现 {len(created_pages)} 个页面",
            "page_count": len(created_pages),
            "component_count": component_count,
            "pages": [{
                "id": p.id,
                "route": p.full_path,
                "name": p.name
            } for p in created_pages]
        }

    except Exception as e:
        await db.rollback()
        await send_log("error", f"❌ 页面嗅探失败: {str(e)}")
        raise HTTPException(500, f"页面嗅探失败: {str(e)}")


@router.post("/mcp/analyze-page/{page_id}", response_model=dict)
async def analyze_single_page(page_id: str, db: AsyncSession = Depends(get_db)):
    """
    单页 LLM 分析
    
    对指定页面进行详细的 LLM 分析，提取功能描述、交互元素等
    """
    page = await db.get(TestPage, page_id)
    if not page:
        raise HTTPException(404, "页面不存在")
    
    project = await db.get(Project, page.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    
    project_id = page.project_id
    
    async def send_log(level: str, message: str, log_data: dict = None):
        """发送WebSocket日志"""
        log_entry = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "data": log_data
        }
        await ws_manager.broadcast(log_entry, channel=f"mcp_{project_id}")
        mcp_log_service.log(project_id, level, message, log_data)
    
    try:
        # 获取页面信息（包含file_path）
        page_info = json.loads(page.component_name) if page.component_name else {}
        file_path_str = page_info.get('file_path', '') if isinstance(page_info, dict) else ''
        
        # 尝试用path字段
        if not file_path_str:
            file_path_str = page.path if page.path else ''
        
        if not file_path_str:
            await send_log("error", f"❌ 页面缺少文件路径信息: {page.name}")
            raise HTTPException(400, "页面缺少文件路径信息，请重新嗅探")
        
        await send_log("info", f"🔍 开始分析页面: {page.name} ({page.full_path})")
        
        # 调用 LLM 分析
        from app.services.page_component_analyzer import PageComponentAnalyzer
        from app.services.component_analyzer import analyze_components
        
        # 获取组件列表（供LLM参考）
        components_info = await analyze_components(project.repo_path)
        components_list = components_info.get('components', [])
        
        # 创建带日志回调的分析器
        async def ws_log(level: str, message: str, data=None):
            log_entry = {
                "type": "log",
                "level": level,
                "message": message,
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "data": data
            }
            await ws_manager.broadcast(log_entry, channel=f"mcp_{project_id}")
            mcp_log_service.log(project_id, level, message, data)
        
        analyzer = PageComponentAnalyzer(
            repo_path=project.repo_path, 
            project_id=page.project_id,
            log_callback=ws_log
        )
        result = await analyzer.analyze_page(
            page_component={
                'name': page.name,
                'file_path': file_path_str,
                'type': 'page',
                'route': page.full_path
            },
            components_list=components_list
        )
        
        if result:
            # 更新页面信息
            page.description = result.get("description", "")
            await db.commit()
            
            await send_log("success", f"✓ 页面分析完成: {page.name} - {page.description[:50]}")
            
            return {
                "success": True,
                "page_id": page_id,
                "description": result.get("description", ""),
                "interactive_elements": result.get("interactive_elements", []),
                "modals": result.get("modals", []),
                "forms": result.get("forms", [])
            }
        else:
            await send_log("error", f"❌ 页面分析失败: {page.name}")
            raise HTTPException(500, "LLM 分析失败，无法解析结果")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"单页分析失败: {e}", exc_info=True)
        await send_log("error", f"❌ 分析失败: {str(e)}")
        raise HTTPException(500, f"分析失败: {str(e)}")


@router.get("/components/{project_id}", response_model=dict)
async def get_components(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取项目的组件列表
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.repo_path:
        raise HTTPException(400, "请先拉取项目代码")
    
    try:
        components_info = await analyze_components(project.repo_path)
        return components_info
    except Exception as e:
        logger.error(f"获取组件列表失败: {e}", exc_info=True)
        raise HTTPException(500, f"获取组件列表失败: {str(e)}")
