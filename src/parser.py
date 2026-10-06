"""
@file: parser.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: module for parsing the output of each supported solver
"""

import re
import os
from fractions import Fraction
from generator import Generator
from gates import Circuit, Gate
from complex.vector import Vector
from logger import Logger

class ModelParser:
    """
    class that converts model from any solver to QASM file
    """
    def __init__(self, logger : Logger) -> None:
        self.logger = logger
        self.stats = {}
        self.stats['gate_counts'] = {} # gate name -> count
        self.stats['cost'] = 0 # total cost of the circuit
        self.complex_representation = None
        self.v = None
        self.q = None
        self.d = None


    def expand_milp_model(self, gen : Generator) -> list:
        # parse the MILP model to a list of items (variable name, value)
        items = []
        for name, var in gen.bool_variables.items():
            if name.startswith("L"):
                if abs(var.value() - 1) < 1e-6:
                    items.append((name, True))
                else:
                    items.append((name, False))
        for name, var in gen.integer_variables.items():
            if name.startswith("W"):
                items.append((name, var.value()))
            if name.startswith("I_"):
                items.append((name, var.value()))
        for name, var in gen.real_variables.items():
            if name.startswith("I_"):
                if var.value() is not None:
                    items.append((name, float(var.value())))
        return items



    def parse_model_to_items(self, model : str) -> list:
        # SMT parsing of solver output: get-model responses (define-fun entries, possibly
        # inside (model ...)) and get-value responses ((name value) ...)
        items = []

        def visit(expr):
            if not isinstance(expr, list) or not expr:
                return
            if expr[0] == "define-fun" and len(expr) == 5:
                # (define-fun name () sort value)
                value = _term_value(expr[4], expr[3])
                if value is not None:
                    items.append((expr[1], value))
                return
            if all(isinstance(e, list) and len(e) == 2 and isinstance(e[0], str) and _numeral(e[0]) is None for e in expr):
                # get-value response: ((name value) ...)
                for name, term in expr:
                    value = _term_value(term)
                    if value is not None:
                        items.append((name, value))
                return
            for e in expr:
                visit(e)

        for expr in _read_sexprs(model):
            visit(expr)
        return items

    def filter_items(self, model : any) -> tuple[Circuit, list[Vector]]:
        # get only the (gate, true) tuples, get the cost of the circuits
        # and the output vectors from the last layer (before equivalence, measurement...)
        new_items = []
        costs = [None] * (self.d + 1)
        best_indice = 0
        circ = Circuit(gates=[], q=self.q, d=self.d)
        out_vectors = [Vector(q=2**self.q, generator=None, element_representation=self.complex_representation, k=0) for _ in range(self.v)]
        for item in model:
            value_obj = None
            variable = None
            if isinstance(item, tuple) and len(item) >= 2:
                # parsing general model
                var_obj, value_obj = item[0], item[1]
                variable = str(var_obj)
            else:
                # possibly parsing gurobi model
                value_obj = item.X
                variable = item.varName
            if variable.startswith("L"):
                # boolean variable parsing (layer selection variable)
                parse = False
                if isinstance(value_obj, bool):
                    if value_obj:
                        parse = True
                elif isinstance(value_obj, float):
                    if abs(value_obj - 1) < 1e-6:
                        parse = True
                else:
                    if value_obj.is_true():
                        parse = True
                if parse: # parse only if the selection variable is True
                    parts = variable.split("_")
                    d = int(parts[0][1:])
                    gate = parts[1]
                    gate_qubits = [int(p[1:]) for p in parts[2:]]
                    gate = Gate(name=gate, qubits=gate_qubits)
                    circ[d] = gate
            
            if variable.startswith("I_") and self.v != 0:
                # vector parsing
                # check that I_{pair_idx}_{d}_{indice}_part, d == depth
                # only get the last vector (output)
                parts = variable.split("_")
                d = int(parts[2])
                if d != self.d: continue

                if isinstance(value_obj, (float, int, str)):
                    # parse part of a vector -- check which vector by pair_idx, then index in the vector and which coefficient it is
                    pair_idx = int(parts[1])
                    if parts[3] == "k": 
                        out_vectors[pair_idx].k = int(value_obj)
                        setattr(out_vectors[pair_idx], "k", value_obj)
                    else:
                        coeff = parts[4].strip()
                        indice = int(parts[3])
                        if coeff == "r":
                            coeff = "real"
                        elif coeff == "i":
                            coeff = "imag"
                        setattr(out_vectors[pair_idx][indice], coeff, value_obj)
            if variable.startswith("W"):
                # weight variable parsing
                if value_obj is None: continue
                # only get the last Weight variable
                indice = int(variable.split("W")[1].strip())
                if indice > self.d: continue
                if indice > best_indice:
                    best_indice = indice
                if isinstance(value_obj, int):
                    costs[indice] = value_obj
                elif isinstance(value_obj, float):
                    costs[indice] = int(value_obj)
                elif isinstance(value_obj, str):
                    costs[indice] = float(value_obj)
                else:
                    costs[indice] = int(value_obj.constant_value())
        self.stats['cost'] = costs[best_indice]
        circ.set_cost(self.stats['cost'])
        return circ, out_vectors

    def parse(self, model : any, qubits : int, depth : int, output_qasm : str = "circuit.qasm", complex_representation: any = None, write_to_file : bool = True, draw_circuit : bool = False, v : int = 0) -> tuple[bool, Circuit, list[Vector]]:
        if complex_representation is not None:
            self.complex_representation = complex_representation
        self.v = v
        self.q = qubits
        self.d = depth
        items = model
        if isinstance(model, Generator): # parsing milp model
            try:
                items = self.expand_milp_model(model)
            except Exception as e:
                print(f"Error expanding MILP model: {e}")
                return False, None, None
        elif isinstance(model, str): # pasrsing smt model
            items = self.parse_model_to_items(model)

        # retrieve the vectors and the circuit from the model
        circ, vectors = self.filter_items(items)

        if write_to_file:
            circ.write_to_file(output_qasm)
        if draw_circuit:
            png_filename = os.path.splitext(output_qasm)[0] + ".png"
            circ.draw(output_file=png_filename)
        return True, circ, vectors

    def get_stats(self) -> dict:
        return self.stats
    
    def print_stats(self) -> None:
        print(f"Gate counts: {self.stats['gate_counts']}")
        print(f"Cost: {self.stats['cost']}")


