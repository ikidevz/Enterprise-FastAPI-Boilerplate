from backend.common.lifespan import build_lifespan


class DummyRateLimiter:
    def reset(self) -> None:
        return None


def test_build_lifespan_uses_shared_startup_shutdown_flow():
    lifespan = build_lifespan(DummyRateLimiter())
    assert lifespan is not None
