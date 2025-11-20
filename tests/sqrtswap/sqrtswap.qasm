OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
id q[0];
z q[0];
z q[0];
sqrtswap q[0],q[1];
