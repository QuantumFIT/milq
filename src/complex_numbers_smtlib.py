import numpy as np
from pysmt.shortcuts import Plus, Minus, Times, Equals, And, Real, Int

class Complex:
    def __init__(self, a=None, b=None, name=None, generator=None):
        self.generator = generator
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

    def _use_pysmt(self):
        if self.generator is not None and self.generator.name == 'PortfolioSolver':
            return True
        return False
    
    def __add__(self, other):
        if self.generator is None:
            return Complex(a=self.real + other.real, b=self.imag + other.imag, generator=self.generator)
        elif self._use_pysmt():
            real_expr = Plus(self.real, other.real)
            imag_expr = Plus(self.imag, other.imag)
        else:
            real_expr = f"(+ {self.real} {other.real})"
            imag_expr = f"(+ {self.imag} {other.imag})"
        return Complex(a=real_expr, b=imag_expr, generator=self.generator)
    
    def __sub__(self, other):
        if self.generator is None:
            return Complex(a=self.real - other.real, b=self.imag - other.imag, generator=self.generator)
        elif self._use_pysmt():
            real_expr = Minus(self.real, other.real)
            imag_expr = Minus(self.imag, other.imag)
        else:
            real_expr = f"(- {self.real} {other.real})"
            imag_expr = f"(- {self.imag} {other.imag})"
        return Complex(a=real_expr, b=imag_expr, generator=self.generator)

    def __mul__(self, other):
        # (a + bi) * (c + di) = (ac - bd) + (ad + bc)i
        if self.generator is None:
            return Complex(a=self.real * other.real - self.imag * other.imag, b=self.real * other.imag + self.imag * other.real, generator=self.generator)
        elif self._use_pysmt():
            real_expr = Minus(Times(self.real, other.real), Times(self.imag, other.imag))
            imag_expr = Plus(Times(self.real, other.imag), Times(self.imag, other.real))
        else:
            real_expr = f"(- (* {self.real} {other.real}) (* {self.imag} {other.imag}))"
            imag_expr = f"(+ (* {self.real} {other.imag}) (* {self.imag} {other.real}))"
        return Complex(a=real_expr, b=imag_expr, generator=self.generator)
    
    def __eq__(self, other):
        if self._use_pysmt():
            real_eq = Equals(self.real, other.real)
            imag_eq = Equals(self.imag, other.imag)
            return And(real_eq, imag_eq)
        else:
            real_eq = f"(= {self.real} {other.real})"
            imag_eq = f"(= {self.imag} {other.imag})"
            return f"(and {real_eq} {imag_eq})"

    def __repr__(self):
        return f"({self.real} + {self.imag}j)"
    
    def copy(self):
        return Complex(a=self.real, b=self.imag, generator=self.generator)

    def conjugate(self):
        if self.generator is None:
            return Complex(a=self.real, b=-self.imag, generator=self.generator)
        elif self._use_pysmt():
            imag_expr = Minus(Real(0), self.imag)
        else:
            imag_expr = f"(- 0 {self.imag})"
        return Complex(a=self.real, b=imag_expr, generator=self.generator)
    
    def to_real(self):
        return self

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
    
    @classmethod
    def one_half(cls, generator):
        return cls(a=1/2, b=0, generator=generator)
    
    @classmethod
    def i_half(cls, generator):
        return cls(a=0, b=1/2, generator=generator)

    def multiply_by_omega(self, generator):
        return self * Complex.t_phase(generator)
        
    def multiply_by_omega_counter(self, generator):
        return self * Complex.t_phase(generator).conjugate()
    
    def multiply_by_i(self, generator):
        return self * Complex.i_phase(generator)
        
    def multiply_by_minus_i(self, generator):
        return self * Complex.i_phase(generator).conjugate()
        
    def multiply_by_minus_one(self, generator):
        return self * Complex.minus_one(generator)
        
    def divide_by_sqrt2(self, generator):
        return self * Complex.inv_sqrt2(generator)

    def divide_by_two(self, generator):
        return self * Complex.one_half(generator)
    
    def divide_by_two_i(self, generator):
        return self * Complex.i_half(generator)

