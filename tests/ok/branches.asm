# Las 6 ramas tipo B hacia adelante y hacia atrás, a 4 bytes y a varias instrucciones
back:   beq  a0, a1, next1
next1:  bne  a2, a3, next2
next2:  blt  t0, t1, far
        bge  t2, s0, far
        bltu s1, a4, far
        bgeu a5, a6, far
        nop
far:    beq  x0, x31, back
        bne  a0, a1, far
        blt  a2, a3, back
        bge  a4, a5, next1
        bltu a6, a7, next2
        bgeu s2, s3, back
