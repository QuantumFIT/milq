"""
@file: simulator.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: separate CLI for the custom simulator module, which can output the state vectors in the custom representations, allows the choice of vector modes
"""

import argparse
import sys
import os

# realpath: also works when called through a symlink
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), '../src/'))
from sim import Simulator
from complex.classic import Complex
from complex.fivetuple import FiveTuple


def at_least(minimum):
    # argparse type: an integer of at least minimum
    def parse(value):
        number = int(value)
        if number < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}, got {value}")
        return number
    parse.__name__ = "int"  # argparse names the type in "invalid int value: ..."
    return parse


parser = argparse.ArgumentParser(description='print the input and output vectors of a circuit in the representations used by the synthesis')
parser.add_argument('qasm_file', type=str, help='qasm file to simulate')
parser.add_argument('-v', '--vectors', type=str, help='vectors mode to use for the synthesis', choices=["zero", "all", "rus", "jamiolkowski", "matrix"], default="all")
parser.add_argument('-c', '--complex_representation', type=str, help='complex representation to use', required=False, choices=["FiveTuple", "Classic"], default="FiveTuple")
parser.add_argument('-T', '--targets', type=at_least(1), help='number of target qubits for -v rus (default: 1)', required=False, default=None)
parser.add_argument('-A', '--ancillas', type=at_least(0), help='number of ancilla qubits for -v rus (default: 1)', required=False, default=None)
parser.add_argument('-m', '--meas', type=int, choices=[0, 1], help='determine measurement outcome - if not set, default is 0 (|0>)', required=False, default=0)
args = parser.parse_args()
if args.vectors != "rus" and (args.targets is not None or args.ancillas is not None):
    parser.error("-T and -A apply only with -v rus")

if args.complex_representation == "FiveTuple":
    complex_representation = FiveTuple
elif args.complex_representation == "Classic":
    complex_representation = Complex

simulator = Simulator(qasm_file=args.qasm_file, complex_representation=complex_representation, meas=args.meas)

def print_matrix(res):
    print(res)
def print_vectors(res):
    for (input_vector, output_vector) in res:
        print(input_vector)
        print(output_vector)
        print("--------------------------------")

print_func = print_matrix if args.vectors == "matrix" else print_vectors
try:
    if args.vectors == "zero":
        res = simulator.simulate_zero()
    elif args.vectors == "all":
        res = simulator.simulate_circuit()
    elif args.vectors == "rus":
        res = simulator.simulate_rus(1 if args.targets is None else args.targets, 1 if args.ancillas is None else args.ancillas)
    elif args.vectors == "jamiolkowski":
        res = simulator.simulate_jamiolkowski()
    elif args.vectors == "matrix":
        res = simulator.simulate_matrix()
except (ValueError, OSError, RuntimeError) as e:
    print(f"simulator: error: {e}", file=sys.stderr)
    sys.exit(1)
    
print_func(res)