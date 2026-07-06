# Tier 4 Architecture — Documentation (Expanded)

This is an expanded, more detailed rewrite of the project's `DOCUMENTATION.md`. It keeps the original's structure and intent, but goes further in three ways:

1. **More depth** — a full endpoint reference table, a complete configuration/environment-variable reference, request-lifecycle detail down to the middleware/dependency level, and per-module "where things live" maps.
2. **Accuracy corrections** — the original documentation describes a few things that don't match the current source (wrong file paths, and a couple of features described as working that are not yet wired up). Each correction is called out explicitly in **Appendix A** so nothing is silently changed out from under you.
3. **A "known limitations" section** — an enterprise boilerplate that's going to be copy-pasted into real projects should document its current gaps as clearly as it documents its features, so this version adds that as first-class content instead of leaving it to a separate audit doc.

> This document describes the code **as it exists in the repository today**, not an idealized version of it. Where the code doesn't yet do what the name suggests, that's called out rather than glossed over.

---

## Table of contents

1. Architecture overview
2. Request lifecycle, in detail
3. Layer-by-layer guide (presentation / application / domain / infrastructure)
4. Full API endpoint reference
5. Configuration & environment variables reference
6. How to implement a new feature (step-by-step)
7. Runtime, observability, and operational endpoints
8. Persistence and data layer
9. Testing strategy
10. Deployment (Docker, Compose, CI)
11. Known limitations & security notes (read before deploying)
12. Core files to check when extending the project
13. Next-direction roadmap
14. Appendix A — corrections from the original documentation

---

## 1. Architecture overview

The project follows a layered, "four-tier" style architecture meant to separate concerns as the codebase grows: **presentation → application → domain → infrastructure**. The intent is that each layer has one job, so a change in one (e.g., swapping Postgres for another database, or REST for GraphQL) doesn't ripple through the others.

```
┌───────────────────────────────────────────────────────────────┐
│  Presentation  (backend/app)                                  │
│  FastAPI routers, Pydantic schemas, WebSocket/Socket.IO,      │
│  middleware, the app factory                                  │
└───────────────────────────┬───────────────────────────────────┘
                             │  calls
┌───────────────────────────▼───────────────────────────────────┐
│  Application  (backend/application)                           │
│  Use cases (RegisterUserUseCase, LoginUseCase, ...),          │
│  ports (interfaces for outbound integrations)                 │
└───────────────────────────┬───────────────────────────────────┘
                             │  calls
┌───────────────────────────▼───────────────────────────────────┐
│  Domain  (backend/domain)                                     │
│  Services (UserService, ProductService) — business rules,     │
│  Repositories — persistence access,                           │
│  Models — SQLAlchemy entities,                                │
│  Events — DomainEvent for meaningful state changes            │
└───────────────────────────┬───────────────────────────────────┘
                             │  uses
┌───────────────────────────▼────────────────────────────────────┐
│  Infrastructure  (backend/database, backend/infrastructure,    │
│  backend/utils, backend/integrations, backend/platform,        │
│  backend/services, backend/common)                             │
│  DB engine/session, Redis client, email transport, runtime     │
│  wiring, shared cross-cutting helpers (logging, rate limiting, │
│  auditing, tracing, exceptions)                                │
└────────────────────────────────────────────────────────────────┘
```

A request typically moves through the stack as follows:

1. **Middleware** (`backend/main.py`) assigns/propagates a request ID and trace ID, enforces rate limiting and max request size, and wraps the call in a trace span.
2. **The API router** (`backend/app/api/v1/...`) receives the request and its dependencies resolve (current user via JWT, DB session, service instances).
3. **The application layer** (a use case in `backend/application/<feature>/use_cases.py`) coordinates the workflow: validates business preconditions, calls the domain layer, and translates domain errors into a result.
4. **The domain layer** (`backend/domain/<feature>/service.py` + `repository.py`) applies business rules and persists/loads data. It emits a `DomainEvent` when something significant happens (currently: user registration).
5. **The infrastructure layer** underneath handles the actual DB/Redis/SMTP calls, plus cross-cutting concerns like audit logging and metrics.
6. **The response** is translated back into a Pydantic schema (`backend/common/schema.py`) and returned; the middleware attaches security headers and records metrics on the way out.

---

## 2. Request lifecycle, in detail

This section traces a single `POST /api/v1/products/` call all the way through, as a concrete example of how the layers connect.

