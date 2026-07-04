from backend.application.users import RegisterUserUseCase
from backend.integrations.email_adapter import EmailIntegrationAdapter


def test_enterprise_architecture_components_are_importable() -> None:
    assert RegisterUserUseCase is not None
    assert EmailIntegrationAdapter is not None
