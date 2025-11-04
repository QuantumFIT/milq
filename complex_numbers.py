from z3 import *
import numpy as np

class Complex:
    def __init__(self, a=None, b=None, name=None):
        if name is not None:
            self.real = Real(name + 'r')
            self.imag = Real(name + 'i')
        else:
            # Accept either Z3 expressions or numeric constants
            if isinstance(a, ArithRef) and isinstance(b, ArithRef):
                self.real = a
                self.imag = b
            else:
                self.real = RealVal(a)
                self.imag = RealVal(b)

    def __add__(self, other):
        return Complex(a=self.real + other.real, b=self.imag + other.imag)
    
    def __sub__(self, other):
        return Complex(a=self.real - other.real, b=self.imag - other.imag)

    def __mul__(self, other):
        return Complex(a=self.real*other.real - self.imag*other.imag,
                       b=self.real*other.imag + self.imag*other.real)

    def __eq__(self, other):
        return And(self.real == other.real, self.imag == other.imag)

    def __repr__(self):
        return f"({self.real} + {self.imag}i)"

class ComplexVector:
    def __init__(self, q, symbolic=True, name=None):
        self.vec = []
        for i in range(q):
            if symbolic:
                self.vec.append(Complex(name=f"{name}[{i}]"))
            else:
                self.vec.append(Complex(0,0))
    def __getitem__(self,i):
        return self.vec[i]
    def __setitem__(self,i,value):
        self.vec[i] = value
    def __eq__(self, other):
        return And(*[self.vec[i] == other.vec[i] for i in range(len(self.vec))])
    def __repr__(self):
        return f"[{', '.join(str(v) for v in self.vec)}]"
    