def _read_sexprs(text : str) -> list:
    # nested lists of atoms; a dReal interval [lo, hi] becomes ["[", lo, hi]
    tokens = re.findall(r'"(?:[^"]|"")*"|[()\[\],]|[^\s()\[\],"]+', text)
    stack = [[]]
    for token in tokens:
        if token in ("(", "["):
            expr = [] if token == "(" else ["["]
            stack[-1].append(expr)
            stack.append(expr)
        elif token in (")", "]"):
            if len(stack) > 1:
                stack.pop()
        elif token != ",":
            stack[-1].append(token)
    return stack[0]


def _numeral(term) -> Fraction | None:
    # exact value of a numeric SMT-LIB term, e.g. 2, 2.0, (- 3), (/ (- 1) 2), (- (/ 1.0 2.0));
    # None if the term is not numeric
    if isinstance(term, str):
        try:
            return Fraction(term)
        except ValueError:
            return None
    if not term:
        return None
    head = term[0]
    if head == "[":
        # dReal interval [lo, hi]: take the lower bound
        return _numeral(term[1]) if len(term) > 1 else None
    if head == "interval":
        # dReal interval (interval (closed lo) (open hi)): take the lower bound
        return _numeral(term[1][1]) if len(term) > 1 and isinstance(term[1], list) and len(term[1]) == 2 else None
    args = [_numeral(arg) for arg in term[1:]]
    if not args or any(arg is None for arg in args):
        return None
    if head == "-":
        return -args[0] if len(args) == 1 else args[0] - sum(args[1:])
    if head == "+":
        return sum(args)
    if head == "*":
        product = Fraction(1)
        for arg in args:
            product *= arg
        return product
    if head == "/" and len(args) == 2:
        # division by zero is unspecified in SMT-LIB; keep the numerator
        return args[0] / args[1] if args[1] != 0 else args[0]
    return None


def _term_value(term, sort : str | None = None):
    # Python value of a model term: bool, int (Int sort or integral literal) or float
    if term in ("true", "false"):
        return term == "true"
    value = _numeral(term)
    if value is None:
        return None
    if sort == "Real":
        return float(value)
    if value.denominator == 1 and (sort == "Int" or "." not in str(term)):
        return int(value)
    return float(value)
