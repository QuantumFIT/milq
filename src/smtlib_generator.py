from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic

class SMTLibGenerator:
    def __init__(self):
        self.declarations = []
        self.declared_names = set()
        self.assertions = []
        self.var_counter = 0
        
        self.num_of_assertions = 0
        self.num_of_bool_variables = 0
        self.num_of_int_variables = 0
    
    def declare_real(self, name):
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Real"))
            self.declared_names.add(name)
        return name
    
    def declare_integer(self, name):
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
        lines.append("(define-fun is_even ((x Int)) Bool (ite (= (mod x 2) 0) true false))")
    
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
    
    def generate(self, complex_representation=None):
        if complex_representation is None:
            raise ValueError()
        
        if complex_representation == Complex:
            logic = "QF_NRA"
        elif complex_representation == Cyclotomic8Dyadic:
            logic = "QF_LIA"
        else:
            raise ValueError()
        
        lines = [f"(set-logic {logic})"]
        self.declare_helpers(lines)
        
        for decl_type, name, sig in self.declarations:
            lines.append(f"({decl_type} {name} {sig})")
        
        if self.declarations:
            lines.append("")
        
        for assertion in self.assertions:
            lines.append(f"(assert {assertion})")
        
        lines.append("")
        lines.append("(check-sat)")
        lines.append("(get-model)")
        
        return "\n".join(lines)