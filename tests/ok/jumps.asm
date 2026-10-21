# jal con rd hacia adelante y atrás, y las formas de jalr
start:  jal  ra, fwd
        jal  t0, start
        jalr t1, 8(a0)
        jalr t2, a1, -4
        jalr a2
        jalr a3, (a4)
        jalr x0, 2047(x31)
fwd:    jal  x0, start
        jal  a5, fwd
