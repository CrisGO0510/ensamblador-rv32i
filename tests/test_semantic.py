import unittest
from typing import Final, TypeAlias

from rvasm.lexer import tokenize
from rvasm.model import AsmError, Diagnostic, Fixup, Instr, Reloc, Statement, Unit
from rvasm.parser import parse
from rvasm.semantic import analyze

InstrView: TypeAlias = tuple[str, int, int, int, int, Reloc | None]

DRAWING: Final[str] = """.data
n:   .word 5
msg: .string "hi"
.text
main: la   a0, msg
      lw   a1, n
      li   a2, 0x12345FFF
loop: beqz a1, end
      j    loop
end:  j    end"""

SUMA: Final[str] = """main: li a0, 10
      li a1, 0
loop: beqz a0, end
      add a1, a1, a0
      addi a0, a0, -1
      j loop
end:  j end"""


def stmts(text: str) -> list[Statement | None]:
    lines: list[str] = text.split("\n")
    out: list[Statement | None] = []
    number: int
    for number in range(len(lines)):
        try:
            out.append(parse(number + 1, tokenize(lines[number])))
        except AsmError:
            out.append(None)
    return out


def run(text: str) -> Unit:
    return analyze(stmts(text))


def view(instr: Instr) -> InstrView:
    return (instr.mnem, instr.rd, instr.rs1, instr.rs2, instr.imm, instr.reloc)


class LayoutTest(unittest.TestCase):
    def test_drawing_example(self) -> None:
        # Arrange
        text: str = DRAWING

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.symtab, {"n": 0x10000000, "msg": 0x10000004, "main": 0, "loop": 0x18, "end": 0x20})
        self.assertEqual(bytes(unit.data), bytes([5, 0, 0, 0, 0x68, 0x69, 0]))
        self.assertEqual([i.addr for i in unit.instrs], list(range(0, 0x24, 4)))
        self.assertEqual(
            [i.mnem for i in unit.instrs], ["auipc", "addi", "auipc", "lw", "lui", "addi", "beq", "jal", "jal"]
        )
        self.assertEqual((unit.instrs[4].imm, unit.instrs[5].imm), (0x12346, -1))
        self.assertEqual(
            (unit.instrs[6].rs1, unit.instrs[6].rs2, unit.instrs[6].reloc), (11, 0, Reloc("pcrel", "end", 0x18))
        )
        self.assertEqual(unit.instrs[0].reloc, Reloc("hi", "msg", 0))
        self.assertEqual(
            (unit.instrs[1].reloc, unit.instrs[1].rd, unit.instrs[1].rs1), (Reloc("lo", "msg", 0), 10, 10)
        )
        self.assertEqual(unit.instrs[3].reloc, Reloc("lo", "n", 8))
        self.assertEqual(unit.errors, [])
        self.assertTrue(unit.layout_ok)

    def test_suma(self) -> None:
        # Arrange
        text: str = SUMA

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(len(unit.instrs), 7)
        self.assertEqual(unit.symtab, {"main": 0, "loop": 8, "end": 0x18})
        self.assertEqual(unit.errors, [])

    def test_interleaved_sections(self) -> None:
        # Arrange
        text: str = "nop\n.data\n.byte 1\n.text\nnop\n.data\nx: .byte 2"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual([i.addr for i in unit.instrs], [0, 4])
        self.assertEqual(bytes(unit.data), b"\x01\x02")
        self.assertEqual(unit.symtab["x"], 0x10000001)

    def test_no_alignment(self) -> None:
        # Arrange
        text: str = '.data\n.string "hi"\nx: .word 1'

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.symtab["x"], 0x10000003)
        self.assertEqual(bytes(unit.data), b"hi\0\x01\0\0\0")

    def test_word_label_adds_fixup(self) -> None:
        # Arrange
        text: str = ".data\n.byte 1\n.word etiqueta"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.fixups, [Fixup(3, 1, "etiqueta")])
        self.assertEqual(bytes(unit.data), b"\x01\0\0\0\0")

    def test_string_is_utf8_with_terminator(self) -> None:
        # Arrange
        text: str = '.data\n.string "ñ, #"'

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(bytes(unit.data), "ñ, #".encode() + b"\0")
        self.assertEqual(unit.errors, [])

    def test_data_values_are_masked_little_endian(self) -> None:
        # Arrange
        text: str = ".data\n.byte -1, 255\n.half -2\n.word -1, 0x12345678"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(bytes(unit.data), b"\xff\xff\xfe\xff\xff\xff\xff\xff\x78\x56\x34\x12")

    def test_globl_is_ignored(self) -> None:
        # Arrange
        text: str = ".globl main\n.global main\nmain: nop"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.errors, [])
        self.assertEqual(unit.symtab, {"main": 0})
        self.assertEqual(len(unit.instrs), 1)


