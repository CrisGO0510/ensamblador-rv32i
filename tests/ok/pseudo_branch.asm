# Pseudoramas con cero y con operandos invertidos, hacia adelante y hacia atrás
back:   beqz a0, fwd
        bnez a1, fwd
        blez a2, fwd
        bgez a3, fwd
        bltz a4, fwd
        bgtz a5, fwd
        bgt  t0, t1, fwd
        ble  t2, s0, fwd
        bgtu s1, a6, fwd
        bleu a7, s2, fwd
fwd:    beqz a0, back
        bnez a1, back
        blez a2, back
        bgez a3, back
        bltz a4, back
        bgtz a5, back
        bgt  t0, t1, back
        ble  t2, s0, back
        bgtu s1, a6, back
        bleu a7, s2, back
