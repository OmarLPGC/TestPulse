from database.db_operations.analysis_jobs import get_run_analysis_job
from database.schemas.user_entity import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.authz import require_project_member
from api.dependencies import get_current_user, get_db_session
from api.schemas.analysis_job_schemas import AnalysisJobRead

router = APIRouter(prefix="/api/v1/projects", tags=["analysis-jobs"])


@router.get(
    "/{project_id}/runs/{run_id}/analysis-job",
    response_model=AnalysisJobRead,
)
def get_run_analysis_job_endpoint(
    project_id: int,
    run_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AnalysisJobRead:
    require_project_member(session, project_id, current_user)

    job = get_run_analysis_job(session, project_id, run_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found.")
    return AnalysisJobRead.model_validate(job)