1. **Uvicorn → FastAPI middleware stack.** `backend/app/bootstrap/middleware_registry.py` has already installed `CORSMiddleware`. `backend/main.py`'s `add_request_context` middleware then runs for every request:
   - Reads/generates `x-request-id` and `x-trace-id`.
   - Calls `bind_request_context(...)` (`backend/common/log.py`) so every log line for this request carries the request ID.
   - If `settings.enable_rate_limiting` is on, checks `shared_rate_limiter.allow_request(...)` (`backend/common/rate_limit.py`) and short-circuits with `429` if the caller has exceeded `rate_limit_requests_per_minute`.
   - Checks `Content-Length` against `settings.max_request_size_bytes` and short-circuits with `413` if too large.
   - Wraps the actual route call in `trace_span("http.request", ...)` (`backend/common/opentelemetry.py`).
2. **Routing.** `backend/app/bootstrap/router_registry.py` mounted `backend/app/api/v1/router.py` at `settings.api_v1_str` (default `/api/v1`), which in turn includes `backend/app/api/v1/products/router.py`'s `create_product` handler for this path.
3. **Dependency resolution.** FastAPI resolves `db: AsyncSession = Depends(get_db)` (`backend/database/session.py`), opening an `AsyncSession` that will be committed/rolled back automatically at the end of the request.
4. **Application layer.** The handler builds `ProductService(ProductRepository(db))` and calls `CreateProductUseCase(service).execute(payload=payload)` (`backend/application/products/use_cases.py`), which validates uniqueness rules and calls into the domain service.
5. **Domain layer.** `ProductService.create(...)` (`backend/domain/products/service.py`) constructs the `Product` SQLAlchemy model, adds it to the session, flushes, and refreshes it to get the generated `id`.
6. **Response translation.** The router converts the returned `Product` into `ProductOut` (`backend/common/schema.py`) via `response_model=ProductOut`.
7. **Audit + metrics on the way out.** The router calls `audit_logger.log(...)` (`backend/common/audit.py`); back in the middleware, `record_request_metrics(...)` (`backend/common/observability.py`) records the method/path/status, and security headers (`x-content-type-options`, `x-frame-options`, `referrer-policy`, and — if `require_https` — `strict-transport-security`) are attached to the response.
8. **Session teardown.** `get_db()`'s `finally` block closes the session; if an exception propagated, it's rolled back first.

The same shape applies to every feature — only steps 4–5 change per domain.

---

## 3. Layer-by-layer guide

### 3.1 Presentation layer — `backend/app`

Responsible for the HTTP/WebSocket surface of the app.

| Concern                                                                     | Where                                                                            |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| App factory (`create_app()`)                                                | `backend/app/factory.py`                                                         |
| Middleware registration (CORS)                                              | `backend/app/bootstrap/middleware_registry.py`                                   |
| Router registration                                                         | `backend/app/bootstrap/router_registry.py`                                       |
| Static file mount for uploads (`/static/uploads`)                           | `backend/app/bootstrap/static_registry.py`                                       |
| Infrastructure wiring hook-up for the factory                               | `backend/app/infrastructure.py` (re-exports `backend/infrastructure/runtime.py`) |
| Top-level router aggregation                                                | `backend/app/api/v1/router.py`                                                   |
| Feature routers                                                             | `backend/app/api/v1/{auth,users,products,uploads,admin}/router.py`               |
| Socket.IO server & handlers                                                 | `backend/app/socketio_app.py`                                                    |
| App entrypoint: middleware, `/health`, `/metrics`, `/runtime`, `/ws/health` | `backend/main.py`                                                                |

### 3.2 Application layer — `backend/application`

Where business workflows become explicit, orchestrated units instead of logic embedded in route handlers.

| Concern                                                                     | Where                                                                                        |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| User registration & update workflows                                        | `backend/application/users/use_cases.py` (`RegisterUserUseCase`, `UpdateUserUseCase`)        |
| Auth workflows (login, refresh, logout, password reset, email verification) | `backend/application/auth/use_cases.py`                                                      |
| Product create/update workflows                                             | `backend/application/products/use_cases.py` (`CreateProductUseCase`, `UpdateProductUseCase`) |
| Outbound integration interfaces ("ports")                                   | `backend/application/ports.py` (`NotificationPort`)                                          |
| Shared application-level runtime handles                                    | `backend/application/services.py` (`ApplicationServices`)                                    |

Each use case takes the domain service(s) it needs as constructor arguments, does precondition checks (e.g., "does this email already exist?"), delegates the actual state change to the domain layer, and returns a result the router can translate into a response — keeping routers limited to request parsing, calling the use case, and formatting the response/errors.

### 3.3 Domain layer — `backend/domain`

The business-rule core of the system.

