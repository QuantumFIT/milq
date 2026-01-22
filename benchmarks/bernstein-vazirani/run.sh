#!/bin/bash

solvers=(dreal)
max_q=6
timeout=300

for q in $(seq 2 $max_q); do
    for solver in ${solvers[@]}; do
        echo "BV for $q qubits with $solver solver"
        k_glob=$((2*q))
        a=$((2**q))
        d=$((2*q + 1 + (q / 2)))
        s=""
        for ((i=0; i<q; i++)); do
            if (( i % 2 == 0 )); then
                s+="1"
            else
                s+="0"
            fi
        done
        if (( q % 2 == 0 )); then
            s="${s:0:$((q-1))}1"
        fi
        
        output=$(timeout $timeout python3 bv.py $q $d $solver "$s" $k_glob $a)
        if [ $? -eq 124 ]; then
            echo "$q $solver TMOUT" >> res.out
        else
            echo "$q $solver $output" >> res.out
        fi
    done
done