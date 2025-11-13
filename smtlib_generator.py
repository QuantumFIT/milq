from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic

class SMTLibGenerator:
    def __init__(self):
        self.declarations = []
        self.declared_names = set()
        self.assertions = []
        self.var_counter = 0
    
    def declare_real(self, name):
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Real"))
            self.declared_names.add(name)
        return name
    
    def declare_integer(self, name):
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Int"))
            self.declared_names.add(name)
        return name
    
    def declare_bool(self, name):
        if name not in self.declared_names:
            self.declarations.append(("declare-fun", name, "() Bool"))
            self.declared_names.add(name)
        return name
    
    def add_assertion(self, assertion):
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