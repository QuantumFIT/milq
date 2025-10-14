from mpmath import *
import numpy as np
import random
import gates as qg

def initial_approximation(theta, epsilon):
    z = None
    omega = np.exp(1j * np.pi/4)
    maxcoeff = 5000
    maxsteps = 200
    while z is None:
        relation_vector = [(np.cos(theta/2) - np.sin(theta/2)), (np.sqrt(2) * np.cos(theta/2)), (np.cos(theta/2) + np.sin(theta/2)), (np.sqrt(2) * np.sin(theta/2))]
        res = pslq(relation_vector, tol=epsilon, maxsteps=maxsteps, maxcoeff=maxcoeff)
        assert(res is not None)
        assert(len(res) == 4)
        # a * omega^3 + b * omega^2 + c * omega + d
        print(res)
        z_tilde = res[0] * np.pow(omega, 3) + res[1] * np.pow(omega, 2) + res[2] * omega + res[3]
        if np.abs((np.conj(z_tilde)/z_tilde) - np.exp(1j * theta)) < epsilon:
            z = z_tilde
    return z

def channel_representation(matrix):
    P = [qg.I, qg.X, qg.Y, qg.Z]
    U_hat = None
    i = 0
    j = 0
    for row in matrix:
        for col in row:
            for gate in P:
                return # TODO
                
            
            
    
    return None # TODO

def sde_single(entry):
    return np.inf # TODO

def sde(U_hat):
    max_sde = 0
    for row in U_hat:
        for entry in row:
            sde_v = sde_single(entry)
            if sde_v > max_sde:
                max_sde = sde_v
    return max_sde

def Tcount(matrix):
    qubits = np.ceil(np.log2(matrix.shape[0]))
    U_hat = channel_representation(matrix)
    T = sde(U_hat)
    return T

def eq_is_easily_solvable(L_r_tilde, r_tilde, z):
    return None, True # TODO

def generate_S_delta(sz, delta, L1):
    S_delta = []
    bound = 100000
    a = -bound
    b = -bound
    while a <= bound:
        while b <= bound:
            num = a + np.sqrt(2)*b
            if np.abs(num) <= np.pow(2, delta*(L1/2)):
                S_delta.append(num)
            b += 1
        a += 1
    return S_delta
    
def find_modifier(z, sz, delta):
    L1 = np.ceil(np.log2(np.pow(np.abs(z), 2)))
    cnt = 0
    r, y = None, None
    Tc = np.inf
    S_delta = generate_S_delta(sz, delta, L1)
    print(len(S_delta))
    while cnt <= sz*delta*np.pow(L1, 2):
        r_tilde = random.sample(S_delta, 1)[0]
        L_r_tilde = np.ceil(np.log2(np.pow(np.abs(r_tilde*z), 2)))
        y_tilde, solvable = eq_is_easily_solvable(L_r_tilde, r_tilde, z)
        if solvable:
            assert(y_tilde is not None)
            p = (np.pow(np.abs(r_tilde*z), 2)) / (np.pow(2, L_r_tilde) * r_tilde)
            matrix = 1/(np.pow(np.sqrt(2), L_r_tilde)) * np.array([[z, y_tilde], [-np.conj(y_tilde), np.conj(z)]])
            tc = Tcount(matrix)/p
            if tc < Tc:
                y = y_tilde
                r = r_tilde
                Tc = tc
        cnt += 1
    return r, y

def generate_unitary(theta, epsilon, sz, delta, z):
    U = None
    epsilon = 2*epsilon
    while U is None:
        epsilon = epsilon/2
        r, y = find_modifier(z, sz, delta)
        if r is not None and y is not None:
            L = np.ceil(np.log2(np.pow(np.abs(r*z), 2) + np.pow(np.abs(y), 2)))
            matrix = np.array([[r*z, y], [-np.conj(y), np.conj(r*z)]])
            U = (1/np.pow(np.sqrt(2), L)) * matrix
            
    return U
