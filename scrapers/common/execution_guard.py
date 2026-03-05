import fcntl
import os
import platform
import subprocess
from dataclasses import dataclass


@dataclass
class RunLock:
    fd: int
    path: str


class LockBusyError(RuntimeError):
    pass


def acquire_run_lock(site: str) -> RunLock:
    lock_dir = os.getenv("RUN_LOCK_DIR", "/tmp")
    os.makedirs(lock_dir, exist_ok=True)
    path = os.path.join(lock_dir, f"supplier-scraper-{site}.lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise LockBusyError(f"lock busy: {path}") from exc
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode("utf-8"))
    return RunLock(fd=fd, path=path)


def release_run_lock(lock: RunLock | None) -> None:
    if not lock:
        return
    try:
        fcntl.flock(lock.fd, fcntl.LOCK_UN)
    finally:
        os.close(lock.fd)


def cleanup_site_processes(site: str) -> None:
    # Keep disabled by default. Enable on Linux server with RUNNER_PROCESS_CLEANUP=true.
    if os.getenv("RUNNER_PROCESS_CLEANUP", "false").lower() != "true":
        return
    if platform.system() != "Linux":
        return

    patterns = [
        f"/root/baysync-{site}-stock-scraper/tmp_chrome",
        "/usr/local/bin/chromedriver",
    ]
    for pat in patterns:
        subprocess.run(["pkill", "-f", pat], check=False)
