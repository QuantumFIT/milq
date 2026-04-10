from .classic import Complex
from .fivetuple import FiveTuple
from .ntuple import nTuple
from .vector import Vector
from gates import GateSet
import numpy as np
from generator import Generator
class Matrix:
    # also implements density matrix interface for pauli basis synthesis
    def __init__(self, matrix: list = None, q=None, name=None, generator=None, element_representation=None, k=0, n=None, bound=None, k_bound=None):
        self.matrix = None
        self.gen = None
        self.k = 0
        self.size = 0
        self.n = n
        if matrix is not None:
            self.element_representation = type(matrix[0][0])
            self.matrix = matrix
            self.size = len(matrix)
            self.k = k
            return
        else:
            self.size = q
            if generator is None:
                self.element_representation = element_representation
                self.matrix = [[None for _ in range(q)] for _ in range(q)]
                for i in range(q):
                    for j in range(q):
                        if i == j:
                            self.matrix[i][j] = element_representation.one(generator)
                        else:
                            self.matrix[i][j] = element_representation.zero(generator)
                self.k = 0
                return
            
            self.gen = generator
            if element_representation is None:
                raise ValueError("element representation must be provided")
            self.element_representation = element_representation
            if element_representation == FiveTuple and k is None:
                raise ValueError("k must be provided for five-tuples")
            self.matrix = [[None for _ in range(q)] for _ in range(q)]
            if name is not None:
                for i in range(q):
                    for j in range(q):
                        indice = i * q + j
                        if element_representation == FiveTuple:
                            self.matrix[i][j] = element_representation(name=f"{name}_{indice}", n=n, generator=generator, bound=bound)
                        else: 
                            self.matrix[i][j] = element_representation(name=f"{name}_{indice}", generator=generator, bound=bound)
                self.k = generator.declare_integer(f"{name}_k", lb=0, ub=k_bound)
            else:
                self.matrix = Matrix.i(element_representation, qubits=int(np.log2(q)), target=0).matrix
                self.k = generator.format_integer(k)
        self.name = name
        self.generator = generator
        
    
    def __mul__(self, other):
        if isinstance(other, Vector):
            if other.element_representation == Complex:
                # U * vec
                new_vec = Vector(q=len(self.matrix), generator=other.gen, element_representation=other.element_representation, k=other.k)
                for i in range(len(self.matrix)):
                    sum = self.element_representation.zero(self.gen)
                    for j in range(len(self.matrix)):
                        sum = sum + self.matrix[i][j] * other[j]
                    new_vec[i] = sum
                return new_vec
            else:
                raise ValueError("matrix multiplication not supported for this representation")
        if isinstance(other, Matrix):
            # U * V
            new_matrix = Matrix(q=len(self.matrix), generator=self.gen, element_representation=self.element_representation, k=self.k)
            for i in range(len(self.matrix)):
                for j in range(len(other.matrix)):
                    sum = self.element_representation.zero(self.gen)
                    for k in range(len(self.matrix)):
                        sum = sum + self.matrix[i][k] * other.matrix[k][j]
                    new_matrix.matrix[i][j] = sum
            new_matrix.k = self.k + other.k
            return new_matrix
        
        if isinstance(other, float) or isinstance(other, int) or isinstance(other, Complex) or isinstance(other, FiveTuple) or isinstance(other, nTuple):
            # pointwise multiplication
            for i in range(len(self.matrix)):
                for j in range(len(self.matrix[i])):
                    self.matrix[i][j] = self.matrix[i][j] * other
            return self
        else:
            raise ValueError("matrix multiplication not supported for this representation")
        
    def __div__(self, other : float) -> "Matrix":
        if other == 0:
            raise ValueError("division by zero")
        return self * (1 / other)
    
    def __truediv__(self, other : float) -> "Matrix":
        return self * (1 / other)
    
    def __repr__(self):
        matrix_str = ""
        for i in range(len(self.matrix)):
            matrix_str += "["
            for j in range(len(self.matrix[i])):
                matrix_str += f"{self.matrix[i][j]}, "
            matrix_str += "]\n"
        return matrix_str
    
    def __add__(self, other : "Matrix") -> "Matrix":
        if isinstance(other, Matrix):
            new_matrix = Matrix(q=len(self.matrix), generator=self.gen, element_representation=self.element_representation, k=self.k)
            for i in range(len(self.matrix)):
                for j in range(len(other.matrix)):
                    new_matrix.matrix[i][j] = self.matrix[i][j] + other.matrix[i][j]
            return new_matrix
        else:
            raise ValueError("matrix addition not supported for this representation")
    
    def __sub__(self, other : "Matrix") -> "Matrix":
        if isinstance(other, Matrix):
            new_matrix = Matrix(q=len(self.matrix), generator=self.gen, element_representation=self.element_representation, k=self.k)
            for i in range(len(self.matrix)):
                for j in range(len(other.matrix)):
                    new_matrix.matrix[i][j] = self.matrix[i][j] - other.matrix[i][j]
            return new_matrix
        else:
            raise ValueError("matrix subtraction not supported for this representation")
        
    def dagger(self) -> "Matrix":
        # conjugate transpose
        return self.transpose().conjugate()
    
    def transpose(self) -> "Matrix":
        new_matrix = Matrix(q=len(self.matrix), generator=self.gen, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                new_matrix.matrix[j][i] = self.matrix[i][j]
        return new_matrix
    
    def conjugate(self) -> "Matrix":
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                self.matrix[i][j] = self.matrix[i][j].conjugate()
        return self
    
    def tensor(self, other : "Matrix") -> "Matrix":
        # U \otimes V
        new_matrix = Matrix(q=len(self.matrix) * len(other.matrix), generator=self.gen, element_representation=self.element_representation, k=self.k)
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                for k in range(len(other.matrix)):
                    for l in range(len(other.matrix[k])):
                        new_matrix.matrix[i * len(other.matrix) + k][j * len(other.matrix[k]) + l] = self.matrix[i][j] * other.matrix[k][l]
        new_matrix.k = self.k + other.k
        return new_matrix
    
    def copy(self) -> "Matrix":
        copied = []
        for i in range(len(self.matrix)):
            row = []
            for j in range(len(self.matrix[i])):
                elem = self.matrix[i][j]
                row.append(elem.copy() if hasattr(elem, "copy") else elem)
            copied.append(row)
        m = Matrix(copied)
        m.gen = self.gen
        m.k = self.k
        m.element_representation = self.element_representation
        m.qubits = getattr(self, "qubits", None)
        m.name = getattr(self, "name", None)
        m.generator = getattr(self, "generator", None)
        return m
    
    @classmethod
    def expand_to(cls, matrix: "Matrix", qubits: int = 1, target: int = 0) -> "Matrix":
        full_mat = None
        if target > qubits:
            raise ValueError("target is greater than qubits")
        if qubits > 1:
            identity = Matrix.i(matrix.element_representation, q=0, qubits=1)
            i = qubits
            while i != target + 1:
                if full_mat is None:
                    full_mat = identity
                else:
                    full_mat = Matrix.tensor(full_mat, identity)
                i -= 1
            if full_mat is None:
                full_mat = matrix
            else:
                full_mat = Matrix.tensor(full_mat, matrix)
            i = target - 1
            while i >= 0:
                if full_mat is None:
                    full_mat = identity
                else:
                    full_mat = Matrix.tensor(full_mat, identity)
                i -= 1
        else:
            return matrix
        return full_mat
    
    @classmethod
    def i(cls, element_representation=Complex, q: int = 0, qubits : int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        for i in range(2):
            for j in range(2):
                if i == j:
                    matrix[i][j] = element_representation.one(None)
                else:
                    matrix[i][j] = element_representation.zero(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def x(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.zero(None)
        matrix[0][1] = element_representation.one(None)
        matrix[1][0] = element_representation.one(None)
        matrix[1][1] = element_representation.zero(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def y(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.zero(None)
        matrix[0][1] = element_representation.one(None).multiply_by_minus_i(None)
        matrix[1][0] = element_representation.one(None).multiply_by_i(None)
        matrix[1][1] = element_representation.zero(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def z(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.one(None).multiply_by_minus_one(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def h(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None).divide_by_sqrt2(None)
        matrix[0][1] = element_representation.one(None).divide_by_sqrt2(None)
        matrix[1][0] = element_representation.one(None).divide_by_sqrt2(None)
        matrix[1][1] = element_representation.one(None).divide_by_sqrt2(None).multiply_by_minus_one(None)
        mat = cls(matrix=matrix)
        mat.k = 1
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def s(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.one(None).multiply_by_i(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def sdg(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.one(None).multiply_by_minus_i(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def t(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.one(None).multiply_by_omega(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def tdg(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.one(None).multiply_by_omega_counter(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def zero_projector(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.one(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.zero(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat
    
    @classmethod
    def one_projector(cls, element_representation=Complex, q: int = 0, qubits: int = 1) -> "Matrix":
        matrix = [[None for _ in range(2)] for _ in range(2)]
        matrix[0][0] = element_representation.zero(None)
        matrix[0][1] = element_representation.zero(None)
        matrix[1][0] = element_representation.zero(None)
        matrix[1][1] = element_representation.one(None)
        mat = cls(matrix=matrix)
        full_mat = Matrix.expand_to(matrix=mat, qubits=qubits, target=q)
        return full_mat

    @classmethod
    def cx(cls, element_representation=Complex, q1: int = 0, q2: int = 1, qubits: int = 2) -> "Matrix":
        n = 2 ** qubits
        one = element_representation.one(None)
        zero = element_representation.zero(None)

        matrix = [[zero for _ in range(n)] for _ in range(n)]
        for col in range(n):
            row = col ^ (1 << q2) if ((col >> q1) & 1) else col
            matrix[row][col] = one
        return cls(matrix=matrix)
    
    @classmethod
    def density_from_vector(cls, vector: Vector) -> "Matrix":
        # outer product of |psi><psi|
        n = len(vector)
        matrix = [[None for _ in range(n)] for _ in range(n)]
        for i in range(n):
            for j in range(n):
                matrix[i][j] = vector[i] * vector[j].conjugate()
        return cls(matrix=matrix)
    
    def max_value(self) -> int:
        max = 0
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                tmp = self.matrix[i][j].max_coefficient()
                if tmp > max:
                    max = tmp
        return max
    
    def __setitem__(self, indices : list, value):
        if isinstance(indices, int) or len(indices) == 1:
            if isinstance(indices, int):
                indice = indices
            else:
                indice = indices[0]
            i = indice // self.size
            j = indice % self.size
            self.matrix[i][j] = value
        elif len(indices) == 2:
            i = indices[0]
            j = indices[1]
            self.matrix[i][j] = value
        else:
            raise ValueError("matrix setitem with more than 2 indices not supported")
            
    def __getitem__(self, indices):
        if isinstance(indices, int) or len(indices) == 1:
            if isinstance(indices, int):
                indice = indices
            else:
                indice = indices[0]
            i = indice // self.size
            j = indice % self.size
            return self.matrix[i][j]
        elif len(indices) == 2:
            i = indices[0]
            j = indices[1]
            return self.matrix[i][j]
        else:
            raise ValueError("matrix getitem with more than 2 indices not supported")
        
    def __len__(self):
        return self.size * self.size
    
    def __iter__(self):
        for row in self.matrix:
            for elem in row:
                yield elem
                
    def multiply_by_omega(self) -> "Matrix":
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                self.matrix[i][j] = self.matrix[i][j].multiply_by_omega(None)
        return self
    
    def increase_k(self) -> "Matrix":
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                self.matrix[i][j] = self.matrix[i][j].increase_k(None)
        self.k = self.k + 1
        return self