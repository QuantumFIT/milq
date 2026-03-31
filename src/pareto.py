from multiprocessing import Process, Queue
import time
import os
from gates import Circuit


def _pareto_run_queue(queue, fn):
    try:
        queue.put(("ok", fn()))
    except Exception as e:
        queue.put(("err", (False, None, None)))


class Pareto:
    def __init__(self, timeout: int = 10*60*60, max_x: int = 10, max_y: float = 1.0):
        self.timeout = timeout
        self.tmout_met = False
        self.start_time = time.time()
        self.end_time = self.start_time + timeout
        self.models = 0
        self.max_x = max_x
        self.max_y = max_y
        self.front = []
        
    
    def start(self, func: callable) -> any:
        time_now = time.time()
        if time_now >= self.end_time:
            self.tmout_met = True
            return False, None, None

        remaining = self.end_time - time_now
        if remaining <= 0:
            self.tmout_met = True
            return False, None, None

        q = Queue()
        proc = Process(target=_pareto_run_queue, args=(q, func))
        proc.start()
        proc.join(timeout=remaining)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=10)
            self.tmout_met = True
            return False, None, None

        self.tmout_met = False
        if q.empty():
            return False, None, None
        status, return_value = q.get()
        if status == "err":
            return False, None, None
        return return_value
    
    def get_frontier(self) -> list:
        def dominated(p):
            x, y = p[0], p[1]
            return any(
                q[0] <= x and q[1] >= y and (q[0] < x or q[1] > y) for q in self.front
            )

        return [p for p in self.front if not dominated(p)]

    def cleanup(self):
        import matplotlib.pyplot as plt

        if not self.front:
            return

        f = self.get_frontier()
        f.sort(key=lambda p: (p[0], -p[1]))
        xs, ys = [p[0] for p in f], [p[1] for p in f]
        all_x = [p[0] for p in self.front]
        all_y = [p[1] for p in self.front]

        plt.figure()
        plt.scatter(all_x, all_y, c="lightgray", s=30, label="All")
        plt.scatter(xs, ys, c="tab:red", s=45, zorder=3, label="Pareto front")
        if len(xs) > 1:
            plt.plot(xs, ys, color="tab:red", zorder=2)
        plt.title("Pareto front")
        plt.xlabel("Circuit cost")
        plt.ylabel("Probability of success")
        plt.legend()
        plt.savefig("pareto_front.pdf")
        plt.close()
        
        
    def get_models_count(self):
        return self.models
    
    def add_point(self, cost_x: int, cost_y: float, depth: int, circuit: Circuit, recovery_circuit: Circuit):
        if cost_x > self.max_x or cost_y > self.max_y:
            return
        self.models += 1
        self.front.append((cost_x, cost_y, depth, circuit, recovery_circuit))
        os.makedirs(f"pareto_front", exist_ok=True)
        output_qasm = f"pareto_front/pareto_{depth}_{cost_x}_{cost_y:.3f}.qasm"
        recovery_output_qasm = f"pareto_front/pareto_{depth}_{cost_x}_{cost_y:.3f}_recovery.qasm"
        circuit.write_to_file(output_qasm)
        if recovery_circuit is not None:
            recovery_circuit.write_to_file(recovery_output_qasm)
    
    def timeout_met(self) -> bool:
        return self.tmout_met