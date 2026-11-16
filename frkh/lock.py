"""Verrou inter-processus : une seule génération à la fois (Linux, macOS et Windows).

Le verrou est posé par le système sur un fichier ouvert ; il disparaît de
lui-même si le processus s'arrête brutalement, sans laisser de verrou fantôme.
"""

from __future__ import annotations

import os
from pathlib import Path


class AlreadyRunning(Exception):
    pass


class ProcessLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise AlreadyRunning("Une génération est déjà en cours (verrou actif).") from None
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
