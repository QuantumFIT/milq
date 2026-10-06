"""
@file: vector.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: implementation of vector abstraction over the custom complex number representations
"""

import numpy as np
from .classic import Complex
from .ntuple import nTuple
from .fivetuple import FiveTuple

class Vector:
    def __init__(self, q, name=None, generator=None, element_representation=None, k=None, n=None, bound=None, k_bound=None):
        # q is number of elements
        if element_representation is None:
            raise ValueError("complex representation must be provided")
        
        self.element_representation = element_representation
        
        if element_representation == FiveTuple and k is None:
            raise ValueError("k must be provided for five-tuples")
        
        # k is stored in the vector (shared by all elements)
        if generator is not None:
            if (element_representation == FiveTuple or element_representation == nTuple) and k is not None:
                if name is not None:
                    self.k = generator.declare_integer(f"{name}_k", lb=0, ub=k_bound)
                else:
                    self.k = generator.format_integer(k)
            else:
                self.k = None
            self.gen = generator
        else:
            self.gen = None
            self.k = k
        
        self.n = n
        
        self.vec = []
        self.name = name
        self.bound = bound
        for i in range(q):
            if name is not None:
                if element_representation == nTuple:
                    self.vec.append(element_representation(name=f"{name}_{i}", n=n, generator=generator, bound=bound))
                else:
                    self.vec.append(element_representation(name=f"{name}_{i}", generator=generator, bound=bound))
            else:
                if element_representation == nTuple:
                    self.vec.append(element_representation.zero(generator, n=n, bound=bound))
                    
                else:
                    self.vec.append(element_representation.zero(generator, bound=bound))

    def __getitem__(self, i):
        return self.vec[i]
    
    def __setitem__(self, i, value):
        self.vec[i] = value
        
    def __eq__(self, other):
        if self.gen is None:
            return all(self.vec[i] == other.vec[i] for i in range(len(self.vec))) and self.k == other.k
        else:
            eqs = [self.vec[i] == other.vec[i] for i in range(len(self.vec))]
            if self.k is not None and other.k is not None:
                eqs.append(self.gen.Equals(self.k, other.k))
            return self.gen.And(*eqs)
    
    def __repr__(self):
        return f"[{', '.join(str(v) for v in self.vec)}], k={self.k}"
    
    def copy(self):
        new_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].copy()
        new_vec.k = self.k
        return new_vec

    def to_real(self, max_k=None):
        # convert all elements to the a+bi representation
        if self.element_representation == Complex:
            return self
        new_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=Complex)
        if self.gen is None:
            for i in range(len(self.vec)):
                new_vec[i] = self.vec[i].to_real(self.k)
            return new_vec

        # the elements share k, so sqrt(2)^k is built once, exactly: 2^(i//2), times sqrt2 for odd i
        if max_k is None:
            raise ValueError("max_k (an upper bound on k) must be provided with a generator")
        gen = self.gen
        sqrt2 = gen.declare_real("sqrt2")
        gen.add_assertion(gen.Equals(gen.Times(sqrt2, sqrt2), gen.Real(2)))
        gen.add_assertion(gen.GT(sqrt2, gen.Real(0)))
        sqrt2_k = gen.declare_real(f"sqrt2_k_{gen.stats['reals']}")
        gen.add_assertion(gen.LE(self.k, gen.Int(max_k)))
        for i in range(max_k + 1):
            power = gen.Real(2 ** (i // 2))
            if i % 2 == 1:
                power = gen.Times(power, sqrt2)
            gen.add_assertion(gen.Implies(gen.Equals(self.k, gen.Int(i)), gen.Equals(sqrt2_k, power)))
        for i in range(len(self.vec)):
            # to_real() without k gives the numerator, a + (b-d)/sqrt2 + (c + (b+d)/sqrt2)i
            new_vec[i] = self.vec[i].to_real().divide_by_real(sqrt2_k)
        return new_vec
    
    def conjugate(self, generator = None):
        new_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].conjugate()
        return new_vec
    
    def __len__(self):
        return len(self.vec)
    
    def __mul__(self, other) -> tuple[any, any]:
        if len(self.vec) == 0:
            raise ValueError("Vector is empty")
        if isinstance(other, tuple):
            max_k = other[1]
            other = other[0]
        gen = None
        if self.gen is not None:
            gen = self.gen
        if gen is None and other.gen is not None:
            gen = other.gen
        
        # inner product v1 * v2.conj()
        dot_product = self.vec[0] * other.vec[0].conjugate(gen)
        for i in range(1, len(self.vec)):
            dot_product = dot_product + self.vec[i] * other.vec[i].conjugate(gen)
        
        k = None
        if self.k is not None and other.k is not None:
            if self.gen is not None:
                k = self.gen.Plus(self.k, other.k)
            else:
                k = self.k + other.k
            
        if gen is None:
            return dot_product, k
        else:
            sum_var = self.element_representation(name=f"Dot_Product_{self.name}_{other.name}", generator=gen, bound=len(self) * self.bound * other.bound)
            self.gen.add_assertion(self.gen.Equals(sum_var, dot_product))
            return sum_var, k
    
    def max_value(self) -> int:
        # maximum coefficient in the vector
        max = 0
        for i in range(len(self.vec)):
            tmp = self.vec[i].max_coefficient()
            if tmp > max:
                max = tmp
        return max
    

    def rescale_with(self, other):
        # bring the vector with the smaller k to the larger k: multiply its elements by sqrt(2)^diff
        if self.gen is not None or other.gen is not None:
            # with a generator, k is a symbolic expression and diff is unknown at encoding time
            raise NotImplementedError("rescale_with is not supported with a generator")
        if self.k == other.k:
            return self, other
        low, high = (self, other) if self.k < other.k else (other, self)
        diff = high.k - low.k
        new_vec = low.copy()
        for i in range(len(new_vec)):
            new_vec[i] = low[i].multiply_by_real(2 ** (diff // 2))
            if diff % 2 == 1:
                # multiply by sqrt2 = omega - omega^3
                new_vec[i] = new_vec[i].increase_k(low.gen)
        new_vec.k = high.k
        return (new_vec, other) if low is self else (self, new_vec)
    
    def norm(self) -> float:
        # compute the L2 norm of the vector
        if self.gen is None:
            norm = 0
            for i in range(len(self.vec)):
                if self.element_representation == Complex:
                    norm = norm + self.vec[i].abs2()
                else:
                    norm = norm + self.vec[i].abs2(self.k)
            return np.sqrt(norm)
        else:
            raise ValueError("norm not supported for formulae generation")
    
    def measure(self, q : list[int], result : int) -> "Vector":
        # measure qubit q to result r in {0, 1}
        if len(q) == 0:
            return self
        new_vec = self.copy()
        if self.gen is not None:
            new_vec = Vector(q=len(self.vec), name=f"Projected_{self.name}", generator=self.gen, element_representation=self.element_representation, k=self.k)
        else:
            new_vec = Vector(q=len(self.vec), element_representation=self.element_representation, k=0)
        # first make the projection, zero out elements
        for pos in range(len(self.vec)):
            if any(pos & (1 << q_i) != (result << q_i) for q_i in q):
                # zero out
                if self.gen is None:
                    new_vec[pos] = self.element_representation.zero(self.gen)
                else:
                    self.gen.add_assertion(new_vec[pos] == self.element_representation.zero(None))
            else:
                if self.gen is None:
                    new_vec[pos] = self.vec[pos]
                else:
                    self.gen.add_assertion(new_vec[pos] == self.vec[pos])
                
        if self.gen is None:
            # also normalize the vector
            norm = new_vec.norm()
            if norm != 0:
                for i in range(len(new_vec)):
                    new_vec[i] = new_vec[i] / norm 
        return new_vec

    def expand_to(self, q : int) -> "Vector":
        # expand the vector to a certain number of qubits
        if 2**q < len(self.vec):
            raise ValueError("vector already longer than desired length")
        
        items_to_add = 2**q - len(self.vec)
        for i in range(items_to_add):
            self.vec.append(self.element_representation.zero(self.gen))
        return self

    def normalize(self) -> "Vector":
        # normalize to unit length
        if self.gen is None:
            norm = self.norm()
            if norm != 0:
                for i in range(len(self.vec)):
                    self.vec[i] = self.vec[i] / norm
            return self
        else:
            raise ValueError("normalize not supported for formulae generation")
        
    def to_precision(self, prec : float) -> "Vector":
        new_vec = self.copy()
        if self.gen is None:
            for i in range(len(new_vec)):
                new_vec[i] = self.vec[i].to_precision(prec)
            return new_vec
        else:
            raise ValueError("to_precision not supported for formulae generation")
        
    def __iter__(self):
        for elem in self.vec:
            yield elem
            
    def multiply_by_real(self, real):
        # scalar multiplication
        new_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=self.element_representation, k=self.k, n=self.n, name=f"Multiplied_by_real_{self.name}", bound=1.0)
        for i in range(len(self.vec)):
            self.gen.add_assertion(new_vec[i] == self.vec[i].multiply_by_real(real))
        return new_vec
    
    def multiply_by_complex(self, complex):
        # complex number multiplication
        new_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=self.element_representation, k=self.k, n=self.n, name=f"Multiplied_by_complex_{self.name}", bound=1.0)
        for i in range(len(self.vec)):
            self.gen.add_assertion(new_vec[i] == self.vec[i] * complex)
        return new_vec
    
    @classmethod
    def dot(cls, vec1 : "Vector", vec2 : "Vector", max_k=None) -> "Vector":
        return vec1 * (vec2, max_k)
