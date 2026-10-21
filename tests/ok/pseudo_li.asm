# li con valores de 12 bits, límites, solo lui y lui+addi con acarreo
        li a0, 0
        li a1, 10
        li a2, 2047
        li a3, 2048
        li a4, -2048
        li a5, -2049
        li a6, 0x12345000
        li a7, 0x12345FFF
        li t0, 0x7FFFFFFF
        li t1, 0x80000000
        li t2, 0xFFFFFFFF
        li s0, -1
        li s1, 0xFFFFF800
        li x31, 0xFFFFF7FF
