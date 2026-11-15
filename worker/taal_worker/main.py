"""Taal worker: takes one job at a time from taal_jobs and runs it."""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
import traceback

from .db import Db
from .jobs import HANDLERS

log = logging.getLogger("taal")
POLL_SECONDS = float(os.environ.get("TAAL_POLL_SECONDS", "5"))
NEEDED = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_one(db: Db) -> bool:
    job = db.claim_job()
    if job is None:
        return False
    log.info("job %s %s (attempt %s)", job["id"], job["type"], job["attempts"])
    handler = HANDLERS.get(job["type"])
    try:
        if handler is None:
            raise RuntimeError(f"no handler for job type {job['type']!r}")
        result = handler(db, job)
        db.update(
            "taal_jobs", job["id"], {"status": "done", "result": result, "finished_at": _now()}
        )
        log.info("job %s done", job["id"])
    except Exception as exc:  # the job fails; the worker carries on
        log.error("job %s failed: %s\n%s", job["id"], exc, traceback.format_exc())
        db.update(
            "taal_jobs",
            job["id"],
            {"status": "failed", "error": str(exc)[:2000], "finished_at": _now()},
        )
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    missing = [name for name in NEEDED if not os.environ.get(name)]
    if missing:
        # Stay up and say what is missing, so the deploy does not crash-loop.
        while True:
            log.warning("waiting: set %s on this service", ", ".join(missing))
            time.sleep(60)
    db = Db()
    log.info("taal worker started; job types: %s", ", ".join(sorted(HANDLERS)))
    while True:
        try:
            worked = run_one(db)
        except Exception as exc:
            log.error("queue error: %s", exc)
            worked = False
        if not worked:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
