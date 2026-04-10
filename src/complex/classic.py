import numpy as np
from pysmt.shortcuts import Plus, Minus, Times, Equals, And, Real

class Complex:
    def __init__(self, a=None, b=None, name=None, generator=None, bound=None):
        #bound = 1.0 # always in -1, 1 range
        self.gen = generator
        if generator is not None:
            generator.stats['complex_numbers'] += 1
        if name is not None:
            self.name = name.replace('[', '_').replace(']', '')
            self.real = generator.declare_real(self.name + '_r', lb=-bound, ub=bound)
            self.imag = generator.declare_real(self.name + '_i', lb=-bound, ub=bound)
        else:
            if generator is not None:
                if isinstance(a, str) and isinstance(b, str):
                    self.real = a
                    self.imag = b
                else:
                    self.real = generator.format_real(a)
                    self.imag = generator.format_real(b)
            else:
                self.real = a
                self.imag = b
                
    @classmethod
    def constrained_equals(cls, sel, bigM, expr1, expr2):
        gen = expr1.gen
        if gen.mode == "milp":
            gen.add_assertion(gen.And(
                (expr1.real - expr2.real <= bigM * (1 - sel)),
                (expr2.real - expr1.real <= bigM * (1 - sel)),
                (expr1.imag - expr2.imag <= bigM * (1 - sel)),
                (expr2.imag - expr1.imag <= bigM * (1 - sel)),
                
            ))
        elif gen.mode == "gurobi":
            gen.add_assertion(gen.Indicator(sel, gen.Equals(expr1.real, expr2.real)))
            gen.add_assertion(gen.Indicator(sel, gen.Equals(expr1.imag, expr2.imag)))
        
    def __add__(self, other):
        if self.gen is None:
            return Complex(a=self.real + other.real, b=self.imag + other.imag, generator=self.gen)
        else:
            return Complex(
                a = self.gen.Plus(self.gen.format_real(self.real), self.gen.format_real(other.real)),
                b = self.gen.Plus(self.gen.format_real(self.imag), self.gen.format_real(other.imag)),
                generator = self.gen
            )
    
    def __sub__(self, other):
        if self.gen is None:
            return Complex(a=self.real - other.real, b=self.imag - other.imag, generator=self.gen)
        else:
            return Complex(
                a = self.gen.Minus(self.gen.format_real(self.real), self.gen.format_real(other.real)),
                b = self.gen.Minus(self.gen.format_real(self.imag), self.gen.format_real(other.imag)),
                generator = self.gen
            )

    def __mul__(self, other):
        # (a + bi) * (c + di) = (ac - bd) + (ad + bc)i
        # r1 * r2 - i1 * i2
        # r1 * i2 + i1 * r2
        if self.gen is None:
            return Complex(a=self.real * other.real - self.imag * other.imag, b=self.real * other.imag + self.imag * other.real, generator=self.gen)
        else:
            return Complex(
                a = self.gen.Minus(self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(other.real)), self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(other.imag))),
                b = self.gen.Plus(self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(other.imag)), self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(other.real))),
                generator = self.gen
            )
            
    def __div__(self, other):
        if self.gen is None:
            if isinstance(other, Complex):
                pass
            elif isinstance(other, float) or isinstance(other, int):
                return Complex(a=self.real / other, b=self.imag / other, generator=self.gen)
            else:
                raise ValueError("division not supported for this representation")
        else:
            if isinstance(other, Complex):
                if other.gen is not None:
                    raise ValueError("division not supported for this representation")
                else:
                    c2_d2 = other.real**2 + other.imag**2
                    return Complex(a=self.gen.Div(self.gen.Plus(self.gen.Times(self.real, other.real), self.gen.Times(self.imag, other.imag)), c2_d2),
                                   b=self.gen.Div(self.gen.Minus(self.gen.Times(self.imag, other.real), self.gen.Times(self.real, other.imag)), c2_d2),
                                   generator=self.gen
                    )
                
            elif isinstance(other, float) or isinstance(other, int):
                return Complex(a=self.gen.Div(self.real, self.gen.format_real(other)), b=self.gen.Div(self.imag, self.gen.format_real(other)), generator=self.gen)
            else:
                raise ValueError("division not supported for this representation")

    def __truediv__(self, other):
        return self.__div__(other)
    
    def __eq__(self, other):
        if self.gen is None:
            return self.real == other.real and self.imag == other.imag
        else:
            return self.gen.And(
                self.gen.Equals(self.gen.format_real(self.real), self.gen.format_real(other.real)),
                self.gen.Equals(self.gen.format_real(self.imag), self.gen.format_real(other.imag))
            )
            
    def __ne__(self, other):
        if self.gen is None:
            return self.real != other.real or self.imag != other.imag
        else:
            return self.gen.Not(self.__eq__(other))

    def __repr__(self):
        if self.gen is None:
            return f"({self.real} + {self.imag}j)"
        else:
            return f"({self.gen.format_real(self.real)} + {self.gen.format_real(self.imag)}j)"
     
    def copy(self):
        return Complex(a=self.real, b=self.imag, generator=self.gen)

    def conjugate(self, generator = None):
        if self.gen is None:
            return Complex(a=self.real, b=-self.imag, generator=self.gen)
        else:
            return Complex(
                a = self.gen.format_real(self.real),
                b = self.gen.Minus(self.gen.Real(0), self.gen.format_real(self.imag)),
                generator = self.gen
            )
    
    def to_real(self):
        return self

    @classmethod
    def zero(cls, generator = None, bound=None):
        return cls(a=0, b=0, generator=generator, bound=bound)
    
    @classmethod
    def one(cls, generator = None, bound=None):
        return cls(a=1, b=0, generator=generator, bound=bound)
    
    @classmethod
    def minus_one(cls, generator = None, bound=None):
        if generator is None:
            return cls(a=-1, b=0, generator=generator, bound=bound)
        else:
            return cls(a=generator.Minus(generator.format_integer(0), generator.format_integer(1)), b=generator.format_integer(0), generator=generator)
    
    @classmethod
    def i_phase(cls, generator = None, bound=None):
        return cls(a=0,b=1, generator=generator, bound=bound)
    
    @classmethod
    def t_phase(cls, generator = None, bound=None):
        if generator is not None:
            if generator.mode == "smtlib":
                return cls(a=generator.format_real("one_half"), b=generator.format_real("one_half"), generator=generator, bound=bound)
        return cls(a=np.sqrt(1/2), b=np.sqrt(1/2), generator=generator, bound=bound)
    
    @classmethod
    def inv_sqrt2(cls, generator = None, bound=None):
        if generator is not None:
            if generator.mode == "smtlib":
                return cls(a=generator.format_real("inv_sqrt2"), b=0, generator=generator, bound=bound)
        return cls(a=np.sqrt(1/2), b=0, generator=generator, bound=bound)
    
    @classmethod
    def one_half(cls, generator = None, bound=None):
        return cls(a=1/2, b=0, generator=generator, bound=bound)
    
    @classmethod
    def i_half(cls, generator = None, bound=None):
        return cls(a=0, b=1/2, generator=generator, bound=bound)
    
    @classmethod
    def two(cls, generator = None, bound=None):
        return cls(a=2, b=0, generator=generator, bound=bound)

    def multiply_by_omega(self, generator = None):
        return self * Complex.t_phase(generator)
        
    def multiply_by_omega_counter(self, generator = None):
        return self * Complex.t_phase(generator).conjugate()
    
    def multiply_by_i(self, generator = None):
        return self * Complex.i_phase(generator)
        
    def multiply_by_minus_i(self, generator = None):
        return self * Complex.i_phase(generator).conjugate()
        
    def multiply_by_minus_one(self, generator = None):
        return self * Complex.minus_one(generator)
        
    def divide_by_sqrt2(self, generator = None):
        return self * Complex.inv_sqrt2(generator)

    def divide_by_two(self, generator = None):
        return self * Complex.one_half(generator)
    
    def multiply_by_two(self, generator = None):
        return self * Complex.two(generator)
    
    def divide_by_two_i(self, generator = None):
        return self * Complex.i_half(generator)
    
    def max_coefficient(self) -> int:
        return max(abs(self.real), abs(self.imag))

    def abs2(self) -> float:
        if self.gen is None:
            return self.real**2 + self.imag**2
        else:
            return self.gen.Plus(self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(self.real)), self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(self.imag)))

    def multiply_by_real(self, num):
        if self.gen is None:
            return Complex(a=self.real * num, b=self.imag * num, generator=self.gen)
        else:
            return Complex(
                a = self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(num)),
                b = self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(num)),
                generator = self.gen
            )
            
    def to_precision(self, prec : float) -> "Complex":
        if self.gen is None:
            a = self.real if abs(self.real) >= prec else 0.0
            b = self.imag if abs(self.imag) >= prec else 0.0
            return Complex(a=a, b=b, generator=self.gen)
        else:
            raise ValueError("to_precision not supported for formulae generation")
        
    def __getitem__(self, key):
        return self.real if key == 0 else self.imag
    
    def __setitem__(self, key, value):
        if key == 0:
            self.real = value
        else:
            self.imag = value

    def __len__(self):
        return 2