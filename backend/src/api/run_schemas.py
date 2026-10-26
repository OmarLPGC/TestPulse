from typing import Optional

from database.enums import TestOutcome, TestRunStatus
from pydantic import BaseModel


class TestResultRead(BaseModel):
    id: int
    test_case_id: int
    name: str
    class_name: Optional[str]
    outcome: TestOutcome
    duration: Optional[int]
    error_message: Optional[str]
    traceback: Optional[str]


class TestRunRead(BaseModel):
    id: int
    project_id: int
    commit_sha: Optional[str]
    branch: Optional[str]
    report_sha: str
    status: TestRunStatus
    duration: Optional[int]
    test_results: list[TestResultRead]
