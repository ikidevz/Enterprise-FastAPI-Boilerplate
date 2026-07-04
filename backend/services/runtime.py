from __future__ import annotations

from backend.common.background_jobs import background_job_manager
from backend.common.email import email_delivery_service
from backend.common.log import logger
from backend.utils.redis_client import redis_client


class RuntimeServices:
    """Simple runtime service container for enterprise-style access."""

    def __init__(self) -> None:
        self.logger = logger
        self.cache = redis_client
        self.background_jobs = background_job_manager
        self.email_service = email_delivery_service
