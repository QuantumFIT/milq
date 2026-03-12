from .classic import Complex
from .fivetuple import FiveTuple
from .ntuple import nTuple
from .vector import Vector
import numpy as np

class Matrix:
    def __init__(self, matrix: np.array):
        self.matrix = [[None for _ in range(matrix.shape[1])] for _ in range(matrix.shape[0])] 
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                real_part = np.real(matrix[i, j])
                imag_part = np.imag(matrix[i, j])
                self.matrix[i][j] = Complex(a=real_part, b=imag_part)
        self.qubits = int(np.log2(matrix.shape[0]))
        
        
    
    def __mul__(self, other : Vector) -> Vector:
        if isinstance(other, Vector):
            if other.element_representation == Complex:
                # U * vec
                new_vec = Vector(q=len(self.matrix), generator=other.gen, element_representation=other.element_representation, k=other.k)
                for i in range(len(self.matrix)):
                    sum = Complex(a=0, b=0)
                    for j in range(len(self.matrix)):
                        sum = sum + self.matrix[i][j] * other[j]
                    new_vec[i] = sum
                return new_vec
            else:
                raise ValueError("matrix multiplication not supported for this representation")
        if isinstance(other, Matrix):
            # U * V
            new_matrix = Matrix(np.zeros((len(self.matrix), len(other.matrix))))
            for i in range(len(self.matrix)):
                for j in range(len(other.matrix)):
                    sum = Complex(a=0, b=0)
                    for k in range(len(self.matrix)):
                        sum = sum + self.matrix[i][k] * other.matrix[k][j]
                    new_matrix.matrix[i][j] = sum
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
            new_matrix = Matrix(np.zeros((len(self.matrix), len(other.matrix))))
            for i in range(len(self.matrix)):
                for j in range(len(other.matrix)):
                    new_matrix.matrix[i][j] = self.matrix[i][j] + other.matrix[i][j]
            return new_matrix
        else:
            raise ValueError("matrix addition not supported for this representation")
    
    def __sub__(self, other : "Matrix") -> "Matrix":
        if isinstance(other, Matrix):
            new_matrix = Matrix(np.zeros((len(self.matrix), len(other.matrix))))
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
        new_matrix = Matrix(np.zeros((len(self.matrix), len(self.matrix[0]))))
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
        new_matrix = Matrix(np.zeros((len(self.matrix) * len(other.matrix), len(self.matrix[0]) * len(other.matrix[0]))))
        for i in range(len(self.matrix)):
            for j in range(len(self.matrix[i])):
                for k in range(len(other.matrix)):
                    for l in range(len(other.matrix[k])):
                        new_matrix.matrix[i * len(other.matrix) + k][j * len(other.matrix[k]) + l] = self.matrix[i][j] * other.matrix[k][l]
        return new_matrix
    
    @classmethod
    def i(cls) -> "Matrix":
        return cls(np.eye(2))
    
    @classmethod
    def x(cls) -> "Matrix":
        return cls(np.array([[0, 1], [1, 0]]))
    
    @classmethod
    def y(cls) -> "Matrix":
        return cls(np.array([[0, -1j], [1j, 0]]))
    
    @classmethod
    def z(cls) -> "Matrix":
        return cls(np.array([[1, 0], [0, -1]]))
    
    @classmethod
    def h(cls) -> "Matrix":
        return cls(np.array([[1, 1], [1, -1]]) / np.sqrt(2))