# ------------------------------------------------------------------------------------------------ #


class Cyclotomic8Dyadic:
    def __init__(self, a=0, b=0, c=0, d=0,
                 name=None, generator=None):
        if generator is not None:
            self.generator = generator
        else:
            self.generator = None
            
        if self.generator is None:
            self.a = a
            self.b = b
            self.c = c
            self.d = d
            return

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
    
    def _use_pysmt(self):
        if self.generator is None or self.generator.name != 'PortfolioSolver':
            return False
        return True
    
    def _to_pysmt_expr(self, value):
        if isinstance(value, str):
            if self.generator is not None and hasattr(self.generator, 'symbols') and value in self.generator.symbols:
                return self.generator.symbols[value]
            try:
                if '.' in value:
                    return Real(float(value))
                else:
                    return Int(int(value))
            except:
                raise ValueError(f"Failed to convert {value} to pysmt expression")
        elif isinstance(value, int):
            return Int(value)
        elif isinstance(value, float):
            return Real(value)
        else:
            return value
            
    def copy(self):
        return Cyclotomic8Dyadic(a=self.a, b=self.b, c=self.c, d=self.d, generator=self.generator)

    def _coeffs(self):
        return (self.a, self.b, self.c, self.d)

    def __add__(self, other):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.a + other.a, b=self.b + other.b, c=self.c + other.c, d=self.d + other.d)
        elif self._use_pysmt():
            # Convert to pysmt expressions if they're strings
            a1 = self._to_pysmt_expr(self.a)
            a2 = self._to_pysmt_expr(other.a)
            b1 = self._to_pysmt_expr(self.b)
            b2 = self._to_pysmt_expr(other.b)
            c1 = self._to_pysmt_expr(self.c)
            c2 = self._to_pysmt_expr(other.c)
            d1 = self._to_pysmt_expr(self.d)
            d2 = self._to_pysmt_expr(other.d)
            return Cyclotomic8Dyadic(
                a = Plus(a1, a2),
                b = Plus(b1, b2),
                c = Plus(c1, c2),
                d = Plus(d1, d2),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
                a = f"(+ {self.a} {other.a})",
                b = f"(+ {self.b} {other.b})",
                c = f"(+ {self.c} {other.c})",
                d = f"(+ {self.d} {other.d})",
                generator=self.generator
            )

    def __sub__(self, other):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.a - other.a, b=self.b - other.b, c=self.c - other.c, d=self.d - other.d)
        elif self._use_pysmt():
            # Convert to pysmt expressions if they're strings
            a1 = self._to_pysmt_expr(self.a)
            a2 = self._to_pysmt_expr(other.a)
            b1 = self._to_pysmt_expr(self.b)
            b2 = self._to_pysmt_expr(other.b)
            c1 = self._to_pysmt_expr(self.c)
            c2 = self._to_pysmt_expr(other.c)
            d1 = self._to_pysmt_expr(self.d)
            d2 = self._to_pysmt_expr(other.d)
            return Cyclotomic8Dyadic(
                a = Minus(a1, a2),
                b = Minus(b1, b2),
                c = Minus(c1, c2),
                d = Minus(d1, d2),
                generator=self.generator
            )
        else:
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
        if self.generator is None:
            return Cyclotomic8Dyadic(
                a=self.a * other.a - self.b * other.d - self.c * other.c - self.d * other.b, 
                b=self.a * other.b + self.b * other.a + self.c * other.d - self.d * other.c, 
                c=self.a * other.c + self.b * other.b + self.c * other.a - self.d * other.d, 
                d=self.a * other.d + self.b * other.c + self.c * other.b + self.d * other.a,
            )
        elif self._use_pysmt():
            a1 = self._to_pysmt_expr(self.a)
            a2 = self._to_pysmt_expr(other.a)
            b1 = self._to_pysmt_expr(self.b)
            b2 = self._to_pysmt_expr(other.b)
            c1 = self._to_pysmt_expr(self.c)
            c2 = self._to_pysmt_expr(other.c)
            d1 = self._to_pysmt_expr(self.d)
            d2 = self._to_pysmt_expr(other.d)
            return Cyclotomic8Dyadic(
                a = Minus(Minus(Minus(Times(a1, a2), Times(b1, d2)), Times(c1, c2)), Times(d1, b2)),
                b = Minus(Minus(Plus(Times(a1, b2), Times(b1, a2)), Times(c1, d2)), Times(d1, c2)),
                c = Minus(Plus(Plus(Times(a1, c2), Times(b1, b2)), Times(c1, a2)), Times(d1, d2)),
                d = Plus(Plus(Plus(Times(a1, d2), Times(b1, c2)), Times(c1, b2)), Times(d1, a2)),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
            a = f"(- (* {self.a} {other.a}) (* {self.b} {other.d}) (* {self.c} {other.c}) (* {self.d} {other.b}))",
            b = f"(- (- (+ (* {self.a} {other.b}) (* {self.b} {other.a})) (* {self.c} {other.d})) (* {self.d} {other.c}))",
            c = f"(- (+ (+ (* {self.a} {other.c}) (* {self.b} {other.b})) (* {self.c} {other.a})) (* {self.d} {other.d}))",
            d = f"(+ (* {self.a} {other.d}) (* {self.b} {other.c}) (* {self.c} {other.b}) (* {self.d} {other.a}))",
            generator=self.generator
            )
    
    def __eq__(self, other):
        if self._use_pysmt():
            # Convert to pysmt expressions if they're strings
            a1 = self._to_pysmt_expr(self.a)
            a2 = self._to_pysmt_expr(other.a)
            b1 = self._to_pysmt_expr(self.b)
            b2 = self._to_pysmt_expr(other.b)
            c1 = self._to_pysmt_expr(self.c)
            c2 = self._to_pysmt_expr(other.c)
            d1 = self._to_pysmt_expr(self.d)
            d2 = self._to_pysmt_expr(other.d)
            return And(
                Equals(a1, a2),
                Equals(b1, b2),
                Equals(c1, c2),
                Equals(d1, d2)
            )
        else:
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
    
    def multiply_by_omega(self, generator):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=-self.d, b=self.a, c=self.b, d=self.c)
        elif self._use_pysmt():
            d_val = self._to_pysmt_expr(self.d)
            return Cyclotomic8Dyadic(
                a = Minus(Int(0), d_val),
                b = self._to_pysmt_expr(self.a),
                c = self._to_pysmt_expr(self.b),
                d = self._to_pysmt_expr(self.c),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
                a = f"(- 0 {self.d})",
                b = f"{self.a}",
                c = f"{self.b}",
                d = f"{self.c}",
                generator=self.generator
            )
        
    def multiply_by_omega_counter(self, generator):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.b, b=self.c, c=self.d, d=-self.a)
        elif self._use_pysmt():
            a_val = self._to_pysmt_expr(self.a)
            return Cyclotomic8Dyadic(
                a = self._to_pysmt_expr(self.b),
                b = self._to_pysmt_expr(self.c),
                c = self._to_pysmt_expr(self.d),
                d = Minus(Int(0), a_val),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
            a = f"{self.b}",
            b = f"{self.c}",
            c = f"{self.d}",
            d = f"(- 0 {self.a})",
            generator=self.generator
        )
    
    def multiply_by_i(self, generator):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=-self.c, b=-self.d, c=self.a, d=self.b)
        elif self._use_pysmt():
            return Cyclotomic8Dyadic(
                a = Minus(Int(0), self._to_pysmt_expr(self.c)),
                b = Minus(Int(0), self._to_pysmt_expr(self.d)),
                c = self._to_pysmt_expr(self.a),
                d = self._to_pysmt_expr(self.b),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
            a = f"(- 0 {self.c})",
            b = f"(- 0 {self.d})",
            c = f"{self.a}",
            d = f"{self.b}",
            generator=self.generator
        )
        
    def multiply_by_minus_i(self, generator):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.c, b=self.d, c=-self.a, d=-self.b)
        elif self._use_pysmt():
            return Cyclotomic8Dyadic(
                a = self._to_pysmt_expr(self.c),
                b = self._to_pysmt_expr(self.d),
                c = Minus(Int(0), self._to_pysmt_expr(self.a)),
                d = Minus(Int(0), self._to_pysmt_expr(self.b)),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
            a = f"{self.c}",
            b = f"{self.d}",
            c = f"(- 0 {self.a})",
            d = f"(- 0 {self.b})",
            generator=self.generator
        )
        
    def multiply_by_minus_one(self, generator):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=-self.a, b=-self.b, c=-self.c, d=-self.d)
        elif self._use_pysmt():
            return Cyclotomic8Dyadic(
                a = Minus(Int(0), self._to_pysmt_expr(self.a)),
                b = Minus(Int(0), self._to_pysmt_expr(self.b)),
                c = Minus(Int(0), self._to_pysmt_expr(self.c)),
                d = Minus(Int(0), self._to_pysmt_expr(self.d)),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
            a = f"(- 0 {self.a})",
            b = f"(- 0 {self.b})",
            c = f"(- 0 {self.c})",
            d = f"(- 0 {self.d})",
            generator=self.generator
        )
        
    def divide_by_sqrt2(self, generator):
        return self

    def divide_by_two(self, generator):
        return self
    
    def divide_by_two_i(self, generator):
        return self.multiply_by_i(generator)
            
    def to_real(self, k): 
        # omega = (1 + i) / sqrt(2)
        # real = (a + ((b - d)/sqrt(2))) / sqrt(2)^k
        # imag = (c + ((b + d)/sqrt(2))) / sqrt(2)^k
        if self.generator is None:
            real = (self.a + ((self.b - self.d)/np.sqrt(2))) / np.sqrt(2)**k
            imag = (self.c + ((self.b + self.d)/np.sqrt(2))) / np.sqrt(2)**k
            return Complex(a=real, b=imag, generator=self.generator)
        else:
            # Declare sqrt2 if not already declared
            if "sqrt2" not in self.generator.declared_names:
                sqrt2 = self.generator.declare_real("sqrt2")
                self.generator.add_assertion(f"(= (* {sqrt2} {sqrt2}) 2.0)")
            else:
                sqrt2 = "sqrt2"
            

            if hasattr(self.generator, 'rescaling') and self.generator.rescaling:
                if isinstance(k, int) and k == 0:
                    sqrt2_k = "1.0"
                else:
                    sqrt2_k = f"(pow {sqrt2} {k})"
            else:
                raise ValueError("rescaling missing")
            
            b_minus_d = f"(- {self.b} {self.d})"
            b_minus_d_over_sqrt2 = f"(/ {b_minus_d} {sqrt2})"
            real_numerator = f"(+ {self.a} {b_minus_d_over_sqrt2})"
            
            b_plus_d = f"(+ {self.b} {self.d})"
            b_plus_d_over_sqrt2 = f"(/ {b_plus_d} {sqrt2})"
            imag_numerator = f"(+ {self.c} {b_plus_d_over_sqrt2})"
            
            real = f"(/ {real_numerator} {sqrt2_k})"
            imag = f"(/ {imag_numerator} {sqrt2_k})"
            
            return Complex(a=real, b=imag, generator=self.generator)
        
    def abs2(self, k):
        # a = a/2^(k/2)
        # b = b/2^(k/2)
        # c = c/2^(k/2)
        # d = d/2^(k/2)
        # res = a^2 + b^2 + c^2 + d^2 + sqrt(2)*(a * (b-d) + c * (b+d))
        a_squared = f"(pow {self.a} 2)"
        b_squared = f"(pow {self.b} 2)"
        c_squared = f"(pow {self.c} 2)"
        d_squared = f"(pow {self.d} 2)"
        two_to_k_minus_half = f"(pow 2 (- {k} 0.5))"
        two_to_k = f"(pow 2 {k})"
        left_term = f"(/ (+ {a_squared} {b_squared} {c_squared} {d_squared}) {two_to_k} )"
        right_term = f"(/ (+ (+ (- (* {self.a} {self.b}) (* {self.a} {self.c})) (* {self.c} {self.b})) (* {self.c} {self.d})) {two_to_k_minus_half})"
        return f"(+ {left_term} {right_term})"
        

    def conjugate(self):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.a, b=-self.d, c=-self.c, d=-self.b, generator=self.generator)
        elif self._use_pysmt():
            return Cyclotomic8Dyadic(
                a = self._to_pysmt_expr(self.a),
                b = Minus(Int(0), self._to_pysmt_expr(self.d)),
                c = Minus(Int(0), self._to_pysmt_expr(self.c)),
                d = Minus(Int(0), self._to_pysmt_expr(self.b)),
                generator=self.generator
            )
        else:
            return Cyclotomic8Dyadic(
            a = f"{self.a}",
            b = f"(- 0 {self.d})",
            c = f"(- 0 {self.c})",
            d = f"(- 0 {self.b})",
            generator=self.generator
        )
    
