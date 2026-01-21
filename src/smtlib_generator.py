from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic, nTuple
from pysmt.smtlib.parser import SmtLibParser
from pysmt.shortcuts import Real, Int, Bool, Symbol, And, Equals, Div, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Times, Minus, Plus

from pysmt.typing import REAL, INT, BOOL

class SMTLibGenerator:
    def __init__(self, rescaling=False, approximate_equivalence=False, logic="QF_NIA"):
        self.declarations = []
        self.declared_names = set()
        self.assertions = []
        self.optimize_objectives = []
        self.var_counter = 0
        self.name = "SMTLibGenerator"
        
        self.num_of_assertions = 0
        self.num_of_bool_variables = 0
        self.num_of_int_variables = 0
        self.rescaling = rescaling
        self.approximate_equivalence = approximate_equivalence
        if approximate_equivalence:
            self.logic = "QF_NRA"
        else:
            self.logic = logic
    
    def declare_real(self, name):
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Real"))
            self.declared_names.add(name)
        return name
    
    def declare_integer(self, name):
        # in nra, use reals in any representation
        if self.rescaling:
            return self.declare_real(name)
            
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Int"))
            self.declared_names.add(name)
            self.num_of_int_variables += 1
        return name
    
    def declare_bool(self, name):
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Bool"))
            self.declared_names.add(name)
            self.num_of_bool_variables += 1
        return name
    
    def add_assertion(self, assertion):
        self.num_of_assertions += 1
        self.assertions.append(assertion)
    
    def enumerate_powers_of_2(self, n):
        self.declare_integer(f"pow2")
        self.declare_integer(f"k")
        # (assert (=> (= k i) (= pow2 (2**i)))
        #k = floor(n/2)
        self.add_assertion(f"(= k (div n 2))")
        for i in range(n):
            self.add_assertion(f"(=> (= k {i}) (= pow2 {2**i}))")
    
    def enumerate_k_values(self, n):
        eqs = []
        for i in range(n):
            eqs.append(f"(= k {i})")
        self.add_assertion(f"(or {' '.join(eqs)})")
            
    def add_rescaling(self, r1, r2, v1, v2):
        # pow2 * M(or I) * v1 = r1
        def multiply_by_m_scaled(result_vec, source_vec, pow2_var):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(f"(= {result_vec.vec[i].a} (* {pow2_var} (- {source_vec.vec[i].b} {source_vec.vec[i].d})))")
                eqs.append(f"(= {result_vec.vec[i].b} (* {pow2_var} (+ {source_vec.vec[i].a} {source_vec.vec[i].c})))")
                eqs.append(f"(= {result_vec.vec[i].c} (* {pow2_var} (+ {source_vec.vec[i].b} {source_vec.vec[i].d})))")
                eqs.append(f"(= {result_vec.vec[i].d} (* {pow2_var} (- {source_vec.vec[i].c} {source_vec.vec[i].a})))")
            return f"(and {' '.join(eqs)})"
        
        def multiply_by_identity_scaled(result_vec, source_vec, pow2_var):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(f"(= {result_vec.vec[i].a} (* {pow2_var} {source_vec.vec[i].a}))")
                eqs.append(f"(= {result_vec.vec[i].b} (* {pow2_var} {source_vec.vec[i].b}))")
                eqs.append(f"(= {result_vec.vec[i].c} (* {pow2_var} {source_vec.vec[i].c}))")
                eqs.append(f"(= {result_vec.vec[i].d} (* {pow2_var} {source_vec.vec[i].d}))")
            return f"(and {' '.join(eqs)})"

        def multiply_by_identity_unscaled(result_vec, source_vec):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(f"(= {result_vec.vec[i].a} {source_vec.vec[i].a})")
                eqs.append(f"(= {result_vec.vec[i].b} {source_vec.vec[i].b})")
                eqs.append(f"(= {result_vec.vec[i].c} {source_vec.vec[i].c})")
                eqs.append(f"(= {result_vec.vec[i].d} {source_vec.vec[i].d})")
            return f"(and {' '.join(eqs)})"
        
        r1_multiply_by_m = f"(and {multiply_by_m_scaled(r1, v1, "pow2")} {multiply_by_identity_unscaled(r2, v2)})"
        r1_multiply_by_i = f"(and {multiply_by_identity_scaled(r1, v1, "pow2")} {multiply_by_identity_unscaled(r2, v2)})"
        r2_multiply_by_m = f"(and {multiply_by_m_scaled(r2, v2, "pow2")} {multiply_by_identity_unscaled(r1, v1)})"
        r2_multiply_by_i = f"(and {multiply_by_identity_scaled(r2, v2, "pow2")} {multiply_by_identity_unscaled(r1, v1)})"
        
        rescale_vec1 = ""
        rescale_vec2 = ""
        if self.logic == "QF_NIA":
            rescale_vec1 = f"(ite (= (mod n 2) 0) {r1_multiply_by_i} {r1_multiply_by_m})"
            rescale_vec2 = f"(ite (= (mod n 2) 0) {r2_multiply_by_i} {r2_multiply_by_m})"
        else:
            rescale_vec1 = f"(ite is_even {r1_multiply_by_i} {r1_multiply_by_m})"
            rescale_vec2 = f"(ite is_even {r2_multiply_by_i} {r2_multiply_by_m})"
        self.add_assertion(f"(ite (< {v1.k} {v2.k}) {rescale_vec1} {rescale_vec2})")
        
    
    def maximize(self, expression):
        self.optimize_objectives.append(("maximize", expression))
    
    def minimize(self, expression):
        self.optimize_objectives.append(("minimize", expression))
    
    def format_real(self, value):
        if isinstance(value, (int, float)):
            # Format as decimal if needed
            if isinstance(value, float) and not value.is_integer():
                return f"{value:.15f}".rstrip('0').rstrip('.')
            return str(value)
        return value
    
    def format_integer(self, value):
        if isinstance(value, int):
            return str(value)
        return value
    
    def declare_helpers(self, lines):
        # add is_even
        #lines.append("(define-fun is_even ((x Int)) Bool (ite (= (mod x 2) 0) true false))")
        pass

    def is_even(self, x):
        return f"(is_even {x})"
    
    def ite(self, condition, true_value, false_value):
        return f"(ite {condition} {true_value} {false_value})"
    
    def mul(self, x, y):
        return f"(* {x} {y})"
    
    def add(self, x, y):
        return f"(+ {x} {y})"
    
    def sub(self, x, y):
        return f"(- {x} {y})"
    
    def mod(self, x, y):
        return f"(mod {x} {y})"
    
    def eq(self, x, y):
        return f"(= {x} {y})"
    
    def maximize(self, expression):
        self.optimize_objectives.append(("maximize", expression))
    
    def generate(self, complex_representation=None):
        if complex_representation is None:
            raise ValueError()
        
        if self.rescaling:
            self.logic = "QF_NRA"
        elif complex_representation == Complex:
            self.logic = "QF_NRA"
        elif complex_representation == Cyclotomic8Dyadic:
            self.logic = "QF_NIA"
        elif complex_representation == nTuple:
            self.logic = "QF_NIA"
        else:
            raise ValueError()
        
        lines = [f"(set-logic {self.logic})"]
        self.declare_helpers(lines)
        
        for decl_type, name, sig in self.declarations:
            lines.append(f"({decl_type} {name} {sig})")
        
        if self.declarations:
            lines.append("")
        
        for assertion in self.assertions:
            if assertion is not None:
                lines.append(f"(assert {assertion})")
        
        for opt_type, expression in self.optimize_objectives:
            lines.append(f"({opt_type} {expression})")
        
        lines.append("")
        lines.append("(check-sat)")
        lines.append("(get-model)")
        
        return "\n".join(lines)
    
