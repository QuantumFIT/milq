from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic, nTuple
from pysmt.smtlib.parser import SmtLibParser
from pysmt.shortcuts import Real, Int, Bool, Symbol, And, Equals, Div, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Times, Minus, Plus

from pysmt.typing import REAL, INT, BOOL
     
class Generator:
    def __init__(self, mode : str = "pysmt", solver : str = "opensmt", logic : str = "QF_LIA") -> None:
        # modes - ["pysmt", "smtlib", "milp"]
        self.mode = mode
        self.declarations = []
        self.declared_names = set()
        self.assertions = []
        self.optimize_objectives = []
        self.solver = solver
        self.logic = logic
        self.Symbol = Symbol
        self.REAL = REAL
        self.INT = INT
        self.BOOL = BOOL
        self.symbols = {}
        self.stats = {}
        self.stats['reals'] = 0
        self.stats['integers'] = 0
        self.stats['bools'] = 0
        self.stats['assertions'] = 0
        self.stats['variables'] = 0
    
    def add_assertion(self, assertion):
        self.stats['assertions'] += 1
        if self.mode == "pysmt":
            self.solver.add_assertion(assertion)
        elif self.mode == "smtlib":
            self.assertions.append(assertion)
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        
    def Plus(self, x, y):
        if self.mode == "pysmt":
            return Plus(x, y)
        elif self.mode == "smtlib":
            return f"(+ {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Minus(self, x, y):
        if self.mode == "pysmt":
            return Minus(x, y)
        elif self.mode == "smtlib":
            return f"(- {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Times(self, x, y):
        if self.mode == "pysmt":
            return Times(x, y)
        elif self.mode == "smtlib":
            return f"(* {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        
    def Pow(self, x, y):
        if self.mode == "smtlib" and self.logic == "QF_NRA":
            return f"(pow {x} {y})"
        else:
            raise NotImplementedError("pow not yet supported")
        
    def Div(self, x, y):
        if self.mode == "pysmt":
            return Div(x, y)
        elif self.mode == "smtlib":
            return f"(/ {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Equals(self, x, y):
        if self.mode == "pysmt":
            return Equals(x, y)
        elif self.mode == "smtlib":
            return f"(= {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def GE(self, x, y):
        if self.mode == "pysmt":
            return GE(x, y)
        elif self.mode == "smtlib":
            return f"(>= {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def LE(self, x, y):
        if self.mode == "pysmt":
            return LE(x, y)
        elif self.mode == "smtlib":
            return f"(<= {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def LT(self, x, y):
        if self.mode == "pysmt":
            return LT(x, y)
        elif self.mode == "smtlib":
            return f"(< {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def GT(self, x, y):
        if self.mode == "pysmt":
            return GT(x, y)
        elif self.mode == "smtlib":
            return f"(> {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Ite(self, condition, true_value, false_value):
        if self.mode == "pysmt":
            return Ite(condition, true_value, false_value)
        elif self.mode == "smtlib":
            return f"(ite {condition} {true_value} {false_value})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def And(self, *args):
        if self.mode == "pysmt":
            return And(*args)
        elif self.mode == "smtlib":
            return f"(and {' '.join(args)})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Or(self, *args):
        if self.mode == "pysmt":
            return Or(*args)
        elif self.mode == "smtlib":
            return f"(or {' '.join(args)})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Not(self, x):
        if self.mode == "pysmt":
            return Not(x)
        elif self.mode == "smtlib":
            return f"(not {x})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def Implies(self, condition, expr):
        if self.mode == "pysmt":
            return Implies(condition, expr)
        elif self.mode == "smtlib":
            return f"(=> {condition} {expr})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        
    def Mod(self, x, y):
        if self.mode == "pysmt":
            q = self.declare_integer(f"q_mod_{self.stats['integers']}")
            r = self.declare_integer(f"r_mod_{self.stats['integers']}")
            self.add_assertion(self.And(self.Equals(x, self.Plus(self.Times(y, q), r)), self.GE(r, Int(0)), self.LT(r, y)))
            return r
        elif self.mode == "smtlib":
            return f"(mod {x} {y})"
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def _pysmt_declaration(self, x, type):
        symbol = self.Symbol(x, type)
        self.symbols[x] = symbol
        self.declared_names.add(x)
        return symbol

    def _smtlib_declaration(self, x, type):
        self.declarations.append(("declare-fun", x, f"() {type}"))
        self.symbols[x] = x
        self.declared_names.add(x)
        return x
    
    def declare_real(self, x):
        if x not in self.declared_names:
            self.stats['reals'] += 1
            if self.mode == "pysmt":
                return self._pysmt_declaration(x, self.REAL)
            elif self.mode == "smtlib":
                return self._smtlib_declaration(x, "Real")
            elif self.mode == "milp":
                raise NotImplementedError("milp mode not yet supported")
        else:
            return self.format_real(x)      
            
    def format_real(self, x):
        if self.mode == "pysmt":
            if isinstance(x, (int, float)):
                return Real(x)
            elif isinstance(x, str):
                if x in self.symbols:
                    return self.symbols[x]
            return x
        elif self.mode == "smtlib":
            if isinstance(x, (int, float)):
                if isinstance(x, float) and not x.is_integer():
                    return f"{x:.15f}".rstrip('0').rstrip('.') # 2.00 -> 2, 2.100 -> 2.1 ...
                return str(x)
            return x
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")

    def Real(self, x):
        return self.format_real(x)
        
    def declare_integer(self, x):
        if x not in self.declared_names:
            # even though declaring integer, in QF_NRA, reals have to be used
            if self.logic == "QF_NRA":
                return self.declare_real(x)
            
            self.stats['integers'] += 1
            if self.mode == "pysmt":
                return self._pysmt_declaration(x, self.INT)
            elif self.mode == "smtlib":
                return self._smtlib_declaration(x, "Int")
            elif self.mode == "milp":
                raise NotImplementedError("milp mode not yet supported")
        else:
            return self.format_integer(x)
            
    def format_integer(self, x):
        if self.mode == "pysmt":
            if isinstance(x, int):
                return Int(x)
            elif isinstance(x, str):
                if x in self.symbols:
                    return self.symbols[x]
            return x
        elif self.mode == "smtlib":
            if isinstance(x, int):
                return str(x)
            return x
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        
    def Int(self, x):
        return self.format_integer(x)
        
    def declare_bool(self, x):
        if x not in self.declared_names:
            self.stats['bools'] += 1
            if self.mode == "pysmt":
                return self._pysmt_declaration(x, self.BOOL)
            elif self.mode == "smtlib":
                return self._smtlib_declaration(x, "Bool")
            elif self.mode == "milp":
                raise NotImplementedError("milp mode not yet supported")
        else:
            if self.mode == "pysmt":
                if x in self.symbols:
                    return self.symbols[x]
                return x
            elif self.mode == "smtlib":
                return x
            elif self.mode == "milp":
                raise NotImplementedError("milp mode not yet supported")

    def declare_helpers(self):
        # possible helper methods
        #sqrt2 for dreal
        self.declare_real("sqrt2")
        self.add_assertion(self.Equals(self.Times(self.format_real("sqrt2"), self.format_real("sqrt2")), self.Real(2.0)))

    def maximize(self, expression):
        if self.mode == "pysmt":
            pass
        elif self.mode == "smtlib":
            self.optimize_objectives.append(("maximize", expression))
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def minimize(self, expression):
        if self.mode == "pysmt":
            pass
        elif self.mode == "smtlib":
            self.optimize_objectives.append(("minimize", expression))
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def write_smtlib(self, filename):
        if self.mode == "pysmt":
            from pysmt.shortcuts import write_smtlib
            formula = self.solver.environment.formula_manager.And(self.solver.assertions)
            write_smtlib(formula, filename)
        elif self.mode == "smtlib":
            with open(filename, 'w') as f:
                f.write(f"(set-logic {self.logic})")
                self.declare_helpers()
                
                for decl_type, name, sig in self.declarations:
                    f.write(f"({decl_type} {name} {sig})")
                
                for assertion in self.assertions:
                    f.write(f"(assert {assertion})")
                
                for opt_type, expression in self.optimize_objectives:
                    f.write(f"({opt_type} {expression})")
                
                f.write("\n")
                f.write("(check-sat)")
                f.write("(get-model)")                
                f.write("\n")
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        
    def enumerate_k_values(self, n, pair_idx):
        if self.mode == "pysmt" or self.mode == "smtlib":
            self.declare_integer(f"k{pair_idx}")
            eqs = []
            for i in range(n):
                eqs.append(self.Equals(self.format_integer(f"k{pair_idx}"), self.format_integer(i)))
            self.add_assertion(self.Or(*eqs))
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        

    def enumerate_powers_of_2(self, n, pair_idx):
        if self.mode == "pysmt" or self.mode == "smtlib":
            self.declare_integer(f"pow2{pair_idx}")
            self.declare_integer(f"k{pair_idx}")
            for i in range(n):
                self.add_assertion(self.Implies(self.Equals(self.format_integer(f"k{pair_idx}"), self.format_integer(i)), self.Equals(self.format_integer(f"pow2{pair_idx}"), self.format_integer(2**i))))
            
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
    
    def add_rescaling(self, r1, r2, v1, v2, pair_idx, d):        
        n = self.declare_integer(f"n{pair_idx}")
        k = self.declare_integer(f"k{pair_idx}")
        # n = k1 - k2 or n = k2 - k1
        self.add_assertion(self.Ite(
            self.LT(self.Int(v1.k), self.Int(v2.k)), 
            self.Equals(n, self.Minus(self.Int(v2.k), self.Int(v1.k))), 
            self.Equals(n, self.Minus(self.Int(v1.k), self.Int(v2.k))))
        )
        # k = floor(n // 2)
        self.add_assertion(self.And(
            self.LE(self.Times(k, self.Int(2)), n),
            self.LT(n, self.Times(self.Plus(k, self.Int(1)), self.Int(2)))
        ))        
        def multiply_by_m_scaled(result_vec, source_vec, pow2_var):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(self.Equals(self.Int(result_vec.vec[i].a), self.Times(pow2_var, self.Minus(self.Int(source_vec.vec[i].b), self.Int(source_vec.vec[i].d)))))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].b), self.Times(pow2_var, self.Plus(self.Int(source_vec.vec[i].a), self.Int(source_vec.vec[i].c)))))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].c), self.Times(pow2_var, self.Plus(self.Int(source_vec.vec[i].b), self.Int(source_vec.vec[i].d)))))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].d), self.Times(pow2_var, self.Minus(self.Int(source_vec.vec[i].c), self.Int(source_vec.vec[i].a)))))
            return self.And(*eqs)
        
        def multiply_by_identity_scaled(result_vec, source_vec, pow2_var):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(self.Equals(self.Int(result_vec.vec[i].a), self.Times(pow2_var, self.Int(source_vec.vec[i].a))))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].b), self.Times(pow2_var, self.Int(source_vec.vec[i].b))))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].c), self.Times(pow2_var, self.Int(source_vec.vec[i].c))))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].d), self.Times(pow2_var, self.Int(source_vec.vec[i].d))))
            return self.And(*eqs)

        def multiply_by_identity_unscaled(result_vec, source_vec):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(self.Equals(self.Int(result_vec.vec[i].a), self.Int(source_vec.vec[i].a)))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].b), self.Int(source_vec.vec[i].b)))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].c), self.Int(source_vec.vec[i].c)))
                eqs.append(self.Equals(self.Int(result_vec.vec[i].d), self.Int(source_vec.vec[i].d)))
            return self.And(*eqs)
        
        if self.logic == "QF_LIA" or self.logic == "QF_NIA":
            if (d // 2) == 0:
                d = 2
            for i in range(d // 2):
                pow2 = self.Int(2 ** i)
                r1_multiply_by_m = self.And(multiply_by_m_scaled(r1, v1, pow2), multiply_by_identity_unscaled(r2, v2))
                r1_multiply_by_i = self.And(multiply_by_identity_scaled(r1, v1, pow2), multiply_by_identity_unscaled(r2, v2))
                r2_multiply_by_m = self.And(multiply_by_m_scaled(r2, v2, pow2), multiply_by_identity_unscaled(r1, v1))
                r2_multiply_by_i = self.And(multiply_by_identity_scaled(r2, v2, pow2), multiply_by_identity_unscaled(r1, v1))
                rescale_vec1 = self.Ite(self.Equals(self.Mod(n, self.Int(2)), self.Int(0)), r1_multiply_by_i, r1_multiply_by_m)
                rescale_vec2 = self.Ite(self.Equals(self.Mod(n, self.Int(2)), self.Int(0)), r2_multiply_by_i, r2_multiply_by_m)
                rescale_formula = self.Implies(self.Equals(k, self.Int(i)), self.Ite(self.LT(self.Int(v1.k), self.Int(v2.k)), rescale_vec1, rescale_vec2))
                same_k_formula = self.Ite(self.Equals(self.Int(v1.k), self.Int(v2.k)), v1 == v2, rescale_formula)
                self.add_assertion(same_k_formula)
        else:
            raise ValueError("rescaling with wrong logic")
        
        
    def add_constraints(self, gate_set, last_encoded_layer, qubits):
        if last_encoded_layer < 1:
            return

        #f"L{layer}_{gate}_q{q}" single qubit
        #f"L{layer}_{gate}_c{c}t{t}" two qubit
        #f"L{layer}_{gate}_c{c1}c{c2}t{t}" three qubit
        i = last_encoded_layer
        for q in range(qubits):
            if 'h' in gate_set:
                prev_layer = f"L{i - 1}_h_q{q}"
                curr_layer = f"L{i}_h_q{q}"
                self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
            if 'z' in gate_set:
                prev_layer = f"L{i - 1}_z_q{q}"
                curr_layer = f"L{i}_z_q{q}"
                self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
            if 'x' in gate_set:
                prev_layer = f"L{i - 1}_x_q{q}"
                curr_layer = f"L{i}_x_q{q}"
                self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
            if 'y' in gate_set:
                prev_layer = f"L{i - 1}_y_q{q}"
                curr_layer = f"L{i}_y_q{q}"
                self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
            if 'cx' in gate_set:
                for q2 in range(qubits):
                    if q2 == q: continue
                    prev_layer = f"L{i - 1}_cx_q{q}_q{q2}"
                    curr_layer = f"L{i}_cx_q{q}_q{q2}"
                    self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
        
    def get_stats(self):
        self.stats['variables'] = self.stats['reals'] + self.stats['integers'] + self.stats['bools']
        return self.stats
    
    def print_stats(self):
        self.stats['variables'] = self.stats['reals'] + self.stats['integers'] + self.stats['bools']
        print(f"Variables: {self.stats['variables']}")
        print(f"Reals: {self.stats['reals']}")
        print(f"Integers: {self.stats['integers']}")
        print(f"Booleans: {self.stats['bools']}")
        print(f"Assertions: {self.stats['assertions']}")