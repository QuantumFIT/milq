"""
@file: solvers.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: abstraction over SMT solvers and portfolio solving, supports incrementality with single-solver
"""

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import queue
import signal
import subprocess
import threading


class SolverError(Exception):
    """the solver failed (error response, crash, ...) instead of answering sat/unsat/unknown"""


def classify_answer(output: str) -> str:
    # the answer is the first line other than SMTInterpol's "success" acknowledgements
    for line in output.splitlines():
        line = line.strip()
        if not line or line == "success":
            continue
        if line == "sat" or line.startswith("delta-sat"):  # dReal: "delta-sat with delta = ..."
            return "sat"
        if line in ("unsat", "unknown"):
            return line
        return "error"
    return "error"


def _describe_failure(name: str, stdout: str, stderr: str, returncode=None) -> str:
    details = (stdout.strip() or stderr.strip() or "no output").splitlines()[0]
    code = f", exit code {returncode}" if returncode is not None else ""
    if returncode == 127:  # the shell could not find a program, e.g. java for SMTInterpol
        code += " (command not found)"
    return f"{name} failed{code}: {details}"


def _kill_process_group(proc: subprocess.Popen) -> None:
    # the solver runs in its own process group (start_new_session), so this also stops the processes
    # it started, e.g. the java process behind the SMTInterpol wrapper script; only a live leader is
    # signalled, since the group ID of an exited leader may already belong to another process
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


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
        # returns "sat" (incremental) or the solver output with the model (file mode), "unsat" or "unknown";
        # raises SolverError when the solver fails instead of answering
        if self.incremental_mode:
            # formula sent to the solver, add check-sat and get-model, retreive result
            result = self.process.stdout.readline()
            # smtinterpol return 'success' first after each statement, 
            while result.strip() == 'success':
                result = self.process.stdout.readline()
            if result == '':  # end of output: the solver exited
                self.process.wait()
                raise SolverError(_describe_failure(self.name, "", self.process.stderr.read(), self.process.returncode))
            answer = classify_answer(result)
            if answer == "error":
                raise SolverError(_describe_failure(self.name, result, ""))
            return answer
        else: # not fully incremental mode (when used in Portfolio), just solve .smt2 file and get the model
            try:
                result = subprocess.Popen(
                    self.args + self.smtlib_flags + [formula_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stdout, stderr = result.communicate()
            except OSError as e:
                raise SolverError(f"{self.name} could not be started: {e}") from e
            # z3 exits with 1 after "unsat" because (get-model) fails, so the answer decides, not the exit code
            answer = classify_answer(stdout)
            if answer == "error":
                raise SolverError(_describe_failure(self.name, stdout, stderr, result.returncode))
            return stdout if answer == "sat" else answer
            
    def get_model(self) -> str:
        if not self.incremental_mode:
            raise ValueError("get_model this way only supported in incremental mode")
        
        open_parentheses = 0
        start = False
        model = ""
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
        # incrementally send a command to the solver's input
        if self.incremental_mode:
            try:
                self.process.stdin.write(statement + "\n")
                self.process.stdin.flush()
            except BrokenPipeError as e:
                self.process.wait()
                raise SolverError(_describe_failure(self.name, "", self.process.stderr.read(), self.process.returncode)) from e


class PortfolioSMTSolver:            
    def __init__(self, solvers: dict[str, SMTSolver], logic="QF_LIA"):
        self.solvers = solvers
        self.logic = logic
    
    def create_process(self):
        for solver in self.solvers.values():
            solver.create_process()
    
    def write_incremental(self, statement : str):
        for solver in self.solvers.values():
            solver.write_incremental(statement)
    
    def solve(self, formula_file) -> str:
        processes = {}
        failures = []  # solvers that failed are skipped, the others keep running
        finished = queue.Queue()

        def collect(name, proc):
            # reading the whole output also keeps a solver printing a large model from blocking on a full pipe
            stdout, stderr = proc.communicate()
            finished.put((name, proc.returncode, stdout, stderr))

        try:
            for name, solver in self.solvers.items():
                try:
                    proc = subprocess.Popen(
                        solver.args + solver.smtlib_flags + [formula_file],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        start_new_session=True,  # own process group, see _kill_process_group
                    )
                except OSError as e:  # e.g. the solver is not installed
                    failures.append(f"{name} could not be started: {e}")
                    continue
                processes[name] = proc
                threading.Thread(target=collect, args=(name, proc), daemon=True).start()

            unknown = False
            for _ in range(len(processes)):
                name, ret, stdout, stderr = finished.get()  # block until the next solver finishes
                answer = classify_answer(stdout)
                if answer == "error":
                    failures.append(_describe_failure(name, stdout, stderr, ret))
                    continue
                if answer == "unknown":
                    unknown = True
                    continue  # let the others continue
                return stdout if answer == "sat" else "unsat"
            if unknown:
                return "unknown"
            raise SolverError("all solvers of the portfolio failed: " + "; ".join(failures))
        finally:
            # stop the solvers that are still running and reap all of them
            for proc in processes.values():
                _kill_process_group(proc)
            for proc in processes.values():
                proc.wait()