class ExpansionTest(unittest.TestCase):
    def test_li(self) -> None:
        # Arrange
        cases: list[tuple[str, list[InstrView]]] = [
            ("li a0, 10", [("addi", 10, 0, 0, 10, None)]),
            ("li a0, 0x12345000", [("lui", 10, 0, 0, 0x12345, None)]),
            ("li a0, 0x12345FFF", [("lui", 10, 0, 0, 0x12346, None), ("addi", 10, 10, 0, -1, None)]),
            ("li a0, -1", [("addi", 10, 0, 0, -1, None)]),
            ("li a0, 0xFFFFFFFF", [("addi", 10, 0, 0, -1, None)]),
            ("li a0, -2048", [("addi", 10, 0, 0, -2048, None)]),
            ("li a0, -2049", [("lui", 10, 0, 0, 0xFFFFF, None), ("addi", 10, 10, 0, 2047, None)]),
            ("li x0, 0x12345000", [("lui", 0, 0, 0, 0x12345, None)]),
        ]
        case: tuple[str, list[InstrView]]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                unit: Unit = run(case[0])

                # Assert
                self.assertEqual([view(i) for i in unit.instrs], case[1])
                self.assertEqual(unit.errors, [])

    def test_li_out_of_range(self) -> None:
        # Arrange
        text: str = "li a0, 0x100000000"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(
            unit.errors, [Diagnostic(1, "inmediato 4294967296 fuera de rango [-2147483648, 4294967295]")]
        )
        self.assertIs(unit.layout_ok, False)

    def test_single_word(self) -> None:
        # Arrange
        cases: list[tuple[str, InstrView]] = [
            ("nop", ("addi", 0, 0, 0, 0, None)),
            ("mv a0, a1", ("addi", 10, 11, 0, 0, None)),
            ("not a0, a1", ("xori", 10, 11, 0, -1, None)),
            ("neg a0, a1", ("sub", 10, 0, 11, 0, None)),
            ("seqz a0, a1", ("sltiu", 10, 11, 0, 1, None)),
            ("snez a0, a1", ("sltu", 10, 0, 11, 0, None)),
            ("sltz a0, a1", ("slt", 10, 11, 0, 0, None)),
            ("sgtz a0, a1", ("slt", 10, 0, 11, 0, None)),
            ("beqz a1, L", ("beq", 0, 11, 0, 0, Reloc("pcrel", "L", 0))),
            ("bnez a1, L", ("bne", 0, 11, 0, 0, Reloc("pcrel", "L", 0))),
            ("blez a1, L", ("bge", 0, 0, 11, 0, Reloc("pcrel", "L", 0))),
            ("bgez a1, L", ("bge", 0, 11, 0, 0, Reloc("pcrel", "L", 0))),
            ("bltz a1, L", ("blt", 0, 11, 0, 0, Reloc("pcrel", "L", 0))),
            ("bgtz a1, L", ("blt", 0, 0, 11, 0, Reloc("pcrel", "L", 0))),
            ("bgt a1, a2, L", ("blt", 0, 12, 11, 0, Reloc("pcrel", "L", 0))),
            ("ble a1, a2, L", ("bge", 0, 12, 11, 0, Reloc("pcrel", "L", 0))),
            ("bgtu a1, a2, L", ("bltu", 0, 12, 11, 0, Reloc("pcrel", "L", 0))),
            ("bleu a1, a2, L", ("bgeu", 0, 12, 11, 0, Reloc("pcrel", "L", 0))),
            ("j L", ("jal", 0, 0, 0, 0, Reloc("pcrel", "L", 0))),
            ("jr a1", ("jalr", 0, 11, 0, 0, None)),
            ("ret", ("jalr", 0, 1, 0, 0, None)),
            ("jal L", ("jal", 1, 0, 0, 0, Reloc("pcrel", "L", 0))),
            ("jal t0, L", ("jal", 5, 0, 0, 0, Reloc("pcrel", "L", 0))),
            ("beq a0, a1, L", ("beq", 0, 10, 11, 0, Reloc("pcrel", "L", 0))),
            ("ecall", ("ecall", 0, 0, 0, 0, None)),
            ("ebreak", ("ebreak", 0, 0, 0, 1, None)),
            ("lw a0, -4(s0)", ("lw", 10, 8, 0, -4, None)),
            ("sw a0, 8(sp)", ("sw", 0, 2, 10, 8, None)),
            ("lui t0, 0xFFFFF", ("lui", 5, 0, 0, 0xFFFFF, None)),
            ("srai a0, a1, 31", ("srai", 10, 11, 0, 31, None)),
            ("ADDI a0, a0, 1", ("addi", 10, 10, 0, 1, None)),
        ]
        case: tuple[str, InstrView]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                unit: Unit = run(case[0])

                # Assert
                self.assertEqual([view(i) for i in unit.instrs], [case[1]])
                self.assertEqual(unit.errors, [])

    def test_two_words(self) -> None:
        # Arrange
        cases: list[tuple[str, list[InstrView]]] = [
            ("la a0, S", [("auipc", 10, 0, 0, 0, Reloc("hi", "S", 4)), ("addi", 10, 10, 0, 0, Reloc("lo", "S", 4))]),
            ("lw a0, S", [("auipc", 10, 0, 0, 0, Reloc("hi", "S", 4)), ("lw", 10, 10, 0, 0, Reloc("lo", "S", 4))]),
            ("lbu a0, S", [("auipc", 10, 0, 0, 0, Reloc("hi", "S", 4)), ("lbu", 10, 10, 0, 0, Reloc("lo", "S", 4))]),
            (
                "sw a0, S, t1",
                [("auipc", 6, 0, 0, 0, Reloc("hi", "S", 4)), ("sw", 0, 6, 10, 0, Reloc("lo", "S", 4))],
            ),
            ("call L", [("auipc", 1, 0, 0, 0, Reloc("hi", "L", 4)), ("jalr", 1, 1, 0, 0, Reloc("lo", "L", 4))]),
            ("tail L", [("auipc", 6, 0, 0, 0, Reloc("hi", "L", 4)), ("jalr", 0, 6, 0, 0, Reloc("lo", "L", 4))]),
        ]
        case: tuple[str, list[InstrView]]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                unit: Unit = run("nop\n" + case[0])

                # Assert
                self.assertEqual([view(i) for i in unit.instrs[1:]], case[1])
                self.assertEqual([i.addr for i in unit.instrs[1:]], [4, 8])
                self.assertEqual([i.line for i in unit.instrs[1:]], [2, 2])
                self.assertEqual(unit.errors, [])

    def test_jalr(self) -> None:
        # Arrange
        cases: list[tuple[str, InstrView]] = [
            ("jalr a0, 8(a1)", ("jalr", 10, 11, 0, 8, None)),
            ("jalr a0, a1, 8", ("jalr", 10, 11, 0, 8, None)),
            ("jalr a1", ("jalr", 1, 11, 0, 0, None)),
            ("jalr a0, a1", ("jalr", 10, 11, 0, 0, None)),
            ("jalr a0, (a1)", ("jalr", 10, 11, 0, 0, None)),
        ]
        case: tuple[str, InstrView]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                unit: Unit = run(case[0])

                # Assert
                self.assertEqual([view(i) for i in unit.instrs], [case[1]])
                self.assertEqual(unit.errors, [])


