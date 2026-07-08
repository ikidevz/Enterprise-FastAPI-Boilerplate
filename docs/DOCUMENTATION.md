# Tier 4 Architecture — Documentation (Expanded)

This is an expanded, more detailed rewrite of the project's `DOCUMENTATION.md`. It keeps the original's structure and intent, but goes further in three ways:

1. **More depth** — a full endpoint reference table, a complete configuration/environment-variable reference, request-lifecycle detail down to the middleware/dependency level, and per-module "where things live" maps.
2. **Accuracy corrections** — the original documentation described a number of things that don't match the current source: stale file paths left over from a `backend/common/*` → `backend/core/security/`, `backend/observability/`, `backend/resilience/`, `backend/web/` reorganization, an endpoint table that hadn't caught up with auth being added to several routes, a documented CI workflow that doesn't exist in the repo, and a couple of features described as working that are not (or, in one case, described as _not_ working when they now are). This revision (July 2026) re-verified every path and claim in this document directly against the source tree and against the project's own test suite — see **Appendix A** for the full corrections list, and this section's siblings for the corrected content itself.
3. **A "known limitations" section** — an enterprise boilerplate that's going to be copy-pasted into real projects should document its current gaps as clearly as it documents its features. **§11 reflects an independent audit performed directly against this source tree** (see `AUDIT_FINDINGS.md` at the project root for the complete, itemized findings and drop-in code fixes) rather than the informal, partly-stale notes an earlier revision carried.

