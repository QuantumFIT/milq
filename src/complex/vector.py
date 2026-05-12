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

    def to_real(self):
        if self.element_representation == Complex:
            return self
        name = None
        if self.name is not None:
            name = f"Rescaled_{self.name}"
        
        # convert all elements to the a+bj representation
        new_vec = Vector(q=len(self.vec), generator=self.gen, name=name, element_representation=Complex, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].to_real(self.k)
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
        k1 = self.k
        k2 = other.k
        diff = abs(k1 - k2)
        parity = diff % 2
        diff = diff // 2
        exponent = 2**diff
        if k1 > k2:
            # rescale other
            new_vec = other.copy()
            for i in range(len(new_vec)):
                if parity == 0:
                    # rescale by identity
                    new_vec[i] = other[i].multiply_by_real(exponent)

                else:
                    # rescale by M
                    new_vec[i].a = (other[i].b + other[i].d) * exponent
                    new_vec[i].b = (other[i].a + other[i].c) * exponent
                    new_vec[i].c = (other[i].b - other[i].d) * exponent
                    new_vec[i].d = (other[i].c - other[i].a) * exponent
            return self, new_vec
        elif k2 > k1:
            # rescale self
            new_vec = self.copy()
            for i in range(len(new_vec)):
                if parity == 0:
                    # rescale by identity
                    new_vec[i] = self[i].multiply_by_real(exponent)
                else:
                    # rescale by M
                    new_vec[i].a = (self[i].b + self[i].d) * exponent
                    new_vec[i].b = (self[i].a + self[i].c) * exponent
                    new_vec[i].c = (self[i].b - self[i].d) * exponent
                    new_vec[i].d = (self[i].c - self[i].a) * exponent
            return new_vec, other
        else:
            # same k, no rescaling
            return self, other
    
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
