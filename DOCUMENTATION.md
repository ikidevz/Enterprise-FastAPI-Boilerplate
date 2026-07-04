# Tier 4 Architecture Documentation

This document is a detailed guide to the architecture used in this project. It is intended to help future developers understand not just what the application does, but why it is structured the way it is and how each major layer contributes to the system in a way that is practical for enterprise-style extension.

## 1. Architecture overview

The project follows a pragmatic enterprise-oriented architecture designed to separate concerns clearly and keep the codebase maintainable as it grows, especially when new domains, services, and infrastructure dependencies are introduced over time. The architecture is intentionally layered, but it now also makes the most important business workflows explicit through application use cases, integration adapters, and domain events.

The primary architectural layers are:

- Presentation
  - FastAPI routers and request handlers
  - Pydantic schemas for validation and response formatting
  - WebSocket routes and Socket.IO integration
  - API documentation and structured error responses
- Application
  - Explicit use cases such as registration flows or domain-driven workflows
  - Ports that define interfaces for outbound behavior
  - Orchestrators that keep route handlers thin and business intent clear
- Domain
  - User and product services that contain business rules
  - Repositories that isolate persistence logic
  - Domain models that represent business entities in the system
  - Domain events that communicate meaningful business changes
- Infrastructure
  - Async SQLAlchemy sessions and database setup
  - Redis-backed token storage when available
  - Infrastructure helpers for persistence, health checks, runtime support, and environment-specific deployment concerns
  - A dedicated platform/runtime layer for cross-cutting observability, introspection, and operational signals

A request typically moves through the stack as follows:

1. The API router receives the incoming request.
2. Dependencies resolve the current user, database session, and middleware concerns.
3. The application layer coordinates the relevant use case.
4. The domain layer applies the business rules and emits events when meaningful state changes occur.
5. The infrastructure layer handles persistence, external integration calls, and runtime concerns.
6. The response is translated back into a schema and returned to the client.

This design makes the system easier to test, extend, and reason about because each layer has a fairly narrow responsibility while still supporting cross-cutting enterprise concerns.

## 2. How the application is organized

### Presentation layer

The presentation layer is responsible for the HTTP and real-time interface of the app.

- Router modules live under backend/app/api/v1 and define endpoints for auth, users, products, admin features, and uploads.
- Schemas in backend/common/schema.py define the external contract for requests and responses, including validation rules and example payloads for OpenAPI generation.
- The app entrypoint in backend/main.py now exposes a create_app() factory for clean app construction, mounts middleware, registers routers, exposes health and WebSocket endpoints, and serves uploaded files from a static mount.
- WebSocket and Socket.IO endpoints expose real-time communication paths for health checks and event-driven workflows.

### Application layer

The application layer is where business workflows become explicit and orchestrated.

- Use-case classes live under backend/application and represent the primary business operations the system supports.
- Ports in backend/application/ports.py define interfaces for outbound integrations such as notifications or messaging.
- The registration flow is now represented as a formal application use case, which makes the workflow discoverable and easier to test than a route-level implementation alone.
- Product creation and update are now also driven by dedicated use cases so create/update behavior is coordinated in one place rather than being spread across route handlers.
- Authentication flows such as login, refresh, password reset, and email verification are now orchestrated through use cases that centralize domain decisions and error handling.
- Application services in backend/application/services.py provide a central place for shared runtime concerns such as background jobs, rate limiting, logging, and metrics.

This layer is intentionally thin but explicit. It exists to translate an incoming request or external trigger into a well-defined business operation without embedding that logic directly in the API router.

### Domain layer

The domain layer contains the business-oriented parts of the system.

- Services such as UserService and ProductService hold behavior and orchestration logic.
- Models in backend/domain define the persisted entities and their structure.
- Repositories in backend/domain/<feature>/repository.py isolate database access for each domain.

### Infrastructure layer

The infrastructure layer manages persistence and runtime concerns outside of core business logic.

