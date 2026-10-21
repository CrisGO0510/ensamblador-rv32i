# Pseudosaltos j, jal, jr, jalr, ret, call y tail hacia adelante y hacia atrás
back:   j    fwd
        jal  fwd
        jr   a0
        jalr a1
        ret
        call fwd
        tail fwd
        nop
fwd:    j    back
        jal  back
        call back
        tail back
