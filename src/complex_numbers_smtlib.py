import numpy as np

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
        return f"({self.real} + {self.imag}j)"
    
    def copy(self):
        return Complex(a=self.real, b=self.imag, generator=self.generator)

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
    
    @classmethod
    def one_half(cls, generator):
        return cls(a=1/2, b=0, generator=generator)
    
    @classmethod
    def i_half(cls, generator):
        return cls(a=0, b=1/2, generator=generator)

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
            
    def copy(self):
        return Cyclotomic8Dyadic(a=self.a, b=self.b, c=self.c, d=self.d, generator=self.generator)

    def _coeffs(self):
        return (self.a, self.b, self.c, self.d)

    def __add__(self, other):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.a + other.a, b=self.b + other.b, c=self.c + other.c, d=self.d + other.d)
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
                d=self.a * other.d + self.b * other.c + self.c * other.b + self.d * other.a
            )
        else:
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
    def one_half(cls, generator):
        # should not be used
        return cls(a=1, b=0, c=0, d=0, generator=generator)
    
    @classmethod
    def i_half(cls, generator):
        return cls(a=0, b=1/2, c=0, d=0, generator=generator)

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
        if self.generator is None:
            return Cyclotomic8Dyadic(a=-self.d, b=self.a, c=self.b, d=self.c)
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
        else:
            return Cyclotomic8Dyadic(
            a = f"(- 0 {self.a})",
            b = f"(- 0 {self.b})",
            c = f"(- 0 {self.c})",
            d = f"(- 0 {self.d})",
            generator=self.generator
        )
        
    def divide_by_sqrt2(self, generator):
        if self.generator is None:
            return Cyclotomic8Dyadic(a=self.a, b=self.b, c=self.c, d=self.d)
        else:
            return Cyclotomic8Dyadic(
            a = f"{self.a}",
            b = f"{self.b}",
            c = f"{self.c}",
            d = f"{self.d}",
            generator=self.generator
        )
            
    def to_real(self, k):
        # omega = (1 + i) / sqrt(2)
        real = (self.a + ((self.b - self.d)/np.sqrt(2))) / np.sqrt(2)**k
        imag = (self.c + ((self.b + self.d)/np.sqrt(2))) / np.sqrt(2)**k
        return Complex(a=real, b=imag, generator=self.generator)
    
    def conjugate(self):
        pass
    
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
            
    def copy(self):
        return nTuple(elements=self.elements.copy(), n=self.n, generator=self.generator)

    def _coeffs(self):
        return self.elements

    def __add__(self, other):
        if self.generator is None:
            return nTuple(elements=self.elements + other.elements)
        else:
            return nTuple(elements=[f"(+ {self.elements[i]} {other.elements[i]})" for i in range(self.n)], n=self.n, generator=self.generator)

    def __sub__(self, other):
        if self.generator is None:
            return nTuple(elements=self.elements - other.elements)
        else:
            return nTuple(elements=[f"(- {self.elements[i]} {other.elements[i]})" for i in range(self.n)], n=self.n, generator=self.generator)

    def __mul__(self, other):
        elements = [0] * self.n
        for i in range(self.n):
            for j in range(other.n):
                target_index = (i + j) % self.n
                amplitude = self.elements[i] * other.elements[j]
                elements[target_index] += amplitude
        return nTuple(elements=elements, n=self.n, generator=self.generator)
    
    def __eq__(self, other):
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
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = f"(- 0 {self.elements[self.n - shifts + i]})"
            for i in range(shifts, self.n):
                elems[i] = f"{self.elements[i - shifts]}"
            return nTuple(elements=elems, n=self.n, generator=self.generator)
        
    def multiply_by_omega_counter(self, generator):
        # HERE omega is e^(ipi/4) -- T gate phase
        shifts = int(self.n/4) 
        # swap the sign of the first shifts numbers, shift to the left by shifts 
        if self.generator is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = -self.elements[i]
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
        else:
            return nTuple(elements=[f"(- 0 {self.elements[i]})" for i in range(self.n)], n=self.n, generator=self.generator)
        
    def divide_by_sqrt2(self, generator):
        if self.generator is None:
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
        for i in range(q):
            if symbolic:
                # Only create named symbolic elements if name is provided
                if name is not None:
                    if element_representation == nTuple:
                        self.vec.append(element_representation(name=f"{name}_{i}", n=n, generator=generator))
                    else:
                        self.vec.append(element_representation(name=f"{name}_{i}", generator=generator))
                else:
                    # If no name, create non-symbolic (literal) elements
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
    
    def __eq__(self, other):
        eqs = [self.vec[i] == other.vec[i] for i in range(len(self.vec))]
        # Also compare k if both vectors have it (for Cyclotomic8Dyadic)
        if self.k is not None and other.k is not None:
            eqs.append(f"(= {self.k} {other.k})")
        return f"(and {' '.join(eqs)})"
    
    def __repr__(self):
        return f"[{', '.join(str(v) for v in self.vec)}], k={self.k}"
    
    def copy(self):
        new_vec = Vector(q=len(self.vec), generator=self.generator, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].copy()
        new_vec.k = self.k
        return new_vec

    def to_real(self):
        assert self.element_representation == Cyclotomic8Dyadic
        new_vec = Vector(q=len(self.vec), generator=self.generator, element_representation=Complex, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].to_real(self.k)
        return new_vec
    
    def __len__(self):
        return len(self.vec)
    
    def __mul__(self, other):
        # inner product of two quantum states
        res = Vector(q=len(self.vec), generator=self.generator, element_representation=self.element_representation, k=self.k, n=self.n)
        i = 0
        while i < len(self.vec):
            res[i] = self.vec[i].conjugate(self.generator) * other.vec[i]
            i += 1
        return res