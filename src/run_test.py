# test to resynthesize a given circuit with a specific method
import argparse
import sys
from synth import Synthesizer
import time
import resource

parser = argparse.ArgumentParser()
parser.add_argument("-c", type=str, required=True)
parser.add_argument("-m", type=str, required=True)
args = parser.parse_args()

if args.m == "incremental":
    synthesizer = Synthesizer()
    synthesizer.synthesis_incremental(args.c)
elif args.m == "zero":
    synthesizer = Synthesizer()
    start_time = time.time()
    res = synthesizer.synthesis_zero(args.c)
    end_time = time.time()
    print(f"SAT") if res else print(f"UNSAT")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
elif args.m in ["opensmt", "yices2", "smtinterpol", "cvc5", "dreal"]:
    synthesizer = Synthesizer(solver=args.m)
    synthesizer.synthesis(args.c)