# ------------------------------------------------------------------------------------------------ #
    
class nTuple:
    def __init__(self, elements=None,
                 name=None, n=0, generator=None):
        
        # n has to be a power of 2
        if n != 0:
            # https://stackoverflow.com/questions/600293/how-to-check-if-a-number-is-a-power-of-2
            if not (n and (n & (n - 1)) == 0):
                raise ValueError("n has to be a power of 2")
        self.n = n
        if generator is not None:
            self.generator = generator
        else:
            self.generator = None
            
        if self.generator is None:
            self.elements = elements
            return

        if name is not None:
            safe = name.replace('[', '_').replace(']', '')
            self.elements = [generator.declare_integer(f"{safe}_{i}") for i in range(n)]
        else:
            self.elements = [generator.format_integer(e) for e in elements]
    
    def _use_pysmt(self):
        if self.generator is not None and self.generator.name == 'PortfolioSolver':
            return True
        return False
            
    def copy(self):
        return nTuple(elements=self.elements.copy(), n=self.n, generator=self.generator)

    def _coeffs(self):
        return self.elements

    def __add__(self, other):
        if self.generator is None:
            return nTuple(elements=[self.elements[i] + other.elements[i] for i in range(self.n)], n=self.n, generator=self.generator)
        elif self._use_pysmt():
            return nTuple(elements=[Plus(self._to_pysmt_expr(self.elements[i]), self._to_pysmt_expr(other.elements[i])) for i in range(self.n)], n=self.n, generator=self.generator)
        else:
            return nTuple(elements=[f"(+ {self.elements[i]} {other.elements[i]})" for i in range(self.n)], n=self.n, generator=self.generator)

    def __sub__(self, other):
        if self.generator is None:
            return nTuple(elements=[self.elements[i] - other.elements[i] for i in range(self.n)], n=self.n, generator=self.generator)
        elif self._use_pysmt():
            return nTuple(elements=[Minus(self._to_pysmt_expr(self.elements[i]), self._to_pysmt_expr(other.elements[i])) for i in range(self.n)], n=self.n, generator=self.generator)
        else:
            return nTuple(elements=[f"(- {self.elements[i]} {other.elements[i]})" for i in range(self.n)], n=self.n, generator=self.generator)

    def __mul__(self, other):
        if self.generator is None:
            elements = [0] * self.n
            for i in range(self.n):
                for j in range(other.n):
                    target_index = (i + j) % self.n
                    amplitude = self.elements[i] * other.elements[j]
                    elements[target_index] += amplitude
            return nTuple(elements=elements, n=self.n, generator=self.generator)
        elif self._use_pysmt():
            elements = [None] * self.n
            for i in range(self.n):
                elements[i] = Int(0)
            for i in range(self.n):
                for j in range(other.n):
                    target_index = (i + j) % self.n
                    e1 = self._to_pysmt_expr(self.elements[i])
                    e2 = self._to_pysmt_expr(other.elements[j])
                    amplitude = Times(e1, e2)
                    if elements[target_index] is None or (isinstance(elements[target_index], int) and elements[target_index] == 0):
                        elements[target_index] = amplitude
                    else:
                        elements[target_index] = Plus(elements[target_index], amplitude)
            return nTuple(elements=elements, n=self.n, generator=self.generator)
        else:
            elements = [0] * self.n
            for i in range(self.n):
                for j in range(other.n):
                    target_index = (i + j) % self.n
                    amplitude = f"(* {self.elements[i]} {other.elements[j]})"
                    if elements[target_index] == 0:
                        elements[target_index] = amplitude
                    else:
                        elements[target_index] = f"(+ {elements[target_index]} {amplitude})"
            return nTuple(elements=elements, n=self.n, generator=self.generator)
    
    def _to_pysmt_expr(self, value):
        if isinstance(value, str):
            if self.generator is not None and hasattr(self.generator, 'symbols') and value in self.generator.symbols:
                return self.generator.symbols[value]
            try:
                if '.' in value:
                    return Real(float(value))
                else:
                    return Int(int(value))
            except:
                return value
        return value
    
    def __eq__(self, other):
        if self._use_pysmt():
            eqs = []
            for i in range(self.n):
                e1 = self._to_pysmt_expr(self.elements[i])
                e2 = self._to_pysmt_expr(other.elements[i])
                eqs.append(Equals(e1, e2))
            return And(*eqs)
        else:
            eqs = [
                f"(= {self.elements[i]} {other.elements[i]})" for i in range(self.n)
            ]
            return f"(and {' '.join(eqs)})"

    def __repr__(self):
        return f"({', '.join(str(e) for e in self.elements)})"

    @classmethod
    def one(cls, generator, n):
        elems = [0] * n
        elems[0] = 1
        return cls(elements=elems, n=n, generator=generator)
    
    @classmethod
    def zero(cls, generator, n):
        elems = [0] * n
        return cls(elements=elems, n=n, generator=generator)
    
    @classmethod
    def inv_sqrt2(cls, generator, n):
        # should not be used
        raise ValueError("inv_sqrt2 is not used for nTuple")

    @classmethod
    def one_half(cls, generator, n):
        # should not be used
        raise ValueError("one_half is not used for nTuple")
    
    @classmethod
    def i_half(cls, generator, n):
        raise ValueError("i_half is not used for nTuple")

    @classmethod
    def omega(cls, generator, n):
        raise ValueError("omega is not used for nTuple")

    @classmethod
    def minus_one(cls, generator, n):
        elems = [0] * n
        elems[0] = -1
        return cls(elements=elems, n=n, generator=generator)

    @classmethod
    def i_phase(cls, generator, n):
        raise ValueError("i_phase is not used for nTuple")

    @classmethod
    def t_phase(cls, generator, n):
        raise ValueError("t_phase is not used for nTuple")
    
    def multiply_by_omega(self, generator):
        # HERE omega is e^(ipi/4) -- T gate phase
        shifts = int(self.n/4) 
        # swap the sign of the last shifts numbers, shift to the right by shifts
        if self.generator is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = -self.elements[self.n - shifts + i]
            for i in range(shifts, self.n):
                elems[i] = self.elements[i - shifts]
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[i] = Minus(Int(0), self._to_pysmt_expr(self.elements[self.n - shifts + i]))
            for i in range(shifts, self.n):
                elems[i] = self._to_pysmt_expr(self.elements[i - shifts])
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = f"(- 0 {self.elements[self.n - shifts + i]})"
            for i in range(shifts, self.n):
                elems[i] = f"{self.elements[i - shifts]}"
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        
    def multiply_by_omega_counter(self, generator):
        shifts = int(self.n/4) 
        if self.generator is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = -self.elements[i]
            for i in range(shifts, self.n):
                elems[i - shifts] = self.elements[i]
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = Minus(Int(0), self.elements[i])
            for i in range(shifts, self.n):
                elems[i - shifts] = self.elements[i]
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = f"(- 0 {self.elements[i]})"
            for i in range(shifts, self.n):
                elems[i - shifts] = f"{self.elements[i]}"
            return nTuple(elements=elems, n=self.n, generator=self.generator)
    
    def multiply_by_i(self, generator):
        shifts = int(self.n/2)
        if self.generator is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = -self.elements[self.n - shifts + i]
            for i in range(shifts, self.n):
                elems[i] = self.elements[i - shifts]
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[i] = Minus(Int(0), self._to_pysmt_expr(self.elements[self.n - shifts + i]))
            for i in range(shifts, self.n):
                elems[i] = self._to_pysmt_expr(self.elements[i - shifts])
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = f"(- 0 {self.elements[self.n - shifts + i]})"
            for i in range(shifts, self.n):
                elems[i] = f"{self.elements[i - shifts]}"
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        
    def multiply_by_minus_i(self, generator):
        shifts = int(self.n/2)
        if self.generator is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = -self.elements[i]
            for i in range(shifts, self.n):
                elems[i - shifts] = self.elements[i]
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = Minus(Int(0), self._to_pysmt_expr(self.elements[i]))
            for i in range(shifts, self.n):
                elems[i - shifts] = self._to_pysmt_expr(self.elements[i])
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = f"(- 0 {self.elements[i]})"
            for i in range(shifts, self.n):
                elems[i - shifts] = f"{self.elements[i]}"
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        
    def multiply_by_minus_one(self, generator):
        if self.generator is None:
            return nTuple(elements=[-self.elements[i] for i in range(self.n)], n=self.n, generator=self.generator)
        elif self._use_pysmt():
            return nTuple(elements=[Minus(Int(0), self._to_pysmt_expr(self.elements[i])) for i in range(self.n)], n=self.n, generator=self.generator)
        else:
            return nTuple(elements=[f"(- 0 {self.elements[i]})" for i in range(self.n)], n=self.n, generator=self.generator)
        
    def divide_by_sqrt2(self, generator):
        if self.generator is None:
            return nTuple(elements=self.elements, n=self.n, generator=self.generator)
        elif self._use_pysmt():
            # divide_by_sqrt2 is a no-op for nTuple (just returns self)
            return nTuple(elements=self.elements, n=self.n, generator=self.generator)
        else:
            return nTuple(elements=[f"{self.elements[i]}" for i in range(self.n)], n=self.n, generator=self.generator)
        
    def to_five_tuple(self):
        elems = [0] * 4
        # if size is X, take every Yth element (X -> Y)
        # 4 -> 1, 8 -> 2, 16 -> 4
        take_every = int(self.n/4)
        j = 0
        for i in range(self.n):
            if i % take_every == 0:
                # take this element
                elems[j] = self.elements[i]
                j += 1
            elif int(self.elements[i]) != 0:
                raise ValueError("cant convert nTuple to five tuple")
        return Cyclotomic8Dyadic(a=elems[0], b=elems[1], c=elems[2], d=elems[3], generator=self.generator)
    
    def abs2(self, k):
        denominator = np.sqrt(2)**k
        num_r = 0
        num_i = 0
        for i in range(self.n):
            num_r += np.cos(np.pi * i / self.n) * self.elements[i]
            num_i += np.sin(np.pi * i / self.n) * self.elements[i]
        num_r = num_r / denominator
        num_i = num_i / denominator
        return num_r ** 2 + num_i ** 2
                

