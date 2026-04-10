import argparse
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/'))
from sim import Simulator
from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.ntuple import nTuple
from gates import GateSet

parser = argparse.ArgumentParser(description='CLI for the synthesis tool')
parser.add_argument('qasm_file', type=str, help='qasm file to synthesize')
parser.add_argument('-v', '--vectors', type=str, help='vectors mode to use for the synthesis', choices=["zero", "all", "rus", "jamiolkowski", "matrix"], default="all")
parser.add_argument('-c', '--complex_representation', type=str, help='complex representation to use', required=False, choices=["FiveTuple", "nTuple", "Classic"], default="FiveTuple")
parser.add_argument('-T', '--targets', type=int, help='number of target qubits', required=False, default=1)
parser.add_argument('-A', '--ancillas', type=int, help='number of ancilla qubits', required=False, default=1)
parser.add_argument('-m', '--meas', type=int, help='determine measurement outcome - if not set, default is 0 (|0>)', required=False, default=0)
args = parser.parse_args()

if args.complex_representation == "FiveTuple":
    complex_representation = FiveTuple
elif args.complex_representation == "nTuple":
    complex_representation = nTuple
elif args.complex_representation == "Classic":
    complex_representation = Complex

simulator = Simulator(qasm_file=args.qasm_file, complex_representation=complex_representation, meas=args.meas)
start_time = time.time()

def print_matrix(res):
    print(res)
def print_vectors(res):
    for (input_vector, output_vector) in res:
        print(input_vector)
        print(output_vector)
        print("--------------------------------")

print_func = print_matrix if args.vectors == "matrix" else print_vectors
if args.vectors == "zero":
    res = simulator.simulate_zero()
elif args.vectors == "all":
    res = simulator.simulate_circuit()
elif args.vectors == "rus":
    res = simulator.simulate_rus(args.targets, args.ancillas)
elif args.vectors == "jamiolkowski":
    res = simulator.simulate_jamiolkowski()
elif args.vectors == "matrix":
    res = simulator.simulate_matrix()
    
print_func(res)