from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from database.enums import TestOutcome


class TestReliability(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    STABLE = "stable"
    PERSISTENTLY_FAILING = "persistently_failing"
    POTENTIALLY_FLAKY = "potentially_flaky"


@dataclass(frozen=True)
class TestObservation:
    test_case_id: int
    run_id: int
    observed_at: datetime
    name: str
    class_name: Optional[str]
    outcome: TestOutcome


@dataclass(frozen=True)
class TestReliabilityAnalysis:
    test_case_id: int
    name: str
    class_name: Optional[str]
    observations: int
    passed: int
    failed: int
    errors: int
    failure_rate: float
    reliability: TestReliability

    @property
    def potentially_flaky(self) -> bool:
        return self.reliability is TestReliability.POTENTIALLY_FLAKY


@dataclass(frozen=True)
class Regression:
    test_case_id: int
    name: str
    class_name: Optional[str]
    previous_outcome: TestOutcome
    current_outcome: TestOutcome


def analyze_test_reliability(
    observations: Sequence[TestObservation],
    *,
    window_size: int = 20,
    minimum_observations: int = 5,
) -> list[TestReliabilityAnalysis]:
    if window_size < 1:
        raise ValueError("window_size must be at least 1.")
    if minimum_observations < 1:
        raise ValueError("minimum_observations must be at least 1.")

    observations_by_test: dict[int, list[TestObservation]] = defaultdict(list)
    for observation in observations:
        if observation.outcome is not TestOutcome.SKIPPED:
            observations_by_test[observation.test_case_id].append(observation)

    analyses = []
    for test_case_id in sorted(observations_by_test):
        history = sorted(
            observations_by_test[test_case_id],
            key=lambda item: (item.observed_at, item.run_id),
            reverse=True,
        )[:window_size]
        passed = sum(item.outcome is TestOutcome.PASSED for item in history)
        failed = sum(item.outcome is TestOutcome.FAILED for item in history)
        errors = sum(item.outcome is TestOutcome.ERROR for item in history)
        unsuccessful = failed + errors
        total = len(history)

        if total < minimum_observations:
            reliability = TestReliability.INSUFFICIENT_DATA
        elif passed and unsuccessful:
            reliability = TestReliability.POTENTIALLY_FLAKY
        elif unsuccessful == total:
            reliability = TestReliability.PERSISTENTLY_FAILING
        else:
            reliability = TestReliability.STABLE

        latest = history[0]
        analyses.append(
            TestReliabilityAnalysis(
                test_case_id=test_case_id,
                name=latest.name,
                class_name=latest.class_name,
                observations=total,
                passed=passed,
                failed=failed,
                errors=errors,
                failure_rate=round(unsuccessful / total, 4) if total else 0.0,
                reliability=reliability,
            )
        )
    return analyses


def detect_regressions(
    *,
    current_run_results: Sequence[TestObservation],
    previous_run_results: Sequence[TestObservation],
) -> list[Regression]:
    previous_by_test = {item.test_case_id: item for item in previous_run_results}
    regressions = []
    for current in current_run_results:
        previous = previous_by_test.get(current.test_case_id)
        if (
            previous is not None
            and previous.outcome is TestOutcome.PASSED
            and current.outcome in {TestOutcome.FAILED, TestOutcome.ERROR}
        ):
            regressions.append(
                Regression(
                    test_case_id=current.test_case_id,
                    name=current.name,
                    class_name=current.class_name,
                    previous_outcome=previous.outcome,
                    current_outcome=current.outcome,
                )
            )
    return sorted(
        regressions,
        key=lambda item: (item.class_name or "", item.name, item.test_case_id),
    )