class PortfolioSolver:
    def __init__(self, solver=None):
        self.solver = solver
        self.declarations = []
        self.declared_names = set()
        self.assertions = []
        self.optimize_objectives = []
        self.var_counter = 0
        self.name = "PortfolioSolver"
        
        self.num_of_assertions = 0
        self.num_of_bool_variables = 0
        self.num_of_int_variables = 0
        self.num_of_real_variables = 0
        self.logic = "QF_NIA"
        self.Symbol = Symbol
        self.REAL = REAL
        self.INT = INT
        self.BOOL = BOOL
        self.symbols = {}
    
    def declare_real(self, name):
        if name not in self.declared_names:
            symbol = self.Symbol(name, self.REAL)
            self.symbols[name] = symbol
            self.declared_names.add(name)
            self.num_of_real_variables += 1
        return self.symbols[name]
    
    def declare_integer(self, name):
        if name not in self.declared_names:
            symbol = self.Symbol(name, self.INT)
            self.symbols[name] = symbol
            self.declared_names.add(name)
            self.num_of_int_variables += 1
        return self.symbols[name]
    
    def declare_bool(self, name):
        if name not in self.declared_names:
            symbol = self.Symbol(name, self.BOOL)
            self.symbols[name] = symbol
            self.declared_names.add(name)
            self.num_of_bool_variables += 1
        return self.symbols[name]
    
    def format_real(self, value):
        if isinstance(value, (int, float)):
            return Real(value)
        elif isinstance(value, str):
            if value in self.symbols:
                return self.symbols[value]
            return value
        return value
    
    def format_integer(self, value):
        if isinstance(value, int):
            return Int(value)
        elif isinstance(value, str):
            if value in self.symbols:
                return self.symbols[value]
            return value
        return value
    
    def add_assertion(self, assertion):
        if assertion is None:
            raise ValueError("Assertion is None")
        self.solver.add_assertion(assertion)
        self.num_of_assertions += 1
        
    def enumerate_powers_of_2(self, n):
        self.declare_integer(f"pow2")
        self.declare_integer(f"k")
        # (assert (=> (= k i) (= pow2 (2**i)))
        for i in range(n):
            self.add_assertion(Implies(Equals(self.symbols["k"], Int(i)), Equals(self.symbols["pow2"], Int(2**i))))
            
    def add_rescaling(self, r1, r2, v1, v2):
        # pow2 * M(or I) * v1 = r1
        
        # sometimes .solve() was throwing errors, because some values are not represented as pysmt expressions properly
        def to_pysmt(value):
            if isinstance(value, str):
                if value in self.symbols:
                    return self.symbols[value]
                try:
                    if '.' in value:
                        return Real(float(value))
                    else:
                        return Int(int(value))
                except (ValueError, TypeError):
                    return Symbol(value, INT)
            elif isinstance(value, int):
                return Int(value)
            elif isinstance(value, float):
                return Real(value)
            else:
                return value 
        
        def multiply_by_m_scaled(result_vec, source_vec, pow2_var):
            eqs = []
            for i in range(len(result_vec.vec)):
                r_a = to_pysmt(result_vec.vec[i].a)
                r_b = to_pysmt(result_vec.vec[i].b)
                r_c = to_pysmt(result_vec.vec[i].c)
                r_d = to_pysmt(result_vec.vec[i].d)
                s_a = to_pysmt(source_vec.vec[i].a)
                s_b = to_pysmt(source_vec.vec[i].b)
                s_c = to_pysmt(source_vec.vec[i].c)
                s_d = to_pysmt(source_vec.vec[i].d)
                eqs.append(Equals(r_a, Times(pow2_var, Minus(s_b, s_d))))
                eqs.append(Equals(r_b, Times(pow2_var, Plus(s_a, s_c))))
                eqs.append(Equals(r_c, Times(pow2_var, Plus(s_b, s_d))))
                eqs.append(Equals(r_d, Times(pow2_var, Minus(s_c, s_a))))
            return And(*eqs)
        
        def multiply_by_identity_scaled(result_vec, source_vec, pow2_var):
            eqs = []
            for i in range(len(result_vec.vec)):
                r_a = to_pysmt(result_vec.vec[i].a)
                r_b = to_pysmt(result_vec.vec[i].b)
                r_c = to_pysmt(result_vec.vec[i].c)
                r_d = to_pysmt(result_vec.vec[i].d)
                s_a = to_pysmt(source_vec.vec[i].a)
                s_b = to_pysmt(source_vec.vec[i].b)
                s_c = to_pysmt(source_vec.vec[i].c)
                s_d = to_pysmt(source_vec.vec[i].d)
                eqs.append(Equals(r_a, Times(pow2_var, s_a)))
                eqs.append(Equals(r_b, Times(pow2_var, s_b)))
                eqs.append(Equals(r_c, Times(pow2_var, s_c)))
                eqs.append(Equals(r_d, Times(pow2_var, s_d)))
            return And(*eqs)

        def multiply_by_identity_unscaled(result_vec, source_vec):
            eqs = []
            for i in range(len(result_vec.vec)):
                r_a = to_pysmt(result_vec.vec[i].a)
                r_b = to_pysmt(result_vec.vec[i].b)
                r_c = to_pysmt(result_vec.vec[i].c)
                r_d = to_pysmt(result_vec.vec[i].d)
                s_a = to_pysmt(source_vec.vec[i].a)
                s_b = to_pysmt(source_vec.vec[i].b)
                s_c = to_pysmt(source_vec.vec[i].c)
                s_d = to_pysmt(source_vec.vec[i].d)
                eqs.append(Equals(r_a, s_a))
                eqs.append(Equals(r_b, s_b))
                eqs.append(Equals(r_c, s_c))
                eqs.append(Equals(r_d, s_d))
            return And(*eqs)
        
        
        pow2 = self.symbols["pow2"]
        r1_multiply_by_m = And(multiply_by_m_scaled(r1, v1, pow2), multiply_by_identity_unscaled(r2, v2))
        r1_multiply_by_i = And(multiply_by_identity_scaled(r1, v1, pow2), multiply_by_identity_unscaled(r2, v2))
        r2_multiply_by_m = And(multiply_by_m_scaled(r2, v2, pow2), multiply_by_identity_unscaled(r1, v1))
        r2_multiply_by_i = And(multiply_by_identity_scaled(r2, v2, pow2), multiply_by_identity_unscaled(r1, v1))
        
        # pysmt doesnt have Mod shortcut
        # x mod y = r <=> x = y * q + r, r in <0, y>
        # so we can use this to define Mod
        def Mod(x, y):
            q = self.declare_integer(f"q_mod_{self.num_of_int_variables}")
            r = self.declare_integer(f"r_mod_{self.num_of_int_variables}")
            self.add_assertion(And(Equals(x, Plus(Times(y, q), r)), GE(r, Int(0)), LT(r, y)))
            return r
        
        rescale_vec1 = Ite(Equals(Mod(self.symbols["n"], Int(2)), Int(0)), r1_multiply_by_i, r1_multiply_by_m)
        rescale_vec2 = Ite(Equals(Mod(self.symbols["n"], Int(2)), Int(0)), r2_multiply_by_i, r2_multiply_by_m)
        self.add_assertion(Ite(LT(v1.k, v2.k), rescale_vec1, rescale_vec2))