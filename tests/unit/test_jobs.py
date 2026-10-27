import time

from app.services.job_service import JobManager


def test_job_progress_and_result():
    jm = JobManager(2)

    def work(h):
        for i in range(5):
            h.progress(i / 5, f"step {i}")
        return 42

    job = jm.wait(jm.submit("t", work).id, timeout=5)
    assert job.status == "done" and job.result == 42 and job.progress == 1.0
    jm.shutdown()


def test_job_cancellation():
    jm = JobManager(1)

    def work(h):
        for _ in range(200):
            time.sleep(0.01)
            h.check()
        return "finished"

    job = jm.submit("slow", work)
    time.sleep(0.05)
    jm.cancel(job.id)
    job = jm.wait(job.id, timeout=5)
    assert job.status == "cancelled"
    jm.shutdown()


def test_job_timeout_and_errors():
    jm = JobManager(1)

    def slow(h):
        while True:
            time.sleep(0.01)
            h.check()

    job = jm.wait(jm.submit("slow", slow, timeout=0.1).id, timeout=5)
    assert job.status == "error" and "longer than" in job.error

    def boom(h):
        raise ValueError("bad input")

    job = jm.wait(jm.submit("boom", boom).id, timeout=5)
    assert job.status == "error" and job.error == "bad input"

    def oom(h):
        raise MemoryError()

    job = jm.wait(jm.submit("oom", oom).id, timeout=5)
    assert "memory" in job.error.lower()
    jm.shutdown()


def test_bounded_concurrency():
    jm = JobManager(2)
    running = []
    peak = []

    def work(h):
        running.append(1)
        peak.append(len(running))
        time.sleep(0.1)
        running.pop()

    jobs = [jm.submit("w", work) for _ in range(6)]
    for j in jobs:
        jm.wait(j.id, timeout=5)
    assert max(peak) <= 2
    jm.shutdown()


def test_run_sync():
    jm = JobManager(1)
    assert jm.run_sync("x", lambda h: "ok") == "ok"
    jm.shutdown()
