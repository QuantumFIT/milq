"""Concrete unitaries (src/complex/matrix.py), checked against NumPy."""

import numpy as np
import pytest

from conftest import OMEGA, unitary
from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.matrix import Matrix
from complex.vector import Vector
from generator import Generator
from sim import Simulator

REPRESENTATIONS = [Complex, FiveTuple]


def to_numpy(matrix):
    if matrix.element_representation is FiveTuple:
        # the matrix shares one k: every element is (a + b w + c w^2 + d w^3) / sqrt(2)^k
        return np.array([[e.a + e.b * OMEGA + e.c * OMEGA**2 + e.d * OMEGA**3 for e in row] for row in matrix.matrix]) / np.sqrt(2) ** matrix.k
    return np.array([[e.real + 1j * e.imag for e in row] for row in matrix.matrix])


def basis_vector(index, size=2):
    vector = Vector(q=size, generator=None, element_representation=Complex, k=0)
    vector[index] = Complex.one(None)
    return vector


H = np.array([[1, 1], [1, -1]]) / np.sqrt(2)
X = np.array([[0, 1], [1, 0]])
Z = np.diag([1, -1])
CX = np.array([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]])  # control q[0], target q[1]


@pytest.mark.parametrize("representation", REPRESENTATIONS)
@pytest.mark.parametrize("qubits, body", [
    (1, "x q[0];\ny q[0];\nz q[0];\nh q[0];\ns q[0];\nsdg q[0];\nt q[0];\ntdg q[0];\nh q[0];\nt q[0];\n"),
    (2, "h q[1];\ncx q[1], q[0];\nt q[0];\ncz q[0], q[1];\nh q[0];\ns q[1];\n"),
    (3, "h q[0];\nh q[2];\nccx q[0], q[2], q[1];\nt q[1];\ncx q[2], q[0];\nh q[1];\n"),
])
def test_simulate_matrix(workdir, representation, qubits, body):
    with open("in.qasm", "w") as f:
        f.write(f"OPENQASM 2.0;\nqreg q[{qubits}];\n" + body)
    matrix = Simulator("in.qasm", complex_representation=representation).simulate_matrix()
    assert matrix.qubits == qubits
    np.testing.assert_allclose(to_numpy(matrix), unitary("in.qasm"), atol=1e-9)


@pytest.mark.parametrize("representation", REPRESENTATIONS)
def test_gates_on_a_qubit_of_a_larger_system(representation):
    # q[0] is the least significant bit, so a gate on q[0] is the rightmost factor
    np.testing.assert_allclose(to_numpy(Matrix.h(representation, q=0, qubits=2)), np.kron(np.eye(2), H), atol=1e-9)
    np.testing.assert_allclose(to_numpy(Matrix.h(representation, q=1, qubits=2)), np.kron(H, np.eye(2)), atol=1e-9)
    np.testing.assert_allclose(to_numpy(Matrix.x(representation, q=1, qubits=3)), np.kron(np.eye(2), np.kron(X, np.eye(2))))
    np.testing.assert_allclose(to_numpy(Matrix.i(representation, qubits=2)), np.eye(4))


@pytest.mark.parametrize("representation", REPRESENTATIONS)
def test_projectors(representation):
    np.testing.assert_allclose(to_numpy(Matrix.zero_projector(representation)), np.diag([1, 0]))
    np.testing.assert_allclose(to_numpy(Matrix.one_projector(representation, q=1, qubits=2)), np.diag([0, 0, 1, 1]))


def test_expand_to_rejects_a_target_outside_the_system():
    with pytest.raises(ValueError, match="target must be less than qubits"):
        Matrix.expand_to(Matrix.x(), qubits=1, target=1)


def test_products():
    np.testing.assert_allclose(to_numpy(Matrix.h() * Matrix.x()), H @ X, atol=1e-9)
    np.testing.assert_allclose(to_numpy(Matrix.h().tensor(Matrix.cx())), np.kron(H, CX), atol=1e-9)
    product = Matrix.h() * basis_vector(1)
    np.testing.assert_allclose([product[i].real for i in range(2)], H[:, 1], atol=1e-9)


def test_product_with_a_five_tuple_vector_is_rejected():
    with pytest.raises(ValueError, match="matrix multiplication not supported"):
        Matrix.h(FiveTuple) * Vector(q=2, generator=None, element_representation=FiveTuple, k=0)
    with pytest.raises(ValueError, match="matrix multiplication not supported"):
        Matrix.h() * "U"


def test_scalar_operations():
    np.testing.assert_allclose(to_numpy(Matrix.x() * 2), 2 * X)
    np.testing.assert_allclose(to_numpy(Matrix.x() / 2), X / 2)
    with pytest.raises(ValueError, match="division by zero"):
        Matrix.x().__div__(0)
    np.testing.assert_allclose(to_numpy(Matrix.x().__div__(4)), X / 4)


def test_scalar_operations_return_a_new_matrix():
    # #82, F60: H * 2 and S.conjugate() used to overwrite their operand
    h, s = Matrix.h(), Matrix.s()
    assert (h * 2) is not h and s.conjugate() is not s
    np.testing.assert_allclose(to_numpy(h), H, atol=1e-9)
    np.testing.assert_allclose(to_numpy(s), np.diag([1, 1j]), atol=1e-9)


