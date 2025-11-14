import numpy as np

class Complex:
    def __init__(self, a=None, b=None, name=None, generator=None):
        self.generator = generator
        if name is not None:
            safe_name = name.replace('[', '_').replace(']', '')
            self.real = generator.declare_real(safe_name + 'r')
            self.imag = generator.declare_real(safe_name + 'i')
        else:
            if isinstance(a, str) and isinstance(b, str):
                self.real = a
                self.imag = b
            else:
                self.real = generator.format_real(a)
                self.imag = generator.format_real(b)

    def __add__(self, other):
        real_expr = f"(+ {self.real} {other.real})"
        imag_expr = f"(+ {self.imag} {other.imag})"
        return Complex(a=real_expr, b=imag_expr, generator=self.generator)
    
    def __sub__(self, other):
        real_expr = f"(- {self.real} {other.real})"
        imag_expr = f"(- {self.imag} {other.imag})"
        return Complex(a=real_expr, b=imag_expr, generator=self.generator)

    def __mul__(self, other):
        # (a + bi) * (c + di) = (ac - bd) + (ad + bc)i
        real_expr = f"(- (* {self.real} {other.real}) (* {self.imag} {other.imag}))"
        imag_expr = f"(+ (* {self.real} {other.imag}) (* {self.imag} {other.real}))"
        return Complex(a=real_expr, b=imag_expr, generator=self.generator)

    def __eq__(self, other):
        real_eq = f"(= {self.real} {other.real})"
        imag_eq = f"(= {self.imag} {other.imag})"
        return f"(and {real_eq} {imag_eq})"

    def __repr__(self):
        return f"({self.real} + {self.imag}i)"

    def conjugate(self, generator):
        return Complex(a=self.real, b=f"(- 0 {self.imag})", generator=self.generator)

    @classmethod
    def zero(cls, generator):
        return cls(a=0, b=0, generator=generator)
    
    @classmethod
    def one(cls, generator):
        return cls(a=1, b=0, generator=generator)
    
    @classmethod
    def minus_one(cls, generator):
        return cls(a=-1, b=0, generator=generator)
    
    @classmethod
    def i_phase(cls, generator):
        return cls(a=0,b=1, generator=generator)
    
    @classmethod
    def t_phase(cls, generator):
        return cls(a=np.sqrt(1/2), b=np.sqrt(1/2), generator=generator)
    
    @classmethod
    def inv_sqrt2(cls,generator):
        return cls(a=np.sqrt(1/2), b=0, generator=generator)

