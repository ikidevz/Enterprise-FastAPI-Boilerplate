from typing import Any, Generic, TypeVar

from fastapi import APIRouter

T = TypeVar("T")


class BaseRouter(APIRouter, Generic[T]):
    """Simple base router that can be extended by feature routers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
