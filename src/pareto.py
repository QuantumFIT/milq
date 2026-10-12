"""
@file: pareto.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: Pareto front class to store circuits in a pareto front with a cost metric
"""

import multiprocessing
import multiprocessing.connection
import time
import os
import traceback
from gates import Circuit


def _pareto_worker(conn, fn):
    # runs in the forked process; an exception is sent back and raised again by Pareto.start
    try:
        result = ("ok", fn(), None)
    except Exception as e:
        result = ("err", e, traceback.format_exc())
    try:
        conn.send(result)
    except Exception as e:  # the result or the exception cannot be pickled
        conn.send(("err", RuntimeError(f"the pareto worker could not send its result back: {e}"), traceback.format_exc()))
    finally:
        conn.close()


class Pareto:
    def __init__(self, timeout: float = 10*60*60, maximize_y: bool = False, x_label: str = "x", y_label: str = "y"):
        # x is always minimized; y is maximized (e.g. probability of success) or minimized (e.g. a cost)
        self.timeout = timeout
        self.tmout_met = False
        self.start_time = time.time()
        self.end_time = self.start_time + timeout
        self.models = 0
        self.maximize_y = maximize_y
        self.x_label = x_label
        self.y_label = y_label
        self.front = []
        
    
    def start(self, func: callable) -> any:
        # run func in another process, this function handles the overall timeout
        remaining = self.end_time - time.time()
        if remaining <= 0:
            self.tmout_met = True
            return False, None, None

        # fork explicitly: func is a closure, which other start methods cannot pickle
        context = multiprocessing.get_context("fork")
        receiver, sender = context.Pipe(duplex=False)
        proc = context.Process(target=_pareto_worker, args=(sender, func))
        proc.start()
        sender.close()  # only the worker writes; closing this copy lets recv() see a worker that exited
        try:
            # read the result as soon as it is there, before joining: a result larger than the pipe
            # buffer would otherwise keep the worker blocked in send() and the join waiting forever
            if not multiprocessing.connection.wait([receiver, proc.sentinel], timeout=remaining):
                proc.terminate()  # the time limit was met while the worker was still running
                self.tmout_met = True
                return False, None, None
            try:
                status, value, details = receiver.recv()
            except EOFError:
                proc.join()
                raise RuntimeError(f"the pareto worker exited (exit code {proc.exitcode}) without a result")
        finally:
            proc.join(timeout=10)
            receiver.close()

        self.tmout_met = False
        if status == "err":
            value.add_note(f"raised in the pareto worker:\n{details}")
            raise value
        return value

    def _sort_key(self, point):
        return (point[0], -point[1] if self.maximize_y else point[1])
    
    def get_frontier(self) -> list:
        def at_least_as_good(q, p):
            return q[0] <= p[0] and (q[1] >= p[1] if self.maximize_y else q[1] <= p[1])

        def dominated(p):
            return any(at_least_as_good(q, p) and (q[0], q[1]) != (p[0], p[1]) for q in self.front)

        return [p for p in self.front if not dominated(p)]

    def cleanup(self):
        import matplotlib.pyplot as plt
        # after timeout, create a plot using matplotlib
        if not self.front:
            return

        f = self.get_frontier()
        f.sort(key=self._sort_key)
        xs, ys = [p[0] for p in f], [p[1] for p in f]
        all_x = [p[0] for p in self.front]
        all_y = [p[1] for p in self.front]

        plt.figure()
        plt.scatter(all_x, all_y, c="lightgray", s=30, label="All")
        plt.scatter(xs, ys, c="tab:red", s=45, zorder=3, label="Pareto front")
        if len(xs) > 1:
            plt.plot(xs, ys, color="tab:red", zorder=2)
        plt.title("Pareto front")
        plt.xlabel(self.x_label)
        plt.ylabel(self.y_label)
        plt.legend()
        plt.savefig("pareto_front.pdf")
        plt.close()
        
        
    def best(self) -> tuple[bool, Circuit, list]:
        # the point with the lowest x of the front (best y among equal x)
        frontier = self.get_frontier()
        if not frontier:
            return False, None, []
        frontier.sort(key=self._sort_key)
        return True, frontier[0][3], []

    def get_models_count(self):
        return self.models
    
    def add_point(self, cost_x: int, cost_y: float, depth: int, circuit: Circuit, recovery_circuit: Circuit):
        # add a new point to the pareto front
        self.models += 1
        self.front.append((cost_x, cost_y, depth, circuit, recovery_circuit))
        os.makedirs(f"pareto_front", exist_ok=True)
        # the model number keeps circuits with the same depth and costs apart
        output_qasm = f"pareto_front/pareto_{depth}_{cost_x}_{cost_y:.3f}_{self.models}.qasm"
        recovery_output_qasm = f"pareto_front/pareto_{depth}_{cost_x}_{cost_y:.3f}_{self.models}_recovery.qasm"
        circuit.write_to_file(output_qasm)
        if recovery_circuit is not None:
            recovery_circuit.write_to_file(recovery_output_qasm)
    
    def timeout_met(self) -> bool:
        return self.tmout_met