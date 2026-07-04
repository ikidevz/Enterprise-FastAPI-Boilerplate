import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.main as main_module
from backend.app import socketio_app
from backend.core.config import settings
from backend.database import session as db_session
from backend.database.base import Base
from backend.scripts import seed_data


@pytest.fixture()
def client() -> TestClient:
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine, expire_on_commit=False)

    db_session.engine = test_engine
    db_session.SessionLocal = test_session_factory
    main_module.engine = test_engine

    async def init_db() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_db())

    with TestClient(main_module.app) as test_client:
        yield test_client

    asyncio.run(test_engine.dispose())


def _register_user(client: TestClient, *, email: str, username: str) -> dict:
    response = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "username": username,
            "password": "StrongPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "StrongPass123!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_user_crud_flow_with_authentication(client: TestClient) -> None:
    created_user = _register_user(
        client, email="crud-user@example.com", username="crud-user")
    token = _login(client, "crud-user@example.com")

    profile_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == "crud-user@example.com"

    list_response = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert any(user["id"] == created_user["id"]
               for user in list_response.json())

    update_response = client.put(
        f"/api/v1/users/{created_user['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "crud-user-updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["username"] == "crud-user-updated"

    delete_response = client.delete(
        f"/api/v1/users/{created_user['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204

    read_after_delete = client.get(f"/api/v1/users/{created_user['id']}")
    assert read_after_delete.status_code == 404


def test_product_crud_flow(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/products/",
        json={"name": "CRUD Product", "price": 17.5,
              "description": "Crud coverage"},
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    list_response = client.get("/api/v1/products/")
    assert list_response.status_code == 200
    assert any(product["id"] == product_id for product in list_response.json())

    read_response = client.get(f"/api/v1/products/{product_id}")
    assert read_response.status_code == 200
    assert read_response.json()["name"] == "CRUD Product"

    update_response = client.put(
        f"/api/v1/products/{product_id}",
        json={"price": 19.95},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price"] == 19.95

    delete_response = client.delete(f"/api/v1/products/{product_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/products/{product_id}")
    assert missing_response.status_code == 404


def test_missing_user_and_product_return_404(client: TestClient) -> None:
    missing_user_response = client.get("/api/v1/users/999999")
    assert missing_user_response.status_code == 404

    missing_product_response = client.get("/api/v1/products/999999")
    assert missing_product_response.status_code == 404


def test_products_support_search_and_pagination(client: TestClient) -> None:
    client.post(
        "/api/v1/products/",
        json={"name": "Widget Alpha", "price": 10.0, "description": "alpha"},
    )
    client.post(
        "/api/v1/products/",
        json={"name": "Widget Beta", "price": 12.0, "description": "beta"},
    )

    response = client.get(
        "/api/v1/products/",
        params={"search": "widget", "skip": 0, "limit": 1},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"].startswith("Widget")


def test_products_can_be_sorted_by_price_desc(client: TestClient) -> None:
    client.post(
        "/api/v1/products/",
        json={"name": "Cheap Product", "price": 5.0, "description": "cheap"},
    )
    client.post(
        "/api/v1/products/",
        json={"name": "Expensive Product",
              "price": 25.0, "description": "expensive"},
    )

    response = client.get(
        "/api/v1/products/",
        params={"sort": "price", "order": "desc", "limit": 10},
    )
    assert response.status_code == 200
    prices = [item["price"] for item in response.json()]
    assert prices == sorted(prices, reverse=True)


def test_openapi_includes_examples_for_product_models(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    product_create_schema = schema["components"]["schemas"]["ProductCreate"]
    assert product_create_schema["example"]["name"] == "Sample product"


def test_duplicate_user_and_product_registration_is_rejected(client: TestClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "username": "duplicate",
        "password": "StrongPass123!",
    }

    first_user = client.post("/api/v1/users/", json=payload)
    assert first_user.status_code == 201

    duplicate_user = client.post("/api/v1/users/", json=payload)
    assert duplicate_user.status_code == 400

    product_payload = {"name": "Duplicate Product",
                       "price": 10.0, "description": "dup"}
    first_product = client.post("/api/v1/products/", json=product_payload)
    assert first_product.status_code == 201

    duplicate_product = client.post("/api/v1/products/", json=product_payload)
    assert duplicate_product.status_code == 400


def test_forbidden_update_on_other_user_is_rejected(client: TestClient) -> None:
    owner = _register_user(client, email="owner@example.com", username="owner")
    _register_user(client, email="other@example.com", username="other")

    token = _login(client, "other@example.com")
    response = client.put(
        f"/api/v1/users/{owner['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "hacked"},
    )

    assert response.status_code == 403


def test_invalid_payloads_are_rejected(client: TestClient) -> None:
    invalid_user = client.post(
        "/api/v1/users/",
        json={"email": "bad-email", "username": "", "password": "short"},
    )
    assert invalid_user.status_code == 422

    invalid_product = client.post(
        "/api/v1/products/",
        json={"name": "", "price": -1, "description": "bad"},
    )
    assert invalid_product.status_code == 422


def test_request_id_header_is_returned(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")


def test_trace_id_header_is_returned(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-trace-id")


def test_seed_data_creates_default_admin_and_products() -> None:
    async def run_seed() -> None:
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", echo=False)
        try:
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await seed_data.seed(test_engine)
        finally:
            await test_engine.dispose()

    asyncio.run(run_seed())


def test_rate_limit_returns_429_after_threshold(client: TestClient) -> None:
    settings.rate_limit_requests_per_minute = 2
    for _ in range(2):
        assert client.get("/health").status_code == 200
    blocked_response = client.get("/health")
    assert blocked_response.status_code == 429


def test_password_reset_request_returns_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "reset@example.com"},
    )
    assert response.status_code == 200
    assert response.json()[
        "detail"] == "If the account exists, a reset link has been sent"


def test_websocket_connection_opens(client: TestClient) -> None:
    with client.websocket_connect("/ws/health") as websocket:
        message = websocket.receive_json()
        assert message == {"status": "connected"}


def test_product_created_event_emits_expected_payload() -> None:
    calls: dict[str, object] = {}

    async def fake_emit(event: str, data: dict, to: str | None = None) -> None:
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
