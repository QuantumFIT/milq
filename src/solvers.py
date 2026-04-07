import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
    
class SMTSolver:
    def __init__(self, name: str, args: list[str], logics: list[str]):
        self.name = name
        self.args = args
        self.logics = logics
    
    def solve(self, formula_file):
            try:
                result = subprocess.Popen(
                    self.args + [formula_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                
                stdout, stderr = result.communicate()
            except Exception as e:
                return None
            if result is None:
                return None
            if result.returncode != 0:
                return None
            if ("sat" in stdout.lower() and "unsat" not in stdout.lower()) or "delta-sat" in stdout.lower():
                return stdout 
            else:
                return None


class PortfolioSMTSolver:
    # class that substitutes pysmt portfolio solver
    def __init__(self, solvers: dict[str, SMTSolver], logic="QF_LIA"):
        new_dict = {}
        for name, solver in solvers.items():
            if logic in solver.logics:
                new_dict[name] = solver
        self.solvers = new_dict
        self.logic = logic
        self.num_workers = min(os.cpu_count(), len(self.solvers))
    
    
    def solve(self, formula_file):
        processes = {}
        for name, solver in self.solvers.items():
            cmd = solver.args + [formula_file]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            processes[name] = proc

        while processes:
            for name, proc in list(processes.items()):
                ret = proc.poll()
                if ret is None:
                    continue
                stdout, stderr = proc.communicate()
                for other_name, other_proc in processes.items():
                    if other_name != name:
                        other_proc.kill()

                if ret == 0 and (("sat" in stdout.lower() and "unsat" not in stdout.lower()) or "delta-sat" in stdout.lower()):
                    return stdout
                else:
                    return None