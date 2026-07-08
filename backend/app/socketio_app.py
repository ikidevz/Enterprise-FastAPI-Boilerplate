import socketio
from jose import JWTError, jwt as jose_jwt

from backend.core.config import settings
from backend.core.security.token_store import TokenStore


_ws_revocation_store = TokenStore(prefix="tier4:revocations")

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins,
)

app_socket = socketio.ASGIApp(sio)


@sio.event
async def connect(sid, environ, auth):
    token = (auth or {}).get("token")
    if not token:
        return False

    try:
        payload = jose_jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError:
        return False

    jti = payload.get("jti")
    if not jti:
        return False

    if await _ws_revocation_store.is_revoked(str(jti)):
        return False

    await sio.save_session(sid, {"token": token})
    await sio.enter_room(sid, "authenticated")
    await sio.emit(
        "status",
        {"message": "connected"},
        to=sid,
    )


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


@sio.event
async def ping(sid, data):
    await sio.emit(
        "pong",
        {
            "message": "pong",
            "data": data,
        },
        to=sid,
    )


@sio.event
async def product_created(sid, data):
    await sio.emit(
        "product_created",
        {
            "message": "product created",
            "data": data,
        },
        to=sid,
    )
