from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Union

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_XML_BYTES = 10 * 1024 * 1024
MAX_TEST_CASES = 100_000
MAX_DURATION_MS = 2_147_483_647


class JUnitReportError(ValueError):
    """Raised when a JUnit XML report is unsafe or invalid."""


class JUnitTestOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ParsedTestCase:
    name: str
    class_name: Optional[str]
    duration_ms: Optional[int]
    outcome: JUnitTestOutcome
    error_message: Optional[str] = None
    traceback: Optional[str] = None


@dataclass(frozen=True)
class ParsedJUnitReport:
    test_cases: tuple[ParsedTestCase, ...]


def parse_junit_xml(xml_content: Union[str, bytes]) -> ParsedJUnitReport:
    """Parse and validate a JUnit XML report without persisting its contents."""
    if isinstance(xml_content, str):
        if len(xml_content) > MAX_XML_BYTES:
            raise JUnitReportError(f"JUnit XML exceeds the {MAX_XML_BYTES}-byte limit.")
        try:
            xml_bytes = xml_content.encode("utf-8")
        except UnicodeEncodeError:
            raise JUnitReportError("JUnit XML must contain valid Unicode text.") from None
    elif isinstance(xml_content, bytes):
        xml_bytes = xml_content
    else:
        raise JUnitReportError("JUnit XML content must be text or bytes.")

    if len(xml_bytes) > MAX_XML_BYTES:
        raise JUnitReportError(f"JUnit XML exceeds the {MAX_XML_BYTES}-byte limit.")

    try:
        root = ElementTree.fromstring(
            xml_bytes,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException, ValueError):
        raise JUnitReportError(
            "JUnit XML is malformed or contains prohibited XML constructs."
        ) from None

    root_name = _local_name(root.tag)
    if root_name not in {"testsuite", "testsuites"}:
        raise JUnitReportError("JUnit XML root element must be <testsuite> or <testsuites>.")

    parsed_cases = []
    seen_identities = set()
    for testcase in root.iter():
        if _local_name(testcase.tag) != "testcase":
            continue
        if len(parsed_cases) >= MAX_TEST_CASES:
            raise JUnitReportError(f"JUnit XML exceeds the {MAX_TEST_CASES}-test limit.")

        name = testcase.get("name")
        if name is None or not name.strip():
            raise JUnitReportError("Each testcase must have a non-empty name.")

        class_name = testcase.get("classname") or None
        identity = (class_name, name)
        if identity in seen_identities:
            identity_label = f"{class_name or '<no class>'}::{name}"
            raise JUnitReportError(
                f"JUnit XML contains a duplicate testcase identity: {identity_label}."
            )
        seen_identities.add(identity)

        duration_ms = _parse_duration(testcase.get("time"), name)
        result_elements = [
            child for child in testcase if _local_name(child.tag) in {"failure", "error", "skipped"}
        ]
        if len(result_elements) > 1:
            raise JUnitReportError(
                f"Testcase {name!r} has multiple outcome elements and is ambiguous."
            )

        if not result_elements:
            outcome = JUnitTestOutcome.PASSED
            error_message = None
            traceback = None
        else:
            result_element = result_elements[0]
            result_type = _local_name(result_element.tag)
            outcome = {
                "failure": JUnitTestOutcome.FAILED,
                "error": JUnitTestOutcome.ERROR,
                "skipped": JUnitTestOutcome.SKIPPED,
            }[result_type]
            error_message = result_element.get("message")
            traceback_text = "".join(result_element.itertext())
            traceback = traceback_text or None

        parsed_cases.append(
            ParsedTestCase(
                name=name,
                class_name=class_name,
                duration_ms=duration_ms,
                outcome=outcome,
                error_message=error_message,
                traceback=traceback,
            )
        )

    return ParsedJUnitReport(test_cases=tuple(parsed_cases))


def _parse_duration(raw_duration: Optional[str], testcase_name: str) -> Optional[int]:
    if raw_duration is None:
        return None

    try:
        duration_seconds = Decimal(raw_duration)
    except InvalidOperation:
        raise JUnitReportError(f"Testcase {testcase_name!r} has a non-numeric duration.") from None

    if not duration_seconds.is_finite() or duration_seconds < 0:
        raise JUnitReportError(f"Testcase {testcase_name!r} has a negative or non-finite duration.")
    if duration_seconds > Decimal(MAX_DURATION_MS) / 1000:
        raise JUnitReportError(
            f"Testcase {testcase_name!r} duration exceeds the supported maximum."
        )

    return int((duration_seconds * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
