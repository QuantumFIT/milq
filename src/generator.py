from ast import Return
from pysmt.smtlib.parser import SmtLibParser
from pysmt.shortcuts import Real, Int, Bool, Symbol, And, Equals, Div, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Times, Minus, Plus
from pysmt.typing import REAL, INT, BOOL
from pulp import *
from gates import self_adjoints, gate_to_qubits
import gurobipy as gp
from gurobipy import GRB, quicksum

class Generator:
    def __init__(self, mode : str = "pysmt", solver : str = "opensmt", logic : str = "QF_LIA") -> None:
        # modes - ["pysmt", "smtlib", "milp", "gurobi"]
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
        self.lp_problem = None
        self.bool_variables = set()
        self.integer_variables = set()
        self.real_variables = set()
        self.saved_lp_problem = None
        self.gurobi_saved_push = None
        self.objective_assertions = []
        self.stats['reals'] = 0
        self.stats['integers'] = 0
        self.stats['bools'] = 0
        self.stats['assertions'] = 0
        self.stats['variables'] = 0
        self.stats['objectives'] = 0
        if self.solver == "dreal":
            self.logic = "QF_NRA"

    def _gp_params(self):
        self.lp_problem.Params.IntFeasTol = 1e-9
        self.lp_problem.Params.FeasibilityTol = 1e-9
        self.lp_problem.Params.MIPGap = 1e-9
        self.lp_problem.Params.OutputFlag = 0

    def add_assertion(self, assertion):
        if self.mode == "pysmt":
            if self.solver is None:
                raise ValueError("solver is not set")
            self.solver.add_assertion(assertion)
        elif self.mode == "smtlib":
            self.assertions.append(assertion)
        elif self.mode == "milp":
            if assertion is None:
                return
            if self.lp_problem is None:
                self.lp_problem = LpProblem("Circuit_Synthesis", LpMinimize)
            self.lp_problem += assertion, f"assertion_{self.stats['assertions']}"
        elif self.mode == "gurobi":
            if assertion is None:
                return
            if self.lp_problem is None:
                self.lp_problem = gp.Model("Circuit_Synthesis")
                self._gp_params()
                self.lp_problem.setObjective(0, GRB.MINIMIZE)
            self.lp_problem.update()
            self.lp_problem.addConstr(assertion, name=f"assertion_{self.stats['assertions']}")
        self.stats['assertions'] += 1
    
    def add_quadratic_assertion(self, assertion):
        if self.mode == "gurobi":
            self.lp_problem.addQConstr(assertion, name=f"assertion_{self.stats['assertions']}")
            self.stats['assertions'] += 1
        else:
            raise NotImplementedError("quadratic assertions only in gurobipy api")

    def add_objective(self, objective):
        if self.mode == "pysmt":
            return
        elif self.mode == "smtlib":
            return
        elif self.mode == "milp":
            # implementation "hack" for push/pop
            self.lp_problem += objective, f"assertion_{self.stats['assertions']}"
            self.objective_assertions.append(self.stats['assertions'])
            self.stats['assertions'] += 1
        elif self.mode == "gurobi":
            self.lp_problem.setObjective(objective, GRB.MINIMIZE)
        self.stats['objectives'] += 1

    def Plus(self, x, y):
        if self.mode == "pysmt":
            return Plus(x, y)
        elif self.mode == "smtlib":
            return f"(+ {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x + y
    
    def Minus(self, x, y):
        if self.mode == "pysmt":
            return Minus(x, y)
        elif self.mode == "smtlib":
            return f"(- {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x - y
    
    def Times(self, x, y):
        if self.mode == "pysmt":
            return Times(x, y)
        elif self.mode == "smtlib":
            return f"(* {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x * y
        
    def Pow(self, x, y):
        if self.mode == "smtlib" and self.logic == "QF_NRA":
            return f"(pow {x} {y})"
        else:
            raise NotImplementedError("pow not yet supported")
    
    def Square(self, x):
        if self.mode == "gurobi":
            return self.Times(x, x)
        else:
            raise NotImplementedError("square not yet supported")
        
    def Div(self, x, y):
        if self.mode == "pysmt":
            return Div(x, y)
        elif self.mode == "smtlib":
            return f"(/ {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x / y
    
    def Equals(self, x, y):
        if self.mode == "pysmt":
            return Equals(x, y)
        elif self.mode == "smtlib":
            return f"(= {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x == y

    def ConstrainedEquals(self, sel, x, y, bigM=None):
        if self.mode == "pysmt" or self.mode == "smtlib":
            return self.Implies(sel, self.Equals(x, y))
        elif self.mode == "milp" or self.mode == "gurobi":
            return x.constrained_equals(sel, bigM, x, y)
    
    def GE(self, x, y):
        if self.mode == "pysmt":
            return GE(x, y)
        elif self.mode == "smtlib":
            return f"(>= {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x >= y
    
    def LE(self, x, y):
        if self.mode == "pysmt":
            return LE(x, y)
        elif self.mode == "smtlib":
            return f"(<= {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x <= y
    
    def LT(self, x, y):
        if self.mode == "pysmt":
            return LT(x, y)
        elif self.mode == "smtlib":
            return f"(< {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x < y
    
    def GT(self, x, y):
        if self.mode == "pysmt":
            return GT(x, y)
        elif self.mode == "smtlib":
            return f"(> {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return x > y
    
    def Ite(self, condition, true_value, false_value):
        if self.mode == "pysmt":
            return Ite(condition, true_value, false_value)
        elif self.mode == "smtlib":
            return f"(ite {condition} {true_value} {false_value})"
        elif self.mode == "milp" or self.mode == "gurobi":
            raise NotImplementedError("explicit Ite not supported in milp/gurobi mode")
    
    def And(self, *args):
        if self.mode == "pysmt":
            return And(*args)
        elif self.mode == "smtlib":
            return f"(and {' '.join(args)})"
        elif self.mode == "milp" or self.mode == "gurobi":
            for arg in args:
                self.add_assertion(arg)
    
    def Or(self, *args):
        if self.mode == "pysmt":
            return Or(*args)
        elif self.mode == "smtlib":
            return f"(or {' '.join(args)})"
        elif self.mode == "milp" or self.mode == "gurobi":
            helper_var = self.declare_bool(f"or_{self.stats['bools']}")
            for arg in args:
                self.add_assertion(self.LE(arg, helper_var))
            self.add_assertion(self.LE(helper_var, self.Sum(args)))
            
    def Indicator(self, sel, expr):
        # sel == 1 >> expr
        if self.mode == "gurobi":
            return ((sel == 1) >> expr)
        else:
            raise NotImplementedError("Indicator not supported in milp/pysmt/smtlib mode")
    
    def NotIndicator(self, sel, expr):
        if self.mode == "gurobi":
            return ((sel == 0) >> expr)
        else:
            raise NotImplementedError("NotIndicator not supported in milp/pysmt/smtlib mode")
        
    def Abs(self, x):
        if self.mode == "gurobi":
            return gp.abs_(x)
        else:
            raise NotImplementedError("Abs not supported in milp/pysmt/smtlib mode")

    def Not(self, x):
        if self.mode == "pysmt":
            return Not(x)
        elif self.mode == "smtlib":
            return f"(not {x})"
        elif self.mode == "milp" or self.mode == "gurobi":
            return 1 - x
        
    def Sum(self, *args):
        if self.mode == "pysmt" or self.mode == "smtlib":
            raise NotImplementedError("Sum not supported in milp/gurobi mode")
        elif self.mode == "milp":
            return lpSum(args)
        elif self.mode == "gurobi":
            return quicksum(*args)

    def AtLeastOne(self, *args):
        # OR between all 
        if self.mode == "milp" or self.mode == "gurobi":
            return self.add_assertion(self.Sum([bool_variable for bool_variable in args]) >= 1)
        elif self.mode == "pysmt" or self.mode == "smtlib":
            return self.add_assertion(self.Or(*args))
    
    def AtMostOne(self, *args):
        # (NOT x1 or x2) and NOT (x1 and x3) ...
        if self.mode == "milp" or self.mode == "pysmt" or self.mode == "smtlib":
            for i in range(len(args)):
                others = [args[j] for j in range(len(args)) if j != i]
                for other in others:
                    self.add_assertion(self.Or(self.Not(args[i]), self.Not(other)))
        elif self.mode == "gurobi":
            self.lp_problem.addSOS(GRB.SOS_TYPE1, [args[i] for i in range(len(args))])

    def ExactlyOne(self, *args):
        if self.mode == "milp":
            self.add_assertion(self.Sum([bool_variable for bool_variable in args]) == 1)
        else:
            self.AtLeastOne(*args)
            self.AtMostOne(*args)
    
    def Implies(self, condition, expr):
        if self.mode == "pysmt":
            return Implies(condition, expr)
        elif self.mode == "smtlib":
            return f"(=> {condition} {expr})"
        elif self.mode == "milp" or self.mode == "gurobi":
            raise NotImplementedError("explicit Implies not supported in milp/gurobi mode")
        
    def Mod(self, x, y):
        if self.mode == "pysmt":
            q = self.declare_integer(f"q_mod_{self.stats['integers']}")
            r = self.declare_integer(f"r_mod_{self.stats['integers']}")
            self.add_assertion(self.And(self.Equals(x, self.Plus(self.Times(y, q), r)), self.GE(r, Int(0)), self.LT(r, y)))
            return r
        elif self.mode == "smtlib":
            return f"(mod {x} {y})"
        elif self.mode == "milp" or self.mode == "gurobi":
            raise NotImplementedError("Mod not supported in milp/gurobi mode")
    
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

    def _milp_declaration(self, x, type, lb=None, ub=None):
        var = LpVariable(x, cat=type, lowBound=lb, upBound=ub)
        self.symbols[x] = var
        self.declared_names.add(x)
        return var

    def _gurobi_declaration(self, x, type, lb=None, ub=None):
        if lb is None:
            lb = -GRB.INFINITY
        if ub is None:
            ub = GRB.INFINITY
        if self.lp_problem is None:
            self.lp_problem = gp.Model("Circuit_Synthesis")
            self._gp_params()
        var = self.lp_problem.addVar(name=x, lb=lb, ub=ub, vtype=type)
        self.lp_problem.update()
        self.symbols[x] = var
        self.declared_names.add(x)
        return var
    
    def declare_real(self, x, lb=None, ub=None):
        res = None
        if x not in self.declared_names:
            self.stats['reals'] += 1
            if self.mode == "pysmt":
                res = self._pysmt_declaration(x, self.REAL)
            elif self.mode == "smtlib":
                res = self._smtlib_declaration(x, "Real")
            elif self.mode == "milp":
                res = self._milp_declaration(x, LpContinuous, lb, ub)
            elif self.mode == "gurobi":
                res = self._gurobi_declaration(x, GRB.CONTINUOUS, lb, ub)
        else:
            res = self.format_real(x)
        
        if res is not None:
            self.real_variables.add(res)
        return res
         
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
        elif self.mode == "milp" or self.mode == "gurobi":
            if isinstance(x, float):
                return x
            elif isinstance(x, str):
                if x in self.symbols:
                    return self.symbols[x]
            return x

    def Real(self, x):
        return self.format_real(x)
        
    def declare_integer(self, x, lb=None, ub=None):
        res = None
        if x not in self.declared_names:
            # even though declaring integer, in QF_NRA, reals have to be used
            if self.logic == "QF_NRA":
                return self.declare_real(x)
            if self.mode == "pysmt":
                res = self._pysmt_declaration(x, self.INT)
            elif self.mode == "smtlib":
                res = self._smtlib_declaration(x, "Int")
            elif self.mode == "milp":
                res =  self._milp_declaration(x, LpInteger, lb, ub)
            elif self.mode == "gurobi":
                res = self._gurobi_declaration(x, GRB.INTEGER, lb, ub)
            self.stats['integers'] += 1
        else:
            res = self.format_integer(x)

        if res is not None:
            self.integer_variables.add(res)
        return res
            
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
        elif self.mode == "milp" or self.mode == "gurobi":
            if isinstance(x, int):
                return x
            elif isinstance(x, str):
                if x in self.symbols:
                    return self.symbols[x]
            return x
        
    def Int(self, x):
        return self.format_integer(x)
        
    def declare_bool(self, x):
        res = None
        if x not in self.declared_names:
            self.stats['bools'] += 1
            if self.mode == "pysmt":
                res = self._pysmt_declaration(x, self.BOOL)
            elif self.mode == "smtlib":
                res =  self._smtlib_declaration(x, "Bool")
            elif self.mode == "milp":
                res = self._milp_declaration(x, LpBinary)
            elif self.mode == "gurobi":
                res = self._gurobi_declaration(x, GRB.BINARY, lb=0.0, ub=1.0)
        else:
            if self.mode == "pysmt":
                if x in self.symbols:
                    res = self.symbols[x]
                else:
                    res = x
            elif self.mode == "smtlib":
                res = x
            elif self.mode == "milp" or self.mode == "gurobi":
                if x in self.symbols:
                    res = self.symbols[x]
                else:
                    res = x
        if res is not None:
            self.bool_variables.add(res)
        return res

    def declare_helpers(self):
        # possible helper methods
        #sqrt2 for dreal
        if self.logic == "QF_NRA":
            self.declare_real("sqrt2")
            self.add_assertion(self.Equals(self.Times(self.format_real("sqrt2"), self.format_real("sqrt2")), self.Real(2.0)))

    def maximize(self, expression):
        if self.mode == "pysmt":
            pass
        elif self.mode == "smtlib":
            self.optimize_objectives.append(("maximize", expression))
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        elif self.mode == "gurobi":
            self.lp_problem.setObjective(expression, GRB.MAXIMIZE)
    
    def minimize(self, expression):
        if self.mode == "pysmt":
            pass
        elif self.mode == "smtlib":
            self.optimize_objectives.append(("minimize", expression))
        elif self.mode == "milp":
            raise NotImplementedError("milp mode not yet supported")
        elif self.mode == "gurobi":
            self.lp_problem.setObjective(expression, GRB.MINIMIZE)
    
    def write_formula(self, filename):
        if self.mode == "pysmt":
            filename = filename.split(".")[0] + ".smt2"
            from pysmt.shortcuts import write_smtlib
            formula = self.solver.environment.formula_manager.And(self.solver.assertions)
            write_smtlib(formula, filename)
        elif self.mode == "smtlib":
            filename = filename.split(".")[0] + ".smt2"
            with open(filename, 'w') as f:
                f.write(f"(set-logic {self.logic})\n")
                self.declare_helpers()
                
                for decl_type, name, sig in self.declarations:
                    f.write(f"({decl_type} {name} {sig})\n")
                
                for assertion in self.assertions:
                    f.write(f"(assert {assertion})\n")
                
                for opt_type, expression in self.optimize_objectives:
                    f.write(f"({opt_type} {expression})\n")
                
                f.write("\n")
                f.write("(check-sat)\n")
                f.write("(get-model)\n")                
                f.write("\n")
        elif self.mode == "milp":
            filename = filename.split(".")[0] + ".lp"
            self.lp_problem.writeLP(filename)
        elif self.mode == "gurobi":
            filename = filename.split(".")[0] + ".lp"
            self.lp_problem.write(filename)
        return filename
        
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
            
        elif self.mode == "milp" or self.mode == "gurobi":
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
            for i in range(d):
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
            
    def add_milp_rescaling(self, r1, r2, v1, v2, pair_idx, d):
        # first encode k as the result of the operation floor(abs(k1 - k2)/2)
        complex_representation = v1.element_representation
        k = self.declare_integer(f"k{pair_idx}", lb=0, ub=d)
        q = self.declare_bool(f"q{pair_idx}")

        bigM = 2*d + 1
        sleq = self.declare_bool(f"sleq{pair_idx}")
        self.add_assertion((v1.k - v2.k) - (2*k + q) <= bigM * sleq)
        self.add_assertion((2*k + q) - (v1.k - v2.k) <= bigM * sleq)
        self.add_assertion((v2.k - v1.k) - (2*k + q) <= bigM * (1 - sleq))
        self.add_assertion((2*k + q) - (v2.k - v1.k) <= bigM * (1 - sleq))

        # now retreive the boolean variable that will express the 2^i constant
        constants = [self.declare_bool(f"s{pair_idx}_{i}") for i in range(d+1)]
        if self.mode == "milp" or self.mode == "gurobi":
            self.add_assertion(self.Sum([s for s in constants]) == 1)
            self.add_assertion(k == self.Sum([constants[i] * i for i in range(d+1)]))
        # now constants[i] is True iff k = i
        # next, determine if k is odd or even

        # now sleq, si, even encode all case splits needed for the rescaling
        # encode all combinations to assign to r1, r2
        
        bigM = (2**(d+1)) + 1
        # for every si, I,M is multiplied by 2^i
        for i in range(len(v1)):
            for j, s in enumerate(constants):
                for parity in [("even", (1 - q)), ("odd", q)]:
                    for rel in [("<=", sleq), (">", (1 - sleq))]:
                        and_var = self.declare_bool(f"and_var{i}_{j}_{parity[0]}_{'lower' if rel[0] == '<=' else 'upper'}")
                        self.add_assertion(and_var <= rel[1])
                        self.add_assertion(and_var <= s)
                        self.add_assertion(and_var <= parity[1])
                        self.add_assertion(and_var >= (rel[1] + s + parity[1] - 2))
                        complex_representation.constrained_rescaling(bigM, and_var, r1[i], r2[i], v1[i], v2[i], 2**j, parity[0], rel[0])

    def add_constraints(self, gate_set, last_encoded_layer, qubits):
        if last_encoded_layer < 1:
            return

        pairs = []
        self_adjoints_in_gate_set = set(gate_set).intersection(set(self_adjoints))
        others = set(gate_set) - self_adjoints_in_gate_set
        for gate in self_adjoints_in_gate_set:
            pairs.append((gate, gate))
        for gate in others:
            name = gate + "dg"
            if name in gate_set:
                pairs.append((gate, name))
        
        for (gate, adjoint) in pairs:
            gate_qubits = gate_to_qubits(gate)
            for q in range(qubits):
                if gate_qubits > 1:
                    for q2 in range(qubits):
                        if q2 == q: continue
                        if gate_qubits > 2:
                            for q3 in range(qubits):
                                if q3 == q or q3 == q2: continue
                                prev_layer = f"L{last_encoded_layer - 1}_{gate}_q{q}_q{q2}_q{q3}"
                                curr_layer = f"L{last_encoded_layer}_{gate}_q{q}_q{q2}_q{q3}"
                                self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
                        else:
                            prev_layer = f"L{last_encoded_layer - 1}_{gate}_q{q}_q{q2}"
                            curr_layer = f"L{last_encoded_layer}_{gate}_q{q}_q{q2}"
                            self.add_assertion(self.Or(self.Not(self.symbols[prev_layer]), self.Not(self.symbols[curr_layer])))
                else:
                    prev_layer = f"L{last_encoded_layer - 1}_{gate}_q{q}"
                    curr_layer = f"L{last_encoded_layer}_{gate}_q{q}"
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

    def push(self):
        if self.mode == "milp":
            self.saved_lp_problem = self.lp_problem.deepcopy()
        elif self.mode == "gurobi":
            self.lp_problem.update()
            self.gurobi_saved_push = [constraint.ConstrName for constraint in self.lp_problem.getConstrs()]
        elif self.mode == "smtlib":
            raise NotImplementedError("push not supported in smtlib mode")
        elif self.mode == "pysmt":
            self.solver.push()
    
    def pop(self):
        if self.mode == "milp":
            self.lp_problem = self.saved_lp_problem
        elif self.mode == "gurobi":
            self.lp_problem.update()
            to_remove = [constr for constr in self.lp_problem.getConstrs() if constr.ConstrName not in self.gurobi_saved_push]
            if to_remove:
                self.lp_problem.remove(to_remove)
            self.lp_problem.update()
            self.gurobi_saved_push = []
        elif self.mode == "smtlib":
            raise NotImplementedError("pop not supported in smtlib mode")
        elif self.mode == "pysmt":
            self.solver.pop()
    
    def filter_model(self, model, depth):
        # not model -> not (g1 and g2 and g3 ...) -> (not g1 or not g2 or not g3 ...)
        # in milp, depth - g1 - g2 - g3 - ... >= 1 (if all gate are 1, this becomes 0, which is false)
        if self.mode == "milp" or self.mode == "gurobi":
            # cant just make it depth >= ... because of numerical imprecisions
            self.add_assertion(depth - 0.5 >= self.Sum([self.symbols[bool_var] for bool_var in model]))
        elif self.mode == "smtlib" or self.mode == "pysmt":
            self.add_assertion(self.Not(self.And(*[self.symbols[bool_var] for bool_var in model])))