from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic, nTuple
from pysmt.smtlib.parser import SmtLibParser
from pysmt.shortcuts import Real, Int, Bool, Symbol
from pysmt.typing import REAL, INT, BOOL

class SMTLibGenerator:
    def __init__(self, rescaling=False, rescaling_tmp=False, logic="QF_NIA"):
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
        self.rescaling_tmp = rescaling_tmp
        if rescaling:
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

        def multiply_by_itentity_unscaled(result_vec, source_vec):
            eqs = []
            for i in range(len(result_vec.vec)):
                eqs.append(f"(= {result_vec.vec[i].a} {source_vec.vec[i].a})")
                eqs.append(f"(= {result_vec.vec[i].b} {source_vec.vec[i].b})")
                eqs.append(f"(= {result_vec.vec[i].c} {source_vec.vec[i].c})")
                eqs.append(f"(= {result_vec.vec[i].d} {source_vec.vec[i].d})")
            return f"(and {' '.join(eqs)})"
        
        r1_multiply_by_m = f"(and {multiply_by_m_scaled(r1, v1, "pow2")} {multiply_by_itentity_unscaled(r2, v2)})"
        r1_multiply_by_i = f"(and {multiply_by_identity_scaled(r1, v1, "pow2")} {multiply_by_itentity_unscaled(r2, v2)})"
        r2_multiply_by_m = f"(and {multiply_by_m_scaled(r2, v2, "pow2")} {multiply_by_itentity_unscaled(r1, v1)})"
        r2_multiply_by_i = f"(and {multiply_by_identity_scaled(r2, v2, "pow2")} {multiply_by_itentity_unscaled(r1, v1)})"
        
        rescale_vec1 = f"(ite (= (mod n 2) 0) {r1_multiply_by_i} {r1_multiply_by_m})"
        rescale_vec2 = f"(ite (= (mod n 2) 0) {r2_multiply_by_i} {r2_multiply_by_m})"
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
    def __init__(self, solver):
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
        self.logic = "QF_LIA"
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