class ErrorTest(unittest.TestCase):
    def test_pass1_errors(self) -> None:
        # Arrange
        cases: list[tuple[str, int, str | None]] = [
            ("mul a0, a1, a2", 1, "instrucción inválida"),
            ("addi x1, x2", 1, "espera 3 operandos"),
            ("addi x1, x2, x3", 1, "debe ser un inmediato"),
            ("addi x1, x2, 4096", 1, "fuera de rango [-2048, 2047]"),
            ("addi x1, x2, 0x7FF", 1, None),
            ("addi x1, x2, -2048", 1, None),
            ("slli x1, x2, 32", 1, "fuera de rango [0, 31]"),
            ("addi x32, x1, 0", 1, "registro inexistente 'x32'"),
            ("addi t7, x1, 0", 1, "registro inexistente 't7'"),
            ("lui t0, 0x100000", 1, "fuera de rango [0, 1048575]"),
            ("lui t0, -1", 1, "fuera de rango"),
            ("lw a0, 2048(sp)", 1, "fuera de rango"),
            ("beq a0, a1, 8", 1, "debe ser una etiqueta"),
            ("j 8", 1, "debe ser una etiqueta"),
            (".data\n.byte 256", 2, "fuera de rango para .byte"),
            (".data\n.half 65536", 2, "fuera de rango"),
            (".data\n.word 4294967296", 2, "fuera de rango"),
            (".data\n.byte -129", 2, "fuera de rango"),
            (".data\n.word", 2, "línea mal formada"),
            (".foo 1", 1, "directiva '.foo' desconocida"),
            (".word 1", 1, "solo es válido en .data"),
            (".data\nadd a0, a0, a0", 2, "solo es válido en .text"),
            (".data\n.half etiqueta", 2, "debe ser un número"),
            ("addi A0, a0, 1", 1, "registro inexistente 'A0'"),
        ]
        case: tuple[str, int, str | None]
        for case in cases:
            with self.subTest(text=case[0]):
                # Act
                errors: list[Diagnostic] = run(case[0]).errors

                # Assert
                if case[2] is None:
                    self.assertEqual(errors, [])
                else:
                    self.assertEqual(len(errors), 1, errors)
                    self.assertEqual(errors[0].line, case[1])
                    self.assertIn(case[2], errors[0].msg)

    def test_exact_messages(self) -> None:
        # Arrange
        cases: list[tuple[str, str]] = [
            ("mul a0, a1, a2", "instrucción inválida 'mul'"),
            ("addi a0, a1", "'addi' espera 3 operandos (rd, rs1, imm), se dieron 2"),
            (
                "jalr a0, a1, a2, a3, a4",
                "'jalr' espera (rd, off(rs1)) o (rd, rs1, imm) o (rs1) o (rd, rs1), se dieron 5",
            ),
            ("addi x1, x2, x3", "operando 3 de 'addi' debe ser un inmediato, se encontró el registro 'x3'"),
            ("lw a0, 100", "operando 2 de 'lw' debe ser desplazamiento(registro), se encontró el inmediato 100"),
            ("beq a0, a1, 8", "operando 3 de 'beq' debe ser una etiqueta, se encontró el inmediato 8"),
            ("addi a0, a0, foo", "operando 3 de 'addi' debe ser un inmediato, se encontró la etiqueta 'foo'"),
            (
                "addi a0, a0, 8(sp)",
                "operando 3 de 'addi' debe ser un inmediato, se encontró el acceso a memoria '8(x2)'",
            ),
            ('addi a0, a0, "s"', "operando 3 de 'addi' debe ser un inmediato, se encontró la cadena \"s\""),
            ("addi x32, x1, 0", "registro inexistente 'x32'"),
            ("addi x1, x2, 4096", "inmediato 4096 fuera de rango [-2048, 2047]"),
            ("lw a0, -2049(sp)", "inmediato -2049 fuera de rango [-2048, 2047]"),
            ("slli x1, x2, 32", "desplazamiento 32 fuera de rango [0, 31]"),
            ("lui t0, 0x100000", "inmediato de 'lui' 1048576 fuera de rango [0, 1048575]"),
            ("auipc t0, -1", "inmediato de 'auipc' -1 fuera de rango [0, 1048575]"),
            ("li a0, -2147483649", "inmediato -2147483649 fuera de rango [-2147483648, 4294967295]"),
            (".data\n.byte 256", "valor 256 fuera de rango para .byte [-128, 255]"),
            (".data\n.half -32769", "valor -32769 fuera de rango para .half [-32768, 65535]"),
            (".data\n.word -2147483649", "valor -2147483649 fuera de rango para .word [-2147483648, 4294967295]"),
            (".data\n.byte x", "operando 1 de '.byte' debe ser un número, se encontró la etiqueta 'x'"),
            (
                ".data\n.word a0",
                "operando 1 de '.word' debe ser un número o una etiqueta, se encontró el registro 'x10'",
            ),
            (".data\n.string \"a\", 1", "operando 2 de '.string' debe ser una cadena, se encontró el inmediato 1"),
            (".data\n.word", "línea mal formada cerca de '.word'"),
            (".text 1", "línea mal formada cerca de '1'"),
            (".foo 1", "directiva '.foo' desconocida"),
            (".word 1", "'.word' solo es válido en .data"),
            (".data\nadd a0, a0, a0", "'add' solo es válido en .text"),
            ("nop 1", "'nop' espera 0 operandos (), se dieron 1"),
            (".data\nmul a0, a1, a2", "instrucción inválida 'mul'"),
            ("sw a0, S", "'sw' con símbolo espera 3 operandos (rs2, símbolo, rt), se dieron 2"),
            ("sb a0, S", "'sb' con símbolo espera 3 operandos (rs2, símbolo, rt), se dieron 2"),
        ]
        case: tuple[str, str]
        for case in cases:
            with self.subTest(text=case[0]):
                # Act
                messages: list[str] = [d.msg for d in run(case[0]).errors]

                # Assert
                self.assertEqual(messages, [case[1]])

    def test_duplicate_label(self) -> None:
        # Arrange
        text: str = "a: nop\na: nop"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.errors, [Diagnostic(2, "etiqueta 'a' duplicada (primera definición en la línea 1)")])
        self.assertEqual(unit.symtab["a"], 0)
        self.assertEqual(len(unit.instrs), 2)

    def test_other_labels_of_line_still_register(self) -> None:
        # Arrange
        text: str = "a: nop\na: b: nop"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.symtab, {"a": 0, "b": 4})
        self.assertEqual(len(unit.errors), 1)

    def test_label_on_failing_line_is_defined(self) -> None:
        # Arrange
        text: str = "dup: addi x1, x2, 4096"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual(unit.symtab, {"dup": 0})
        self.assertEqual(len(unit.errors), 1)

    def test_two_errors_on_one_line(self) -> None:
        # Arrange
        text: str = "a: nop\na: mul x0,x0,x0"

        # Act
        unit: Unit = run(text)

        # Assert
        self.assertEqual([d.line for d in unit.errors], [2, 2])
        self.assertIn("duplicada", unit.errors[0].msg)
        self.assertIn("instrucción inválida", unit.errors[1].msg)


