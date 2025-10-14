import synthesis as synth
import matrix_design as mat
import numpy as np
import sys

if __name__ == "__main__":
    theta = np.pi/64
        
    # hyperparameter specification
        
    sz = 1
    delta = 1
    epsilon = 1e-12
    # -----
    z = mat.initial_approximation(theta, epsilon)
    U = mat.generate_unitary(theta, epsilon, sz, delta, z)
    synth.synthesis(U)

    
    