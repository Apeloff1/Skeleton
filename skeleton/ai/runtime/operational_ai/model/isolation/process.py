"""Owned local worker process, minimal environment, bounded termination.

The worker never receives a shell command or model path in public argv. Model
root is transferred through a private anonymous pipe after process creation.
"""
from __future__ import annotations
import os
from pathlib import Path
import signal
import subprocess
import sys
from .contracts import IsolationUnavailable

_ALLOW_ENV = ('PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'HOME', 'LANG', 'LC_ALL',
              'CUDA_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES', 'OMP_NUM_THREADS',
              'GGML_CUDA_FORCE_MMQ')


def sanitized_environment() -> dict[str, str]:
    env = {key: os.environ[key] for key in _ALLOW_ENV if key in os.environ}
    # The only trusted import root comes from this installed/source package.
    # Do not inherit arbitrary operator PYTHONPATH or PYTHONSTARTUP.
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[6])
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    return env


class OwnedWorker:
    def __init__(self, *, retained_fds:tuple[int,...]=()) -> None:
        if os.name != 'posix':
            raise IsolationUnavailable('native process isolation requires POSIX')
        if (type(retained_fds) is not tuple or len(retained_fds)>1
                or any(type(fd) is not int or fd<3 for fd in retained_fds)):
            raise IsolationUnavailable('invalid native capacity descriptors')
        for fd in retained_fds:
            try:os.fstat(fd)
            except OSError as exc:
                raise IsolationUnavailable('native capacity descriptor not open') from exc
        command = [sys.executable, '-u', '-m',
            'skeleton.ai.runtime.operational_ai.model.isolation.worker']
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd='/', env=sanitized_environment(), close_fds=True,
                pass_fds=retained_fds, start_new_session=True, bufsize=0)
        except OSError as exc:
            raise IsolationUnavailable('unable to launch native worker') from exc
        self._closed = False

    @property
    def read_fd(self) -> int:
        if self._closed or self.process.stdout is None:
            raise IsolationUnavailable('native process output is closed')
        return self.process.stdout.fileno()

    @property
    def write_fd(self) -> int:
        if self._closed or self.process.stdin is None:
            raise IsolationUnavailable('native process input is closed')
        return self.process.stdin.fileno()

    def alive(self) -> bool:
        return not self._closed and self.process.poll() is None

    def stop(self, *, grace_ms: int = 2000) -> None:
        if self._closed:
            return
        self._closed = True
        process = self.process
        try:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=grace_ms / 1000)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
            else:
                process.wait(timeout=0)
        finally:
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()

    def __enter__(self) -> 'OwnedWorker':
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
