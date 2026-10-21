# .word tras .string y .half tras .byte quedan sin alinear
        .data
s:      .string "hi"
w:      .word 0x11223344
b:      .byte 0xAB
h:      .half 0x5566
        .text
main:   la   a0, w
        la   a1, h
