"""Live event feed. Mounted at /ws/live (outside /api, per the contract)."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import client_count, publish, subscribe, unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/live")
async def live(websocket: WebSocket) -> None:
    """One connection, all event types. The client filters by `type`.

    Nothing is expected from the client — the receive loop exists purely to
    notice a disconnect. Without it a closed browser tab would linger in the
    subscriber set until the next publish failed.
    """
    await websocket.accept()
    subscribe(websocket)

    try:
        await websocket.send_json(
            {"type": "connected", "data": {"clients": client_count()}}
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws connection error")
    finally:
        unsubscribe(websocket)


__all__ = ["router", "publish"]
