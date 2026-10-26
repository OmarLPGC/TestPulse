from typing import Optional

import pytest
from testpulse.junit_parser import (
    MAX_TEST_CASES,
    MAX_XML_BYTES,
    JUnitReportError,
    JUnitTestOutcome,
    parse_junit_xml,
)


def test_parses_passing_testcases_and_converts_seconds_to_milliseconds() -> None:
    report = parse_junit_xml(
        '<testsuite><testcase name="passes" classname="sample.Test" time="0.1254"/>'
        '<testcase name="without-duration"/></testsuite>'
    )

    assert len(report.test_cases) == 2
    assert report.test_cases[0].name == "passes"
    assert report.test_cases[0].class_name == "sample.Test"
    assert report.test_cases[0].duration_ms == 125
    assert report.test_cases[0].outcome is JUnitTestOutcome.PASSED
    assert report.test_cases[1].duration_ms is None
    assert report.test_cases[1].outcome is JUnitTestOutcome.PASSED


def test_parses_bytes_and_all_outcomes_in_one_report() -> None:
    report = parse_junit_xml(
        b'<testsuites><testsuite><testcase name="passed"/>'
        b'<testcase name="failed"><failure message="assertion"/></testcase>'
        b'<testcase name="errored"><error/></testcase>'
        b'<testcase name="skipped"><skipped/></testcase>'
        b"</testsuite></testsuites>"
    )

    assert [test.outcome for test in report.test_cases] == [
        JUnitTestOutcome.PASSED,
        JUnitTestOutcome.FAILED,
        JUnitTestOutcome.ERROR,
        JUnitTestOutcome.SKIPPED,
    ]
    assert report.test_cases[1].error_message == "assertion"


@pytest.mark.parametrize(
    ("element", "expected_outcome", "message"),
    [
        (
            '<failure message="assertion failed">trace</failure>',
            JUnitTestOutcome.FAILED,
            "assertion failed",
        ),
        ('<error message="unexpected exception"/>', JUnitTestOutcome.ERROR, "unexpected exception"),
        ('<skipped message="not applicable"/>', JUnitTestOutcome.SKIPPED, "not applicable"),
    ],
)
def test_parses_testcase_outcomes(
    element: str, expected_outcome: JUnitTestOutcome, message: str
) -> None:
    report = parse_junit_xml(f'<testsuite><testcase name="case">{element}</testcase></testsuite>')

    assert report.test_cases[0].outcome is expected_outcome
    assert report.test_cases[0].error_message == message


def test_preserves_failure_traceback() -> None:
    report = parse_junit_xml(
        '<testsuite><testcase name="case">'
        '<failure message="assertion failed">expected 1, got 2</failure>'
        "</testcase></testsuite>"
    )

    assert report.test_cases[0].traceback == "expected 1, got 2"


@pytest.mark.parametrize(
    "element",
    [
        '<testcase name="failed"><failure/></testcase>',
        '<testcase name="errored"><error/></testcase>',
        '<testcase name="skipped"><skipped/></testcase>',
    ],
)
def test_classifies_each_outcome_independently(element: str) -> None:
    report = parse_junit_xml(
        f"<testsuites><testsuite>{element}</testsuite>"
        '<testsuite><testcase name="passed"/></testsuite></testsuites>'
    )

    assert report.test_cases[0].outcome in {
        JUnitTestOutcome.FAILED,
        JUnitTestOutcome.ERROR,
        JUnitTestOutcome.SKIPPED,
    }
    assert report.test_cases[1].outcome is JUnitTestOutcome.PASSED


@pytest.mark.parametrize(
    "xml",
    [
        "<testsuite><testcase>",
        "<testsuite><testcase name='x'></testsuite>",
        "",
        "<not-a-report/>",
    ],
)
def test_rejects_malformed_or_unsupported_xml(xml: str) -> None:
    with pytest.raises(JUnitReportError):
        parse_junit_xml(xml)


@pytest.mark.parametrize("name", ["", "   ", None])
def test_rejects_testcase_without_name(name: Optional[str]) -> None:
    attribute = "" if name is None else f' name="{name}"'

    with pytest.raises(JUnitReportError, match="non-empty name"):
        parse_junit_xml(f"<testsuite><testcase{attribute}/></testsuite>")


@pytest.mark.parametrize("duration", ["-0.01", "NaN", "Infinity", "abc", ""])
def test_rejects_invalid_duration(duration: str) -> None:
    with pytest.raises(JUnitReportError):
        parse_junit_xml(f'<testsuite><testcase name="case" time="{duration}"/></testsuite>')


def test_rejects_duplicate_testcase_identities() -> None:
    xml = (
        '<testsuite><testcase classname="sample.Test" name="case"/>'
        '<testcase classname="sample.Test" name="case"/></testsuite>'
    )

    with pytest.raises(JUnitReportError, match="duplicate testcase identity"):
        parse_junit_xml(xml)


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE testsuite [<!ENTITY xxe SYSTEM "file:///secret">]>'
        '<testsuite><testcase name="&xxe;"/></testsuite>',
        '<!DOCTYPE testsuite SYSTEM "http://example.invalid/testsuite.dtd"><testsuite/>',
    ],
)
def test_rejects_dtd_and_entity_constructs(xml: str) -> None:
    with pytest.raises(JUnitReportError):
        parse_junit_xml(xml)


def test_accepts_empty_report() -> None:
    report = parse_junit_xml("<testsuites><testsuite/></testsuites>")

    assert report.test_cases == ()


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        ("x" * (MAX_XML_BYTES + 1), "byte limit"),
        (
            "<testsuite>"
            + "".join(f'<testcase name="{index}"/>' for index in range(MAX_TEST_CASES + 1))
            + "</testsuite>",
            "test limit",
        ),
    ],
    ids=["size-limit", "test-count-limit"],
)
def test_enforces_report_size_and_test_count_limits(xml: str, message: str) -> None:
    with pytest.raises(JUnitReportError, match=message):
        parse_junit_xml(xml)
