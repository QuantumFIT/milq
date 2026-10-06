"""
@file: fivetuple.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: implementation of the algebraic five-tuple representation of complex numbers (without k, k is handled in vector.py)
"""

import numpy as np
from pysmt.shortcuts import Plus, Minus, Times, Equals, And, Real
from .classic import Complex

class FiveTuple:
    def __init__(self, a = 0, b = 0, c = 0, d = 0, name = None, generator = None, bound=None):
        # if the name is provided, create a variables in the generator
        # bounds are generally 2^i where i is the number of the current layer
        if generator is not None:
            self.gen = generator
            generator.stats['complex_numbers'] += 1
        else:
            self.gen = None
            
        if self.gen is None:
            self.a = a
            self.b = b
            self.c = c
            self.d = d
            return

        if name is not None:
            self.name = name.replace('[', '_').replace(']', '')
            if bound is not None:
                self.a = generator.declare_integer(f"{self.name}_a", lb=-bound, ub=bound)
                self.b = generator.declare_integer(f"{self.name}_b", lb=-bound, ub=bound)
                self.c = generator.declare_integer(f"{self.name}_c", lb=-bound, ub=bound)
                self.d = generator.declare_integer(f"{self.name}_d", lb=-bound, ub=bound)
            else:
                self.a = generator.declare_integer(f"{self.name}_a")
                self.b = generator.declare_integer(f"{self.name}_b")
                self.c = generator.declare_integer(f"{self.name}_c")
                self.d = generator.declare_integer(f"{self.name}_d")
        else:
            self.a = generator.format_integer(a)
            self.b = generator.format_integer(b)
            self.c = generator.format_integer(c)
            self.d = generator.format_integer(d)
            
    def copy(self):
        return FiveTuple(a=self.a, b=self.b, c=self.c, d=self.d, generator=self.gen)

    def _coeffs(self):
        return (self.a, self.b, self.c, self.d)

    def __add__(self, other):
        if self.gen is None:
            return FiveTuple(a=self.a + other.a, b=self.b + other.b, c=self.c + other.c, d=self.d + other.d)
        else:
            return FiveTuple(
                a = self.gen.Plus(self.gen.format_integer(self.a), self.gen.format_integer(other.a)),
                b = self.gen.Plus(self.gen.format_integer(self.b), self.gen.format_integer(other.b)),
                c = self.gen.Plus(self.gen.format_integer(self.c), self.gen.format_integer(other.c)),
                d = self.gen.Plus(self.gen.format_integer(self.d), self.gen.format_integer(other.d)),
                generator=self.gen
            )

    def __sub__(self, other):
        if self.gen is None:
            return FiveTuple(a=self.a - other.a, b=self.b - other.b, c=self.c - other.c, d=self.d - other.d)
        else:
            return FiveTuple(
                a = self.gen.Minus(self.gen.format_integer(self.a), self.gen.format_integer(other.a)),
                b = self.gen.Minus(self.gen.format_integer(self.b), self.gen.format_integer(other.b)),
                c = self.gen.Minus(self.gen.format_integer(self.c), self.gen.format_integer(other.c)),
                d = self.gen.Minus(self.gen.format_integer(self.d), self.gen.format_integer(other.d)),
                generator=self.gen
            )

    def __mul__(self, other):
        # a = a1*a2 - b1*d2 - c1*c2 - d1*b2
        # b = a1*b2 + b1*a2 - c1*d2 - d1*c2
        # c = a1*c2 + b1*b2 + c1*a2 - d1*d2
        # d = a1*d2 + b1*c2 + c1*b2 + d1*a2
        # k = k1 + k2
        if self.gen is None:
            return FiveTuple(
                a=self.a * other.a - self.b * other.d - self.c * other.c - self.d * other.b, 
                b=self.a * other.b + self.b * other.a - self.c * other.d - self.d * other.c, 
                c=self.a * other.c + self.b * other.b + self.c * other.a - self.d * other.d, 
                d=self.a * other.d + self.b * other.c + self.c * other.b + self.d * other.a,
            )
        else:
            Minus = self.gen.Minus
            Times = self.gen.Times
            Plus = self.gen.Plus
            Int = self.gen.format_integer
            return FiveTuple(
                a = Minus(Minus(Minus(Times(Int(self.a), Int(other.a)), Times(Int(self.b), Int(other.d))), Times(Int(self.c), Int(other.c))), Times(Int(self.d), Int(other.b))),
                b = Minus(Minus(Plus(Times(Int(self.a), Int(other.b)), Times(Int(self.b), Int(other.a))), Times(Int(self.c), Int(other.d))), Times(Int(self.d), Int(other.c))),
                c = Minus(Plus(Plus(Times(Int(self.a), Int(other.c)), Times(Int(self.b), Int(other.b))), Times(Int(self.c), Int(other.a))), Times(Int(self.d), Int(other.d))),
                d = Plus(Plus(Plus(Times(Int(self.a), Int(other.d)), Times(Int(self.b), Int(other.c))), Times(Int(self.c), Int(other.b))), Times(Int(self.d), Int(other.a))),
                generator=self.gen
            )
            
    def __div__(self, other):
        if isinstance(other, float):
            if self.gen is None:
                return FiveTuple(a=self.a / other, b=self.b / other, c=self.c / other, d=self.d / other)
            else:
                return FiveTuple(
                    a = self.gen.Div(self.gen.format_integer(self.a), self.gen.format_real(other)),
                    b = self.gen.Div(self.gen.format_integer(self.b), self.gen.format_real(other)),
                    c = self.gen.Div(self.gen.format_integer(self.c), self.gen.format_real(other)),
                    d = self.gen.Div(self.gen.format_integer(self.d), self.gen.format_real(other)),
                    generator=self.gen)
        else:
            raise ValueError("division not supported for this representation")
        
    def __truediv__(self, other):
        return self.__div__(other)

    def __eq__(self, other):
        if self.gen is None:
            return self.a == other.a and self.b == other.b and self.c == other.c and self.d == other.d
        else:
            return self.gen.And(
                self.gen.Equals(self.gen.format_integer(self.a), self.gen.format_integer(other.a)),
                self.gen.Equals(self.gen.format_integer(self.b), self.gen.format_integer(other.b)),
                self.gen.Equals(self.gen.format_integer(self.c), self.gen.format_integer(other.c)),
                self.gen.Equals(self.gen.format_integer(self.d), self.gen.format_integer(other.d))
            )

    def __ne__(self, other):
        if self.gen is None:
            return self.a != other.a or self.b != other.b or self.c != other.c or self.d != other.d
        else:
            return self.gen.Not(self.__eq__(other))

    def __repr__(self):
        return f"({self.a} + {self.b} ω + {self.c} ω² + {self.d} ω³)"

    @classmethod
    def constrained_equals(cls, sel, bigM, expr1, expr2):
        gen = expr1.gen
        if gen.mode == "milp":
            gen.add_assertion(gen.And(
                (expr1.a - expr2.a <= bigM * (1 - sel)),
                (expr2.a - expr1.a <= bigM * (1 - sel)),
                (expr1.b - expr2.b <= bigM * (1 - sel)),  
                (expr2.b - expr1.b <= bigM * (1 - sel)),
                (expr1.c - expr2.c <= bigM * (1 - sel)),
                (expr2.c - expr1.c <= bigM * (1 - sel)),
                (expr1.d - expr2.d <= bigM * (1 - sel)),
                (expr2.d - expr1.d <= bigM * (1 - sel)),
            ))
        elif gen.mode == "gurobi":
            gen.add_assertion(gen.Indicator(sel, gen.Equals(expr1.a, expr2.a)))
            gen.add_assertion(gen.Indicator(sel, gen.Equals(expr1.b, expr2.b)))
            gen.add_assertion(gen.Indicator(sel, gen.Equals(expr1.c, expr2.c)))
            gen.add_assertion(gen.Indicator(sel, gen.Equals(expr1.d, expr2.d)))

    @classmethod
    def constrained_rescaling(cls, bigM, sel, r1, r2, fivetuple1, fivetuple2, exponent, parity, rel):
        # the problem of rescaled equivalence checking between two fivetuples in pure MILP
        # case splits - parity of k1-k2, which k is higher, rescaling exponent
        gen = fivetuple1.gen
        a1 = exponent if rel == "<=" else 1
        a2 = exponent if rel == ">" else 1
        tmp = bigM
        #bigM = bigM * exponent
        if parity == "even":
            if rel == "<=":
            # rescale fivetuple1 by exponent
                bigM = 2 * tmp * a1
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * fivetuple1.a, r1.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * fivetuple1.b, r1.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * fivetuple1.c, r1.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * fivetuple1.d, r1.d)))
                else:
                    gen.add_assertion(a1 * fivetuple1.a - r1.a <= bigM * (1 - sel)) 
                    gen.add_assertion(r1.a - a1 * fivetuple1.a <= bigM * (1 - sel))
                    gen.add_assertion(a1 * fivetuple1.b - r1.b <= bigM * (1 - sel))
                    gen.add_assertion(r1.b - a1 * fivetuple1.b <= bigM * (1 - sel))
                    gen.add_assertion(a1 * fivetuple1.c - r1.c <= bigM * (1 - sel))
                    gen.add_assertion(r1.c - a1 * fivetuple1.c <= bigM * (1 - sel))
                    gen.add_assertion(a1 * fivetuple1.d - r1.d <= bigM * (1 - sel))
                    gen.add_assertion(r1.d - a1 * fivetuple1.d <= bigM * (1 - sel))

                bigM = 2 * tmp
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.a, r2.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.b, r2.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.c, r2.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.d, r2.d)))
                else:
                    gen.add_assertion(r2.a - fivetuple2.a <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.a - r2.a <= bigM * (1 - sel))
                    gen.add_assertion(r2.b - fivetuple2.b <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.b - r2.b <= bigM * (1 - sel))
                    gen.add_assertion(r2.c - fivetuple2.c <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.c - r2.c <= bigM * (1 - sel))
                    gen.add_assertion(r2.d - fivetuple2.d <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.d - r2.d <= bigM * (1 - sel))
            else:
                bigM = 2 * tmp
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.a, r1.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.b, r1.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.c, r1.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.d, r1.d)))
                else:
                    gen.add_assertion(r1.a - fivetuple1.a <= bigM * (1 - sel)) 
                    gen.add_assertion(fivetuple1.a - r1.a <= bigM * (1 - sel))
                    gen.add_assertion(r1.b - fivetuple1.b <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.b - r1.b <= bigM * (1 - sel))
                    gen.add_assertion(r1.c - fivetuple1.c <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.c - r1.c <= bigM * (1 - sel))
                    gen.add_assertion(r1.d - fivetuple1.d <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.d - r1.d <= bigM * (1 - sel))

                bigM = 2 * a2 * tmp
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * fivetuple2.a, r2.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * fivetuple2.b, r2.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * fivetuple2.c, r2.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * fivetuple2.d, r2.d)))
                else:
                    gen.add_assertion(r2.a - a2 * fivetuple2.a <= bigM * (1 - sel))
                    gen.add_assertion(a2 * fivetuple2.a - r2.a <= bigM * (1 - sel))
                    gen.add_assertion(r2.b - a2 * fivetuple2.b <= bigM * (1 - sel))
                    gen.add_assertion(a2 * fivetuple2.b - r2.b <= bigM * (1 - sel))
                    gen.add_assertion(r2.c - a2 * fivetuple2.c <= bigM * (1 - sel))
                    gen.add_assertion(a2 * fivetuple2.c - r2.c <= bigM * (1 - sel)) 
                    gen.add_assertion(r2.d - a2 * fivetuple2.d <= bigM * (1 - sel))
                    gen.add_assertion(a2 * fivetuple2.d - r2.d <= bigM * (1 - sel)) 
        else:
            # rescale fivetuple1 by the matrix M
            if rel == "<=":
                bigM = 3 * tmp * a1
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * (fivetuple1.b - fivetuple1.d), r1.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * (fivetuple1.a + fivetuple1.c), r1.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * (fivetuple1.b + fivetuple1.d), r1.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a1 * (fivetuple1.c - fivetuple1.a), r1.d)))
                else:
                    gen.add_assertion(a1 * (fivetuple1.b - fivetuple1.d) - r1.a <= bigM * (1 - sel))
                    gen.add_assertion(r1.a - a1 * (fivetuple1.b - fivetuple1.d) <= bigM * (1 - sel))
                    gen.add_assertion(a1 * (fivetuple1.a + fivetuple1.c) - r1.b <= bigM * (1 - sel))
                    gen.add_assertion(r1.b - a1 * (fivetuple1.a + fivetuple1.c) <= bigM * (1 - sel))
                    gen.add_assertion(a1 * (fivetuple1.b + fivetuple1.d) - r1.c <= bigM * (1 - sel))
                    gen.add_assertion(r1.c - a1 * (fivetuple1.b + fivetuple1.d) <= bigM * (1 - sel))
                    gen.add_assertion(a1 * (fivetuple1.c - fivetuple1.a) - r1.d <= bigM * (1 - sel))
                    gen.add_assertion(r1.d - a1 * (fivetuple1.c - fivetuple1.a) <= bigM * (1 - sel))


                bigM = 2 * tmp
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.a, r2.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.b, r2.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.c, r2.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple2.d, r2.d)))
                else:
                    gen.add_assertion(r2.a - fivetuple2.a <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.a - r2.a <= bigM * (1 - sel))
                    gen.add_assertion(r2.b - fivetuple2.b <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.b - r2.b <= bigM * (1 - sel))
                    gen.add_assertion(r2.c - fivetuple2.c <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.c - r2.c <= bigM * (1 - sel))
                    gen.add_assertion(r2.d - fivetuple2.d <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple2.d - r2.d <= bigM * (1 - sel))
            else:
                bigM = 3 * tmp * a2
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * (fivetuple2.b - fivetuple2.d), r2.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * (fivetuple2.a + fivetuple2.c), r2.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * (fivetuple2.b + fivetuple2.d), r2.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(a2 * (fivetuple2.c - fivetuple2.a), r2.d)))
                else:
                    gen.add_assertion(r2.a - a2 * (fivetuple2.b - fivetuple2.d) <= bigM * (1 - sel))
                    gen.add_assertion(a2 * (fivetuple2.b - fivetuple2.d) - r2.a <= bigM * (1 - sel))
                    gen.add_assertion(r2.b - a2 * (fivetuple2.a + fivetuple2.c) <= bigM * (1 - sel))
                    gen.add_assertion(a2 * (fivetuple2.a + fivetuple2.c) - r2.b <= bigM * (1 - sel))
                    gen.add_assertion(r2.c - a2 * (fivetuple2.b + fivetuple2.d) <= bigM * (1 - sel))
                    gen.add_assertion(a2 * (fivetuple2.b + fivetuple2.d) - r2.c <= bigM * (1 - sel))
                    gen.add_assertion(r2.d - a2 * (fivetuple2.c - fivetuple2.a) <= bigM * (1 - sel))
                    gen.add_assertion(a2 * (fivetuple2.c - fivetuple2.a) - r2.d <= bigM * (1 - sel))

                bigM = 2 * tmp
                if gen.mode == "gurobi":
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.a, r1.a)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.b, r1.b)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.c, r1.c)))
                    gen.add_assertion(gen.Indicator(sel, gen.Equals(fivetuple1.d, r1.d)))
                else:
                    gen.add_assertion(r1.a - fivetuple1.a <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.a - r1.a <= bigM * (1 - sel))
                    gen.add_assertion(r1.b - fivetuple1.b <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.b - r1.b <= bigM * (1 - sel))
                    gen.add_assertion(r1.c - fivetuple1.c <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.c - r1.c <= bigM * (1 - sel))
                    gen.add_assertion(r1.d - fivetuple1.d <= bigM * (1 - sel))
                    gen.add_assertion(fivetuple1.d - r1.d <= bigM * (1 - sel))

    
    @classmethod
    def one(cls, generator, bound=None):
        return cls(a=1, b=0, c=0, d=0, generator=generator, bound=bound)
    
    @classmethod
    def zero(cls, generator, bound=None):
        return cls(a=0, b=0, c=0, d=0, generator=generator, bound=bound)
    
    @classmethod
    def inv_sqrt2(cls, generator, bound=None):
        # a = 1, k = 1, k is in the vector
        return cls(a=1, b=0, c=0, d=0, generator=generator, bound=bound)
    
    def multiply_by_omega(self, generator):
        # rotation on the unit circle by * e^(i*pi/4)
        if self.gen is None:
            return FiveTuple(a=-self.d, b=self.a, c=self.b, d=self.c)
        else:
            return FiveTuple(
                a = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.d)),
                b = self.gen.format_integer(self.a),
                c = self.gen.format_integer(self.b),
                d = self.gen.format_integer(self.c),
                generator=self.gen
            )
        
    def multiply_by_omega_counter(self, generator):
        # rotation on the unit circle by * e^(-i*pi/4)
        if self.gen is None:
            return FiveTuple(a=self.b, b=self.c, c=self.d, d=-self.a)
        else:
            return FiveTuple(
                a = self.gen.format_integer(self.b),
                b = self.gen.format_integer(self.c),
                c = self.gen.format_integer(self.d),
                d = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.a)),
                generator=self.gen
            )
    
    def multiply_by_i(self, generator):
        if self.gen is None:
            return FiveTuple(a=-self.c, b=-self.d, c=self.a, d=self.b)
        else:
            return FiveTuple(
                a = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.c)),
                b = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.d)),
                c = self.gen.format_integer(self.a),
                d = self.gen.format_integer(self.b),
                generator=self.gen
            )

    def multiply_by_minus_i(self, generator):
        if self.gen is None:
            return FiveTuple(a=self.c, b=self.d, c=-self.a, d=-self.b)
        else:
            return FiveTuple(
                a = self.gen.format_integer(self.c),
                b = self.gen.format_integer(self.d),
                c = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.a)),
                d = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.b)),
                generator=self.gen
            )
        
    def multiply_by_minus_one(self, generator):
        if self.gen is None:
            return FiveTuple(a=-self.a, b=-self.b, c=-self.c, d=-self.d)
        else:
            return FiveTuple(
                a = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.a)),
                b = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.b)),
                c = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.c)),
                d = self.gen.Minus(self.gen.format_integer(0), self.gen.format_integer(self.d)),
                generator=self.gen
            )
            
    def multiply_by_two(self, generator):
        if self.gen is None:
            return FiveTuple(a=2*self.a, b=2*self.b, c=2*self.c, d=2*self.d)
        else:
            return FiveTuple(
                a = self.gen.Times(self.gen.format_integer(2), self.gen.format_integer(self.a)),
                b = self.gen.Times(self.gen.format_integer(2), self.gen.format_integer(self.b)),
                c = self.gen.Times(self.gen.format_integer(2), self.gen.format_integer(self.c)),
                d = self.gen.Times(self.gen.format_integer(2), self.gen.format_integer(self.d)),
                generator=self.gen
            )
        
    def divide_by_sqrt2(self, generator):
        # handled by k increment in the vector
        return self

    def divide_by_two(self, generator):
        # handled by k increment in the vector
        return self
    
    def divide_by_two_i(self, generator):
        # handled by k increment in the vector
        return self.multiply_by_i(generator)
            
    def to_real(self, k=None, max_k=None): 
        # omega = (1 + i) / sqrt(2)
        # real = (a + ((b - d)/sqrt(2))) / sqrt(2)^k
        # imag = (c + ((b + d)/sqrt(2))) / sqrt(2)^k
        if k is not None:
            if self.gen is None:
                real = (self.a + ((self.b - self.d)/np.sqrt(2))) / np.sqrt(2)**k
                imag = (self.c + ((self.b + self.d)/np.sqrt(2))) / np.sqrt(2)**k
                return Complex(a=real, b=imag, generator=self.gen)
            else:
                sqrt2 = self.gen.declare_real("sqrt2")
                self.gen.add_assertion(self.gen.Equals(self.gen.Times(sqrt2, sqrt2), self.gen.Real(2)))
            
                # enumerate the powers sqrt(2)^k
                inv_sqrt2_k = None
                if isinstance(k, int) and k == 0:
                    sqrt2_k = self.gen.format_real(1)
                else:
                    sqrt2_k = self.gen.declare_real(f"sqrt2_k_{self.name}")
                    if self.gen.mode == "smtlib":
                        for i in range(max_k + 1):
                            self.gen.add_assertion(self.gen.Implies(self.gen.Equals(k, i), self.gen.Equals(sqrt2_k, np.sqrt(2) ** i)))
                    elif self.gen.mode == "gurobi":
                        sqrt2_k_expr = self.gen.Exp(self.gen.Div(self.gen.Real(k), self.gen.Real(2)))
                        self.gen.add_assertion(self.gen.Equals(sqrt2_k, sqrt2_k_expr))
                
                b_minus_d = self.gen.Minus(self.gen.format_integer(self.b), self.gen.format_integer(self.d))
                b_minus_d_over_sqrt2 = self.gen.Div(b_minus_d, sqrt2)
                real_numerator = self.gen.Plus(self.gen.format_integer(self.a), b_minus_d_over_sqrt2)
                
                b_plus_d = self.gen.Plus(self.gen.format_integer(self.b), self.gen.format_integer(self.d))
                b_plus_d_over_sqrt2 = self.gen.Div(b_plus_d, sqrt2)
                imag_numerator = self.gen.Plus(self.gen.format_integer(self.c), b_plus_d_over_sqrt2)
                
                real = self.gen.Div(real_numerator, sqrt2_k)
                imag = self.gen.Div(imag_numerator, sqrt2_k)
                
                return Complex(a=real, b=imag, generator=self.gen)
        else:
            # just do a + (b-d)/sqrt(2)
            # (c + (b+d)/sqrt(2))i without any division
            if self.gen is None:
                return Complex(a=self.a + ((self.b - self.d)/np.sqrt(2)), b=self.c + ((self.b + self.d)/np.sqrt(2)), generator=self.gen)
            else:
                sqrt2 = self.gen.declare_real("sqrt2")
                b_minus_d = self.gen.Minus(self.gen.format_integer(self.b), self.gen.format_integer(self.d))
                b_minus_d_over_sqrt2 = self.gen.Div(b_minus_d, sqrt2)
                real_numerator = self.gen.Plus(self.gen.format_integer(self.a), b_minus_d_over_sqrt2)
                
                b_plus_d = self.gen.Plus(self.gen.format_integer(self.b), self.gen.format_integer(self.d))
                b_plus_d_over_sqrt2 = self.gen.Div(b_plus_d, sqrt2)
                imag_numerator = self.gen.Plus(self.gen.format_integer(self.c), b_plus_d_over_sqrt2)
                
                return Complex(a=real_numerator, b=imag_numerator, generator=self.gen)
        
    def abs2(self, k):
        # a = a/2^(k/2)
        # b = b/2^(k/2)
        # c = c/2^(k/2)
        # d = d/2^(k/2)
        # res = a^2 + b^2 + c^2 + d^2 + sqrt(2)*(a * (b-d) + c * (b+d))
        if self.gen is None:
            a = self.a / np.power(2, k/2)
            b = self.b / np.power(2, k/2)
            c = self.c / np.power(2, k/2)
            d = self.d / np.power(2, k/2)
            return (a ** 2 + b ** 2 + c ** 2 + d ** 2) + np.sqrt(2) * (a * (b - d) + c * (b + d))
        else:
            a_squared = self.gen.Pow(self.gen.format_integer(self.a), 2)
            b_squared = self.gen.Pow(self.gen.format_integer(self.b), 2)
            c_squared = self.gen.Pow(self.gen.format_integer(self.c), 2)
            d_squared = self.gen.Pow(self.gen.format_integer(self.d), 2)
            two_to_k_minus_half = self.gen.Pow(self.gen.Real(2), self.gen.Minus(self.gen.Real(k), self.gen.Real(0.5)))
            two_to_k = self.gen.Pow(self.gen.Int(2), self.gen.Int(k))
            left_term = self.gen.Div(self.gen.Plus(self.gen.Plus(self.gen.Plus(a_squared, b_squared), c_squared), d_squared), two_to_k)
            ab = self.gen.Times(self.gen.format_integer(self.a), self.gen.format_integer(self.b))
            ad = self.gen.Times(self.gen.format_integer(self.a), self.gen.format_integer(self.d))
            cb = self.gen.Times(self.gen.format_integer(self.c), self.gen.format_integer(self.b))
            cd = self.gen.Times(self.gen.format_integer(self.c), self.gen.format_integer(self.d))
            right_term = self.gen.Div(self.gen.Plus(self.gen.Plus(self.gen.Minus(ab, ad), cb), cd), two_to_k_minus_half)
            return self.gen.Plus(left_term, right_term)
        

    def conjugate(self, generator = None):
        if generator is None:
            return FiveTuple(a=self.a, b=-self.d, c=-self.c, d=-self.b, generator=generator)
        else:
            return FiveTuple(
                a = self.gen.format_integer(self.a),
                b = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.d)),
                c = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.c)),
                d = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.b)),
                generator=self.gen
            )
        
    def max_coefficient(self) -> int:
        return max(abs(self.a), abs(self.b), abs(self.c), abs(self.d))
    
    def multiply_by_real(self, num):
        if self.gen is None:
            return FiveTuple(a=self.a * num, b=self.b * num, c=self.c * num, d=self.d * num)
        else:
            return FiveTuple(
                a = self.gen.Times(self.gen.format_integer(self.a), self.gen.format_real(num)),
                b = self.gen.Times(self.gen.format_integer(self.b), self.gen.format_real(num)),
                c = self.gen.Times(self.gen.format_integer(self.c), self.gen.format_real(num)),
                d = self.gen.Times(self.gen.format_integer(self.d), self.gen.format_real(num)),
                generator=self.gen
            )
            
    def __getitem__(self, key):
        return self.a if key == 0 else self.b if key == 1 else self.c if key == 2 else self.d
    
    def __setitem__(self, key, value):
        if key == 0:
            self.a = value
        elif key == 1:
            self.b = value
        elif key == 2:
            self.c = value
        else:
            self.d = value
            
    def __len__(self):
        return 4
    
    def increase_k(self, generator):
        # k itself is incremented in the Vector
        # numerical equivalence is the same after the increment
        if self.gen is None:
            return FiveTuple(a = self.b - self.d,
                             b = self.a + self.c,
                             c = self.b + self.d,
                             d = self.c - self.a,
                             generator=generator)
        else:
            return FiveTuple(
                a = self.gen.Minus(self.gen.format_integer(self.b), self.gen.format_integer(self.d)),
                b = self.gen.Plus(self.gen.format_integer(self.a), self.gen.format_integer(self.c)),
                c = self.gen.Plus(self.gen.format_integer(self.b), self.gen.format_integer(self.d)),
                d = self.gen.Minus(self.gen.format_integer(self.c), self.gen.format_integer(self.a)),
                generator=self.gen
            )