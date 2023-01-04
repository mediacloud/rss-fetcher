"""
pid file interlock

Meant to exclude multiple instances of a script run from cron.
Does NOT delay waiting for lock holder to exit, as that would allow
a pileup of processes if the lock holder runs slowly or hangs.

Uses UNIX system calls to atomically create a "pid file"
(file contain process pid).

ASSUMPTION: all instances of script run in same container!
(but putting pid files in a shared volume (/storage/locks) would fix this)
"""

# Phil Budne, January 2023

from enum import Enum
import errno
from os import (
    close, getpid, kill, open, path, read, unlink, write,
    O_CREAT, O_EXCL, O_RDONLY, O_RDWR)
import time
from typing import Any


LOCKDIR = '/tmp'


class LockedException(Exception):
    """thrown if pidfile exists, appears valid"""


class PidFile:
    """
    context manager for a .pid file lock
    """

    def __init__(self, fname: str):
        self._fname = path.join(LOCKDIR, fname + '.pid')

    def _checkpid(self, pid: int) -> bool:
        try:
            kill(pid, 0)    # test if pid is valid
            return True     # pid file is valid
        except OSError as err:
            if err.errno == errno.ESRCH:
                return False    # pid file not valid
            raise

    def _lock(self) -> bool:
        while True:
            try:
                fd = open(self._fname, O_CREAT | O_EXCL | O_RDWR)
                write(fd, f"{getpid()}\n".encode())
                close(fd)
                return True     # got lock
            except OSError as err:
                if err.errno != errno.EEXIST:
                    raise

            # here with EEXIST (lock file exists); validate pidfile
            try:
                fd = open(self._fname, O_RDONLY)
            except OSError as err:
                if err.errno == errno.ENOENT:  # file now missing!
                    continue  # try again
                raise

            # pid file exists, read contents:
            contents = read(fd, 100)
            close(fd)
            try:
                pid = int(contents.decode().strip())
            except ValueError:
                # invalid file contents: remove??
                raise

            # validate pid:
            if self._checkpid(pid):
                # here if process exists
                raise LockedException()

            # pid not valid (process died without removal)
            unlink(self._fname)

    def _unlock(self) -> None:
        try:
            unlink(self._fname)
        except OSError:
            pass

    def __enter__(self) -> "PidFile":
        self._lock()
        return self

    def __exit__(self, *args: Any) -> None:
        self._unlock()


if __name__ == '__main__':
    import os
    pid = os.fork()
    try:
        with PidFile("foo"):
            print(getpid(), "got lock")
            time.sleep(2)
    except LockedException:
        print(getpid(), "failed to get lock")

    if pid:
        os.waitpid(pid, 0)
