from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.websocket import ws_manager
from app.models.database import init_db
from app.routers import project, testcase, generate, execute, settings as settings_router, page_tree, recording


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174", 
        "http://localhost:3000",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(project.router)
app.include_router(testcase.router)
app.include_router(generate.router)
app.include_router(execute.router)
app.include_router(settings_router.router)
app.include_router(page_tree.router)
app.include_router(recording.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.websocket("/ws/execution/{execution_id}")
async def ws_execution(websocket: WebSocket, execution_id: str):
    channel = f"execution:{execution_id}"
    await ws_manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, channel)


@app.websocket("/ws/mcp/{project_id}")
async def ws_mcp_log(websocket: WebSocket, project_id: str):
    """WebSocket端点：订阅MCP分析实时日志"""
    channel = f"mcp_{project_id}"
    print(f"[WS-CONNECT] Client connecting to channel: {channel}", flush=True)
    await ws_manager.connect(websocket, channel)
    print(f"[WS-CONNECT] Client connected. Active channels: {list(ws_manager.active_connections.keys())}", flush=True)
    try:
        # 保持连接，不需要等待消息
        while True:
            # 使用asyncio.sleep让出控制权，保持连接活跃
            import asyncio
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        print(f"[WS-CONNECT] Client disconnected from channel: {channel}", flush=True)
        ws_manager.disconnect(websocket, channel)