- backend/database contains SQLAlchemy engine/session setup.
- backend/utils contains Redis helpers and other runtime utilities.
- backend/common contains reusable abstractions such as base repositories, base services, schemas, middleware, logging, and tracing helpers.
- backend/infrastructure is the package that owns runtime registration and persistence wiring for the application.
- backend/integrations contains adapter implementations that bridge the domain to external systems such as email delivery.
- backend/services provides a small runtime service container that exposes logging, cache, background workers, and email services in a consistent way.
- backend/platform/runtime.py provides a focused runtime facade that can build a service snapshot for health, readiness, and operational diagnostics without mixing business logic with platform concerns.
- backend/contracts contains explicit API contracts for auth, users, products, and shared health/metrics payloads. These contracts describe the stable interface boundaries between the transport layer and the rest of the application.
- backend/app/infrastructure.py registers runtime services explicitly so the application can expose consistent access to logging, cache, background workers, email delivery, and the underlying persistence layer during startup and shutdown. This keeps the app factory focused on composition while infrastructure concerns remain explicit and reusable.

## 3. How to implement a new feature

Every new feature should follow the same layered pattern so the app stays predictable, easy to test, and easy to extend in an enterprise-style codebase. The goal is not just to add endpoints, but to add capabilities in a way that is maintainable, observable, and safe to evolve over time.

### Recommended implementation pattern

Use the following flow when introducing a new business capability:

1. Start with the domain model.
   - Create the core entity or aggregate in the backend/domain folder.
   - Define its identity, invariants, and the business rules that should always hold.
   - Keep this layer focused on the business concept, not on HTTP or infrastructure concerns.

2. Add persistence boundaries.
   - Create a repository for database access and query behavior.
   - Keep persistence logic isolated so the business layer does not depend directly on SQLAlchemy details.
   - Make the repository explicitly responsible for loading, saving, and filtering the domain model.

3. Add application behavior.
   - Define one or more application use cases under backend/application to capture the workflow explicitly.
   - Use use cases to describe what the system is supposed to do for a given business action.
   - Keep orchestration here so the route layer only receives input, delegates to the use case, and returns a response.
   - If the workflow needs shared runtime concerns, route them through the application services layer rather than embedding them in the router.

4. Define integration contracts.
   - Define ports for outbound dependencies that the use case needs, such as notifications, billing systems, or messaging platforms.
   - Keep these interfaces small and business-focused rather than framework-specific.
   - This makes the application logic more testable and easier to swap later if the infrastructure changes.
   - For API-facing boundaries, keep a matching contract module under backend/contracts so the shape of requests and responses remains explicit and versionable.

5. Implement adapters.
   - Implement adapters under backend/integrations for each external integration.
   - Adapters translate between the domain/application contract and the concrete third-party service.
   - This keeps the core application independent from external SDKs and implementation details.
   - Keep adapter boundaries narrow and explicit so the rest of the system only depends on the port or contract, not on the vendor SDK.

6. Publish domain events when appropriate.
   - Emit domain events when the workflow changes business state in a meaningful way.
   - Events should represent something important that happened, not every internal detail.
   - They are useful for notifications, audit trails, downstream workflows, and future extensibility.

7. Define the external contract.
   - Define request/response schemas in backend/common/schema.py or a feature-local schema file.
   - Keep schemas explicit so the API contract is clear and validated consistently.
   - When a boundary needs a stable API payload shape, add or extend a contract module under backend/contracts so the transport layer and application layer share a clear definition.
   - Treat contracts as first-class design artifacts: they should describe the expected interface, default behavior, and any important validation rules before implementation is finalized.
   - This also improves generated OpenAPI documentation and makes the API easier to consume.

8. Expose the capability over HTTP.
   - Create API routes under backend/app/api/v1/<feature>/.
   - Keep the routes thin by delegating to the application layer rather than embedding business logic inside the handler.
   - Handle request parsing, validation, and response formatting here, but keep the actual decision-making elsewhere.
   - Use the shared middleware and tracing context so the route participates in request correlation, audit logging, and operational visibility without custom glue code.