# ------------------------------------------------------------------------------------------------ #

class Vector:
    def __init__(self, q, symbolic=True, name=None, generator=None, element_representation=None, k=None, n=None):
        if element_representation is None:
            raise ValueError("element_representation must be provided")
        
        self.element_representation = element_representation
        
        if element_representation == Cyclotomic8Dyadic and k is None:
            raise ValueError("k must be provided for Cyclotomic8Dyadic")
        
        # k is stored in the vector (shared by all elements)
        if generator is not None:
            if (element_representation == Cyclotomic8Dyadic or element_representation == nTuple) and k is not None:
                if name is not None:
                    self.k = generator.declare_integer(f"{name}_k")
                else:
                    self.k = generator.format_integer(k)
            else:
                self.k = None
            self.generator = generator
        else:
            self.generator = None
            self.k = k
        
        self.n = n
        
        self.vec = []
        self.name = name
        for i in range(q):
            if symbolic:
                if name is not None:
                    if element_representation == nTuple:
                        self.vec.append(element_representation(name=f"{name}_{i}", n=n, generator=generator))
                    else:
                        self.vec.append(element_representation(name=f"{name}_{i}", generator=generator))
                else:
                    if element_representation == Cyclotomic8Dyadic:
                        self.vec.append(element_representation.zero(generator))
                    elif element_representation == nTuple:
                        self.vec.append(element_representation.zero(generator, n=n))
                    elif element_representation == Complex:
                        self.vec.append(element_representation.zero(generator))
                    else:
                        raise ValueError("element_representation must be a Cyclotomic8Dyadic, nTuple or Complex")
            else:
                if element_representation == Cyclotomic8Dyadic:
                    self.vec.append(element_representation.zero(generator))
                elif element_representation == nTuple:
                    self.vec.append(element_representation.zero(generator, n=n))
                elif isinstance(element_representation, Complex):
                    self.vec.append(element_representation.zero(generator))
                else:
                    raise ValueError("element_representation must be a Cyclotomic8Dyadic, nTuple or Complex")
    
    def __getitem__(self, i):
        return self.vec[i]
    
    def __setitem__(self, i, value):
        self.vec[i] = value
        
    def _to_pysmt_expr(self, value):
        if isinstance(value, str):
            if self.generator is not None and hasattr(self.generator, 'symbols') and value in self.generator.symbols:
                return self.generator.symbols[value]
            try:
                if '.' in value:
                    return Real(float(value))
                else:
                    return Int(int(value))
            except:
                raise ValueError(f"Failed to convert {value} to pysmt expression")
        return value
    
    def _use_pysmt(self):
        if self.generator is not None and self.generator.name == 'PortfolioSolver':
            return True
        return False
    
    def __eq__(self, other):
        eqs = [self.vec[i] == other.vec[i] for i in range(len(self.vec))]
        if self.k is not None and other.k is not None:
            if self._use_pysmt():
                eqs.append(Equals(self.k, other.k))
                return And(*eqs)
            else:
                # TODO rescaling -- remove this
                #eqs.append(f"(= {self.k} {other.k})")
                return f"(and { ' '.join(eqs) })"
    
    
    def __repr__(self):
        return f"[{', '.join(str(v) for v in self.vec)}], k={self.k}"
    
    def copy(self):
        new_vec = Vector(q=len(self.vec), generator=self.generator, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].copy()
        new_vec.k = self.k
        return new_vec

    def to_real(self):
        if self.element_representation == Complex:
            return self
        name = None
        if self.name is not None:
            name = f"Rescaled_{self.name}"
                    
        new_vec = Vector(q=len(self.vec), generator=self.generator, name=name, element_representation=Complex, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].to_real(self.k)
        return new_vec
    
    def conjugate(self):
        new_vec = Vector(q=len(self.vec), generator=self.generator, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].conjugate()
        return new_vec
    
    def __len__(self):
        return len(self.vec)
    
    def __mul__(self, other) -> tuple[any, any]:
        if len(self.vec) == 0:
            raise ValueError("Vector is empty")
    
        dot_vec = Vector(q=len(self.vec), generator=self.generator, element_representation=self.element_representation, k=self.k, n=self.n, name=f"Dot_Product")
        gen = self.generator if self.generator is not None else other.generator
        for i in range(len(self.vec)):
            gen.add_assertion(dot_vec[i] == self.vec[i] * other.vec[i])
            
        sum_var = self.element_representation(name=f"Dot_Sum", generator=gen)
        sum = dot_vec[0]
        for i in range(1, len(dot_vec)):
            sum = sum + dot_vec[i]
        gen.add_assertion(sum_var == sum)
        k_final = f"(+ {self.k} {other.k})"
        if self.element_representation == Cyclotomic8Dyadic or self.element_representation == nTuple:
            gen.add_assertion(f"(= {dot_vec.k} {k_final})")
        # because multiplication does not need rescaling (it scales to k1 + k2), and k is shared by all elements of a vector
        # the k of the result is the sum of k's of the vectors
        return sum_var, k_final