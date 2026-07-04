# Enterprise FastAPI Boilerplate

A production-oriented FastAPI starter project built around a pragmatic enterprise-ready architecture. It is designed to be easy to understand, straightforward to extend, and suitable for building serious backend services without starting from a completely empty scaffold.

This repository now goes beyond a conventional starter template by making application use cases, integration adapters, and domain events explicit. It provides a working foundation for authentication, CRUD, file uploads, real-time features, middleware, observability, configuration management, infrastructure registration, and testing in a single cohesive backend platform.

![Enterprise FastAPI Boilerplate](https://tdhghaslnufgtzjybhhf.supabase.co/storage/v1/object/public/content/Enterprise%20FastAPI%20Boilerplate/cover.png)

## Table of Contents

- [Overview](#overview)
- [Why this project](#why-this-project)
- [Architecture](#architecture)
- [Core features](#core-features)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API overview](#api-overview)
- [Development workflow](#development-workflow)
- [Testing](#testing)
- [Deployment notes](#deployment-notes)
- [Roadmap](#roadmap)
- [Documentation](#documentation)

## Overview

Tier 4 Architecture is a backend starter focused on clarity and maintainability. It separates concerns into four layers so that business logic, infrastructure concerns, API concerns, and shared utilities remain easy to reason about as the project grows.

### What you get out of the box

- A fully runnable FastAPI application with health endpoints and OpenAPI docs
- Authentication and authorization primitives for users and admin-style access
- A sample product module to demonstrate CRUD patterns and query behavior
- File upload handling with local storage and static serving
- Middleware for request context, correlation headers, rate limiting, and payload protection
- Configuration support with environment profiles and secret-file resolution
- Email delivery hooks for password reset and verification flows
- An explicit infrastructure layer for logging, cache, background workers, and runtime service registration
- Automated tests that cover core backend behaviors

## Why this project

This project is intentionally practical rather than theoretical. It aims to provide a foundation that feels close to what you would actually ship in a modern backend service:

- Clear separation of concerns
- Fast iteration for new features
- Built-in support for common operational concerns
- Easy onboarding for developers who are new to FastAPI and layered architecture
- Strong test coverage around the most important flows

Whether you are building an internal tool, a SaaS backend, or a learning project, this starter gives you a ready-made structure to build upon.

## Architecture

The project follows a pragmatic enterprise-style architecture that is easy to extend while still staying approachable:

1. Presentation Layer
   - FastAPI routers and handlers
   - Request/response validation with Pydantic
   - WebSocket and Socket.IO endpoints
   - OpenAPI documentation

2. Application Layer
   - Explicit use cases such as registration workflows
   - Ports and adapters that isolate external integrations from business rules
   - Lightweight orchestration that keeps route handlers thin

3. Domain Layer
   - Business logic in services
   - Persistence logic in repositories
   - Domain models for users, products, and related entities
   - Domain events that communicate meaningful state changes across the system

4. Infrastructure Layer
   - Async SQLAlchemy sessions and model setup
   - Redis-backed token storage and runtime helpers
   - Explicit registration for logging, cache, background workers, email delivery, and runtime services
   - Deployment-ready configuration conventions for environment-specific behavior

This layering helps keep the codebase maintainable as it matures into a more formal enterprise platform.

## Core features

### Authentication and session management

The starter includes a functional authentication workflow with:

- User registration
- Login and logout
- Access-token and refresh-token support
- Password reset flow
- Email verification flow
- Account lockout protection after repeated failed attempts
- Lightweight email notifications for password reset and verification actions

### User and admin workflows

- CRUD endpoints for users
- Profile access for the current authenticated user
- Admin-style access examples with permission checks
- Governance-style permission evaluation examples

### Product module

A sample product domain is included to demonstrate a typical second feature module with:

- Create, read, update, and delete operations
- Search and filtering support
- Sorting and pagination-friendly list behavior

### Files and media

- Multipart file upload endpoint
- Local file storage by default
- Static serving for uploaded files under /static/uploads

### Reliability and observability

- Request ID and trace ID propagation
- Structured logging with request context
- Rate limiting to reduce abuse and accidental traffic spikes
- Request-size protection for oversized payloads
- Health and readiness checks for deployment and monitoring
- A lightweight runtime facade and explicit API contracts for operational introspection and service boundaries
- OpenTelemetry-compatible tracing hooks for basic and production-style deployments

### Real-time support

- Socket.IO integration for event-driven communication
- WebSocket-based health endpoint for lightweight connection testing

## Project structure

The repository is organized for clarity and extensibility:

- [backend/app](backend/app) — API routes, auth endpoints, Socket.IO wiring, and router composition
- [backend/application](backend/application) — explicit use cases and application orchestration for enterprise workflows
- [backend/domain](backend/domain) — services, repositories, business logic, and domain events
- [backend/database](backend/database) — database session setup, engines, and models
- [backend/common](backend/common) — shared abstractions such as schemas, dependencies, permissions, logging, audit, context helpers, and bootstrap support
- [backend/infrastructure](backend/infrastructure) — infrastructure package for runtime registration, persistence wiring, and shared service hooks
- [backend/integrations](backend/integrations) — adapter layer for outbound services such as email delivery
- [backend/services](backend/services) — explicit runtime service container for logging, cache, background workers, and email delivery
- [backend/app/factory.py](backend/app/factory.py) — centralized FastAPI application construction and app assembly
- [backend/app/bootstrap](backend/app/bootstrap) — enterprise-style registration modules for routers, middleware, and static assets
- [backend/app/infrastructure.py](backend/app/infrastructure.py) — compatibility entrypoint for infrastructure registration
- [backend/platform](backend/platform) — runtime facade for environment-aware snapshots and operational metadata
- [backend/contracts](backend/contracts) — explicit API contracts for health, metrics, auth, users, and products
- [backend/utils](backend/utils) — runtime utilities such as the Redis client and related helpers
- [tests](tests) — regression and behavior tests for the main backend flows
- [alembic](alembic) — migration scaffolding and schema evolution support

## Quick start

### Prerequisites

- Python 3.10 or newer
- A virtual environment tool such as venv or conda
- Optional: Docker and Docker Compose for containerized development

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd main
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy [.env.example](.env.example) to .env and adjust the values as needed.

At minimum, you will typically want to review:

- DATABASE_URL
- REDIS_URL
- SECRET_KEY
- EMAIL_BACKEND
- SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD
- ENABLE_TRACING / OTEL_MODE / OTEL_EXPORTER_OTLP_ENDPOINT

### 5. Run the application

```bash
uvicorn backend.main:app --reload
```

The API docs will be available at:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/redoc

### 6. Optional: run with Docker

```bash
docker compose up --build
```

## Configuration

The application uses environment-based configuration with support for profile-specific files and secret-file resolution. This helps keep credentials and deployment-specific settings out of the source tree.

Common settings include:

- Project metadata such as name and API version prefix
- Database and Redis connection strings
- Secret keys and signing algorithms
- CORS origins
- Rate limiting settings
- Upload directory location
- Email backend configuration for console or SMTP delivery

If you are deploying to a real environment, it is strongly recommended to provide secrets through environment variables or mounted secret files rather than hardcoding them.

## API overview

The application exposes a modern REST-style API via the v1 router.

### Primary routes

- POST /api/v1/users/ — register a user
- POST /api/v1/auth/login — authenticate a user
- POST /api/v1/auth/refresh — rotate a refresh token
- POST /api/v1/auth/logout — revoke a refresh token
- POST /api/v1/auth/password-reset/request — start password reset
- POST /api/v1/auth/password-reset/confirm — complete password reset
- POST /api/v1/auth/email-verification/request — request email verification
- POST /api/v1/auth/email-verification/confirm — confirm verification
- GET /health — application health payload
- GET /health/ready — readiness checks for database and Redis
- GET /runtime — platform-level runtime snapshot with environment and uptime metadata
- GET /metrics — collected request metrics for observability
- POST /api/v1/uploads/ — upload a file

### Example request

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=StrongPass123!"
```

## Development workflow

A simple and maintainable development workflow is encouraged:

1. Keep routers thin and focused on HTTP concerns
2. Put business rules into services instead of route handlers
3. Keep repositories focused on persistence logic
4. Reuse the shared abstractions in [backend/common](backend/common)
5. Prefer explicit, validated schemas over ad-hoc dictionaries
6. Register new infrastructure concerns through [backend/app/infrastructure.py](backend/app/infrastructure.py) instead of scattering runtime wiring throughout the app
7. Add regression tests whenever behavior changes

### Adding a new feature module

A typical feature follows this pattern:

1. Create a domain model in [backend/domain](backend/domain)
2. Add a repository for persistence logic
3. Add a service for application/business rules
4. Define schemas for request and response payloads
5. Add API routes under [backend/app/api/v1](backend/app/api/v1)
6. Register the router in [backend/app/api/v1/router.py](backend/app/api/v1/router.py)
7. Add any necessary infrastructure support such as storage, cache, or background jobs

## Testing

The repository includes a comprehensive test suite for the main backend flows.

Run the full suite with:

```bash
pytest -q
```

The suite covers:

- Authentication and authorization flows
- User CRUD behavior
- Product CRUD and query behavior
- Health and readiness endpoints
- Upload handling
- WebSocket and Socket.IO interaction
- Trace header propagation and request correlation
- Seed-data initialization

## Deployment notes

The project is prepared for local development and can be extended for container-based deployment.

Recommended production hardening steps include:

- Use a real database instead of local development defaults where appropriate
- Configure environment variables or secret files for all credentials
- Enable proper TLS and reverse-proxy settings
- Replace the default in-memory or local-first behaviors with durable infrastructure when necessary
- Add monitoring, logging aggregation, and alerting for operational visibility
- Promote configuration through environment-specific profiles rather than relying on local defaults
- Add deployment health checks and readiness probes that consume /health/ready and /runtime

Docker support is already present through the provided compose and container configuration files.

## Roadmap

The project is already more than a blank starter, but there are still plenty of opportunities to improve it:

- Add richer Alembic migrations and stronger seed-data workflows
- Introduce more mature cache and background-task orchestration patterns for distributed deployments
- Expand observability with OpenTelemetry and richer metrics
- Add additional business modules such as orders, invoices, or audit logs
- Evolve the permissions system into a fuller authorization model
- Add cloud-native storage and queue integrations for production workloads
- Formalize use-case tests and contract tests around the application layer
- Introduce a richer event bus and outbox pattern for reliable domain-event propagation

## Documentation

For a deeper explanation of the architecture, design decisions, and extension patterns, see:

- [DOCUMENTATION.md](DOCUMENTATION.md)
