OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
z q[1];
id q[0];
swap q[1],q[0];
z q[0];
