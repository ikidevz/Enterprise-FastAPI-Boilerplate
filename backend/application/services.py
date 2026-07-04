from __future__ import annotations

from backend.common.background_jobs import background_job_manager
from backend.common.email import email_delivery_service
from backend.common.log import logger
from backend.common.observability import metrics_collector
from backend.common.rate_limit import shared_rate_limiter


class ApplicationServices:
    def __init__(self) -> None:
        self.logger = logger
        self.metrics = metrics_collector
        self.rate_limiter = shared_rate_limiter
        self.background_jobs = background_job_manager
        self.email = email_delivery_service
