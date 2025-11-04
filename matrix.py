from complex_numbers import Complex, ComplexVector
import numpy as np

class Matrix:
    def __init__(self, q, symbolic=True, name=None):
        self.mat = []
        for i in range(q):
            for j in range(q):
                if symbolic:
                    self.mat.append(Complex(name=f"{name}[{i},{j}]"))
                else:
                    self.mat.append(Complex(0,0))
    def __getitem__(self,i,j):
        return self.mat[i][j]
    def __setitem__(self,i,j,value):
        self.mat[i][j] = value
        
    