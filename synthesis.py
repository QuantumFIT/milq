import numpy as np

def Lift(C):
    # use lift on every gate
    pass # TODO
    
def Lift_gate(g):
    # if g is Pauli, do Lambda(g), otherwise, do I kron g
    pass # TODO
    
def Lambda(G):
    # return controlled version of G
    pass # TODO

def synthesis(U):
    # represent U as g1 * c_1 * g2
    # represent U^dg as g3 * c_2 * g4
    # c_2 is decoration of Tcode c_1
    pass # TODO