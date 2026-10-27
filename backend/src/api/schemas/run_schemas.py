from datetime import datetime
from typing import Optional

from database.enums import TestOutcome, TestRunStatus
from pydantic import BaseModel, ConfigDict


class TestResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class TestRunHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    commit_sha: Optional[str]
    branch: Optional[str]
    report_sha: Optional[str]
    status: TestRunStatus
    duration: Optional[int]
    ingested_at: datetime
    completed_at: Optional[datetime]


class TestRunHistoryPage(BaseModel):
    items: list[TestRunHistoryItem]
    limit: int
    offset: int
    total: int


class TestRunSummaryRead(TestRunHistoryItem):
    total: int
    passed: int
    failed: int
    skipped: int
    error: int


class TestResultPage(BaseModel):
    items: list[TestResultRead]
    limit: int
    offset: int
    total: int