| Concern                                                      | Where                                                                 |
| ------------------------------------------------------------ | --------------------------------------------------------------------- |
| User entity                                                  | `backend/domain/users/model.py`                                       |
| User business rules (hashing, auth, lockout, token issuance) | `backend/domain/users/service.py`                                     |
| User persistence                                             | `backend/domain/users/repository.py`                                  |
| Product entity                                               | `backend/domain/products/model.py`                                    |
| Product business rules                                       | `backend/domain/products/service.py`                                  |
| Product persistence (search/sort/filter)                     | `backend/domain/products/repository.py`                               |
| Domain events                                                | `backend/domain/events/__init__.py` (`DomainEvent`)                   |
| Shared generic repository/service base classes               | `backend/common/base_repository.py`, `backend/common/base_service.py` |

### 3.4 Infrastructure layer

Everything that talks to the outside world, or wires the app together at startup/shutdown.

| Concern                                                           | Where                                                                                         |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Async SQLAlchemy engine/session                                   | `backend/database/session.py`, re-exported by `backend/infrastructure/persistence/session.py` |
| Declarative base                                                  | `backend/database/base.py`                                                                    |
| Redis client                                                      | `backend/utils/redis_client.py`                                                               |
| Email transport (console/SMTP)                                    | `backend/common/email.py`, adapted by `backend/integrations/email_adapter.py`                 |
| Startup/shutdown wiring onto `app.state`                          | `backend/infrastructure/runtime.py` (`build_infrastructure_registry`)                         |
| Generic hook registry used by the above                           | `backend/common/bootstrap.py` (`BootstrapRegistry`)                                           |
| App lifespan (DB table creation, background jobs, registry hooks) | `backend/common/lifespan.py`                                                                  |
| Background job queue                                              | `backend/common/background_jobs.py`                                                           |
| Rate limiting                                                     | `backend/common/rate_limit.py`                                                                |
| Request-scoped logging context                                    | `backend/common/log.py`                                                                       |
| Metrics collection                                                | `backend/common/observability.py`, `backend/common/exporters.py`                              |
| Tracing/spans                                                     | `backend/common/opentelemetry.py` (the one actually wired into `main.py`)                     |
| Audit trail                                                       | `backend/common/audit.py`                                                                     |
| Auth/JWT dependency, current-user resolution                      | `backend/common/dependencies.py`                                                              |
| Role/permission checks                                            | `backend/common/rbac.py`, `backend/common/permissions.py`                                     |
| Token issuance/rotation/revocation storage                        | `backend/common/token_store.py`                                                               |
| Config/settings                                                   | `backend/core/config.py`                                                                      |
| Shared exception hierarchy + HTTP translation                     | `backend/common/exceptions.py`                                                                |
| Runtime/operational snapshot facade                               | `backend/platform/runtime.py` (`PlatformRuntime`, backs the `/runtime` route)                 |
| API-facing "contract" mirror types                                | `backend/contracts/`                                                                          |

---

## 4. Full API endpoint reference

All routes below are mounted under the `settings.api_v1_str` prefix, default `/api/v1`, except `/health`, `/metrics`, `/runtime`, `/ws/health`, and `/health/ready`, which are mounted at the app root.