9. Register and wire the feature into the platform.
   - Register the router in backend/app/api/v1/router.py.
   - Add any supporting infrastructure, such as cache, event emission, background work, or file storage.
   - Make sure startup and shutdown concerns are registered in the infrastructure layer rather than being scattered through the feature code.
   - If the feature exposes runtime status or health meaning, consider extending the runtime facade and readiness checks so operators can observe it without bespoke instrumentation.

### Why this structure matters

This pattern helps the system stay healthy as it grows because each layer has a single clear responsibility:

- The domain layer owns business meaning.
- The application layer owns workflow orchestration.
- The infrastructure layer owns runtime concerns.
- The presentation layer owns transport and user interaction.

That separation makes the code easier to reason about, easier to evolve, and easier to test without coupling unrelated concerns together. In this codebase, that principle now applies not only to users but also to products and authentication flows, which means new features can be introduced without duplicating business checks across routers.

A practical extension rule is that every new feature should also answer four operational questions before it is considered complete: how does it expose its API contract, how does it participate in tracing and metrics, how does it surface readiness or runtime state, and how does it fit into the existing dependency and infrastructure registration model?

### Example: adding a new module

For a module such as products, the expected structure is:

- backend/domain/products/model.py
- backend/domain/products/repository.py
- backend/domain/products/service.py
- backend/application/products/use_cases.py or a feature-specific use case module
- backend/application/ports.py or a feature-specific port interface
- backend/contracts/products.py for explicit API payload contracts
- backend/integrations/<integration>\_adapter.py for external services
- backend/domain/events/<event>.py for domain events
- backend/app/api/v1/products/router.py
- backend/app/api/v1/router.py registration
- backend/platform/runtime.py or a feature-specific runtime extension when the module has operational signals to expose

A practical way to think about it is:

- the route receives the request,
- the use case interprets the request as a business action,
- the domain service applies the business rule,
- the repository persists or loads the data,
- the adapter handles any external dependency,
- the contract ensures the payload shape is explicit and reusable,
- the runtime layer can surface health, readiness, or metrics context if needed,
- and the response is returned to the client in a consistent shape.

This pattern keeps the router thin and ensures most logic lives in the service, application, infrastructure, and contract layers rather than being embedded directly in the API surface.

## 4. Runtime, contracts, and operational readiness

The project now includes a more explicit operational layer that complements the business and API layers:

- backend/platform/runtime.py exposes a runtime facade for environment-aware snapshots, uptime, and platform-level health metadata.
- backend/contracts contains stable response models for shared health/metrics payloads and the main feature domains such as auth, users, and products.
- The application entrypoint exposes /runtime for an operational snapshot and keeps /health and /health/ready aligned with deployment probes.
- Observability remains lightweight but intentional: request metrics are collected, exported, and surfaced through the metrics endpoint, while the platform runtime can be extended with additional checks as the system grows.
- The tracing layer now supports a basic local mode and a production-style OpenTelemetry configuration via environment variables such as ENABLE_TRACING, OTEL_MODE, OTEL_EXPORTER_OTLP_ENDPOINT, and OTEL_SERVICE_NAME.

This makes the project easier to operate in a real environment because the same platform-level signals can be consumed by dashboards, load balancers, and deployment automation without needing to understand the full request pipeline.

## 5. How the current features work

### Authentication flow

The authentication flow is now much more complete and production-minded than a simple starter example, and it now follows the same orchestration model as the rest of the application:

- A user registers via POST /api/v1/users/.
- The user logs in via POST /api/v1/auth/login.
- The server returns an access token and a refresh token.
- Protected routes require the access token in the Authorization header.
- Refresh tokens can be rotated or revoked through the auth endpoints.
- Password reset requests can be initiated through POST /api/v1/auth/password-reset/request.
- Password reset confirmation is handled through POST /api/v1/auth/password-reset/confirm.
- Email verification requests and confirmations are exposed through POST /api/v1/auth/email-verification/request and POST /api/v1/auth/email-verification/confirm.
- The auth endpoints now dispatch lightweight email notifications through a pluggable delivery service so password reset and verification steps produce a concrete outbound message rather than remaining token-generation stubs.
- Failed login attempts now increment a counter and eventually lock the account for a period of time, improving resilience against brute-force activity.
- Runtime and readiness metadata are surfaced through the platform runtime facade so deployments can introspect the application’s operational state without depending on ad-hoc implementation details.

