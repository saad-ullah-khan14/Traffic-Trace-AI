"""In-process event bus for the live WebSocket feed.

Deliberately just a set of connected sockets and a broadcast function. The API
runs as a single uvicorn process by design, so there is nothing to coordinate
across — Redis or a real broker would be infrastructure with no second consumer.

Events are fire-and-forget: a browser that misses one is not re-sent it. The
dashboard reads durable state over REST and uses these only to know when to
update, so a dropped event costs a delayed refresh, not lost data.
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_clients: set[WebSocket] = set()


def subscribe(websocket: WebSocket) -> None:
    _clients.add(websocket)
    logger.info("ws client connected (%d total)", len(_clients))


def unsubscribe(websocket: WebSocket) -> None:
    _clients.discard(websocket)
    logger.info("ws client disconnected (%d left)", len(_clients))


def client_count() -> int:
    return len(_clients)


async def publish(event_type: str, data: dict[str, Any]) -> None:
    """Send one event to every connected client.

    Sends run concurrently: one phone on a weak link must not hold up the
    officer's dashboard. Anything that raises is dropped from the set — a
    half-closed socket would otherwise collect errors on every future event.
    """
    if not _clients:
        return

    message = {"type": event_type, "data": data}
    results = await asyncio.gather(
        *(client.send_json(message) for client in list(_clients)),
        return_exceptions=True,
    )

    for client, result in zip(list(_clients), results):
        if isinstance(result, Exception):
            unsubscribe(client)
