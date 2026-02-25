# test to resynthesize a given circuit with a specific method
import sys
from synth import Synthesizer
import time
import resource
from mqt.core import load
import numpy as np
from mqt.ddsim import CircuitSimulator
from sim import Simulator
from gates import GateSet

circuit = sys.argv[1]
method = sys.argv[2]
choice = sys.argv[3] if len(sys.argv) > 3 else None

if method == "incremental":
    synthesizer = Synthesizer()
    synthesizer.synthesis_incremental(circuit)
elif method == "all":
    synthesizer = Synthesizer()
    start_time = time.time()
    res = synthesizer.synthesis(circuit)
    end_time = time.time()
    print(f"SAT") if res else print(f"UNSAT")
    print(f"Time taken: {end_time - start_time} seconds")
    #print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
    synthesizer.parser.print_stats()
    
    qc = load(circuit)
    sim = CircuitSimulator(qc)

    # run the simulation
    result = sim.simulate(shots=1024)

    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print(sv)
    filename = "circuit.qasm"
    qc = load(filename)
    sim = CircuitSimulator(qc)

    # run the simulation
    result = sim.simulate(shots=1024)

    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print(sv)
elif method == "zero":
    synthesizer = Synthesizer()
    start_time = time.time()
    res = synthesizer.synthesis_zero(circuit)
    end_time = time.time()
    print(f"SAT") if res else print(f"UNSAT")
    print(f"Time taken: {end_time - start_time} seconds")
    #print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
    synthesizer.parser.print_stats()
    
    qc = load(circuit)
    sim = CircuitSimulator(qc)

    # run the simulation
    result = sim.simulate(shots=1024)

    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print(sv)
    filename = "circuit.qasm"
    qc = load(filename)
    sim = CircuitSimulator(qc)

    # run the simulation
    result = sim.simulate(shots=1024)

    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print(sv)
elif method == "rus":
    synthesizer = Synthesizer()
    start_time = time.time()
    res = synthesizer.synthesis_rus(circuit)
    end_time = time.time()
    print(f"SAT") if res else print(f"UNSAT")
    print(f"Time taken: {end_time - start_time} seconds")
    #print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
    synthesizer.parser.print_stats()
    
    qc = load(circuit)
    sim = CircuitSimulator(qc)

    # run the simulation
    result = sim.simulate(shots=1024)

    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print(sv)
    filename = "circuit.qasm"
    qc = load(filename)
    sim = CircuitSimulator(qc)

    # run the simulation
    result = sim.simulate(shots=1024)

    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print(sv)
elif method in ["opensmt", "yices2", "smtinterpol", "cvc5", "dreal"]:
    synthesizer = Synthesizer(solver=method)
    synthesizer.synthesis(circuit)
    
elif method == "mqt":
    gate_set = GateSet(['id', 'x', 'y', 'z', 'h', 's', 'sdg', 't', 'tdg', 'sx', 'sxdg', 'cx', 'cy', 'cz', 'swap', 'iswap', 'dcx'])
    if choice not in ["binary", "bottom_up", "top_down", "incremental"]:
        raise ValueError(f"Invalid choice: {args.ch}")
    synthesizer = Synthesizer(gate_set=gate_set)
    start_time = time.time()
    res = synthesizer.synthesis(circuit, choice=choice)
    end_time = time.time()
    print(f"SAT") if res else print(f"UNSAT")
    print(f"Time taken: {end_time - start_time} seconds")
    synthesizer.parser.print_stats()