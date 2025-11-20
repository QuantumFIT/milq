OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
xcx q[1],q[0];
s q[0];
z q[0];
s q[0];
