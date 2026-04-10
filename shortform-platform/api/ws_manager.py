"""
WebSocket 연결 관리 - 작업 진행 상태를 실시간으로 클라이언트에 전송
"""

import json
from collections import defaultdict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # job_id -> [WebSocket, ...]
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self._connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str):
        self._connections[job_id].remove(websocket)

    async def send(self, job_id: str, event: str, data: dict):
        """특정 job의 모든 연결된 클라이언트에 이벤트 전송"""
        message = json.dumps({"event": event, "data": data})
        dead = []
        for ws in self._connections.get(job_id, []):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[job_id].remove(ws)


ws_manager = ConnectionManager()
