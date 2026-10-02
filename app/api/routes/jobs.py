from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_job_service
from app.schemas.job import JobRunListOut, JobRunOut
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobRunListOut)
def list_jobs(
    job_name: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    service: JobService = Depends(get_job_service),
) -> JobRunListOut:
    items = service.list_runs(job_name=job_name, limit=limit) #calling the service
    return JobRunListOut( #convert database objects to reponse schema
        items=[JobRunOut.model_validate(row) for row in items],
        count=len(items),
    )


@router.get("/{job_run_id}", response_model=JobRunOut)
def get_job( #get a single job run by its ID
    job_run_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobRunOut:
    # convert the database object to the response schema
    return JobRunOut.model_validate(service.get_run(job_run_id))
