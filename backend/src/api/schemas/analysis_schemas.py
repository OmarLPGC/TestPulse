from typing import Optional

from database.enums import TestOutcome
from pydantic import BaseModel
from testpulse.analysis import TestReliability


class TestReliabilityRead(BaseModel):
    test_case_id: int
    name: str
    class_name: Optional[str]
    observations: int
    passed: int
    failed: int
    errors: int
    failure_rate: float
    reliability: TestReliability
    potentially_flaky: bool


class TestReliabilityReport(BaseModel):
    branch: Optional[str]
    window_size: int
    minimum_observations: int
    tests: list[TestReliabilityRead]


class RegressionRead(BaseModel):
    test_case_id: int
    name: str
    class_name: Optional[str]
    previous_outcome: TestOutcome
    current_outcome: TestOutcome


class RunRegressionReport(BaseModel):
    project_id: int
    run_id: int
    branch: Optional[str]
    previous_run_id: Optional[int]
    regressions: list[RegressionRead]
