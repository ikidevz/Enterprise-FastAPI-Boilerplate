from backend.core.config import settings
from backend.infrastructure.queue.inprocess_queue import InProcessJobQueue
from backend.infrastructure.queue.redis_queue import job_queue as redis_job_queue

if settings.job_queue_backend == "inprocess" or (
    settings.environment == "dev" and settings.job_queue_backend != "redis"
):
    job_queue = InProcessJobQueue()
else:
    job_queue = redis_job_queue

__all__ = ["job_queue"]
