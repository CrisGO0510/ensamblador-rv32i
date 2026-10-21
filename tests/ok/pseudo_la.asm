# la y cargas/almacenamientos con símbolo hacia .text (antes y después) y .data
        .data
d0:     .word 1, 2, 3
d1:     .half 7
        .text
before: la   a0, before
        la   a1, after
        la   a2, d0
        la   a3, d1
        lw   t0, d0
        lb   t1, d1
        lh   t2, d0
        lbu  s0, after
        lhu  s1, before
        sw   a4, d0, t3
        sh   a5, d1, t4
        sb   a6, before, t5
        sw   x0, after, t6
after:  nop
