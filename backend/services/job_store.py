from models.schemas import JobStatus
from datetime import datetime, timezone
import asyncio
import uuid


class JobStore:
    def __init__(self):
        self._jobs: dict[str, JobStatus] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> JobStatus:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        job = JobStatus(
            job_id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self._jobs[job_id] = job
        return job

    async def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id) or None

    async def update_status(self, job_id: str, status: str, **kwargs) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = status
            for key, value in kwargs.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(timezone.utc).isoformat()

    async def list_all(self) -> list[JobStatus]:
        return sorted(
            self._jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )


job_store = JobStore()