> This document describes the code **as it exists in the repository today**, not an idealized version of it. Where the code doesn't yet do what the name suggests, that's called out rather than glossed over. Where a previous revision of this document made a claim that no longer holds (or never held), that's corrected rather than repeated.
>
> **For the full, itemized audit (severity-ranked, each with a before/after code fix), see `AUDIT_FINDINGS.md`.** This document summarizes the highlights inline (§11) but doesn't repeat every fix's code.

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
│  backend/utils, backend/integrations, backend/core/security,   │
│  backend/resilience, backend/observability, backend/common)    │
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
   - Calls `bind_request_context(...)` (`backend/observability/logging.py`) so every log line for this request carries the request ID.
   - If `settings.enable_rate_limiting` is on, checks `shared_rate_limiter.allow_request(...)` (`backend/resilience/rate_limit.py` — see §11 for a note on a stale duplicate of this module) and short-circuits with `429` if the caller has exceeded `rate_limit_requests_per_minute`.
   - A separate ASGI middleware, `backend/web/request_size_middleware.py`, checks `Content-Length` against `settings.max_request_size_bytes` and short-circuits with `413` if too large.
   - Wraps the actual route call in `trace_span("http.request", ...)` (`backend/observability/tracing.py` — this is the sole tracing module; `backend/common/opentelemetry.py` does not exist in this codebase despite being referenced elsewhere in this project's history).
2. **Routing.** `backend/app/bootstrap/router_registry.py` mounted `backend/app/api/v1/router.py` at `settings.api_v1_str` (default `/api/v1`), which in turn includes `backend/app/api/v1/products/router.py`'s `create_product` handler for this path.
3. **Dependency resolution.** FastAPI resolves `db: AsyncSession = Depends(get_db)` (`backend/database/session.py`), opening an `AsyncSession` that will be committed/rolled back automatically at the end of the request.
4. **Application layer.** The handler builds `ProductService(ProductRepository(db))` and calls `CreateProductUseCase(service).execute(payload=payload)` (`backend/application/products/use_cases.py`), which validates uniqueness rules and calls into the domain service.
5. **Domain layer.** `ProductService.create(...)` (`backend/domain/products/service.py`) constructs the `Product` SQLAlchemy model, adds it to the session, flushes, and refreshes it to get the generated `id`.
6. **Response translation.** The router converts the returned `Product` into `ProductOut` (`backend/common/schema.py`) via `response_model=ProductOut`.
7. **Audit + metrics on the way out.** The router calls `audit_logger.log(...)` (`backend/observability/audit.py`); back in the middleware, `record_request_metrics(...)` (`backend/observability/metrics.py`) records the method/path/status, and security headers (`x-content-type-options`, `x-frame-options`, `referrer-policy`, and — if `require_https` — `strict-transport-security`) are attached to the response.
8. **Session teardown.** `get_db()`'s `finally` block closes the session; if an exception propagated, it's rolled back first.

The same shape applies to every feature — only steps 4–5 change per domain.

---

## 3. Layer-by-layer guide

### 3.1 Presentation layer — `backend/app`

Responsible for the HTTP/WebSocket surface of the app.

| Concern                                                                     | Where                                                                                                                          |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| App factory (`create_app()`)                                                | `backend/app/factory.py`                                                                                                       |
| Middleware registration (CORS)                                              | `backend/app/bootstrap/middleware_registry.py`                                                                                 |
| Router registration                                                         | `backend/app/bootstrap/router_registry.py`                                                                                     |
| Static file mount for uploads (`/static/uploads`)                           | `backend/app/bootstrap/static_registry.py`                                                                                     |
| Infrastructure wiring hook-up for the factory                               | `backend/app/infrastructure/__init__.py` (re-exports `build_infrastructure_registry` from `backend/infrastructure/runtime.py`) |
| Top-level router aggregation                                                | `backend/app/api/v1/router.py`                                                                                                 |
| Feature routers                                                             | `backend/app/api/v1/{auth,users,products,uploads,admin}/router.py`                                                             |
| Socket.IO server & handlers                                                 | `backend/app/socketio_app.py`                                                                                                  |
| App entrypoint: middleware, `/health`, `/metrics`, `/runtime`, `/ws/health` | `backend/main.py`                                                                                                              |

### 3.2 Application layer — `backend/application`

Where business workflows become explicit, orchestrated units instead of logic embedded in route handlers.

| Concern                                                                     | Where                                                                                        |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| User registration & update workflows                                        | `backend/application/users/use_cases.py` (`RegisterUserUseCase`, `UpdateUserUseCase`)        |
| Auth workflows (login, refresh, logout, password reset, email verification) | `backend/application/auth/use_cases.py`                                                      |
| Product create/update workflows                                             | `backend/application/products/use_cases.py` (`CreateProductUseCase`, `UpdateProductUseCase`) |
| Outbound integration interfaces ("ports")                                   | `backend/application/ports.py` (`NotificationPort`)                                          |

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

| Concern                                                           | Where                                                                                                                                                                                                                                                   |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Async SQLAlchemy engine/session                                   | `backend/database/session.py`                                                                                                                                                                                                                           |
| Declarative base                                                  | `backend/database/base.py`                                                                                                                                                                                                                              |
| Redis client                                                      | `backend/utils/redis_client.py`                                                                                                                                                                                                                         |
| Email transport (console/SMTP)                                    | `backend/infrastructure/email/transport.py`, adapted by `backend/integrations/email_adapter.py`; `backend/common/email.py` does not exist in this codebase                                                                                              |
| Startup/shutdown wiring onto `app.state`                          | `backend/infrastructure/runtime.py` (`build_infrastructure_registry`)                                                                                                                                                                                   |
| Generic hook registry used by the above                           | `backend/common/bootstrap.py` (`BootstrapRegistry`)                                                                                                                                                                                                     |
| App lifespan (DB table creation, background jobs, registry hooks) | `backend/app/lifespan.py`                                                                                                                                                                                                                               |
| Background job queue                                              | `backend/common/background_jobs.py`                                                                                                                                                                                                                     |
| Rate limiting                                                     | `backend/resilience/rate_limit.py` — the sole rate-limiter module (`RateLimiter` + Redis-backed `RedisRateLimiter`). `backend/common/rate_limit.py` does not exist in this codebase; the test suite's cleanup fixture correctly resets the real module. |
| Request-scoped logging context                                    | `backend/observability/logging.py`                                                                                                                                                                                                                      |
| Request size limiting                                             | `backend/web/request_size_middleware.py`                                                                                                                                                                                                                |
| Metrics collection                                                | `backend/observability/metrics.py`, `backend/common/exporters.py`                                                                                                                                                                                       |
| Tracing/spans                                                     | `backend/observability/tracing.py` — the sole tracing module; `backend/common/opentelemetry.py` does not exist in this codebase                                                                                                                         |
| Audit trail                                                       | `backend/observability/audit.py`                                                                                                                                                                                                                        |
| Auth/JWT dependency, current-user resolution                      | `backend/core/security/dependencies.py`                                                                                                                                                                                                                 |
| Role/permission checks                                            | `backend/core/security/rbac.py` (`require_role`, `AuthorizationPolicy`, `require_policy`) — there is no separate `PermissionPolicy`/permissions module; a user's `permissions` field is a plain string list checked ad hoc where needed.                |
| Token issuance/rotation/revocation storage                        | `backend/core/security/token_store.py`                                                                                                                                                                                                                  |
| Config/settings                                                   | `backend/core/config.py`                                                                                                                                                                                                                                |
| Shared exception hierarchy + HTTP translation                     | `backend/web/exceptions.py`                                                                                                                                                                                                                             |
| Runtime/operational snapshot facade                               | `backend/infrastructure/runtime.py` (`PlatformRuntime.build_runtime_snapshot`, backs the `/runtime` route) — there is no separate `backend/platform/` package.                                                                                          |
| API-facing "contract" mirror types                                | `backend/contracts/` (`backend/contracts/__init__.py` is the public import gateway)                                                                                                                                                                     |

---

## 4. Full API endpoint reference

All routes below are mounted under the `settings.api_v1_str` prefix, default `/api/v1`, except `/health`, `/metrics`, `/runtime`, `/ws/health`, and `/health/ready`, which are mounted at the app root.

| Method    | Path                                      | Auth required today?                             | Description                                                                                                |
| --------- | ----------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| POST      | `/api/v1/users/`                          | No (public registration)                         | Create a new user account.                                                                                 |
| GET       | `/api/v1/users/me`                        | Yes                                              | Get the current authenticated user's profile.                                                              |
| GET       | `/api/v1/users/{user_id}`                 | Yes (self or superuser only)                     | Get a user's profile by id; returns `403` if the caller is neither that user nor a superuser.              |
| GET       | `/api/v1/users/`                          | Yes (admin only)                                 | List all users.                                                                                            |
| PUT       | `/api/v1/users/{user_id}`                 | Yes                                              | Update a user; non-superusers cannot change `is_superuser`, `is_active`, `role`, or `permissions`.         |
| DELETE    | `/api/v1/users/{user_id}`                 | Yes (self or superuser only)                     | Delete a user by id; returns `403` if the caller is neither that user nor a superuser.                     |
| POST      | `/api/v1/auth/login`                      | No (this _is_ the login)                         | OAuth2 password-flow login; returns access + refresh tokens.                                               |
| POST      | `/api/v1/auth/refresh`                    | No (bearer of a valid refresh token)             | Rotates a refresh token for a new access/refresh pair.                                                     |
| POST      | `/api/v1/auth/logout`                     | No (bearer of a valid refresh token)             | Revokes a refresh token.                                                                                   |
| POST      | `/api/v1/auth/email-verification/request` | No                                               | Requests an email-verification token be sent.                                                              |
| POST      | `/api/v1/auth/email-verification/confirm` | No (bearer of the token)                         | Confirms email verification.                                                                               |
| POST      | `/api/v1/auth/password-reset/request`     | No                                               | Requests a password-reset token be sent.                                                                   |
| POST      | `/api/v1/auth/password-reset/confirm`     | No (bearer of the token)                         | Confirms a password reset with a new password.                                                             |
| GET       | `/api/v1/auth/me`                         | Yes                                              | Alias of `/users/me`, returns the current user.                                                            |
| POST      | `/api/v1/products/`                       | Yes (admin/staff only)                           | Create a product.                                                                                          |
| GET       | `/api/v1/products/`                       | No (public catalog browsing — by design)         | List products; supports `search`, `skip`, `limit`, `sort`, `order`.                                        |
| GET       | `/api/v1/products/{product_id}`           | No (public)                                      | Get a single product.                                                                                      |
| PUT       | `/api/v1/products/{product_id}`           | Yes (admin/staff only)                           | Update a product.                                                                                          |
| DELETE    | `/api/v1/products/{product_id}`           | Yes (admin/staff only)                           | Delete a product.                                                                                          |
| POST      | `/api/v1/uploads/`                        | Yes                                              | Upload a file (multipart). Stored under the configured upload dir, served back from `/static/uploads`.     |
| GET       | `/api/v1/admin/users`                     | Yes (`require_role("admin")`, see ⚠️ note below) | List users via the admin surface.                                                                          |
| PATCH     | `/api/v1/admin/users/{user_id}/role`      | Yes (`require_role("admin")`)                    | Change a user's `role`/`permissions`; audit-logged with a before/after diff.                               |
| GET       | `/health`                                 | No                                               | Liveness probe: status, environment, version.                                                              |
| GET       | `/health/ready`                           | No                                               | Readiness probe: pings the DB and Redis.                                                                   |
| GET       | `/metrics`                                | No                                               | In-process request-count/status-code/method/path metrics snapshot.                                         |
| GET       | `/runtime`                                | No                                               | Operational snapshot (uptime, metrics) via `PlatformRuntime`.                                              |
| WS        | `/ws/health`                              | No                                               | Trivial WebSocket that accepts, sends `{"status": "connected"}`, and closes.                               |
| Socket.IO | `/socket.io`                              | No                                               | Socket.IO server; handles `connect`, `disconnect`, `ping`, and authenticated `product_created` broadcasts. |

**⚠️ marked rows** are endpoints that are intentionally public or have a narrower auth contract than the rest of the system. Current examples are the public product catalog and the public registration route — every other user/product/upload endpoint requires at least an authenticated caller, and several require `admin`/`staff` role or self/superuser ownership on top of that (see the Auth column above). A previous revision of this table incorrectly marked `GET`/`DELETE /api/v1/users/{user_id}` as unauthenticated; that was never accurate for the current router implementation (verified directly against `backend/app/api/v1/users/router.py`) and has been corrected above.

The `require_role("admin")`/`require_role("admin", "staff")` dependency (`backend/core/security/rbac.py`) checks `current_user.role` (or `current_user.is_superuser`) against the given role names, and is wired into every admin, user-listing, and product-write route. There is no separate `PermissionPolicy`/`/api/v1/admin/permissions` endpoint in the current code — a previous revision of this document described one that doesn't exist.

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
- `GET /metrics` — returns an in-process snapshot of request counts, status codes, methods, and paths, collected by `backend/observability/metrics.py`'s `MetricsCollector`. This is process-local, in-memory, and resets on restart — it is not a Prometheus-scrape-compatible endpoint (no `text/plain` exposition format) and does not aggregate across multiple workers/pods. **It requires an authenticated admin caller** (`Depends(require_role("admin"))` in `backend/main.py`).
- `GET /runtime` — returns an operational snapshot (service name, environment, uptime, the same metrics snapshot) via `PlatformRuntime` (`backend/infrastructure/runtime.py` — not a separate `backend/platform/` package). **Also requires an authenticated admin caller.**
- Every response carries `x-request-id`, `x-trace-id`, `x-content-type-options: nosniff`, `x-frame-options: DENY`, and `referrer-policy: strict-origin-when-cross-origin`; if `require_https` is enabled, also `strict-transport-security`.
- Tracing: `backend/observability/tracing.py`'s `trace_span` context manager wraps the whole HTTP request in `main.py`, and several individual routes (`auth.login`, `product.create`, `upload.create`) wrap their own operation in a span too. Today this only produces structured log lines (see §11 for the gap between this and a real OpenTelemetry exporter pipeline).

---

## 8. Persistence and data layer

- Async SQLAlchemy engine/session setup lives in `backend/database/session.py`; `backend/infrastructure/persistence/session.py` re-exports the same objects for infrastructure-layer imports.
- `Base` (SQLAlchemy `DeclarativeBase`) is shared across all models, defined in `backend/database/base.py`.
- Repositories inherit `BaseRepository` (`backend/common/base_repository.py`) for `get_by_id`, `list`, `create`, `update`, `delete`, `count` — though note that `UserService`/`ProductService` currently implement their own create/update logic directly rather than calling the base repository's, for reasons tied to the extra fields they need to set (hashed passwords, timestamps).
- Migrations: `alembic/versions/20260704_initial_schema.py` is the initial migration, creating the `users` and `products` tables — as first written it was missing `users.is_verified`, `users.failed_login_attempts`, and `users.locked_until`, and typed `created_at`/`updated_at` as `VARCHAR(50)` instead of a timestamp. **This is already corrected by the follow-up migration `alembic/versions/20260707_add_missing_user_columns.py`**, which adds the three missing columns and converts both timestamp columns to real `DateTime` columns. `alembic upgrade head` was run against a throwaway database as part of this audit and completes cleanly, producing a schema that matches the `User`/`Product` models. Whenever you add or change a model going forward, generate/hand-write a matching migration and keep `tests/test_migrations_match_models.py`'s `test_alembic_upgrade_head_runs_cleanly_against_a_throwaway_database` test passing — the app's `lifespan` (`backend/app/lifespan.py`) also calls `Base.metadata.create_all` at startup as a convenience for local development, but that is not a substitute for migrations in any shared environment.
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
- **docker-compose.yml**: brings up the API alongside `postgres:16-alpine` and `redis:7-alpine` for local/integration use. It requires real `POSTGRES_PASSWORD`/`REDIS_PASSWORD` values via `${POSTGRES_PASSWORD:?set a real password in .env}`/`${REDIS_PASSWORD:?set a real password in .env}` — there is no hard-coded `postgres`/`postgres` default, and Redis is started with `--requirepass`, so the compose file will refuse to start without both passwords supplied.
- **CI: exists at `.github/workflows/ci.yml`**, running on push/PR to `main`/`master`: lint (`ruff check backend tests`) → real `alembic upgrade head` against a Postgres service container → `pytest -q` → `scripts/security_scan.sh`. As currently checked in, however, the **lint step fails** (24 `ruff` errors — see `AUDIT_FINDINGS.md` §1/A-3) and would block every later step, and the test step depends on `aiosqlite`, which isn't declared in `pyproject.toml`'s `dev` extra (`AUDIT_FINDINGS.md` §1/A-2) — so the pipeline as shipped does not currently go green. Both are one-line/one-dependency fixes; see `AUDIT_FINDINGS.md` §4 for the exact diffs.
- **Environment files**: `deployment/env/{dev,staging,prod}.env` hold environment-specific defaults; production secrets (DB URL, Redis URL, JWT secret) should be supplied via the `*_FILE` settings (pointing at a mounted secret file) rather than committed to any `.env`.
- **scripts/security_scan.sh**: runs `safety` (dependency CVE scan) and `bandit` (static security lint) and **does gate the build** — it sets `status=1` on either tool finding something and `exit 1`s unless `SECURITY_SCAN_SOFT_FAIL=1` is set, which CI never sets. It is wired into CI as the last step of `ci.yml`.

---

## 11. Known limitations & security notes (read before deploying)

This project is a boilerplate, and boilerplates get copy-pasted wholesale into real products more often than they get read line-by-line first. **This section reflects an independent audit performed directly against this source tree** — every claim below was checked by reading the relevant code and, where applicable, running it (migrations, the full `pytest` suite, `ruff`), not by trusting a previous revision of this document. The full report, including a file-and-diff fix for every open item, lives in **`AUDIT_FINDINGS.md`** at the project root (there is no separate `FIXES.md` — fixes are inlined in that report's §4).

### 11.1 What's still genuinely open

- **Test suite doesn't run out of the box (`AUDIT_FINDINGS.md` A-2):** every test depends on `sqlite+aiosqlite:///:memory:` via `tests/conftest.py`, but `aiosqlite` isn't declared in `requirements.txt` or the `dev` extra in `pyproject.toml`. A fresh `pip install -e .[dev] && pytest -q` fails with `ModuleNotFoundError` on every DB-touching test until `aiosqlite` is installed by hand.
- **CI lint step currently fails (`AUDIT_FINDINGS.md` A-3):** `ruff check backend tests` — the first step of `.github/workflows/ci.yml` — has 24 errors (mostly unused imports) as shipped, which blocks the rest of the pipeline (migrations-against-Postgres, tests, security scan) from ever running in CI.
- **Retry/circuit-breaker primitives are unused (`AUDIT_FINDINGS.md` A-4):** `backend/resilience/retry.py`'s `CircuitBreaker` is implemented and unit-tested but not wired into `SMTPEmailTransport` (or anything else that calls out over the network) — a flaky SMTP server currently gets no retry, and the only signal of a failed send is a generic `background_job_failed` log line.
- **Mass-assignment path in `BaseRepository` (`AUDIT_FINDINGS.md` A-5):** `create()`/`update()` in `backend/common/base_repository.py` accept a raw `dict` and construct/mutate the model directly from it. Nothing currently calls this with untrusted input, but it's a latent privilege-escalation footgun for the first caller that does.
- **`staging` isn't covered by the insecure-default guard (`AUDIT_FINDINGS.md` A-6):** `Settings._reject_insecure_prod_defaults()` in `backend/core/config.py` only refuses to boot with the default `SECRET_KEY`/`DEFAULT_ADMIN_PASSWORD` when `environment == "prod"`; a `staging` deployment (a first-class environment value, and the one CI itself runs under) gets no such protection.
- **Rate limiting has a single-process ceiling outside of Redis:** `RedisRateLimiter` (`backend/resilience/rate_limit.py`) is used whenever `environment != "dev"` and Redis is reachable, and falls back to the in-process `RateLimiter` if Redis is unreachable (failing _open_ to degraded limiting, not a full outage) — the only remaining multi-instance gap is `dev` mode or a sustained Redis outage.
- **Tracing and metrics are lightweight by design:** `backend/observability/tracing.py` produces structured log lines gated by `OTEL_MODE`/`ENABLE_TRACING`, not a real `opentelemetry` SDK span exporter, even though the `opentelemetry-*` packages are dependencies and `OTEL_EXPORTER_OTLP_ENDPOINT` exists as a setting. `/metrics` and `/runtime` are process-local snapshots (though both are admin-authenticated today) that reset on restart and don't aggregate across workers/replicas.

### 11.2 What's already fixed (verify before re-fixing)

An earlier revision of this document, and the docstrings on a handful of tests, described several bugs below as open. Each was checked directly against the current source and/or exercised via the test suite and found **already resolved**:

- Login lockout returns the identical `"Incorrect email or password"` 401 for an unknown email, a wrong password, and a locked account — no enumeration signal.
- The Socket.IO `connect` handler checks the same Redis-backed revocation store that `/auth/logout` writes to, so a revoked access token can't open a realtime session.
- File uploads use server-generated UUID filenames with path-traversal protection, are served only through the authenticated, ownership-checked `GET /api/v1/uploads/{stored_name}` route, and have magic-byte content validation for binary types — there is no public `/static/uploads` mount.
- `/metrics` and `/runtime` require `require_role("admin")`.
- The rate limiter's Redis path fails open to an in-process fallback on a Redis outage, not closed to a full 429 outage.
- The audit log (`backend/observability/audit.py`) persists every entry to `logs/audit.jsonl` in addition to structured logging, and `user.deleted` entries correctly record the acting user.
- There is no stale duplicate rate limiter at `backend/common/rate_limit.py` — that module doesn't exist, and the test suite's cleanup fixture correctly resets `backend.resilience.rate_limit.shared_rate_limiter`.
- Login and registration both normalize email to `.strip().lower()` before lookup/compare — no case-sensitivity mismatch.
- `LocalUploadStorage.save()` returns a route path (`/api/v1/uploads/{stored_name}`), not a server filesystem path.
- `backend/core/security/rbac.py`'s `require_role()`/`AuthorizationPolicy` check `current_user.role`/`is_superuser`, not `username`.
- The initial migration's missing columns and mistyped timestamps are fixed by the follow-up migration `alembic/versions/20260707_add_missing_user_columns.py`; `alembic upgrade head` runs cleanly end-to-end (verified in this audit).

Several `tests/*` docstrings (e.g. in `test_authorization_and_roles.py`, `test_password_reset_and_email_verification.py`) still cite a file named `IMPROVEMENT.MD`/`IMPROVEMENT_SUGGESTIONS_MERGED.md` and describe some of the above as open bugs. That file doesn't exist in this repository — treat those docstrings as stale and due for a rewrite, not as a live issue list.

### 11.3 Test coverage note

Some tests assert that a package/module exists, imports successfully, or that a particular substring appears in a router's source, rather than exercising real behavior end-to-end. That's a useful smoke test, but a green suite alone isn't proof that realtime events, role checks, or endpoint auth are fully correct — prefer a behavioral test (real HTTP/Socket.IO client, real assertions on the response) going forward.

## 12. Core files to check when extending the project

- `backend/main.py` — app startup, middleware, `/health`, `/metrics`, `/runtime`, WebSocket mount.
- `backend/app/api/v1/router.py` — top-level route registration for all modules.
- `backend/app/api/v1/users/router.py`, `.../products/router.py`, `.../auth/router.py`, `.../uploads/router.py`, `.../admin/router.py` — feature routers. (There is no `.../admin/governance_router.py` in the current source; it was removed as dead/demo code — see `backend/app/bootstrap/router_registry.py`'s comment.)
- `backend/application/users/use_cases.py`, `backend/application/products/use_cases.py`, `backend/application/auth/use_cases.py` — application-layer workflow entry points (these live in per-feature subpackages, not as flat `user_use_cases.py`/`product_use_cases.py`/`auth_use_cases.py` files, and there is no top-level `backend/application/services.py`).
- `backend/application/ports.py` — outbound-integration interfaces.
- `backend/domain/users/service.py` — auth, password reset, email verification, and lockout logic.
- `backend/domain/products/service.py`, `backend/domain/products/repository.py` — product business rules and query behavior.
- `backend/domain/events/__init__.py` — domain-event definitions and payload conventions.
- `backend/domain/users/repository.py`, `backend/domain/products/repository.py` — persistence access.
- `backend/integrations/email_adapter.py` — adapter implementations for external services.
- `backend/common/schema.py` — request/response models, including OpenAPI examples.
- `backend/core/security/dependencies.py` — authentication and dependency-injection helpers.
- `backend/core/security/rbac.py` — role/policy authorization checks.
- `backend/core/security/token_store.py` — access/refresh token issuance, rotation, and revocation.
- `backend/observability/audit.py` — audit trail (persists to `logs/audit.jsonl` in addition to structured logging).
- `backend/observability/logging.py` — request correlation/logging context.
- `backend/resilience/rate_limit.py` — the sole rate limiter module (`backend/common/rate_limit.py` does not exist in this codebase).
- `backend/common/bootstrap.py` — startup/shutdown hook registration.
- `backend/app/lifespan.py` — app lifespan (DB table creation for dev, background jobs, registry hooks).
- `backend/scripts/seed_data.py` — development seeding for default admin and sample products.
- `backend/app/socketio_app.py` — Socket.IO event handlers and real-time hooks.
- `alembic/versions/` — schema migrations; `alembic upgrade head` was verified clean end-to-end as part of this audit (§11.2).
- `AUDIT_FINDINGS.md` — the independent audit and its file-and-diff code fixes for every open item; start here for anything flagged with an "A-#" reference in this document.
- `tests/test_authentication.py`, `tests/test_authorization_and_roles.py`, `tests/test_users_api.py`, `tests/test_products_api.py`, `tests/test_uploads.py`, `tests/test_realtime.py` — regression coverage for the core API (see §9 for the full test-file table; `tests/test_crud_and_socketio.py`, `tests/test_enterprise_architecture_layers.py`, and `tests/test_enterprise_layout.py`, cited by name in a previous revision of this document, do not exist in the current test suite).

---

## 13. Next-direction roadmap

Suggested next steps, roughly in order of impact:

- **Get the CI pipeline green first** — add `aiosqlite` to the `dev` extra and run `ruff check backend tests --fix` (see `AUDIT_FINDINGS.md` §4/A-2, A-3). Neither the app nor the migrations are broken; the pipeline as checked in just can't currently prove that on its own.
- Close the remaining gaps in §11.1 (retry/circuit-breaker wiring, the `BaseRepository` mass-assignment path, the `staging` insecure-default guard) — see `AUDIT_FINDINGS.md` for the full list and file-and-diff fixes.
- Wire up a real OpenTelemetry SDK + OTLP exporter for auth, database, Redis, and Socket.IO boundaries, replacing the current logging-only span bridge.
- Move rate limiting fully onto Redis in every environment (not just `environment != "dev"`), so local dev exercises the same code path as production.
- Wire the existing `CircuitBreaker` primitive (`backend/resilience/retry.py`) into the SMTP transport and Redis calls, rather than leaving it unit-tested but unused (`AUDIT_FINDINGS.md` A-4).
- Add object-storage integration (S3/Azure Blob) for production file handling, replacing local-disk uploads (the storage backends already exist in `backend/infrastructure/upload_storage.py` — this is a matter of configuring `UPLOAD_BACKEND` and credentials, not new code).
- Add contract tests for API schemas and backward compatibility.
- Add a second, richer domain module (orders, invoices, or subscriptions) as a guided example of the full layered pattern.
- Introduce an outbox pattern and event publisher for reliable domain-event propagation (today, `DomainEvent`s are only logged, not published anywhere).
- Formalize a container-based deployment strategy with environment promotion across dev/staging/prod.

---

## Appendix A — corrections from the original documentation

The original `DOCUMENTATION.md` described a few things that don't match the current source. Listed here for transparency rather than silently changed:

| Original claim                                                                                                                                                                                                                                       | What the source actually shows                                                                                                                                                                                                                                                                                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "backend/application/user_use_cases.py, backend/application/product_use_cases.py, and backend/application/auth_use_cases.py: domain-specific use-case modules"                                                                                       | These live at `backend/application/users/use_cases.py`, `backend/application/products/use_cases.py`, and `backend/application/auth/use_cases.py` (per-feature subpackages), not as flat top-level files.                                                                                                                         |
| "backend/application/use_cases.py: shared application workflow entry points"                                                                                                                                                                         | There is no single flat `backend/application/use_cases.py` — orchestration is split per feature as above.                                                                                                                                                                                                                        |
| "Product creation emits a Socket.IO event that can be consumed by a connected client"                                                                                                                                                                | The REST `POST /api/v1/products/` handler now emits a `product_created` Socket.IO event after a product is created, so connected clients can receive it from the server side.                                                                                                                                                    |
| "The tracing layer now supports a basic local mode and a production-style OpenTelemetry configuration"                                                                                                                                               | `OpenTelemetryBridge` reads the `OTEL_*` settings but only produces structured log lines — it does not instantiate the real `opentelemetry` SDK or export spans to an OTLP endpoint today.                                                                                                                                       |
| Registration example payload showing `role`/`permissions` in the request body                                                                                                                                                                        | Treat this as a payload the public endpoint should **not** accept; role/permission assignment should be a separate, admin-gated operation.                                                                                                                                                                                       |
| "A dedicated platform/runtime layer for cross-cutting observability, introspection, and operational signals" living at `backend/platform/runtime.py`, separate from an `backend/application/services.py`/`backend/services/runtime.py` service layer | None of `backend/platform/`, `backend/application/services.py`, or `backend/services/` exist in the current source. `PlatformRuntime` and `build_infrastructure_registry` both live in the single module `backend/infrastructure/runtime.py`; treat that file as the sole source of truth for what gets attached to `app.state`. |

### Appendix A.2 — additional corrections from the July 2026 audit re-verification

The previous revision of this document (the table above) was itself checked against the current source as part of a full security/reliability audit; the corrections below are new as of that pass. Full details, severities, and fixes for anything marked "F#"/"A-#" are in `AUDIT_FINDINGS.md`.

| Previous documentation claim                                                                                                                                                                                                                                                                                                                | What the source actually shows                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Numerous "Where" table entries across §2–§3 pointed at `backend/common/rbac.py`, `backend/common/dependencies.py`, `backend/common/audit.py`, `backend/common/log.py`, `backend/common/observability.py`, `backend/common/token_store.py`, `backend/common/exceptions.py`, `backend/common/lifespan.py`, and `backend/platform/runtime.py`. | None of these paths exist. The real locations are `backend/core/security/rbac.py`, `backend/core/security/dependencies.py`, `backend/observability/audit.py`, `backend/observability/logging.py`, `backend/observability/metrics.py`, `backend/core/security/token_store.py`, `backend/web/exceptions.py`, `backend/app/lifespan.py`, and `backend/infrastructure/runtime.py` respectively — corrected throughout §2, §3.4, §7, and §12 above.                                             |
| `backend/common/permissions.py` — role/permission checks                                                                                                                                                                                                                                                                                    | This file doesn't exist. Role checks live entirely in `backend/core/security/rbac.py`; there is no separate `PermissionPolicy`/permissions module, and no `GET /api/v1/admin/permissions` endpoint — the admin router's actual second route is `PATCH /api/v1/admin/users/{user_id}/role`, reflected in §4.                                                                                                                                                                                |
| §4 endpoint table listed `GET /api/v1/users/{user_id}` and `DELETE /api/v1/users/{user_id}` as unauthenticated (`**No** ⚠️`)                                                                                                                                                                                                                | Both require `Depends(get_current_active_user)` **and** a self-or-superuser check in the current router (`backend/app/api/v1/users/router.py`) — verified directly against source. This was never accurate for the code as it exists; corrected in §4.                                                                                                                                                                                                                                     |
| §11 (previous revision) warned that role checks "might" compare `username` instead of `role`, and that public registration "might" persist client-supplied `role`/`permissions`                                                                                                                                                             | Both were verified as **already fixed** in the current source (`rbac.py` checks `.role`; `UserCreate` forbids extra fields and self-registration is hardcoded to `role="user"`). Several test-file docstrings in `tests/` still describe these as open bugs and cite a nonexistent `IMPROVEMENT_SUGGESTIONS_MERGED.md`/`IMPROVEMENT.MD` — that's stale test documentation, not a live issue. §11.2 above lists the full set of "described as open, actually already fixed" items.          |
| Migrations were described only as "the initial migration, creating the users and products tables," with no note on drift from the models                                                                                                                                                                                                    | The _initial_ migration alone is missing three columns (`is_verified`, `failed_login_attempts`, `locked_until`) the `User` model requires, and mistypes two timestamp columns as strings — but a second migration, `alembic/versions/20260707_add_missing_user_columns.py`, already corrects this. `alembic upgrade head` (both migrations in sequence) was run against a throwaway database as part of this audit and produces a schema matching the models. Now covered in §8 and §11.2. |
| No mention of a duplicate rate-limiter implementation                                                                                                                                                                                                                                                                                       | Re-checked in this audit pass: `backend/common/rate_limit.py` does not exist in this codebase. There is a single rate-limiter module, `backend/resilience/rate_limit.py`, and the test suite's cleanup fixture correctly resets it. (An earlier draft of this document asserted a duplicate existed; that assertion did not hold up against the actual source and has been removed.)                                                                                                       |
| A prior revision of §10 stated "CI: does not currently exist" / "there is no `.github/` directory in this repository"                                                                                                                                                                                                                       | **Incorrect** — `.github/workflows/ci.yml` exists and defines a real lint → migrate → test → security-scan pipeline. What's actually true: as currently checked in, the lint step fails (24 `ruff` errors) and the test step depends on an undeclared `aiosqlite` dependency, so the pipeline doesn't currently run green end-to-end — a meaningfully different problem than "CI doesn't exist." Corrected in §10 and §11.1/A-2, A-3.                                                      |
