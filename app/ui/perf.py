"""Temporary / lightweight UI performance logging."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("vless.perf")


@contextmanager
def perf(label: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        msg = f"[PERF] {label} = {ms:.1f} ms"
        logger.info(msg)
        print(msg, flush=True)
