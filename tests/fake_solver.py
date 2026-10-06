"""
Stand-in for an SMT solver binary, used to test src/solvers.py without real solvers.

usage: fake_solver.py MODE DELAY [formula.smt2]

With a formula file the solver answers once and exits (file mode); without one it
reads commands from stdin and answers every (check-sat) (incremental mode). The
answer is chosen by MODE:
  sat, unsat, unknown, delta-sat    the corresponding answer (sat also prints a model)
  unsat-then-error                  "unsat", then an error for (get-model), exit code 1 (like z3)
  error                             (error "boom"), exit code 1
  crash                             no answer, message on stderr, exit code 3
  hang                              never answers
A "success+" prefix makes the solver print "success" after every command (like SMTInterpol).
DELAY is the number of seconds to wait before answering.
"""

import sys
import time

mode, delay = sys.argv[1], float(sys.argv[2])
echo_success = mode.startswith("success+")
mode = mode.removeprefix("success+")


def answer():
    time.sleep(delay)
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        sys.stderr.write("fake solver crashed\n")
        sys.exit(3)
    if mode == "error":
        print('(error "boom")', flush=True)
        return 1
    if mode == "delta-sat":
        print("delta-sat with delta = 0.001", flush=True)
    elif mode == "unsat-then-error":
        print("unsat")
        print('(error "model is not available")', flush=True)
        return 1
    else:
        print(mode, flush=True)
    return 0


if len(sys.argv) > 3:  # file mode
    status = answer()
    if mode in ("sat", "delta-sat"):
        print("(\n  (define-fun x () Int 1)\n)", flush=True)
    sys.exit(status)

for line in sys.stdin:  # incremental mode
    line = line.strip()
    if line == "(check-sat)":
        answer()
    elif line.startswith("(get-value"):
        print("((x 1))", flush=True)
    elif line and echo_success:
        print("success", flush=True)
