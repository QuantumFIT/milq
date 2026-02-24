from .classic import Complex
from .ntuple import nTuple
from .fivetuple import FiveTuple

class Vector:
    def __init__(self, q, name=None, generator=None, element_representation=None, k=None, n=None):
        if element_representation is None:
            raise ValueError("complex representation must be provided")
        
        self.element_representation = element_representation
        
        if element_representation == FiveTuple and k is None:
            raise ValueError("k must be provided for five-tuples")
        
        # k is stored in the vector (shared by all elements)
        if generator is not None:
            if (element_representation == FiveTuple or element_representation == nTuple) and k is not None:
                if name is not None:
                    self.k = generator.declare_integer(f"{name}_k")
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
        for i in range(q):
            if name is not None:
                if element_representation == nTuple:
                    self.vec.append(element_representation(name=f"{name}_{i}", n=n, generator=generator))
                else:
                    self.vec.append(element_representation(name=f"{name}_{i}", generator=generator))
            else:
                if element_representation == nTuple:
                    self.vec.append(element_representation.zero(generator, n=n))
                    
                else:
                    self.vec.append(element_representation.zero(generator))

    def __getitem__(self, i):
        return self.vec[i]
    
    def __setitem__(self, i, value):
        self.vec[i] = value
        
    def __eq__(self, other):
        if self.gen is None:
            return all(self.vec[i] == other.vec[i] for i in range(len(self.vec))) and self.k == other.k
        else:
            if self.k is None or other.k is None:
                raise ValueError("k must be provided for vectors")
            
            eqs = [self.vec[i] == other.vec[i] for i in range(len(self.vec))]
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
                    
        new_vec = Vector(q=len(self.vec), generator=self.gen, name=name, element_representation=Complex, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].to_real(self.k)
        return new_vec
    
    def conjugate(self):
        new_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.vec)):
            new_vec[i] = self.vec[i].conjugate()
        return new_vec
    
    def __len__(self):
        return len(self.vec)
    
    def __mul__(self, other) -> tuple[any, any]:
        if len(self.vec) == 0:
            raise ValueError("Vector is empty")
        if self.gen is None:
            sum = self.vec[0] * other.vec[0]
            for i in range(1, len(self.vec)):
                sum = sum + self.vec[i] * other.vec[i]
            return sum, self.k + other.k
        else:
            dot_vec = Vector(q=len(self.vec), generator=self.gen, element_representation=self.element_representation, k=self.k, n=self.n, name=f"Dot_Product")
            for i in range(len(self.vec)):
                self.gen.add_assertion(dot_vec[i] == self.vec[i] * other.vec[i])
            sum_var = self.element_representation(name=f"Dot_Sum", generator=self.gen)
            sum = dot_vec[0]
            for i in range(1, len(dot_vec)):
                sum = sum + dot_vec[i]
            self.gen.add_assertion(sum_var == sum)
            k_final = self.gen.Plus(self.k, other.k)
            if self.element_representation == FiveTuple or self.element_representation == nTuple:
                self.gen.add_assertion(self.gen.Equals(dot_vec.k, k_final))
            # because multiplication does not need rescaling (it scales to k1 + k2), and k is shared by all elements of a vector
            # the k of the result is the sum of k's of the vectors
            return sum_var, k_final