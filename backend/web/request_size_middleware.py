from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.responses import JSONResponse

from backend.core.config import settings


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int):
        self.app = app
        self._max_body_size = max_body_size

    @property
    def max_body_size(self) -> int:
        return getattr(settings, "max_request_size_bytes", self._max_body_size)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # If the client declares a Content-Length larger than the configured
        # maximum, reject immediately rather than handing the request to the
        # app and waiting for body data to arrive.
        max_size = self.max_body_size
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    declared_length = int(value.decode("ascii"))
                except ValueError:
                    break
                if declared_length > max_size:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )

                    async def _empty_receive() -> Message:
                        return {"type": "http.request", "body": b"", "more_body": False}

                    await response(scope, _empty_receive, send)
                    return
                break

        received = 0

        class _BodyTooLarge(Exception):
            pass

        async def limited_receive() -> Message:
            nonlocal received

            message = await receive()

            if message["type"] == "http.request":
                body = message.get("body", b"")

                received += len(body)

                if received > max_size:
                    raise _BodyTooLarge()

            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            response = JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )

            async def _empty_receive() -> Message:
                return {"type": "http.request", "body": b"", "more_body": False}

            await response(scope, _empty_receive, send)
