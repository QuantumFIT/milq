import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
    
class SMTSolver:
    def __init__(self, name: str, args: list[str], logics: list[str], smtlib_flags: list[str] | None = None, incremental_mode: bool = False):
        self.name = name
        self.args = args
        self.logics = logics
        self.smtlib_flags = smtlib_flags or []
        self.incremental_mode = incremental_mode
        self.process = None
            
    def create_process(self):
        self.process = subprocess.Popen(
            self.args + self.smtlib_flags,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def solve(self, formula_file : str = None) -> str:
        if self.incremental_mode:
            # formula sent to the solver, add check-sat and get-model, retreive result
            result = self.process.stdout.readline()
            # smtinterpol return 'success' first after each statement, 
            while 'success' in result.lower():
                result = self.process.stdout.readline()

            if ("sat" in result.lower() and "unsat" not in result.lower()) or "delta-sat" in result.lower():
                return "sat"
            elif "unknown" in result.lower():
                return "unknown"
            else:
                return "unsat"
        else:
            try:
                print(self.args + self.smtlib_flags + [formula_file])
                result = subprocess.Popen(
                    self.args + self.smtlib_flags + [formula_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                
                stdout, stderr = result.communicate()
            except Exception as e:
                return "unknown"
            if result is None:
                return "unknown"
            if result.returncode != 0:
                return "unknown"
            if ("sat" in stdout.lower() and "unsat" not in stdout.lower()) or "delta-sat" in stdout.lower():
                return stdout
            elif "unknown" in stdout.lower():
                return "unknown"
            else:
                return "unsat"
            
    def get_model(self) -> str:
        if not self.incremental_mode:
            raise ValueError("get_model this way only supported in incremental mode")
        
        open_parentheses = 0
        start = False
        model = ""
        print("Getting model")
        while True:
            result = self.process.stdout.readline()
            open_parentheses += result.count("(")
            open_parentheses -= result.count(")")
            model += result + "\n"
            if open_parentheses == 0:
                # this still may be dreal name : [interval] format
                if ":" in result:
                    continue
                break
        return model
            
    def write_incremental(self, statement : str):
        if self.incremental_mode:
            self.process.stdin.write(statement + "\n")
            self.process.stdin.flush()


class PortfolioSMTSolver:            
    def __init__(self, solvers: dict[str, SMTSolver], logic="QF_LIA"):
        self.solvers = solvers
        self.logic = logic
        self.num_workers = min(os.cpu_count(), len(self.solvers))
    
    def create_process(self):
        for solver in self.solvers.values():
            solver.create_process()
    
    def write_incremental(self, statement : str):
        for solver in self.solvers.values():
            solver.write_incremental(statement)
    
    def solve(self, formula_file) -> str:
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
                if "unknown" in stdout.lower():
                    # just kill the current process and let the others continue
                    proc.kill()
                    continue
                for other_name, other_proc in processes.items():
                    if other_name != name:
                        other_proc.kill()

                if ret == 0 and (("sat" in stdout.lower() and "unsat" not in stdout.lower()) or "delta-sat" in stdout.lower()):
                    return stdout                        
                else:
                    return "unsat"