| Method    | Path                                      | Auth required today?                             | Description                                                                                                     |
| --------- | ----------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| POST      | `/api/v1/users/`                          | No (public registration)                         | Create a new user account.                                                                                      |
| GET       | `/api/v1/users/me`                        | Yes                                              | Get the current authenticated user's profile.                                                                   |
| GET       | `/api/v1/users/{user_id}`                 | **No** ⚠️                                        | Get any user's profile by id.                                                                                   |
| GET       | `/api/v1/users/`                          | Yes (admin only)                                 | List all users.                                                                                                 |
| PUT       | `/api/v1/users/{user_id}`                 | Yes                                              | Update a user; non-superusers cannot change `is_superuser`, `is_active`, `role`, or `permissions`.              |
| DELETE    | `/api/v1/users/{user_id}`                 | **No** ⚠️                                        | Delete a user by id.                                                                                            |
| POST      | `/api/v1/auth/login`                      | No (this _is_ the login)                         | OAuth2 password-flow login; returns access + refresh tokens.                                                    |
| POST      | `/api/v1/auth/refresh`                    | No (bearer of a valid refresh token)             | Rotates a refresh token for a new access/refresh pair.                                                          |
| POST      | `/api/v1/auth/logout`                     | No (bearer of a valid refresh token)             | Revokes a refresh token.                                                                                        |
| POST      | `/api/v1/auth/email-verification/request` | No                                               | Requests an email-verification token be sent.                                                                   |
| POST      | `/api/v1/auth/email-verification/confirm` | No (bearer of the token)                         | Confirms email verification.                                                                                    |
| POST      | `/api/v1/auth/password-reset/request`     | No                                               | Requests a password-reset token be sent.                                                                        |
| POST      | `/api/v1/auth/password-reset/confirm`     | No (bearer of the token)                         | Confirms a password reset with a new password.                                                                  |
| GET       | `/api/v1/auth/me`                         | Yes                                              | Alias of `/users/me`, returns the current user.                                                                 |
| POST      | `/api/v1/products/`                       | Yes (admin/staff only)                           | Create a product.                                                                                               |
| GET       | `/api/v1/products/`                       | No (public catalog browsing — by design)         | List products; supports `search`, `skip`, `limit`, `sort`, `order`.                                             |
| GET       | `/api/v1/products/{product_id}`           | No (public)                                      | Get a single product.                                                                                           |
| PUT       | `/api/v1/products/{product_id}`           | Yes (admin/staff only)                           | Update a product.                                                                                               |
| DELETE    | `/api/v1/products/{product_id}`           | Yes (admin/staff only)                           | Delete a product.                                                                                               |
| POST      | `/api/v1/uploads/`                        | Yes                                              | Upload a file (multipart). Stored under the configured upload dir, served back from `/static/uploads`.          |
| GET       | `/api/v1/admin/users`                     | Yes (`require_role("admin")`, see ⚠️ note below) | List users via the admin surface.                                                                               |
| GET       | `/api/v1/admin/permissions`               | Yes                                              | Example endpoint demonstrating the `PermissionPolicy` evaluation flow.                                          |
| GET       | `/health`                                 | No                                               | Liveness probe: status, environment, version.                                                                   |
| GET       | `/health/ready`                           | No                                               | Readiness probe: pings the DB and Redis.                                                                        |
| GET       | `/metrics`                                | No                                               | In-process request-count/status-code/method/path metrics snapshot.                                              |
| GET       | `/runtime`                                | No                                               | Operational snapshot (uptime, metrics) via `PlatformRuntime`.                                                   |
| WS        | `/ws/health`                              | No                                               | Trivial WebSocket that accepts, sends `{"status": "connected"}`, and closes.                                    |
| Socket.IO | `/socket.io`                              | No                                               | Socket.IO server; handles `connect`, `disconnect`, `ping`, and authenticated `product_created` broadcasts. |

**⚠️ marked rows** are endpoints that are intentionally public or have a narrower auth contract than the rest of the system. Current examples are the public product catalog and the public registration route. The user-listing and product-write routes now require authenticated admin/staff access, so they are no longer marked as public.

The `require_role("admin")` dependency on `/api/v1/admin/users` checks `current_user.role` against the given role names and is wired into the current router implementation.

---

## 5. Configuration & environment variables reference

All settings are defined in `backend/core/config.py` (`Settings`, loaded via `pydantic-settings`), sourced from (in order of precedence) `ENV_FILE` if set, then `.env`, `.env.<environment>`, `.env.<environment>.local`, `.env.local`, then real process environment variables, then field defaults.

