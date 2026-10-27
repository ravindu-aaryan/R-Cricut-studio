"""Local background job manager.

CPU-heavy work (segmentation, full-resolution renders, exports, variant
generation) runs on a bounded thread pool, never inside a request
handler. Clients poll ``/api/jobs/<id>`` for progress and may cancel.
Work functions receive a :class:`JobHandle` and should call
``handle.progress()`` and check ``handle.cancelled()`` regularly.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class JobTimeout(Exception):
    pass


@dataclass
class Job:
    id: str
    kind: str
    project_id: str | None
    status: str = "queued"  # queued | running | done | error | cancelled
    progress: float = 0.0
    message: str = "Waiting to start"
    result: Any = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    timeout: float | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "projectId": self.project_id, "status": self.status,
            "progress": round(self.progress, 4), "message": self.message, "result": self.result,
            "error": self.error, "created": self.created, "started": self.started, "finished": self.finished,
        }


class JobHandle:
    def __init__(self, job: Job):
        self._job = job

    @property
    def id(self) -> str:
        return self._job.id

    def progress(self, fraction: float, message: str | None = None) -> None:
        self._job.progress = max(self._job.progress, max(0.0, min(1.0, float(fraction))))
        if message:
            self._job.message = message
        self.check()

    def cancelled(self) -> bool:
        j = self._job
        if j.timeout and j.started and time.time() - j.started > j.timeout:
            return True
        return j._cancel.is_set()

    def check(self) -> None:
        j = self._job
        if j._cancel.is_set():
            raise JobCancelled()
        if j.timeout and j.started and time.time() - j.started > j.timeout:
            raise JobTimeout(f"The operation took longer than {int(j.timeout)} seconds and was stopped.")


class JobManager:
    def __init__(self, max_workers: int = 2, default_timeout: float = 300, keep_seconds: float = 3600):
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="oss-job")
        self._jobs: dict[str, Job] = {}
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()
        self.default_timeout = default_timeout
        self.keep_seconds = keep_seconds
        self.max_workers = max_workers

    def submit(self, kind: str, fn: Callable[[JobHandle], Any], *, project_id: str | None = None,
               timeout: float | None = None) -> Job:
        self._gc()
        job = Job(id=uuid.uuid4().hex[:16], kind=kind, project_id=project_id,
                  timeout=timeout if timeout is not None else self.default_timeout)
        with self._lock:
            self._jobs[job.id] = job
        self._futures[job.id] = self._pool.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[JobHandle], Any]) -> Any:
        if job._cancel.is_set():
            job.status, job.message, job.finished = "cancelled", "Cancelled", time.time()
            return None
        job.status, job.started, job.message = "running", time.time(), "Working"
        handle = JobHandle(job)
        try:
            result = fn(handle)
            if job._cancel.is_set():
                raise JobCancelled()
            job.result = result
            job.progress, job.status, job.message = 1.0, "done", "Finished"
            return result
        except JobCancelled:
            job.status, job.message = "cancelled", "Cancelled"
        except JobTimeout as exc:
            job.status, job.error, job.message = "error", str(exc), "Timed out"
        except MemoryError:
            job.status, job.message = "error", "Out of memory"
            job.error = "Not enough memory for this operation. Try a smaller photo or close other applications."
        except OSError as exc:
            job.status, job.message = "error", "File error"
            job.error = ("The disk is full. Free some space and try again." if getattr(exc, "errno", None) == 28
                         else f"A file operation failed: {exc.strerror or exc}")
            log.warning("job %s (%s) failed: %s", job.id, job.kind, exc)
        except Exception as exc:  # noqa: BLE001 - reported to the user, logged in full
            job.status, job.message = "error", "Failed"
            job.error = str(exc) or type(exc).__name__
            log.error("job %s (%s) failed:\n%s", job.id, job.kind, traceback.format_exc())
        finally:
            job.finished = time.time()
        return None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job._cancel.set()
        fut = self._futures.get(job_id)
        if fut is not None and fut.cancel():
            job.status, job.message, job.finished = "cancelled", "Cancelled", time.time()
        return True

    def list(self, project_id: str | None = None) -> list[Job]:
        return [j for j in self._jobs.values() if project_id is None or j.project_id == project_id]

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        fut = self._futures.get(job_id)
        if fut is not None:
            try:
                fut.result(timeout=timeout)
            except FutureTimeout:
                pass
        return self._jobs[job_id]

    def run_sync(self, kind: str, fn: Callable[[JobHandle], Any], *, timeout: float = 30, project_id: str | None = None) -> Any:
        """Run quick work on the pool and wait for it (used for small previews).

        Keeps request threads free of CPU-heavy work while still letting the
        browser receive the image in one round-trip.
        """
        job = self.submit(kind, fn, project_id=project_id, timeout=timeout)
        job = self.wait(job.id, timeout=timeout + 5)
        if job.status == "done":
            return job.result
        if job.status in ("queued", "running"):
            self.cancel(job.id)
            raise JobTimeout("The preview took too long.")
        raise RuntimeError(job.error or job.message)

    def _gc(self) -> None:
        now = time.time()
        with self._lock:
            for jid in [j.id for j in self._jobs.values() if j.finished and now - j.finished > self.keep_seconds]:
                self._jobs.pop(jid, None)
                self._futures.pop(jid, None)

    def shutdown(self) -> None:
        for j in self._jobs.values():
            j._cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)
