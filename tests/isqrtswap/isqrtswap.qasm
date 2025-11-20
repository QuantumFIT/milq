OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
z q[1];
z q[1];
id q[1];
isqrtswap q[1],q[0];
