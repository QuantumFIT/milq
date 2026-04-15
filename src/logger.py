import time
from datetime import datetime
class Logger:
    def __init__(self, filename = None, verbosity: int = 0) -> None:
        self.verbosity = verbosity
        self.start_time = time.time()
        if filename is not None:
            self.file = open(filename, "w")
        else:
            self.file = None
        
    def log(self, tag="INFO", message="") -> None:
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_elapsed = time.time() - self.start_time
        if self.file is not None:
            self.file.write(f"[{time_now}][{time_elapsed:.2f}s][{tag}] : {message}\n")
        else:
            print(f"[{time_now}][{time_elapsed:.2f}s][{tag}] : {message}")