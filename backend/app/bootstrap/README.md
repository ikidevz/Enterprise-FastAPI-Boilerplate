# Application bootstrap modules

This package contains the registration hooks used to assemble the FastAPI application in a layered, enterprise-friendly way.

- router_registry.py registers API and health routers
- middleware_registry.py registers shared middleware
- static_registry.py registers upload/static assets

Keeping these registrations separate makes the app easier to evolve as new modules and integrations are added.
