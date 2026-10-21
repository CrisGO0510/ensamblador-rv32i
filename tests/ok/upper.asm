# lui y auipc con 0, 1, 0xFFFFF, 0x80000 y 0x12345
        lui   a0, 0
        lui   a1, 1
        lui   a2, 0xFFFFF
        lui   a3, 0x80000
        lui   x31, 0x12345
        auipc t0, 0
        auipc t1, 1
        auipc t2, 0xFFFFF
        auipc s0, 0x80000
        auipc x0, 0x12345
