import argparse
import os
import sys
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Optional

import httpx

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ERROR_DETAIL_LENGTH = 500


def _default_commit() -> Optional[str]:
    return os.environ.get("GITHUB_SHA") or os.environ.get("CI_COMMIT_SHA")


def _default_branch() -> Optional[str]:
    return (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or os.environ.get("CI_COMMIT_REF_NAME")
    )


def _default_idempotency_key(project_id: int) -> str:
    run_id = os.environ.get("GITHUB_RUN_ID")
    if run_id:
        repository = os.environ.get("GITHUB_REPOSITORY", "unknown-repository")
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        return f"github-actions:{repository}:{run_id}:{attempt}:{project_id}"
    return str(uuid.uuid4())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testpulse",
        description="Sends a report JUnit XML to TestPulse.",
    )
    parser.add_argument("--url", required=True, help="Base URL of the TestPulse API.")
    parser.add_argument("--project", required=True, type=int, help="Project ID.")
    parser.add_argument("--report", required=True, type=Path, help="Path to the JUnit XML report.")
    parser.add_argument(
        "--commit",
        default=_default_commit(),
        help="Associated commit (default: GITHUB_SHA or CI_COMMIT_SHA).",
    )
    parser.add_argument(
        "--branch",
        default=_default_branch(),
        help="Associated branch (default: GITHUB_REF_NAME or CI_COMMIT_REF_NAME).",
    )
    parser.add_argument(
        "--idempotency-key",
        help=(
            "Idempotency key. In GitHub Actions it is derived from the workflow, run, attempt, and project."
        ),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("TESTPULSE_API_TOKEN"),
        help="Optional API token (default: TESTPULSE_API_TOKEN).",
    )
    return parser


def _request_headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {
        "Content-Type": "application/xml",
        "Idempotency-Key": args.idempotency_key or _default_idempotency_key(args.project),
    }
    if args.commit:
        headers["X-Commit-SHA"] = args.commit
    if args.branch:
        headers["X-Branch"] = args.branch
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    return headers


def _http_error_message(response: httpx.Response) -> str:
    if response.status_code in {401, 403}:
        return f"Authentication rejected by TestPulse (HTTP {response.status_code})."
    if response.status_code >= 500:
        return f"TestPulse returned a server error (HTTP {response.status_code})."

    detail = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
    if not isinstance(detail, str) or not detail.strip():
        detail = response.reason_phrase or "request rejected"
    detail = " ".join(detail.split())[:MAX_ERROR_DETAIL_LENGTH]
    return f"TestPulse rejected the report (HTTP {response.status_code}): {detail}"


def _upload_report(
    args: argparse.Namespace,
    report_content: bytes,
    client_factory: Callable[..., httpx.Client],
) -> int:
    endpoint = f"{args.url.rstrip('/')}/api/v1/projects/{args.project}/runs"
    try:
        with client_factory(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.post(
                endpoint,
                content=report_content,
                headers=_request_headers(args),
            )
    except httpx.InvalidURL:
        print("Error: the TestPulse URL is not valid.", file=sys.stderr)
        return EXIT_FAILURE
    except httpx.TimeoutException:
        print("Error: the timeout was exceeded while connecting to TestPulse.", file=sys.stderr)
        return EXIT_FAILURE
    except httpx.RequestError as error:
        print(f"Network error while connecting to TestPulse: {error}", file=sys.stderr)
        return EXIT_FAILURE

    if response.status_code not in {200, 201}:
        print(_http_error_message(response), file=sys.stderr)
        return EXIT_FAILURE

    try:
        result = response.json()
    except ValueError:
        print("Error: TestPulse returned an invalid success response.", file=sys.stderr)
        return EXIT_FAILURE
    if not isinstance(result, dict) or not isinstance(result.get("id"), int):
        print("Error: TestPulse returned an invalid success response.", file=sys.stderr)
        return EXIT_FAILURE

    action = "reused" if response.status_code == 200 else "created"
    print(
        f"Execution {action} successfully: id={result['id']}, "
        f"status={result.get('status', 'unknown')}."
    )
    return EXIT_SUCCESS


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.project < 1:
        parser.error("--project must be a positive integer.")
    try:
        parsed_url = httpx.URL(args.url)
    except httpx.InvalidURL:
        parser.error("--url is not a valid URL.")
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.host:
        parser.error("--url must start with http:// or https://.")
    args.url = str(parsed_url)

    try:
        report_content = args.report.read_bytes()
    except OSError as error:
        print(
            f"Error: could not read the report '{args.report}': {error.strerror}.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not report_content:
        print(f"Error: the report '{args.report}' is empty.", file=sys.stderr)
        return EXIT_USAGE

    return _upload_report(args, report_content, client_factory)


if __name__ == "__main__":
    raise SystemExit(main())
