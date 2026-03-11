import numpy as np
from generator import Generator


re = 1
im = 0

gen = Generator(mode="smtlib", solver="dreal")

a = gen.declare_integer("a")
b = gen.declare_integer("b")
c = gen.declare_integer("c")
d = gen.declare_integer("d")
k = gen.declare_integer("k")
sqrt2 = gen.declare_real("sqrt2")

gen.add_assertion(gen.GT(k, 0))
gen.add_assertion(gen.LT(k, 10))
gen.add_assertion(gen.GT(a, -10))
gen.add_assertion(gen.LT(a, 10))
gen.add_assertion(gen.Equals(re, gen.Div(gen.Plus(a, gen.Div(gen.Minus(b, d), sqrt2)), gen.Pow(sqrt2, k))))
gen.add_assertion(gen.Equals(im, gen.Div(gen.Plus(c, gen.Div(gen.Plus(b, d), sqrt2)), gen.Pow(sqrt2, k))))
gen.write_smtlib("test.smt2")