# Mayúsculas en mnemónicos y directivas, tabuladores, espacios raros, etiquetas y comentarios
	.GLOBL	main
	.TEXT

# solo comentario
main:
	ADDI	a0 ,  a0,	1
loop:   Beq a0,a1,end   # comentario

	  J	loop
end:	.globl end
	.DATA
v:  .WORD	1 ,2
	.Text
x:  LA a2, v
    nop
