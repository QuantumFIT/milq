import numpy as np
from pysmt.shortcuts import Plus, Minus, Times, Equals, And, Real

class Complex:
    def __init__(self, a=None, b=None, name=None, generator=None, bound=None):
        self.gen = generator
        if name is not None:
            safe_name = name.replace('[', '_').replace(']', '')
            self.real = generator.declare_real(safe_name + 'r')
            self.imag = generator.declare_real(safe_name + 'i')
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
        if self.gen is None:
            return Complex(a=self.real * other.real - self.imag * other.imag, b=self.real * other.imag + self.imag * other.real, generator=self.gen)
        else:
            return Complex(
                a = self.gen.Minus(self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(other.real)), self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(other.imag))),
                b = self.gen.Plus(self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(other.imag)), self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(other.real))),
                generator = self.gen
            )
    
    def __eq__(self, other):
        if self.gen is None:
            return self.real == other.real and self.imag == other.imag
        else:
            return self.gen.And(
                self.gen.Equals(self.gen.format_real(self.real), self.gen.format_real(other.real)),
                self.gen.Equals(self.gen.format_real(self.imag), self.gen.format_real(other.imag))
            )

    def __repr__(self):
        if self.gen is None:
            return f"({self.real} + {self.imag}j)"
        else:
            return f"({self.gen.format_real(self.real)} + {self.gen.format_real(self.imag)}j)"
     
    def copy(self):
        return Complex(a=self.real, b=self.imag, generator=self.gen)

    def conjugate(self):
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
    def zero(cls, generator = None):
        return cls(a=0, b=0, generator=generator)
    
    @classmethod
    def one(cls, generator = None):
        return cls(a=1, b=0, generator=generator)
    
    @classmethod
    def minus_one(cls, generator = None):
        return cls(a=-1, b=0, generator=generator)
    
    @classmethod
    def i_phase(cls, generator = None):
        return cls(a=0,b=1, generator=generator)
    
    @classmethod
    def t_phase(cls, generator = None):
        return cls(a=np.sqrt(1/2), b=np.sqrt(1/2), generator=generator)
    
    @classmethod
    def inv_sqrt2(cls,generator = None):
        return cls(a=np.sqrt(1/2), b=0, generator=generator)
    
    @classmethod
    def one_half(cls, generator = None):
        return cls(a=1/2, b=0, generator=generator)
    
    @classmethod
    def i_half(cls, generator = None):
        return cls(a=0, b=1/2, generator=generator)
    
    @classmethod
    def two(cls, generator = None):
        return cls(a=2, b=0, generator=generator)

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

    def multiply_by_real(self, num):
        if self.gen is None:
            return Complex(a=self.real * num, b=self.imag * num, generator=self.gen)
        else:
            return Complex(
                a = self.gen.Times(self.gen.format_real(self.real), self.gen.format_real(num)),
                b = self.gen.Times(self.gen.format_real(self.imag), self.gen.format_real(num)),
                generator = self.gen
            )