#!/bin/bash

solvers=(z3 cvc5 yices2 opensmt smtinterpol z3alpha)
max_q=6
timeout=300

for q in $(seq 2 $max_q); do
    for solver in ${solvers[@]}; do
        echo "MOBV for $q qubits with $solver solver"
        k_glob=$((2*(q+1)))
        a=$((2**(q+1)))
        d=$((2*(q+1) + 1 + q))

        output=$(timeout $timeout python3 mobv.py $q $d $solver $k_glob $a)
        if [ $? -eq 124 ]; then
            echo "$q $solver TMOUT" >> res.out
        else
            echo "$q $solver $output" >> res.out
        fi
    done
done