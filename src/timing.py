"""
@file: timing.py
@author: Jakub Havlík
@date: 14.10.2026
@brief: timings, accumulated per process; read `times` after a run
"""

import time
from collections import defaultdict
from contextlib import contextmanager

times = defaultdict(float)  # phase name -> seconds
_runs = 0  # runs in the process

@contextmanager
def run():
    # one synthesis: the outermost run starts from zero, a nested one adds to it
    global _runs
    if _runs == 0:
        times.clear()
    _runs += 1
    try:
        yield
    finally:
        _runs -= 1


@contextmanager
def timed(name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        times[name] += time.perf_counter() - start