class Cyclotomic8Dyadic:
    def __init__(self, a=0, b=0, c=0, d=0,
                 name=None, generator=None):
        self.generator = generator

        if name is not None:
            safe = name.replace('[', '_').replace(']', '')
            self.a = generator.declare_integer(f"{safe}_a")
            self.b = generator.declare_integer(f"{safe}_b")
            self.c = generator.declare_integer(f"{safe}_c")
            self.d = generator.declare_integer(f"{safe}_d")
        else:
            self.a = generator.format_integer(a)
            self.b = generator.format_integer(b)
            self.c = generator.format_integer(c)
            self.d = generator.format_integer(d)

    def _coeffs(self):
        return (self.a, self.b, self.c, self.d)

    def __add__(self, other):
        return Cyclotomic8Dyadic(
            a = f"(+ {self.a} {other.a})",
            b = f"(+ {self.b} {other.b})",
            c = f"(+ {self.c} {other.c})",
            d = f"(+ {self.d} {other.d})",
            generator=self.generator
        )

    def __sub__(self, other):
        return Cyclotomic8Dyadic(
            a = f"(- {self.a} {other.a})",
            b = f"(- {self.b} {other.b})",
            c = f"(- {self.c} {other.c})",
            d = f"(- {self.d} {other.d})",
            generator=self.generator
        )

    def __mul__(self, other):
        # a = a1*a2 - b1*d2 - c1*c2 - d1*b2
        # b = a1*b2 + b1*a2 + c1*d2 - d1*c2
        # c = a1*c2 + b1*b2 + c1*a2 - d1*d2
        # d = a1*d2 + b1*c2 + c1*b2 + d1*a2
        # k = k1 + k2
        return Cyclotomic8Dyadic(
            a = f"(- (* {self.a} {other.a}) (* {self.b} {other.d}) (* {self.c} {other.c}) (* {self.d} {other.b}))",
            b = f"(+ (* {self.a} {other.b}) (* {self.b} {other.a}) (* {self.c} {other.d}) (* {self.d} {other.c}))",
            c = f"(+ (* {self.a} {other.c}) (* {self.b} {other.b}) (* {self.c} {other.a}) (* {self.d} {other.d}))",
            d = f"(+ (* {self.a} {other.d}) (* {self.b} {other.c}) (* {self.c} {other.b}) (* {self.d} {other.a}))",
            generator=self.generator
        )
    
    def __eq__(self, other):
        eqs = [
            f"(= {self.a} {other.a})",
            f"(= {self.b} {other.b})",
            f"(= {self.c} {other.c})",
            f"(= {self.d} {other.d})",
        ]
        return "(and " + " ".join(eqs) + ")"

    def __repr__(self):
        num = f"{self.a} + {self.b} ω + {self.c} ω² + {self.d} ω³"
        return f"({num})"

    @classmethod
    def one(cls, generator):
        return cls(a=1, b=0, c=0, d=0, generator=generator)
    
    @classmethod
    def zero(cls, generator):
        return cls(a=0, b=0, c=0, d=0, generator=generator)
    
    @classmethod
    def inv_sqrt2(cls, generator):
        # should not be used
        return cls(a=1, b=0, c=0, d=0, generator=generator)

    @classmethod
    def omega(cls, generator):
        return cls(b=1, generator=generator)

    @classmethod
    def minus_one(cls, generator):
        return cls(a=-1, generator=generator)

    @classmethod
    def i_phase(cls, generator):
        return cls(c=1, generator=generator)

    @classmethod
    def t_phase(cls, generator):
        """T-gate phase = e^{iπ/4} = (1+i)/√2 = ω"""
        return cls(b=1, generator=generator)
    
    def multiply_by_omega(self, generator):
        return Cyclotomic8Dyadic(
            a = f"(- 0 {self.d})",
            b = f"{self.a}",
            c = f"{self.b}",
            d = f"{self.c}",
            generator=self.generator
        )
        
    def multiply_by_omega_counter(self, generator):
        return Cyclotomic8Dyadic(
            a = f"{self.b}",
            b = f"{self.c}",
            c = f"{self.d}",
            d = f"(- 0 {self.a})",
            generator=self.generator
        )
    
    def multiply_by_i(self, generator):
        return Cyclotomic8Dyadic(
            a = f"(- 0 {self.c})",
            b = f"(- 0 {self.d})",
            c = f"{self.a}",
            d = f"{self.b}",
            generator=self.generator
        )
        
    def multiply_by_minus_i(self, generator):
        return Cyclotomic8Dyadic(
            a = f"{self.c}",
            b = f"{self.d}",
            c = f"(- 0 {self.a})",
            d = f"(- 0 {self.b})",
            generator=self.generator
        )
        
    def multiply_by_minus_one(self, generator):
        return Cyclotomic8Dyadic(
            a = f"(- 0 {self.a})",
            b = f"(- 0 {self.b})",
            c = f"(- 0 {self.c})",
            d = f"(- 0 {self.d})",
            generator=self.generator
        )
        
    def divide_by_sqrt2(self, generator):
        return Cyclotomic8Dyadic(
            a = f"{self.a}",
            b = f"{self.b}",
            c = f"{self.c}",
            d = f"{self.d}",
            generator=self.generator
        )


class Vector:
    def __init__(self, q, symbolic=True, name=None, generator=None, element_representation=None, k=None):
        if element_representation is None:
            raise ValueError("element_representation must be provided")
        
        if element_representation == Cyclotomic8Dyadic and k is None:
            raise ValueError("k must be provided for Cyclotomic8Dyadic")
        
        # k is stored in the vector (shared by all elements)
        if element_representation == Cyclotomic8Dyadic and k is not None:
            if name is not None:
                self.k = generator.declare_integer(f"{name}_k")
            else:
                self.k = generator.format_integer(k)
        else:
            self.k = None
        
        self.generator = generator
        self.vec = []
        for i in range(q):
            if symbolic:
                # Only create named symbolic elements if name is provided
                if name is not None:
                    self.vec.append(element_representation(name=f"{name}_{i}", generator=generator))
                else:
                    # If no name, create non-symbolic (literal) elements
                    if element_representation == Cyclotomic8Dyadic:
                        self.vec.append(element_representation.zero(generator))
                    elif isinstance(element_representation, Complex):
                        self.vec.append(element_representation.zero(generator))
                    else:
                        raise ValueError("element_representation must be a Cyclotomic8Dyadic or Complex")
            else:
                if element_representation == Cyclotomic8Dyadic:
                    self.vec.append(element_representation.zero(generator))
                elif isinstance(element_representation, Complex):
                    self.vec.append(element_representation.zero(generator))
                else:
                    raise ValueError("element_representation must be a Cyclotomic8Dyadic or Complex")
    
    def __getitem__(self, i):
        return self.vec[i]
    
    def __setitem__(self, i, value):
        self.vec[i] = value
    
    def __eq__(self, other):
        eqs = [self.vec[i] == other.vec[i] for i in range(len(self.vec))]
        # Also compare k if both vectors have it (for Cyclotomic8Dyadic)
        if self.k is not None and other.k is not None:
            eqs.append(f"(= {self.k} {other.k})")
        return f"(and {' '.join(eqs)})"
    
    def __repr__(self):
        return f"[{', '.join(str(v) for v in self.vec)}]"