class ReservationTest(unittest.TestCase):
    def test_size_reserved_on_failure(self) -> None:
        # Arrange
        cases: list[tuple[str, int, bool]] = [
            ("addi x1, x2, 4096\nfin: nop", 4, True),
            ("la a0\nfin: nop", 8, True),
            ("lw x32, S\nfin: nop", 8, True),
            ("sw a0, S, x32\nfin: nop", 8, True),
            ("call 8\nfin: nop", 8, True),
            ("li x32, 0x12345FFF\nfin: nop", 8, True),
            ("li a0, 0x100000000\nfin: nop", 4, False),
            ("li a0, foo\nfin: nop", 4, False),
            ("mul a0,a0,a0\nfin: nop", 0, False),
        ]
        case: tuple[str, int, bool]
        for case in cases:
            with self.subTest(text=case[0]):
                # Act
                unit: Unit = run(case[0])

                # Assert
                self.assertEqual(unit.symtab["fin"], case[1])
                self.assertIs(unit.layout_ok, case[2])
                self.assertEqual(len(unit.errors), 1)

    def test_unparsed_line_breaks_layout(self) -> None:
        # Arrange
        statements: list[Statement | None] = [None, Statement(2, ("fin",), "nop", ())]

        # Act
        unit: Unit = analyze(statements)

        # Assert
        self.assertIs(unit.layout_ok, False)
        self.assertEqual(unit.symtab, {"fin": 0})
        self.assertEqual(unit.errors, [])
