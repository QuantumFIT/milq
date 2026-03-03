import numpy as np
from pysmt.shortcuts import Plus, Minus, Times, Equals, And, Real
from .classic import Complex

class FiveTuple:
    def __init__(self, a = 0, b = 0, c = 0, d = 0, name = None, generator = None):
        if generator is not None:
            self.gen = generator
        else:
            self.gen = None
            
        if self.gen is None:
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
            # Convert to pysmt expressions if they're strings
            return FiveTuple(
                a = self.gen.Minus(self.gen.format_integer(self.a), self.gen.format_integer(other.a)),
                b = self.gen.Minus(self.gen.format_integer(self.b), self.gen.format_integer(other.b)),
                c = self.gen.Minus(self.gen.format_integer(self.c), self.gen.format_integer(other.c)),
                d = self.gen.Minus(self.gen.format_integer(self.d), self.gen.format_integer(other.d)),
                generator=self.gen
            )

    def __mul__(self, other):
        # a = a1*a2 - b1*d2 - c1*c2 - d1*b2
        # b = a1*b2 + b1*a2 + c1*d2 - d1*c2
        # c = a1*c2 + b1*b2 + c1*a2 - d1*d2
        # d = a1*d2 + b1*c2 + c1*b2 + d1*a2
        # k = k1 + k2
        if self.gen is None:
            return FiveTuple(
                a=self.a * other.a - self.b * other.d - self.c * other.c - self.d * other.b, 
                b=self.a * other.b + self.b * other.a + self.c * other.d - self.d * other.c, 
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

    def __repr__(self):
        return f"({self.a} + {self.b} ω + {self.c} ω² + {self.d} ω³)"

    @classmethod
    def constrained_equals(cls, sel, expr1, expr2):
        gen = expr1.gen
        bigM = 1e3
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

    @classmethod
    def constrained_rescaling(cls, bigM, sel, r1, r2, fivetuple1, fivetuple2, exponent, parity, rel):
        gen = fivetuple1.gen
        a1 = exponent if rel == "<=" else 1
        a2 = exponent if rel == ">" else 1
        bigM = bigM * exponent
        if parity == "even":
            if rel == "<=":
            # rescale fivetuple1 by exponent
                gen.add_assertion(a1 * fivetuple1.a - r1.a <= bigM * sel)
                gen.add_assertion(r1.a - a1 * fivetuple1.a <= bigM * sel)
                gen.add_assertion(a1 * fivetuple1.b - r1.b <= bigM * sel)
                gen.add_assertion(r1.b - a1 * fivetuple1.b <= bigM * sel)
                gen.add_assertion(a1 * fivetuple1.c - r1.c <= bigM * sel)
                gen.add_assertion(r1.c - a1 * fivetuple1.c <= bigM * sel)
                gen.add_assertion(a1 * fivetuple1.d - r1.d <= bigM * sel)
                gen.add_assertion(r1.d - a1 * fivetuple1.d <= bigM * sel)

                gen.add_assertion(r2.a - fivetuple2.a <= bigM * sel)
                gen.add_assertion(fivetuple2.a - r2.a <= bigM * sel)
                gen.add_assertion(r2.b - fivetuple2.b <= bigM * sel)
                gen.add_assertion(fivetuple2.b - r2.b <= bigM * sel)
                gen.add_assertion(r2.c - fivetuple2.c <= bigM * sel)
                gen.add_assertion(fivetuple2.c - r2.c <= bigM * sel)
                gen.add_assertion(r2.d - fivetuple2.d <= bigM * sel)
                gen.add_assertion(fivetuple2.d - r2.d <= bigM * sel)
            else:
                gen.add_assertion(r1.a - fivetuple1.a <= bigM * sel)
                gen.add_assertion(fivetuple1.a - r1.a <= bigM * sel)
                gen.add_assertion(r1.b - fivetuple1.b <= bigM * sel)
                gen.add_assertion(fivetuple1.b - r1.b <= bigM * sel)
                gen.add_assertion(r1.c - fivetuple1.c <= bigM * sel)
                gen.add_assertion(fivetuple1.c - r1.c <= bigM * sel)
                gen.add_assertion(r1.d - fivetuple1.d <= bigM * sel)
                gen.add_assertion(fivetuple1.d - r1.d <= bigM * sel)

                gen.add_assertion(r2.a - a2 * fivetuple2.a <= bigM * sel)
                gen.add_assertion(a2 * fivetuple2.a - r2.a <= bigM * sel)
                gen.add_assertion(r2.b - a2 * fivetuple2.b <= bigM * sel)
                gen.add_assertion(a2 * fivetuple2.b - r2.b <= bigM * sel)
                gen.add_assertion(r2.c - a2 * fivetuple2.c <= bigM * sel)
                gen.add_assertion(a2 * fivetuple2.c - r2.c <= bigM * sel)
                gen.add_assertion(r2.d - a2 * fivetuple2.d <= bigM * sel)
                gen.add_assertion(a2 * fivetuple2.d - r2.d <= bigM * sel)
        else:
            # rescale fivetuple1 by the matrix M
            if rel == "<=":
                gen.add_assertion(a1 * (fivetuple1.b - fivetuple1.d) - r1.a <= bigM * sel)
                gen.add_assertion(r1.a - a1 * (fivetuple1.b - fivetuple1.d) <= bigM * sel)
                gen.add_assertion(a1 * (fivetuple1.a + fivetuple1.c) - r1.b <= bigM * sel)
                gen.add_assertion(r1.b - a1 * (fivetuple1.a + fivetuple1.c) <= bigM * sel)
                gen.add_assertion(a1 * (fivetuple1.b + fivetuple1.d) - r1.c <= bigM * sel)
                gen.add_assertion(r1.c - a1 * (fivetuple1.b + fivetuple1.d) <= bigM * sel)
                gen.add_assertion(a1 * (fivetuple1.c - fivetuple1.a) - r1.d <= bigM * sel)
                gen.add_assertion(r1.d - a1 * (fivetuple1.c - fivetuple1.a) <= bigM * sel)

                gen.add_assertion(r2.a - fivetuple2.a <= bigM * sel)
                gen.add_assertion(fivetuple2.a - r2.a <= bigM * sel)
                gen.add_assertion(r2.b - fivetuple2.b <= bigM * sel)
                gen.add_assertion(fivetuple2.b - r2.b <= bigM * sel)
                gen.add_assertion(r2.c - fivetuple2.c <= bigM * sel)
                gen.add_assertion(fivetuple2.c - r2.c <= bigM * sel)
                gen.add_assertion(r2.d - fivetuple2.d <= bigM * sel)
                gen.add_assertion(fivetuple2.d - r2.d <= bigM * sel)
            else:
                gen.add_assertion(r2.a - a2 * (fivetuple2.b - fivetuple2.d) <= bigM * sel)
                gen.add_assertion(a2 * (fivetuple2.b - fivetuple2.d) - r2.a <= bigM * sel)
                gen.add_assertion(r2.b - a2 * (fivetuple2.a + fivetuple2.c) <= bigM * sel)
                gen.add_assertion(a2 * (fivetuple2.a + fivetuple2.c) - r2.b <= bigM * sel)
                gen.add_assertion(r2.c - a2 * (fivetuple2.b + fivetuple2.d) <= bigM * sel)
                gen.add_assertion(a2 * (fivetuple2.b + fivetuple2.d) - r2.c <= bigM * sel)
                gen.add_assertion(r2.d - a2 * (fivetuple2.c - fivetuple2.a) <= bigM * sel)
                gen.add_assertion(a2 * (fivetuple2.c - fivetuple2.a) - r2.d <= bigM * sel)

                gen.add_assertion(r1.a - fivetuple1.a <= bigM * sel)
                gen.add_assertion(fivetuple1.a - r1.a <= bigM * sel)
                gen.add_assertion(r1.b - fivetuple1.b <= bigM * sel)
                gen.add_assertion(fivetuple1.b - r1.b <= bigM * sel)
                gen.add_assertion(r1.c - fivetuple1.c <= bigM * sel)
                gen.add_assertion(fivetuple1.c - r1.c <= bigM * sel)
                gen.add_assertion(r1.d - fivetuple1.d <= bigM * sel)
                gen.add_assertion(fivetuple1.d - r1.d <= bigM * sel)

    
    @classmethod
    def one(cls, generator):
        return cls(a=1, b=0, c=0, d=0, generator=generator)
    
    @classmethod
    def zero(cls, generator):
        return cls(a=0, b=0, c=0, d=0, generator=generator)
    
    def multiply_by_omega(self, generator):
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
        if self.gen is None:
            real = (self.a + ((self.b - self.d)/np.sqrt(2))) / np.sqrt(2)**k
            imag = (self.c + ((self.b + self.d)/np.sqrt(2))) / np.sqrt(2)**k
            return Complex(a=real, b=imag, generator=self.gen)
        else:
            sqrt2 = self.gen.declare_real("sqrt2")
        
            if isinstance(k, int) and k == 0:
                sqrt2_k = self.gen.format_real(1)
            else:
                sqrt2_k = self.gen.Pow(sqrt2, k)
            
            b_minus_d = self.gen.Minus(self.gen.format_integer(self.b), self.gen.format_integer(self.d))
            b_minus_d_over_sqrt2 = self.gen.Div(b_minus_d, sqrt2)
            real_numerator = self.gen.Plus(self.gen.format_integer(self.a), b_minus_d_over_sqrt2)
            
            b_plus_d = self.gen.Plus(self.gen.format_integer(self.b), self.gen.format_integer(self.d))
            b_plus_d_over_sqrt2 = self.gen.Div(b_plus_d, sqrt2)
            imag_numerator = self.gen.Plus(self.gen.format_integer(self.c), b_plus_d_over_sqrt2)
            
            real = self.gen.Div(real_numerator, sqrt2_k)
            imag = self.gen.Div(imag_numerator, sqrt2_k)
            
            return Complex(a=real, b=imag, generator=self.gen)
        
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
                a = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.a)),
                b = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.d)),
                c = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.c)),
                d = self.gen.Minus(self.gen.Int(0), self.gen.format_integer(self.b)),
                generator=self.gen
            )