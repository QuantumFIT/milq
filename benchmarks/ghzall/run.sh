#!/bin/bash

solvers=(z3 cvc5 yices2 opensmt smtinterpol z3alpha)
max_q=6
timeout=300

for q in $(seq 1 $max_q); do
    for solver in ${solvers[@]}; do
        echo "GHZ-zero for $q qubits with $solver solver"
        d=$q
        
        output=$(timeout $timeout python3 ghz.py $q $d $solver)
        if [ $? -eq 124 ]; then
            echo "$q $solver TMOUT" >> res.out
        else
            echo "$q $solver $output" >> res.out
        fi
    done
done