def test_five_tuple_scalar_operations():
    # #82, F60: FiveTuple * int used to raise AttributeError
    h = Matrix.h(FiveTuple)
    np.testing.assert_allclose(to_numpy(h * 2), 2 * H, atol=1e-9)
    np.testing.assert_allclose(to_numpy(h), H, atol=1e-9)
    with pytest.raises(ValueError, match="only by an integer"):
        h / 2


def test_five_tuple_matrices_keep_k():
    # #82, F26: transpose, dagger, + and - of a matrix with k = 2 used to return k = 0
    u = Matrix.h(FiveTuple) * Matrix.t(FiveTuple) * Matrix.h(FiveTuple)
    expected = H @ np.diag([1, OMEGA]) @ H
    np.testing.assert_allclose(to_numpy(u.transpose()), expected.T, atol=1e-9)
    np.testing.assert_allclose(to_numpy(u.dagger()), expected.conj().T, atol=1e-9)
    np.testing.assert_allclose(to_numpy(u + u), 2 * expected, atol=1e-9)
    np.testing.assert_allclose(to_numpy(u + u - u), expected, atol=1e-9)
    with pytest.raises(ValueError, match="different k"):
        u + Matrix.x(FiveTuple)


def test_sum_and_difference():
    np.testing.assert_allclose(to_numpy(Matrix.x() + Matrix.z()), X + Z)
    np.testing.assert_allclose(to_numpy(Matrix.x() - Matrix.z()), X - Z)
    with pytest.raises(ValueError, match="matrix addition not supported"):
        Matrix.x() + 1
    with pytest.raises(ValueError, match="matrix subtraction not supported"):
        Matrix.x() - 1


def test_dagger_inverts_unitaries():
    for gate in ("h", "s", "t", "y"):
        u = getattr(Matrix, gate)()
        np.testing.assert_allclose(to_numpy(u.copy().dagger() * u), np.eye(2), atol=1e-9)
    y = np.array([[0, -1j], [1j, 0]])
    np.testing.assert_allclose(to_numpy(Matrix.y().transpose()), y.T)


def test_copy_is_independent():
    h = Matrix.h()
    copy = h.copy()
    copy.conjugate()
    copy[0, 0] = Complex(0, 0)
    assert copy.k == h.k
    np.testing.assert_allclose(to_numpy(h), H, atol=1e-9)


def test_indexing():
    cx = Matrix.cx()
    assert len(cx) == 16
    assert [e.real for e in cx] == list(CX.flatten())
    assert cx[1, 3].real == 1      # row, column
    assert cx[7].real == 1         # flat index: row 1, column 3
    assert cx[(7,)].real == 1
    cx[0] = Complex(2, 0)
    cx[(1,)] = Complex(3, 0)
    cx[1, 1] = Complex(4, 0)
    assert (cx[0, 0].real, cx[0, 1].real, cx[1, 1].real) == (2, 3, 4)
    with pytest.raises(ValueError, match="getitem with more than 2 indices"):
        cx[0, 1, 2]
    with pytest.raises(ValueError, match="setitem with more than 2 indices"):
        cx[0, 1, 2] = Complex(0, 0)


def test_density_from_vector():
    plus = Matrix.h() * basis_vector(0)
    np.testing.assert_allclose(to_numpy(Matrix.density_from_vector(plus)), np.full((2, 2), 0.5), atol=1e-9)


def test_density_from_vector_keeps_fivetuple_scale():
    # #82, F59: |+> = (1, 1) / sqrt(2)^1, so |+><+| = (1, 1; 1, 1) / sqrt(2)^2
    plus = Vector(q=2, element_representation=FiveTuple, k=1)
    plus[0], plus[1] = FiveTuple.one(None), FiveTuple.one(None)
    density = Matrix.density_from_vector(plus)
    assert density.k == 2
    np.testing.assert_allclose(to_numpy(density), np.full((2, 2), 0.5), atol=1e-9)


def test_five_tuple_helpers():
    matrix = Matrix.x(FiveTuple).multiply_by_omega()
    np.testing.assert_allclose(to_numpy(matrix), OMEGA * X, atol=1e-9)
    assert matrix.max_value() == 1
    # increase_k keeps the value: the numerators are multiplied by sqrt(2) as k grows
    matrix.increase_k()
    assert matrix.k == 1
    np.testing.assert_allclose(to_numpy(matrix), OMEGA * X, atol=1e-9)


def test_repr():
    assert repr(Matrix.x()) == "[(0 + 0j), (1 + 0j), ]\n[(1 + 0j), (0 + 0j), ]\nk=0"


def test_matrix_of_variables():
    generator = Generator()
    generator.mode = "smtlib"
    matrix = Matrix(q=2, generator=generator, element_representation=Complex, name="U", k_bound=4)
    assert matrix.qubits == 1
    assert len({str(e) for e in matrix}) == 4  # one variable per element
    with pytest.raises(ValueError, match="element representation must be provided"):
        Matrix(q=2, generator=generator)
    with pytest.raises(ValueError, match="k must be provided for five-tuples"):
        Matrix(q=2, generator=generator, element_representation=FiveTuple, k=None, name="V")
