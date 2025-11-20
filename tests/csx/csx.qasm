OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
csx q[0],q[1];
y q[0];
y q[0];
