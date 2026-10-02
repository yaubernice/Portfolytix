from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import JobRun, JobStatus
from app.jobs.market_data_job import JOB_NAME


def test_list_jobs_and_get_job(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    run = JobRun(
        job_name=JOB_NAME,
        status=JobStatus.SUCCESS,
        trigger="cli",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        window_start=datetime.now(UTC).date(),
        window_end=datetime.now(UTC).date(),
        provider="fake",
        fetched=1,
        accepted=1,
        upserted=1,
        skipped_invalid=0,
        failed_tickers=[],
    )
    sqlite_session.add(run)
    sqlite_session.flush()

    listed = client.get("/jobs", params={"job_name": JOB_NAME})
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == str(run.id)
    assert body["items"][0]["status"] == "success"
    assert body["items"][0]["job_name"] == JOB_NAME

    fetched = client.get(f"/jobs/{run.id}")
    assert fetched.status_code == 200
    assert fetched.json()["upserted"] == 1


def test_get_job_404(client: TestClient) -> None:
    response = client.get("/jobs/00000000-0000-4000-8000-000000000099")
    assert response.status_code == 404


def test_jobs_list_empty(client: TestClient) -> None:
    response = client.get("/jobs")
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
