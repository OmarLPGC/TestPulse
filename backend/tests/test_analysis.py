from datetime import datetime, timedelta, timezone

import pytest
from database.enums import TestOutcome as Outcome
from testpulse.analysis import (
    TestObservation as Observation,
)
from testpulse.analysis import (
    TestReliability as Reliability,
)
from testpulse.analysis import (
    analyze_test_reliability,
    detect_regressions,
)

BASE_TIME = datetime(2025, 1, 1, tzinfo=timezone.utc)


def observation(run_id: int, outcome: Outcome, test_case_id: int = 1) -> Observation:
    return Observation(
        test_case_id=test_case_id,
        run_id=run_id,
        observed_at=BASE_TIME + timedelta(days=run_id),
        name=f"test_{test_case_id}",
        class_name="tests.test_sample",
        outcome=outcome,
    )


def test_mixed_history_below_minimum_is_insufficient() -> None:
    history = [
        observation(4, Outcome.FAILED),
        observation(3, Outcome.PASSED),
        observation(2, Outcome.PASSED),
        observation(1, Outcome.PASSED),
    ]

    result = analyze_test_reliability(history)[0]

    assert result.observations == 4
    assert result.reliability is Reliability.INSUFFICIENT_DATA
    assert not result.potentially_flaky


def test_all_passing_history_is_stable() -> None:
    history = [observation(run_id, Outcome.PASSED) for run_id in range(1, 6)]

    result = analyze_test_reliability(history)[0]

    assert result.reliability is Reliability.STABLE
    assert result.failure_rate == 0


def test_all_failed_history_is_persistent_failure_not_flaky() -> None:
    history = [observation(run_id, Outcome.FAILED) for run_id in range(1, 6)]

    result = analyze_test_reliability(history)[0]

    assert result.reliability is Reliability.PERSISTENTLY_FAILING
    assert result.failure_rate == 1
    assert not result.potentially_flaky


def test_mixed_pass_and_failure_history_is_potentially_flaky() -> None:
    history = [
        observation(5, Outcome.FAILED),
        observation(4, Outcome.PASSED),
        observation(3, Outcome.PASSED),
        observation(2, Outcome.PASSED),
        observation(1, Outcome.PASSED),
    ]

    result = analyze_test_reliability(history)[0]

    assert result.reliability is Reliability.POTENTIALLY_FLAKY
    assert result.potentially_flaky
    assert result.observations == 5
    assert result.passed == 4
    assert result.failed == 1
    assert result.failure_rate == 0.2


def test_skipped_observations_are_excluded_from_window_and_rate() -> None:
    history = [
        observation(5, Outcome.SKIPPED),
        observation(4, Outcome.PASSED),
        observation(3, Outcome.PASSED),
        observation(2, Outcome.PASSED),
        observation(1, Outcome.PASSED),
        observation(0, Outcome.FAILED),
    ]

    result = analyze_test_reliability(history)[0]

    assert result.observations == 5
    assert result.failed == 1
    assert result.failure_rate == 0.2
    assert result.reliability is Reliability.POTENTIALLY_FLAKY


def test_skips_do_not_satisfy_minimum_observation_count() -> None:
    history = [
        observation(5, Outcome.SKIPPED),
        observation(4, Outcome.PASSED),
        observation(3, Outcome.PASSED),
        observation(2, Outcome.PASSED),
        observation(1, Outcome.PASSED),
    ]

    result = analyze_test_reliability(history)[0]

    assert result.observations == 4
    assert result.reliability is Reliability.INSUFFICIENT_DATA
    assert not result.potentially_flaky


def test_oldest_observation_outside_window_does_not_affect_analysis() -> None:
    history = (
        [observation(21, Outcome.PASSED)]
        + [observation(run_id, Outcome.PASSED) for run_id in range(2, 21)]
        + [observation(1, Outcome.FAILED)]
    )

    result = analyze_test_reliability(history, window_size=20)[0]

    assert result.observations == 20
    assert result.failed == 0
    assert result.reliability is Reliability.STABLE


def test_analysis_is_independent_of_input_order() -> None:
    history = [
        observation(3, Outcome.FAILED),
        observation(5, Outcome.PASSED),
        observation(1, Outcome.PASSED),
        observation(4, Outcome.PASSED),
        observation(2, Outcome.PASSED),
    ]

    forward = analyze_test_reliability(history)
    reverse = analyze_test_reliability(list(reversed(history)))

    assert forward == reverse


def test_error_outcomes_count_as_failures() -> None:
    history = [observation(run_id, Outcome.ERROR) for run_id in range(1, 6)]

    result = analyze_test_reliability(history)[0]

    assert result.reliability is Reliability.PERSISTENTLY_FAILING
    assert result.failed == 0
    assert result.errors == 5


@pytest.mark.parametrize(
    "values",
    [{"window_size": 0}, {"minimum_observations": 0}],
)
def test_analysis_rejects_non_positive_thresholds(values: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        analyze_test_reliability([], **values)


def test_regression_detects_pass_to_failure_but_not_persistent_failure() -> None:
    regressions = detect_regressions(
        current_run_results=[
            observation(2, Outcome.FAILED, test_case_id=1),
            observation(2, Outcome.ERROR, test_case_id=2),
            observation(2, Outcome.PASSED, test_case_id=3),
        ],
        previous_run_results=[
            observation(1, Outcome.PASSED, test_case_id=1),
            observation(1, Outcome.FAILED, test_case_id=2),
            observation(1, Outcome.PASSED, test_case_id=3),
        ],
    )

    assert [regression.test_case_id for regression in regressions] == [1]


def test_new_failed_test_is_not_a_regression() -> None:
    regressions = detect_regressions(
        current_run_results=[observation(2, Outcome.FAILED)],
        previous_run_results=[],
    )

    assert regressions == []


def test_previously_skipped_test_is_not_a_regression() -> None:
    regressions = detect_regressions(
        current_run_results=[observation(2, Outcome.FAILED)],
        previous_run_results=[observation(1, Outcome.SKIPPED)],
    )

    assert regressions == []


def test_regressions_have_stable_identity_order() -> None:
    regressions = detect_regressions(
        current_run_results=[
            observation(2, Outcome.FAILED, test_case_id=3),
            observation(2, Outcome.FAILED, test_case_id=1),
        ],
        previous_run_results=[
            observation(1, Outcome.PASSED, test_case_id=3),
            observation(1, Outcome.PASSED, test_case_id=1),
        ],
    )

    assert [regression.test_case_id for regression in regressions] == [1, 3]
