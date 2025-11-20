OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
ch q[1],q[0];
swap q[0],q[1];
swap q[0],q[1];