| Variable                                                                    | Default                                                       | Purpose                                                                                                           |
| --------------------------------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `project_name`                                                              | `Tier 4 Architecture`                                         | OpenAPI title.                                                                                                    |
| `api_v1_str`                                                                | `/api/v1`                                                     | Prefix for all v1 routes.                                                                                         |
| `environment` / `APP_ENV`                                                   | `dev`                                                         | One of `dev`, `staging`, `prod`.                                                                                  |
| `DATABASE_URL`                                                              | `postgresql+asyncpg://postgres:postgres@localhost:5432/tier4` | Async SQLAlchemy connection string.                                                                               |
| `DATABASE_URL_FILE`                                                         | —                                                             | Path to a file containing the DB URL (for secret-mount deployments); overrides `DATABASE_URL` if the file exists. |
| `REDIS_URL`                                                                 | `redis://localhost:6379/0`                                    | Redis connection string.                                                                                          |
| `REDIS_URL_FILE`                                                            | —                                                             | File-based override, same pattern as above.                                                                       |
| `SECRET_KEY`                                                                | `change-me-in-production`                                     | JWT signing secret. **Must be overridden outside of local dev.**                                                  |
| `SECRET_KEY_FILE`                                                           | —                                                             | File-based override.                                                                                              |
| `algorithm`                                                                 | `HS256`                                                       | JWT signing algorithm.                                                                                            |
| `access_token_expire_minutes`                                               | `1440` (24h)                                                  | Access token lifetime.                                                                                            |
| `CORS_ORIGINS`                                                              | `["http://localhost:3000", "http://localhost:5173"]`          | Comma-separated or JSON-array list of allowed origins.                                                            |
| `enable_rate_limiting`                                                      | `true`                                                        | Toggles the in-memory rate limiter middleware.                                                                    |
| `rate_limit_requests_per_minute`                                            | `120`                                                         | Requests/minute/client-path before a `429`.                                                                       |
| `request_id_header`                                                         | `x-request-id`                                                | Header name used for request correlation.                                                                         |
| `max_request_size_bytes`                                                    | `2097152` (2MB)                                               | Rejects requests with a larger `Content-Length`.                                                                  |
| `upload_dir`                                                                | `./uploads`                                                   | Where uploaded files are written.                                                                                 |
| `password_reset_token_ttl_minutes`                                          | `15`                                                          | Password-reset token lifetime.                                                                                    |
| `EMAIL_BACKEND`                                                             | `console`                                                     | `console` (prints) or `smtp` (real send).                                                                         |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD`               | — / `587` / — / —                                             | SMTP transport settings, used only when `EMAIL_BACKEND=smtp`.                                                     |
| `SMTP_USE_TLS` / `SMTP_USE_SSL`                                             | `true` / `false`                                              | STARTTLS vs. implicit TLS.                                                                                        |
| `SMTP_FROM_EMAIL`                                                           | `no-reply@example.com`                                        | From-address for outbound email.                                                                                  |
| `default_admin_email` / `default_admin_username` / `default_admin_password` | `admin@example.com` / `admin` / `Admin123!`                   | Used by `backend/scripts/seed_data.py` to bootstrap an admin account. **Must be changed outside of local dev.**   |
| `require_https`                                                             | `false`                                                       | When true, adds `Strict-Transport-Security` to responses.                                                         |
| `enable_tracing`                                                            | `true`                                                        | Master toggle read by the tracing module.                                                                         |
| `OTEL_MODE`                                                                 | `basic`                                                       | Tracing mode flag (see §11 for what this does today vs. its name).                                                |
| `OTEL_EXPORTER_OTLP_ENDPOINT`                                               | —                                                             | Configured but not currently used to export real OTLP spans (see §11).                                            |
| `OTEL_SERVICE_NAME`                                                         | `tier4`                                                       | Service name tag attached to trace log lines.                                                                     |

---

## 6. How to implement a new feature (step-by-step)

Every new feature should follow the same layered pattern so the app stays predictable and testable.

1. **Domain model.** Add the entity under `backend/domain/<feature>/model.py`. Keep it focused on the business concept — no HTTP/infrastructure concerns.
2. **Persistence.** Add `backend/domain/<feature>/repository.py`, inheriting `BaseRepository` for the common `get_by_id`/`list`/`count` operations, and add feature-specific queries (filters, search, sort) alongside them.
3. **Domain service.** Add `backend/domain/<feature>/service.py` for the actual business rules — validation, state transitions, anything that must always hold true regardless of which caller triggers it.
4. **Application use case(s).** Add `backend/application/<feature>/use_cases.py` for the orchestration: precondition checks that need to look across services (e.g., "does this email already exist"), calling the domain service, and returning a result. This is what keeps route handlers thin.
5. **Ports (only if there's an outbound integration).** If the workflow needs to call an external system (email, SMS, a third-party API), define a small `Protocol` in `backend/application/ports.py` describing only the methods the use case needs, and implement it under `backend/integrations/<integration>_adapter.py`. Keep the adapter the only place that imports the third-party SDK.
6. **Domain events (optional).** If the workflow represents a meaningful business change other parts of the system might care about later (analytics, notifications, audit), emit a `DomainEvent.create({...})` (`backend/domain/events/__init__.py`) from the use case.
7. **Schemas.** Define request/response models in `backend/common/schema.py` (or a feature-local file if it's getting large). Be deliberate about which fields are client-writable — see §11.2 for why this matters.
8. **Router.** Add `backend/app/api/v1/<feature>/router.py`. Keep it to: parse the request, resolve dependencies (DB session, current user, service), call the use case, translate the result/errors into a response. Decide explicitly whether each route needs `Depends(get_current_active_user)` and/or `Depends(require_role(...))` — don't rely on "the other routes in this file have it so this one probably does too."
9. **Register the router** in `backend/app/api/v1/router.py`.
10. **Tests.** Add both a unit test for the use case/service logic and an integration test (via `TestClient`) that exercises the real route, including a negative case for missing auth if the route is protected.

---

## 7. Runtime, observability, and operational endpoints

- `GET /health` — returns `{status, environment, version}`. Suitable for a liveness probe.
- `GET /health/ready` — pings the DB (`SELECT 1`) and Redis (`PING`); returns `ready` if both succeed, `degraded` otherwise. Suitable for a readiness probe.
- `GET /metrics` — returns an in-process snapshot of request counts, status codes, methods, and paths, collected by `backend/common/observability.py`'s `MetricsCollector`. This is process-local, in-memory, and resets on restart — it is not a Prometheus-scrape-compatible endpoint (no `text/plain` exposition format) and does not aggregate across multiple workers/pods.
- `GET /runtime` — returns an operational snapshot (service name, environment, uptime, the same metrics snapshot) via `backend/platform/runtime.py`'s `PlatformRuntime`.
- Every response carries `x-request-id`, `x-trace-id`, `x-content-type-options: nosniff`, `x-frame-options: DENY`, and `referrer-policy: strict-origin-when-cross-origin`; if `require_https` is enabled, also `strict-transport-security`.
- Tracing: `backend/common/opentelemetry.py`'s `trace_span` context manager wraps the whole HTTP request in `main.py`, and several individual routes (`auth.login`, `product.create`, `upload.create`) wrap their own operation in a span too. Today this only produces structured log lines (see §11 for the gap between this and a real OpenTelemetry exporter pipeline).

---

## 8. Persistence and data layer

- Async SQLAlchemy engine/session setup lives in `backend/database/session.py`; `backend/infrastructure/persistence/session.py` re-exports the same objects for infrastructure-layer imports.
- `Base` (SQLAlchemy `DeclarativeBase`) is shared across all models, defined in `backend/database/base.py`.
- Repositories inherit `BaseRepository` (`backend/common/base_repository.py`) for `get_by_id`, `list`, `create`, `update`, `delete`, `count` — though note that `UserService`/`ProductService` currently implement their own create/update logic directly rather than calling the base repository's, for reasons tied to the extra fields they need to set (hashed passwords, timestamps).
- Migrations: `alembic/versions/20260704_initial_schema.py` is the initial migration, creating the `users` and `products` tables. Whenever you add or change a model, generate/hand-write a matching migration — the app's `lifespan` will also call `Base.metadata.create_all` at startup as a convenience for local development, but that is not a substitute for migrations in any shared environment.
- `backend/scripts/seed_data.py` creates a default admin account (from the `default_admin_*` settings) and two sample products, if they don't already exist. Intended for local development only.

---

## 9. Testing strategy

Run the whole suite with:

```bash
python -m pytest -q
```

The test files, and what each is actually checking:

| File                                           | What it covers                                                                                                                                                      |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_authentication.py`                 | Registration, login, lockout, refresh token rotation, and logout flows.                                                                                             |
| `tests/test_authorization_and_roles.py`        | `AuthorizationPolicy` checks, admin endpoints, and role/permission behavior.                                                                                        |
| `tests/test_users_api.py`                      | User CRUD and access-control expectations.                                                                                                                          |
| `tests/test_products_api.py`                   | Product CRUD, validation, duplicates, and the recent auth requirement on writes.                                                                                    |
| `tests/test_uploads.py`                        | Upload auth, filename handling, and storage-path behavior.                                                                                                          |
| `tests/test_realtime.py`                       | Socket.IO interaction and realtime event handling.                                                                                                                  |
| `tests/test_background_jobs_and_resilience.py` | Background-job processing, resilience helpers, and tracing/metrics primitives.                                                                                      |
| `tests/test_email_delivery.py`                 | Console/SMTP email transport selection and message formatting.                                                                                                      |
| `tests/test_bootstrap_and_infrastructure.py`   | App factory/lifespan/bootstrap wiring and registry hooks.                                                                                                           |
| `tests/test_seed_data.py`                      | Seed-data script behavior.                                                                                                                                          |
| `tests/test_health_and_runtime.py`             | `/health`, `/health/ready`, `/metrics`, `/runtime`, security headers, trace/request IDs, and the middleware branches for rate limiting and request-size protection. |
| `tests/test_config.py`                         | Settings/env-profile parsing and configuration behavior.                                                                                                            |