Implementation notes:

- Login, token creation, and lockout logic are coordinated in backend/application/auth_use_cases.py.
- The router layer in backend/app/api/v1/auth/router.py now focuses on request parsing, audit logging, and delegating to the application use cases.
- Token storage and rotation are managed in backend/common/token_store.py.
- Protected dependencies are defined in backend/common/dependencies.py.
- Password reset and email verification tokens are also stored through the shared token-store layer.

### User CRUD flow

Users follow a standard CRUD lifecycle:

- Create: POST /api/v1/users/
- Read: GET /api/v1/users/{user_id}
- List: GET /api/v1/users/
- Update: PUT /api/v1/users/{user_id}
- Delete: DELETE /api/v1/users/{user_id}

What this means in practice:

- A new user is created with email, username, and password.
- The profile route GET /api/v1/auth/me allows the current user to inspect their own data.
- Updates are restricted so normal users cannot change privileged fields such as is_superuser or role.
- Deletion removes the user record and returns a 204 response.

Implementation notes:

- Routes are defined in backend/app/api/v1/users/router.py.
- Business rules are implemented in backend/domain/users/service.py.
- Persistence is handled by backend/domain/users/repository.py.

### Product CRUD flow

The products module is included as a simple example of a second domain feature, but it has also been strengthened with more realistic query behavior:

- Create: POST /api/v1/products/
- Read: GET /api/v1/products/{product_id}
- List: GET /api/v1/products/
- Update: PUT /api/v1/products/{product_id}
- Delete: DELETE /api/v1/products/{product_id}

The list endpoint now supports optional search, skip/limit pagination, and sorting by fields such as price. This makes the example module behave more like a real API rather than a trivial CRUD scaffold. The OpenAPI schema for product payloads also includes example values so the API documentation is more informative out of the box.

Implementation notes:

- Listing behavior is implemented in backend/domain/products/repository.py and backend/domain/products/service.py.
- Product creation and update now use application use cases in backend/application/product_use_cases.py so the route layer remains thin and the workflow is easy to test.
- The route layer in backend/app/api/v1/products/router.py exposes the new search and sorting parameters and delegates the core behavior to the application layer.
- Request and response schemas for the endpoint live in backend/common/schema.py.
- The public response shapes are also mirrored in backend/contracts so the API boundary remains explicit and reusable across the application layer.

### Admin access flow

Admin access is handled through a lightweight permission-based approach:

- Admin-only routes are defined in backend/app/api/v1/admin/router.py.
- The permissions example endpoint is available at GET /api/v1/admin/permissions.
- Access is granted only when the current user satisfies the required policy.

### Permissions and policy layer

The project now includes a simple but extensible permissions system:

- Users can be assigned a role such as manager.
- Users can also receive a list of explicit permissions.
- Permission checks are performed through policy objects.
- Access decisions can be logged for auditing.

This layer is designed to be easy to understand first and then expanded into a richer authorization model later.

Example registration payload:

```json
{
	"email": "manager@example.com",
	"username": "manager",
	"password": "StrongPass123!",
	"role": "manager",
	"permissions": ["read:admin"]
}
```

Implementation notes:

- User role and permission fields live on the user model in backend/domain/users/model.py.
- The fields are exposed through backend/common/schema.py.
- The example endpoint is implemented in backend/app/api/v1/admin/governance_router.py.
- Permission evaluation helpers are in backend/common/permissions.py.
- Audit events are recorded in backend/common/audit.py.

### Health and readiness

The app exposes basic health endpoints:

- GET /health returns a simple application status payload with the current environment and version.
- GET /health/ready is useful for container orchestration and liveness checks.

These endpoints help verify that the application starts correctly and stays available for traffic.

### WebSocket and real-time flow

The project includes both Socket.IO and a simple WebSocket health route:

