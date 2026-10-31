from datetime import datetime
from typing import Any, Optional

from database.enums import AnalysisJobStatus
from pydantic import BaseModel, ConfigDict


class AnalysisJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    test_run_id: int
    status: AnalysisJobStatus
    attempts: int
    max_attempts: int
    last_error: Optional[str]
    result: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
