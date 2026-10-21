main:   li   a0, 10
        addi a0, a0, 5000
        add  a1, a1, a0
        sub  a2, a3
        nop
        bnez a0, nowhere
loop:   addi a0, a0, -1
        lw   a1, 0(x40)
loop:   nop
        and  a1, a2, a3
        div  a0, a1, a2
