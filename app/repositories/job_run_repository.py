from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import JobRun, JobStatus

JOB_NAME_MARKET_DATA = "update_market_data"


class JobRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: JobRun) -> JobRun: 
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, job_run_id: UUID) -> JobRun | None: #find the JobRun
        return self.session.get(JobRun, job_run_id)

    def list_recent( #get recent job history
        self,
        *,
        job_name: str | None = None,
        limit: int = 20,
    ) -> list[JobRun]:
        # newest first; limit is the page size (default 20)
        statement = select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)
        if job_name is not None:
            statement = statement.where(JobRun.job_name == job_name)
        return list(self.session.scalars(statement))

    def get_running(self, job_name: str) -> JobRun | None:
        # see if this job is already running
        statement = (
            select(JobRun)
            .where(
                JobRun.job_name == job_name,
                JobRun.status == JobStatus.RUNNING,
            )
            .limit(1)
        )
        return self.session.scalar(statement)

    def fail_stale_running(self, job_name: str, older_than: timedelta) -> int:
        # mark leftover running rows failed so a new run can start
        """Mark leftover ``running`` rows failed so a new run can start."""
        cutoff = datetime.now(UTC) - older_than
        statement = (
            update(JobRun) #update the JobRun record
            .where(
                JobRun.job_name == job_name,
                JobRun.status == JobStatus.RUNNING,
                JobRun.started_at <= cutoff,
            )
            .values(
                status=JobStatus.FAILED,
                finished_at=datetime.now(UTC),
                error="stale_running",
            )
        )
        result = self.session.execute(statement)
        return result.rowcount or 0 #return the number of rows updated
