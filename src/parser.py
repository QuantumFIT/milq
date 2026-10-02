"""
@file: parser.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: module for parsing the output of each supported solver
"""

import re
import os
from generator import Generator
from gates import Circuit, Gate
from complex.vector import Vector
import time
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
        # SMT parsing (either get-model or get-value, which both have different formats)
        lines = model.split('\n')
        items = []
        i = 0
        line = ""
        time_start = time.time()
        while i < len(lines):
            line += lines[i].strip()
            get_value = False
            # match (<whitespaces>define-fun var_name () var_type var_value<whitespaces>)
            # possibly starts with (( instead of (
            # matches (get-model)
            var_name, var_value = None, None
            get_model, (var_name, var_value) = self.parse_get_model(line) # get-model parsing
            get_value = (get_model == False)
            if get_value:
                values = self.parse_get_value(line) # get-value parsing
                for value in values:
                    items.append(value)
                    line = ""
            else:
                if var_name is not None and var_value is not None:
                    items.append((var_name, var_value))
                    line = ""
            i += 1
        time_end = time.time()
        return items
    
    def parse_get_value(self, line : str) -> list[tuple[str, any]]:
        number = r"-?\d+(?:\.\d+)?"
        minus_int = r"\(\s*-\s*\d+\s*\)"
        rational_number = rf"\(\s*/\s*(?:{number}|{minus_int})\s+(?:{number}|{minus_int})\s*\)"
        dreal_interval = rf"\(\s*interval\s*\(\s*(?:closed|open)\s*(?:{number}|{minus_int}|{rational_number})\s*\)\(\s*(?:closed|open)\s*(?:{number}|{minus_int}|{rational_number})\s*\)\)"

        pattern = re.compile(rf"""
        \(+\s*(\w+)\s*   # variable name
        (
            {number}                  # decimal/integer
            | true
            | false
            | \(/\s*(?:{number})\s+(?:{number})\s*\)   # rational
            | \[\s*(?:{number})\s*,\s*(?:{number})\s*\] # interval
            | {minus_int}            # negative integer
            | {dreal_interval}       # dreal-style interval
        )
        \)+\s*
        """, re.IGNORECASE | re.VERBOSE | re.DOTALL)
        matches = pattern.findall(line)
        values = []
        for match in matches:
            var_name = match[0]
            var_value = match[1]
            if var_value.lower() == "true":
                var_value = True
            elif var_value.lower() == "false":
                var_value = False
            elif '/' in var_value:
                num = var_value.split('/')[1].strip().split(' ')[0].strip().split(')')[0]
                den = var_value.split('/')[1].strip().split(' ')[1].strip().split(')')[0]
                var_value = float(num) / float(den)
            values.append((var_name, var_value))
        return values

    def parse_get_model(self, line : str) -> tuple[bool, tuple[any, any]]:
        # decimal, true, false, rational, interval
        number = r"-?\d+(?:\.\d+)?"
        minus_int = r"\(\s*-\s*\d+\s*\)"
        pattern = re.compile(rf"""
            \(+\s*
            define-fun\s+
            (\w+)\s*\(\s*\)\s*(\w+)\s*
            (
                {number}
                | true
                | false
                | \(/\s*{number}\s+{number}\s*\)
                | \[\s*{number},\s*{number}\s*\]
                | {minus_int}
            )
            \s*\)+\s*
        """, re.IGNORECASE | re.VERBOSE)
        match = pattern.search(line)
        if match:
            var_name = match.group(1)
            var_type = match.group(2)
            var_value = match.group(3)
            if var_type.lower() == "bool":
                var_value = var_value.lower() == "true"
            elif var_type.lower() == "int":
                if '(' in var_value:
                    var_value = var_value.split('-')[1].split(')')[0].strip()
                    var_value = -int(var_value)
                else:
                    var_value = int(var_value)
            elif var_type.lower() == "real":
                if '[' in var_value:
                    # parsing interval (dreal)
                    min_val = var_value.split('[')[1].strip().split(',')[0].strip().split(')')[0]
                    var_value = float(min_val)
                elif '/' in var_value:
                    # parsing rational number
                    num = var_value.split('/')[1].strip().split(' ')[0].strip().split(')')[0]
                    den = var_value.split('/')[1].strip().split(' ')[1].strip().split(')')[0]
                    if float(den) == 0:
                        var_value = float(num)
                    else:
                        var_value = float(num) / float(den)
                var_value = float(var_value)
            return True, (var_name, var_value)
        else:
            return False, (None, None)
        

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
                return False
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

    def is_sat(self, model : any) -> bool:
        if isinstance(model, str):
            if ("sat" in model.lower() and "unsat" not in model.lower()) or "delta-sat" in model.lower():
                return True
            else:
                return False
        else:
            return True