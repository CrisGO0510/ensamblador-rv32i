# Secciones .text y .data intercaladas con etiquetas en cada tramo
        .text
txt1:   la   a0, dat2
        .data
dat1:   .word 0x11111111
        .text
txt2:   la   a1, dat1
        j    txt1
        .data
dat2:   .byte 0x22
        .word txt2
        .text
txt3:   la   a2, txt3
