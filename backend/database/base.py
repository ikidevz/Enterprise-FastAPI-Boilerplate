from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _register_models() -> None:
    import backend.domain.users.model as user_models  # noqa: F401
    import backend.domain.api_keys.model as api_key_models  # noqa: F401
    import backend.domain.audit_log.model as audit_log_models  # noqa: F401
    import backend.domain.billing.models as billing_models  # noqa: F401
    import backend.domain.billing.webhook_models as billing_webhook_models  # noqa: F401
    import backend.domain.rbac.models as rbac_models  # noqa: F401
    import backend.domain.webhooks.model as webhook_models  # noqa: F401


_register_models()
