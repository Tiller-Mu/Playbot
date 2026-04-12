"""MCP分析实时日志服务 - 通过WebSocket推送分析进度和日志"""
import logging
import json
import asyncio
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MCPLogService:
    """MCP分析日志服务 - 管理实时日志推送"""
    
    def __init__(self):
        # 日志缓冲，按project_id分组
        self.log_buffers: dict[str, list[dict]] = {}
        # 订阅者，按project_id分组
        self.subscribers: dict[str, list] = {}
    
    def start_session(self, project_id: str):
        """开始新的分析会话"""
        self.log_buffers[project_id] = []
        self._add_log(project_id, {
            "type": "session_start",
            "timestamp": datetime.now().isoformat(),
            "message": "开始MCP页面分析会话"
        })
    
    def end_session(self, project_id: str, success: bool = True):
        """结束分析会话"""
        self._add_log(project_id, {
            "type": "session_end",
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "message": "MCP分析会话结束" if success else "MCP分析会话失败"
        })
        # 保留最后一条日志一会儿，便于前端显示
        # 实际清理由调用方控制
    
    def _add_log(self, project_id: str, log_entry: dict):
        """添加日志条目"""
        if project_id not in self.log_buffers:
            self.log_buffers[project_id] = []
        self.log_buffers[project_id].append(log_entry)
    
    def log(self, project_id: str, level: str, message: str, data: Optional[dict] = None):
        """
        添加日志
        
        参数:
            project_id: 项目ID
            level: 日志级别 (info/success/warning/error/debug)
            message: 日志消息
            data: 额外数据
        """
        log_entry = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self._add_log(project_id, log_entry)
        logger.debug(f"[MCP-{level.upper()}] {message}")
    
    def log_step(self, project_id: str, step: int, total: int, message: str):
        """记录分析步骤"""
        log_entry = {
            "type": "step",
            "step": step,
            "total": total,
            "progress": f"{step}/{total}",
            "percentage": int((step / total) * 100) if total > 0 else 0,
            "timestamp": datetime.now().isoformat(),
            "message": message
        }
        self._add_log(project_id, log_entry)
    
    def log_llm_request(self, project_id: str, page_name: str, model: str):
        """记录LLM请求开始"""
        self._add_log(project_id, {
            "type": "llm_request",
            "action": "start",
            "page": page_name,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "message": f"正在调用 {model} 分析页面: {page_name}"
        })
    
    def log_llm_response(self, project_id: str, page_name: str, success: bool, 
                         components_count: int = 0, tokens_used: int = 0):
        """记录LLM响应"""
        self._add_log(project_id, {
            "type": "llm_response",
            "action": "complete" if success else "error",
            "page": page_name,
            "success": success,
            "components_count": components_count,
            "tokens_used": tokens_used,
            "timestamp": datetime.now().isoformat(),
            "message": f"✓ 页面分析完成，发现 {components_count} 个组件" if success else f"✗ 页面分析失败"
        })
    
    def log_page_discovered(self, project_id: str, route: str, components: list):
        """记录发现的页面"""
        self._add_log(project_id, {
            "type": "page_discovered",
            "route": route,
            "components": components,
            "components_count": len(components),
            "timestamp": datetime.now().isoformat(),
            "message": f"发现页面: {route} ({len(components)} 个组件)"
        })
    
    def log_error(self, project_id: str, error: str, details: Optional[str] = None):
        """记录错误"""
        self._add_log(project_id, {
            "type": "error",
            "error": error,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "message": f"✗ 错误: {error}"
        })
    
    def get_logs(self, project_id: str) -> list[dict]:
        """获取所有日志"""
        return self.log_buffers.get(project_id, [])
    
    def clear_logs(self, project_id: str):
        """清空日志缓存"""
        if project_id in self.log_buffers:
            self.log_buffers[project_id] = []
    
    def clear_session(self, project_id: str):
        """清空会话"""
        self.clear_logs(project_id)
        if project_id in self.subscribers:
            del self.subscribers[project_id]


# 全局单例
mcp_log_service = MCPLogService()
