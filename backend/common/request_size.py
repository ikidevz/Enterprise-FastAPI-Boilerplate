from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.responses import JSONResponse


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received

            message = await receive()

            if message["type"] == "http.request":
                body = message.get("body", b"")

                received += len(body)

                if received > self.max_body_size:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
                    await response(scope, receive, send)
                    return {
                        "type": "http.disconnect"
                    }

            return message

        await self.app(scope, limited_receive, send)
