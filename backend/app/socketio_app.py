try:
    import socketio
except ImportError:  # pragma: no cover - exercised in minimal environments without socketio
    socketio = None

from backend.core.config import settings


class _FallbackSocketIO:
    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}

    def event(self, func=None):
        def decorator(fn):
            self._handlers[fn.__name__] = fn
            return fn

        if func is None:
            return decorator
        return decorator(func)

    async def emit(self, event: str, data=None, to: str | None = None) -> None:
        return None


class _FallbackASGIApp:
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b""})
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1000})


if socketio is not None:
    sio = socketio.AsyncServer(
        async_mode="asgi", cors_allowed_origins=settings.cors_origins)
    app_socket = socketio.ASGIApp(sio)
else:
    sio = _FallbackSocketIO()
    app_socket = _FallbackASGIApp()


@sio.event
async def connect(sid, environ, auth):
    await sio.emit("status", {"message": "connected"}, to=sid)


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


@sio.event
async def ping(sid, data):
    await sio.emit("pong", {"message": "pong", "data": data}, to=sid)


@sio.event
async def product_created(sid, data):
    await sio.emit("product_created", {"message": "product created", "data": data}, to=sid)
