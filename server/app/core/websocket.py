"""WebSocket connection manager for real-time updates."""
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "default"):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str = "default"):
        if channel in self.active_connections:
            self.active_connections[channel] = [
                ws for ws in self.active_connections[channel] if ws != websocket
            ]

    async def broadcast(self, message: dict, channel: str = "default"):
        is_stream = message.get("level") == "stream"
        
        if channel not in self.active_connections:
            if not is_stream:
                print(f"[WS-BROADCAST] Channel '{channel}' not found, skipping. Active channels: {list(self.active_connections.keys())}", flush=True)
            return
            
        if not is_stream:
            print(f"[WS-BROADCAST] Broadcasting to '{channel}', connections: {len(self.active_connections[channel])}", flush=True)
            
        dead = []
        for ws in self.active_connections[channel]:
            try:
                await ws.send_json(message)
                if not is_stream:
                    print(f"[WS-BROADCAST] Sent to client: {str(message.get('message', ''))[:50]}...", flush=True)
            except Exception as e:
                print(f"[WS-BROADCAST] Send failed: {e}", flush=True)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)


ws_manager = ConnectionManager()
