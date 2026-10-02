from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import JobRun
from app.repositories.job_run_repository import JobRunRepository

MAX_LIST = 100


class JobService:
    """Read-only job status. Starting ingest is the scheduler or CLI."""

    def __init__(self, session: Session) -> None:
        self.jobs = JobRunRepository(session)

    def list_runs(
        self,
        *,
        job_name: str | None = None,
        limit: int = 20,
    ) -> list[JobRun]:
        capped = min(max(limit, 1), MAX_LIST)
        name = job_name.strip() if job_name else None
        return self.jobs.list_recent(job_name=name or None, limit=capped)

    def get_run(self, job_run_id: UUID) -> JobRun:
        run = self.jobs.get(job_run_id)
        if run is None:
            raise NotFoundError(f"Job run {job_run_id} not found")
        return run
