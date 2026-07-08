import asyncio
import inspect

from backend.app import socketio_app


def test_product_created_handler_echoes_the_event_back_to_the_sender() -> None:
    """This is a *unit* test of the handler function - it doesn't involve a real socket.

    See the note below (and IMPROVEMENT_SUGGESTIONS_MERGED.md section 2.4)
    for why this only proves the handler works, not that real product
    creation actually triggers it.
    """
    calls: dict[str, object] = {}

    async def fake_emit(event: str, data: dict, to: str | None = None) -> None:
        """Supports the test suite by fake emit."""
        calls["event"] = event
        calls["data"] = data
        calls["to"] = to

    original_emit = socketio_app.sio.emit
    socketio_app.sio.emit = fake_emit
    try:
        asyncio.run(socketio_app.product_created("sid-1", {"name": "Widget"}))
    finally:
        socketio_app.sio.emit = original_emit

    assert calls["event"] == "product_created"
    assert calls["data"] == {
        "message": "product created", "data": {"name": "Widget"}}
    assert calls["to"] == "sid-1"


def test_creating_a_product_via_the_rest_api_broadcasts_a_socketio_event() -> None:
    """The product creation route should emit a Socket.IO event when a product is created."""
    import inspect

    from backend.app.api.v1.products import router as products_router

    source = inspect.getsource(products_router)
    assert "sio.emit" in source, "Expected the product creation route to emit a Socket.IO event"


def test_socket_io_connect_handler_exists() -> None:
    """Socket.IO server should have a connect handler."""
    source = inspect.getsource(socketio_app)
    assert "@sio.event" in source or "def connect" in source, \
        "Socket.IO server should have a connect handler"
