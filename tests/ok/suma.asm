# Suma 10 + 9 + ... + 1 en a1
        .text
main:   li   a0, 10        # contador
        li   a1, 0         # acumulador
loop:   beqz a0, end
        add  a1, a1, a0
        addi a0, a0, -1
        j    loop
end:    j    end
