"""
@file: logger.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: logger module to save logging info into .log files
"""

import time
from datetime import datetime

class Logger:
    def __init__(self, filename = None, verbosity: int = 0) -> None:
        self.verbosity = verbosity
        self.start_time = time.time()
        self.times = {}
        self.times['full'] = 0
        self.times['parsing'] = 0
        self.times['encoding'] = 0
        self.times['solving'] = 0
        self.times['updating'] = 0
        if filename is not None:
            self.file = open(filename, "w")
        else:
            self.file = None
        
    def log(self, tag="INFO", message="") -> None:
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_elapsed = time.time() - self.start_time
        if self.file is not None:
            self.file.write(f"[{time_now}][{time_elapsed:.2f}s][{tag}] : {message}\n")
            self.file.flush()
        else:
            print(f"[{time_now}][{time_elapsed:.2f}s][{tag}] : {message}")
            
    def update_time(self, tag: str, time: float) -> None:
        if tag not in self.times:
            self.times[tag] = 0
        self.times[tag] += time
    
    def get_times(self) -> dict:
        return self.times