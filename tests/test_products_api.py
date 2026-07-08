from fastapi.testclient import TestClient

from conftest import auth_headers, login_user, register_user


def _auth_headers_for_user(client: TestClient, *, email: str, username: str, role: str = "user") -> dict[str, str]:
    """Supports the test suite by  auth headers for user."""
    register_user(client, email=email, username=username, role=role)
    token = login_user(client, email=email)
    return auth_headers(token)


def test_creating_a_product_returns_its_public_representation(client: TestClient) -> None:
    """Ensures creating a product returns its public representation."""
    headers = _auth_headers_for_user(
        client,
        email="product-owner@example.com",
        username="product-owner",
        role="admin",
    )
    response = client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Example Product", "price": 19.99,
              "description": "Demo product"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Example Product"
    assert body["price"] == 19.99


def test_product_catalog_can_be_listed_and_read_by_anyone(client: TestClient) -> None:
    """Reading the catalog is intentionally public - no token needed here on purpose."""
    headers = _auth_headers_for_user(
        client,
        email="public-read@example.com",
        username="public-read",
        role="admin",
    )
    create_response = client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Readable Product", "price": 9.99,
              "description": "public read"},
    )
    product_id = create_response.json()["id"]

    list_response = client.get("/api/v1/products/")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["meta"]["total"] >= 1
    assert any(p["id"] == product_id for p in payload["data"])

    read_response = client.get(f"/api/v1/products/{product_id}")
    assert read_response.status_code == 200
    assert read_response.json()["name"] == "Readable Product"


def test_reading_a_nonexistent_product_returns_404(client: TestClient) -> None:
    """Ensures reading a nonexistent product returns 404."""
    response = client.get("/api/v1/products/999999")

    assert response.status_code == 404


def test_duplicate_product_name_is_rejected(client: TestClient) -> None:
    """Ensures duplicate product name is rejected."""
    headers = _auth_headers_for_user(
        client,
        email="duplicate-product@example.com",
        username="duplicate-product",
        role="admin",
    )
    payload = {"name": "Duplicate Product",
               "price": 10.0, "description": "dup"}

    first = client.post("/api/v1/products/", headers=headers, json=payload)
    assert first.status_code == 201

    duplicate = client.post("/api/v1/products/", headers=headers, json=payload)
    assert duplicate.status_code in (400, 409)
    assert duplicate.json()["error_code"] == "duplicate_product"


def test_product_create_accepts_an_idempotency_key(client: TestClient) -> None:
    """A repeated create request with the same idempotency key should return the original response."""
    headers = _auth_headers_for_user(
        client,
        email="idempotency-product@example.com",
        username="idempotency-product",
        role="admin",
    )
    payload = {"name": "Idempotent Product",
               "price": 13.5, "description": "idem"}
    idem_headers = {**headers, "Idempotency-Key": "product-create-1"}

    first = client.post("/api/v1/products/",
                        headers=idem_headers, json=payload)
    second = client.post("/api/v1/products/",
                         headers=idem_headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()

    list_response = client.get(
        "/api/v1/products/", params={"search": "Idempotent Product"})
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1


def test_invalid_product_payload_is_rejected_with_422(client: TestClient) -> None:
    """Ensures invalid product payload is rejected with 422."""
    headers = _auth_headers_for_user(
        client,
        email="invalid-product@example.com",
        username="invalid-product",
        role="admin",
    )
    response = client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "", "price": -1, "description": "bad"},
    )

    assert response.status_code == 422


def test_product_search_filters_by_name(client: TestClient) -> None:
    """Ensures product search filters by name."""
    headers = _auth_headers_for_user(
        client,
        email="search-product@example.com",
        username="search-product",
        role="admin",
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Widget Alpha", "price": 10.0, "description": "alpha"},
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Widget Beta", "price": 12.0, "description": "beta"},
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Completely Unrelated",
              "price": 5.0, "description": "n/a"},
    )

    response = client.get("/api/v1/products/", params={"search": "widget"})

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["data"]}
    assert names == {"Widget Alpha", "Widget Beta"}


def test_product_listing_supports_pagination(client: TestClient) -> None:
    """Ensures product listing supports pagination."""
    headers = _auth_headers_for_user(
        client,
        email="pagination-product@example.com",
        username="pagination-product",
        role="admin",
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Page Item One", "price": 12.0, "description": "a"},
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Page Item Two", "price": 12.0, "description": "b"},
    )

    response = client.get(
        "/api/v1/products/", params={"search": "page item", "skip": 0, "limit": 1}
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_products_can_be_sorted_by_price_descending(client: TestClient) -> None:
    """Ensures products can be sorted by price descending."""
    headers = _auth_headers_for_user(
        client,
        email="sort-product@example.com",
        username="sort-product",
        role="admin",
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Cheap Product", "price": 5.0, "description": "cheap"},
    )
    client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Expensive Product",
              "price": 25.0, "description": "expensive"},
    )

    response = client.get(
        "/api/v1/products/", params={"sort": "price", "order": "desc", "limit": 10}
    )

    assert response.status_code == 200
    prices = [item["price"] for item in response.json()["data"]]
    assert prices == sorted(prices, reverse=True)


def test_updating_and_deleting_a_product(client: TestClient) -> None:
    """Ensures updating and deleting a product."""
    headers = _auth_headers_for_user(
        client,
        email="mutate-product@example.com",
        username="mutate-product",
        role="admin",
    )
    create_response = client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "Mutable Product", "price": 17.5,
              "description": "will change"},
    )
    product_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/products/{product_id}", headers=headers, json={"price": 24.99}
    )
    assert update_response.status_code == 200
    assert update_response.json()["price"] == 24.99

    delete_response = client.delete(
        f"/api/v1/products/{product_id}", headers=headers)
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/products/{product_id}")
    assert missing_response.status_code == 404


def test_creating_a_product_requires_authentication(client: TestClient) -> None:
    """Ensures creating a product requires authentication."""
    response = client.post(
        "/api/v1/products/",
        json={"name": "Should Require Auth", "price": 1.0, "description": "x"},
    )

    assert response.status_code == 401


def test_updating_a_product_requires_authentication(client: TestClient) -> None:
    """Ensures updating a product requires authentication."""
    create_response = client.post(
        "/api/v1/products/",
        headers=_auth_headers_for_user(
            client,
            email="protect-product@example.com",
            username="protect-product",
            role="admin",
        ),
        json={"name": "Protect Me", "price": 1.0, "description": "x"},
    )
    product_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/products/{product_id}", json={"price": 2.0})

    assert response.status_code == 401


def test_deleting_a_product_requires_authentication(client: TestClient) -> None:
    """Ensures deleting a product requires authentication."""
    create_response = client.post(
        "/api/v1/products/",
        headers=_auth_headers_for_user(
            client,
            email="delete-product@example.com",
            username="delete-product",
            role="admin",
        ),
        json={"name": "Delete Me If You Can",
              "price": 1.0, "description": "x"},
    )
    product_id = create_response.json()["id"]

    response = client.delete(f"/api/v1/products/{product_id}")

    assert response.status_code == 401