- Socket.IO is mounted through backend/app/socketio_app.py.
- The app entrypoint in backend/main.py wires the Socket.IO app into the FastAPI service.
- A simple websocket endpoint is available at /ws/health for lightweight connection testing.
- Product creation emits a Socket.IO event that can be consumed by a connected client for event-driven workflows.

This makes it straightforward to add real-time features such as notifications, live updates, or event-driven workflows later.

## 5. Middleware and cross-cutting concerns

Several features in this project are implemented as cross-cutting middleware or shared helpers rather than being tied to a single route.

### Tracing process and request correlation

The tracing story in this project is now more explicit and useful for debugging. Each incoming request is assigned a request ID and a trace ID, both of which are stored in request state and attached to the response headers as x-request-id and x-trace-id. These values are also bound into the logging context so engineers can follow a single request across middleware, auth, service calls, and error handling.

In practice, the flow looks like this:

1. The HTTP middleware in backend/main.py creates a request ID when one is not supplied and derives a trace ID from the incoming header or request ID.
2. Both values are pushed into the logging context for the duration of the request.
3. The log formatter writes the request ID into every log line for easy correlation.
4. The middleware also records lifecycle events such as request completion, throttling, and request-size rejection.
5. Audit events capture the request context so auth and resource changes can be correlated with the originating request.

This gives the project a practical traceability baseline without requiring a full observability stack. The next evolutionary step is to add OpenTelemetry spans and exporter integration for database, Redis, auth, and Socket.IO boundaries.

### Rate limiting

The project now includes a simple in-memory rate limiter for basic abuse prevention. It is not a full distributed rate limiter, but it provides a practical safeguard for local and single-instance deployments.

### Structured logging

Logging is configured to include request IDs and other context values so that operational troubleshooting is easier. The shared request context helpers also make it practical to pass additional request-scoped metadata beyond the request ID and trace ID when a feature needs it.

### Request size protection

The middleware also rejects requests that exceed a size threshold so oversized payloads are blocked early.

### File uploads

The project now includes a lightweight multipart upload endpoint at POST /api/v1/uploads/. Files are stored in the configured upload directory and return metadata about the saved file. Uploaded assets are also served under /static/uploads so local inspection and integration testing are straightforward. This is intentionally simple and local-first so it can be extended later into object storage or cloud-backed file handling.

## 6. Persistence and data layer

The data layer is intentionally thin and easy to understand, but it now includes more practical initialization and migration support.

- SQLAlchemy async engines and sessions are configured in backend/database.
- The Base model is shared across entities.
- Repositories inherit from shared base classes to reduce repeated boilerplate.
- Alembic migration support is present under alembic/versions, and the initial migration creates the users and products tables.
- A seed-data helper in backend/scripts/seed_data.py can create a default admin account and example products for local development.

When you add a new model, you should also add a corresponding migration so schema evolution remains explicit and controlled. The seed-data helper is intended to simplify local development setup rather than replace proper migration management in production.

## 7. Testing strategy

The project includes automated tests for the main behaviors that matter in a starter backend, and the coverage now extends to the new capabilities added recently:

- health and readiness endpoints
- authentication flow
- admin and permissions access
- refresh-token behavior
- logout revocation
- CRUD behavior for users and products
- negative CRUD cases for missing resources
- duplicate-record handling for users and products
- authorization failures for cross-user updates
- invalid payload validation for users and products
- WebSocket connectivity
- Socket.IO event dispatch behavior
- trace-header propagation for request correlation
- seed-data initialization behavior for default admin and sample products
- product list sorting and OpenAPI schema example rendering
- multipart upload storage and metadata responses

The main test files are:

- tests/test_auth_and_admin.py
- tests/test_refresh_and_health.py
- tests/test_crud_and_socketio.py

Run the test suite with:

```bash
python -m pytest -q
```

The CRUD and websocket tests use an in-memory SQLite database and FastAPI TestClient, which keeps the coverage fast and isolated while still exercising the real app paths. The Socket.IO coverage focuses on the event dispatch behavior exposed by the server layer so that real-time integrations can be validated without needing a full external client stack.

