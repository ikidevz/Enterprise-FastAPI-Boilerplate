from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _register_models() -> None:
    import backend.domain.billing.models as billing_models  # noqa: F401
    import backend.domain.billing.webhook_models as billing_webhook_models  # noqa: F401
    import backend.domain.rbac.models as rbac_models  # noqa: F401


_register_models()
