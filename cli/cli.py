"""
@file: cli.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: CLI for the synthesis tool
"""

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/'))
from synth import Synthesizer
from solvers import SolverError

parser = argparse.ArgumentParser(description='CLI for the synthesis tool')
parser.add_argument('qasm_file', type=str, help='qasm file to synthesize')
parser.add_argument('-v', '--vectors', type=str, help='vectors mode to use for the synthesis', choices=["zero", "all", "rus", "jamiolkowski"], default="all")
parser.add_argument('-s', '--solving', type=str, help='solving method to use', choices=["smt", "milp", "gurobi"], default="gurobi")
parser.add_argument('-m', '--mode', type=str, help='solving mode to use', choices=["basic", "incremental", "binary", "topdown", "bottomup", "pareto-incremental"], default="incremental")
parser.add_argument('-a', '--solver', type=str, help='solver to use', required=False, choices=["z3", "cvc5", "yices2", "opensmt", "smtinterpol", "dreal", "gurobi", "cbc", "portfolio"], default="gurobi")
parser.add_argument('-o', '--output_qasm', type=str, help='output qasm file', required=False, default="circuit.qasm")
parser.add_argument('-c', '--complex_representation', type=str, help='complex representation to use', required=False, choices=["FiveTuple", "Classic"], default="FiveTuple")
parser.add_argument('-f', '--fidelity_threshold', type=float, help='fidelity threshold (use with dreal solver)', required=False, default=1.0)
parser.add_argument('-ap', '--approx', action='store_true', help='approximate equivalence', default=False)
parser.add_argument('-T', '--targets', type=int, help='number of target qubits', required=False, default=1)
parser.add_argument('-A', '--ancillas', type=int, help='number of ancilla qubits', required=False, default=1)
parser.add_argument('-u', '--up_to_global_phase', action='store_true', help='up to global phase', default=False)
parser.add_argument('-b', '--basis', type=str, help='basis to use', required=False, choices=["cb"], default="cb")
parser.add_argument('-d', '--depth', type=int, help='number of allowed gates', required=False, default=None)
parser.add_argument('-nm', '--no_measurement', action='store_true', help='do not measure the output qubits', default=False)
args = parser.parse_args()
synthesizer = Synthesizer()
try:
    res, circuit, _ = synthesizer.synthesis(qasm_file=args.qasm_file, 
                                      vectors=args.vectors, 
                                      solving=args.solving, 
                                      mode=args.mode, 
                                      solver=args.solver, 
                                      output_qasm=args.output_qasm, 
                                      complex_representation=args.complex_representation, 
                                      fidelity_threshold=args.fidelity_threshold, 
                                      targets=args.targets, ancillas=args.ancillas, 
                                      up_to_global_phase=args.up_to_global_phase, 
                                      basis=args.basis,
                                      d=args.depth,
                                      approx=args.approx,
                                      no_measurement=args.no_measurement)
except SolverError as e:
    print(f"synthesis failed: {e}", file=sys.stderr)
    sys.exit(1)
if res:
    print("synthesis successful")
else:
    print("synthesis failed")
    
print(f"Full time: {synthesizer.logger.get_times()['full']} seconds")
print(f"Parsing time: {synthesizer.logger.get_times()['parsing']} seconds")
print(f"Encoding time: {synthesizer.logger.get_times()['encoding']} seconds")
print(f"Solving time: {synthesizer.logger.get_times()['solving']} seconds")
print(f"Updating time: {synthesizer.logger.get_times()['updating']} seconds")
print(circuit)