## 8. Shared error handling and orchestration conventions

A new shared exception model now helps the app stay consistent when business rules fail. Domain and application exceptions are translated into structured HTTP responses through backend/common/exceptions.py and handled centrally by the FastAPI app factory.

This means that when your application logic raises a domain-style error such as a duplicate resource, not found, forbidden, or unauthorized condition, the router layer does not need to manually construct a different error payload each time. The error shape is standardized and easy to consume by clients.

The main convention is now:

- Routes receive requests and return responses.
- Use cases contain business orchestration and business-rule decisions.
- Domain services contain business behavior and persistence coordination.
- Shared exceptions translate failures into consistent API responses.

This is now the expected pattern for new features across users, products, and authentication.

## 9. Core files to check when extending the project

When you make changes, these are the primary files to review first:

- backend/main.py: app startup, middleware, router registration, health endpoints, and WebSocket mounting
- backend/app/api/v1/router.py: top-level route registration for all modules
- backend/app/api/v1/users/router.py: user CRUD endpoints
- backend/app/api/v1/products/router.py: product CRUD endpoints and list-query parameters
- backend/application/use_cases.py: shared application workflow entry points and orchestration helpers
- backend/application/ports.py: interfaces for outbound integrations and dependencies
- backend/application/services.py: shared application-layer runtime concerns
- backend/application/user_use_cases.py, backend/application/product_use_cases.py, and backend/application/auth_use_cases.py: domain-specific use-case modules for users, products, and authentication
- backend/domain/users/service.py: auth, password reset, email verification, and lockout logic
- backend/domain/products/service.py and backend/domain/products/repository.py: product business rules and query behavior
- backend/domain/events/**init**.py: domain-event definitions and event payload conventions
- backend/domain/users/repository.py and backend/domain/products/repository.py: persistence access
- backend/integrations/email_adapter.py: adapter implementations for external services
- backend/common/schema.py: request and response models, including OpenAPI examples
- backend/common/dependencies.py: authentication and dependency injection helpers
- backend/common/email.py: pluggable email delivery hooks for password reset and verification messages
- backend/common/permissions.py and backend/common/audit.py: authorization and audit behavior
- backend/common/log.py and backend/common/rate_limit.py: request correlation, logging, and throttling helpers
- backend/common/context.py and backend/common/bootstrap.py: lightweight request-scoped context storage and startup/shutdown hook registration
- backend/scripts/seed_data.py: development seeding for default admin and sample products
- backend/app/socketio_app.py: Socket.IO event handlers and real-time hooks
- tests/test_crud_and_socketio.py, tests/test_enterprise_architecture_layers.py, and tests/test_enterprise_layout.py: regression coverage for the core API and the new enterprise structure

## 10. Deployment-ready package conventions

To make the project more suitable for enterprise-style delivery, the repository now follows a more deliberate package convention:

- backend/application contains orchestration and use-case entry points
- backend/domain contains business entities, services, repositories, and domain events
- backend/infrastructure contains runtime wiring and persistence concerns
- backend/integrations contains adapters for external systems
- backend/common remains the shared support layer for cross-cutting concerns
- backend/app remains focused on transport, routing, and presentation concerns

This convention helps keep infrastructure dependencies, external integrations, and business logic from being mixed together as the system grows.

## 11. Recent changes and next direction

The project has now moved well beyond a basic starter scaffold. These capabilities are now part of the established baseline and should be treated as implemented functionality.

The next high-value improvements are therefore focused on more advanced production work and a stronger enterprise foundation:

- add OpenTelemetry-style span instrumentation for auth, database, Redis, and Socket.IO boundaries as a follow-on observability upgrade
- add object-storage integration such as S3 or Azure Blob Storage for production file handling
- add contract tests for API schemas and backward compatibility
- add a richer domain module such as orders, invoices, or subscriptions as a guided architectural example rather than an app change
- introduce an outbox pattern and event publisher for reliable domain-event propagation
- formalize a container-based deployment strategy with environment promotion across development, staging, and production