The suite spins up an in-memory SQLite database and uses FastAPI's `TestClient`, keeping the tests fast while still exercising real route → use case → service → repository paths.

---

## 10. Deployment

- **Dockerfile**: multi-stage-free, single `python:3.12-slim` build; installs `requirements.txt`, copies the app, creates a dedicated non-root `app` user (`addgroup`/`adduser --system`), runs as that user, and defines a `HEALTHCHECK` that curls `/health`. Entrypoint is `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
- **docker-compose.yml**: brings up the API alongside `postgres:16-alpine` and `redis:7-alpine` for local/integration use; the Postgres credentials in the compose file (`postgres`/`postgres`) are for local development only and should never be reused as-is anywhere else.
- **CI** (`.github/workflows/ci.yml`): on push/PR to `main`/`master`, installs the project with `pip install -e .[dev]`, runs `ruff check backend tests`, then `python -m pytest -q`.
- **Environment files**: `deployment/env/{dev,staging,prod}.env` hold environment-specific defaults; production secrets (DB URL, Redis URL, JWT secret) should be supplied via the `*_FILE` settings (pointing at a mounted secret file) rather than committed to any `.env`.
- **scripts/security_scan.sh**: a helper script present in the repo for running a security scan pass; see the script itself for what it currently checks, and run it as part of your pre-deploy checklist.

---

## 11. Known limitations & security notes (read before deploying)

This project is a boilerplate, and boilerplates get copy-pasted wholesale into real products more often than they get read line-by-line first. The items below are the ones most likely to bite if that happens, listed so they're documented as clearly as the features are.

### 11.1 Public surface is intentionally limited

The current baseline now keeps the public surface narrow: user registration and the product catalog read endpoints are intentionally public, while product creation/update/delete and file uploads require an authenticated user. Before deploying anything derived from this boilerplate, review the route-specific access rules and keep any new public endpoints deliberate rather than accidental.

### 11.2 Public registration schema and role/permission fields

`UserCreate` historically has included `role`/`permissions` fields that are then persisted verbatim by `UserService.create()`. If your copy of this schema still includes those fields on the _public_ registration endpoint, treat that as something to separate into an admin-only path before shipping — a self-registration endpoint should never let the caller choose their own privilege level.

### 11.3 File uploads and filenames

`POST /api/v1/uploads/` writes to `UPLOAD_DIR / file.filename` using the client-supplied filename directly. Sanitize this (strip directory components, or better, generate a server-side name) before trusting this endpoint with untrusted clients.

### 11.4 Tracing and metrics are lightweight by design, not full observability stacks

- `backend/common/opentelemetry.py`'s `OpenTelemetryBridge` is a small internal abstraction that logs span start/end lines gated by `OTEL_MODE`/`ENABLE_TRACING` — it does not currently instantiate the real `opentelemetry` SDK or export to `OTEL_EXPORTER_OTLP_ENDPOINT`, even though that setting exists and the `opentelemetry-*` packages are dependencies. If you need real distributed tracing (e.g., to view traces in Jaeger/Tempo/a vendor backend), wire up the actual SDK rather than assuming this module already does it.
- `GET /metrics` and `GET /runtime` reflect **process-local** in-memory counters. They reset on restart and don't aggregate across multiple workers or replicas. For real production metrics, back this with Prometheus client library counters (or push to your metrics backend) instead of/in addition to the current `MetricsCollector`.
- There is a second tracing helper, `backend/common/tracing.py`, defined alongside `opentelemetry.py`. Only one of the two is actually imported by `main.py`'s top-level middleware span; check which one your feature routers import before assuming spans nest the way the code visually suggests.

### 11.5 Rate limiting and audit logging are single-process, in-memory

- `shared_rate_limiter` (`backend/common/rate_limit.py`) keeps counters in a process-local dict. Running more than one worker or replica means the effective limit multiplies by the worker/replica count, not a global cap. For a real multi-instance deployment, back this with Redis (already a dependency in this project).
- `audit_logger` (`backend/common/audit.py`) keeps every audit entry in an in-memory Python list for the life of the process — it is not persisted and does not survive a restart. If audit history needs to survive restarts or satisfy compliance requirements, persist entries to the database or an external log sink.

### 11.6 Role checks

`backend/common/rbac.py`'s `require_role()`/`AuthorizationPolicy` are meant to check a user's `role` field. Confirm your working copy compares against `current_user.role` and not `current_user.username` — a mismatch here silently changes who counts as "admin."

### 11.7 Test coverage includes structural checks, not just behavioral ones

Some of the `tests/test_enterprise_*.py` files assert that a package/module exists or imports successfully, rather than exercising behavior. That's useful as a smoke test, but a green test suite alone shouldn't be read as proof that role checks, registration field-scoping, or endpoint auth are all correct — add a behavioral test for each item in this section as you address it.

---

## 12. Core files to check when extending the project

- `backend/main.py` — app startup, middleware, `/health`, `/metrics`, `/runtime`, WebSocket mount.
- `backend/app/api/v1/router.py` — top-level route registration for all modules.
- `backend/app/api/v1/users/router.py`, `.../products/router.py`, `.../auth/router.py`, `.../uploads/router.py`, `.../admin/router.py`, `.../admin/governance_router.py` — feature routers.
- `backend/application/users/use_cases.py`, `backend/application/products/use_cases.py`, `backend/application/auth/use_cases.py` — application-layer workflow entry points (note: these live in per-feature subpackages, not as flat `user_use_cases.py`/`product_use_cases.py`/`auth_use_cases.py` files).
- `backend/application/ports.py` — outbound-integration interfaces.
- `backend/application/services.py` — shared application-layer runtime handles.
- `backend/domain/users/service.py` — auth, password reset, email verification, and lockout logic.
- `backend/domain/products/service.py`, `backend/domain/products/repository.py` — product business rules and query behavior.
- `backend/domain/events/__init__.py` — domain-event definitions and payload conventions.
- `backend/domain/users/repository.py`, `backend/domain/products/repository.py` — persistence access.
- `backend/integrations/email_adapter.py` — adapter implementations for external services.
- `backend/common/schema.py` — request/response models, including OpenAPI examples.
- `backend/common/dependencies.py` — authentication and dependency-injection helpers.
- `backend/common/email.py` — pluggable email delivery for password reset/verification messages.
- `backend/common/permissions.py`, `backend/common/rbac.py`, `backend/common/audit.py` — authorization and audit behavior.
- `backend/common/log.py`, `backend/common/rate_limit.py` — request correlation, logging, throttling.
- `backend/common/bootstrap.py` — startup/shutdown hook registration.
- `backend/scripts/seed_data.py` — development seeding for default admin and sample products.
- `backend/app/socketio_app.py` — Socket.IO event handlers and real-time hooks.
- `tests/test_crud_and_socketio.py`, `tests/test_enterprise_architecture_layers.py`, `tests/test_enterprise_layout.py` — regression coverage for the core API and package structure.

---

## 13. Next-direction roadmap

Suggested next steps, roughly in order of impact:

- Close the gaps in §11 (auth on the flagged endpoints, registration field-scoping, upload filename sanitization) — these affect correctness/safety of the current baseline, not just future features.
- Wire up a real OpenTelemetry SDK + OTLP exporter for auth, database, Redis, and Socket.IO boundaries, replacing the current logging-only span bridge.
- Move rate limiting and audit logging onto Redis/the database respectively, so both work correctly across multiple workers/replicas and survive restarts.
- Add object-storage integration (S3/Azure Blob) for production file handling, replacing local-disk uploads.
- Add contract tests for API schemas and backward compatibility.
- Add a second, richer domain module (orders, invoices, or subscriptions) as a guided example of the full layered pattern.
- Introduce an outbox pattern and event publisher for reliable domain-event propagation (today, `DomainEvent`s are only logged, not published anywhere).
- Formalize a container-based deployment strategy with environment promotion across dev/staging/prod.

---

## Appendix A — corrections from the original documentation

The original `DOCUMENTATION.md` described a few things that don't match the current source. Listed here for transparency rather than silently changed:

| Original claim                                                                                                                                                 | What the source actually shows                                                                                                                                                                                                                                                                                                                                                                                                                        |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "backend/application/user_use_cases.py, backend/application/product_use_cases.py, and backend/application/auth_use_cases.py: domain-specific use-case modules" | These live at `backend/application/users/use_cases.py`, `backend/application/products/use_cases.py`, and `backend/application/auth/use_cases.py` (per-feature subpackages), not as flat top-level files.                                                                                                                                                                                                                                              |
| "backend/application/use_cases.py: shared application workflow entry points"                                                                                   | There is no single flat `backend/application/use_cases.py` — orchestration is split per feature as above.                                                                                                                                                                                                                                                                                                                                             |
| "Product creation emits a Socket.IO event that can be consumed by a connected client"                                                                          | The REST `POST /api/v1/products/` handler now emits a `product_created` Socket.IO event after a product is created, so connected clients can receive it from the server side.                                                                                                                                                                                                                                                                         |
| "The tracing layer now supports a basic local mode and a production-style OpenTelemetry configuration"                                                         | `OpenTelemetryBridge` reads the `OTEL_*` settings but only produces structured log lines — it does not instantiate the real `opentelemetry` SDK or export spans to an OTLP endpoint today.                                                                                                                                                                                                                                                            |
| Registration example payload showing `role`/`permissions` in the request body                                                                                  | Treat this as a payload the public endpoint should **not** accept; role/permission assignment should be a separate, admin-gated operation.                                                                                                                                                                                                                                                                                                            |
| "A dedicated platform/runtime layer for cross-cutting observability, introspection, and operational signals" (implying this is fully independent)              | `PlatformRuntime` and the application-layer/service-layer runtime containers (`backend/application/services.py`, `backend/services/runtime.py`) overlap significantly — several of them wrap the same underlying `logger`/`redis_client`/`background_job_manager`/`email_delivery_service` singletons. Treat `backend/infrastructure/runtime.py`'s `build_infrastructure_registry` as the primary source of truth for what's attached to `app.state`. |
