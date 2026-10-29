# .word/.half/.byte/.string con escapes y separadores dentro, .word etiqueta, y la sobre ellos
        .data
w:      .word 1, 2147483647, -1, 0xFFFFFFFF
h:      .half 1, -1, 0xFFFF, 0x1234
b:      .byte 1, 2, 3, -1, 0xFF
s:      .string "a#b,c\n\t\"q\"\\ AA"
p:      .word w, s, main
        .text
main:   la   a0, w
        la   a1, h
        la   a2, b
        la   a3, s
        la   a4, p
