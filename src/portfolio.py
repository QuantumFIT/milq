import subprocess
import os
import signal
import sys
import queue
import threading

class PortfolioSMTSolver:
    # class that substitutes pysmt portfolio solver
    def __init__(self, solvers: list[tuple[str, str, list[str]]], logic="QF_LIA"):
        # tuples are name, path, supported logics
        self.solvers = solvers
        self.logic = logic
        self.num_workers = min(os.cpu_count(), len(solvers))
        self.threads = []
        self.threads_queue = queue.Queue()
    
    
    def solve(self, formula_file):
        active_solvers = 0
        for solver in self.solvers:
            if self.logic in solver[2]:
                self.threads_queue.put(solver)
        
        return model