import argparse
import logging
import time
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from testpulse.analysis_worker import (
    DEFAULT_JOB_LEASE_SECONDS,
    process_next_analysis_job,
)
from testpulse.config import load_settings

DEFAULT_POLL_INTERVAL_SECONDS = 1.0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testpulse-worker",
        description="Processes durable TestPulse analysis jobs.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one available job and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds to wait when no jobs are available (default: 1).",
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=DEFAULT_JOB_LEASE_SECONDS,
        help=(
            "Seconds before an abandoned claim can be recovered "
            f"(default: {DEFAULT_JOB_LEASE_SECONDS})."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than zero.")
    if args.lease_seconds < 1:
        parser.error("--lease-seconds must be at least 1.")

    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("TestPulse analysis worker started.")
    try:
        if args.once:
            process_next_analysis_job(
                engine,
                lease_seconds=args.lease_seconds,
            )
            return 0

        while True:
            try:
                worked = process_next_analysis_job(
                    engine,
                    lease_seconds=args.lease_seconds,
                )
            except SQLAlchemyError:
                logger.exception("Could not reach the analysis job store; retrying.")
                time.sleep(args.poll_interval)
                continue
            if not worked:
                time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        logger.info("TestPulse analysis worker stopped.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
