import unittest
from dataclasses import replace
from typing import Final

from rvasm.codegen import generate
from rvasm.lexer import tokenize
from rvasm.model import AsmError, Diagnostic, Image, Operand, Statement, Unit
from rvasm.parser import parse
from rvasm.semantic import analyze

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

NOP: Final[Statement] = Statement(0, (), "nop", ())
FAR: Final[Statement] = Statement(0, ("far",), "nop", ())


def build(texto: str) -> Unit:
    lines: list[str] = texto.split("\n")
    out: list[Statement | None] = []
    number: int
    for number in range(len(lines)):
        try:
            out.append(parse(number + 1, tokenize(lines[number])))
        except AsmError:
            out.append(None)
    return analyze(out)


def text_of(words: list[int]) -> bytes:
    return b"".join(w.to_bytes(4, "little") for w in words)


def word_at(image: Image, index: int) -> int:
    return int.from_bytes(image.text[4 * index:4 * index + 4], "little")


def sym(name: str) -> Operand:
    return Operand("sym", name)


def branch(mnem: str, target: str) -> Statement:
    args: tuple[Operand, ...] = (sym(target),) if mnem == "j" else (Operand("reg", 1), Operand("reg", 2), sym(target))
    return Statement(0, (), mnem, args)


def padded(first: Statement, n: int, last: Statement) -> Unit:
    # sin pasar por el lexer: con cientos de miles de líneas la suite se volvería lenta
    stmts: list[Statement | None] = [first]
    stmts += [NOP] * n
    stmts.append(last)
    return analyze(stmts)


def forward(mnem: str, n: int) -> Unit:
    return padded(branch(mnem, "far"), n, FAR)


def backward(mnem: str, n: int) -> Unit:
    return padded(FAR, n, branch(mnem, "far"))


class GenerateTest(unittest.TestCase):
    def test_drawing_example(self) -> None:
        # Arrange
        unit: Unit = build(DRAWING)
        words: list[int] = [
            0x10000517, 0x00450513, 0x10000597, 0xFF85A583, 0x12346637, 0xFFF60613, 0x00058463, 0xFFDFF06F, 0x0000006F,
        ]

        # Act
        image: Image = generate(unit)

        # Assert
        self.assertEqual(image.text, text_of(words))
        self.assertEqual(image.data, bytes([5, 0, 0, 0, 0x68, 0x69, 0]))
        self.assertEqual(unit.errors, [])

    def test_suma(self) -> None:
        # Arrange
        unit: Unit = build(SUMA)
        words: list[int] = [0x00A00513, 0x00000593, 0x00050863, 0x00A585B3, 0xFFF50513, 0xFF5FF06F, 0x0000006F]

        # Act
        image: Image = generate(unit)

        # Assert
        self.assertEqual(image.text, text_of(words))
        self.assertEqual(unit.errors, [])

    def test_undefined_branch_target_keeps_size(self) -> None:
        # Arrange
        unit: Unit = build("nop\nbeq x1, x2, nowhere")

        # Act
        image: Image = generate(unit)

        # Assert
        self.assertEqual(unit.errors, [Diagnostic(2, "etiqueta 'nowhere' no definida")])
        self.assertEqual(len(image.text), 8)

    def test_undefined_symbol_in_two_word_pseudo_is_reported_once(self) -> None:
        # Arrange
        unit: Unit = build("la a0, nowhere")

        # Act
        image: Image = generate(unit)

        # Assert
        self.assertEqual(unit.errors, [Diagnostic(1, "etiqueta 'nowhere' no definida")])
        self.assertEqual(len(image.text), 8)

    def test_word_fixups(self) -> None:
        # Arrange
        cases: list[tuple[str, bytes, list[Diagnostic]]] = [
            ("nop\nnop\nfoo: nop\n.data\n.word foo", bytes([8, 0, 0, 0]), []),
            (".data\n.byte 1, 2, 3\nfoo: .word foo", bytes([1, 2, 3, 3, 0, 0, 0x10]), []),
            (".data\n.word foo", bytes(4), [Diagnostic(2, "etiqueta 'foo' no definida")]),
            (".data\n.word x, x", bytes(8), [Diagnostic(2, "etiqueta 'x' no definida")]),
        ]
        case: tuple[str, bytes, list[Diagnostic]]
        for case in cases:
            with self.subTest(source=case[0]):
                # Arrange
                unit: Unit = build(case[0])

                # Act
                image: Image = generate(unit)

                # Assert
                self.assertEqual(image.data, case[1])
                self.assertEqual(unit.errors, case[2])

    def test_far_targets(self) -> None:
        # Arrange
        cases: list[tuple[str, str, int, str | None]] = [
            ("beq adelante", "beq", 1022, None),
            ("beq adelante", "beq", 1023, "destino 'far' de 'beq' a +4096 bytes fuera de rango [-4096, 4094]"),
            ("beq atrás", "beq", 1023, None),
            ("beq atrás", "beq", 1024, "destino 'far' de 'beq' a -4100 bytes fuera de rango [-4096, 4094]"),
            ("jal adelante", "j", 262142, None),
            (
                "jal adelante", "j", 262143,
                "destino 'far' de 'jal' a +1048576 bytes fuera de rango [-1048576, 1048574]",
            ),
        ]
        case: tuple[str, str, int, str | None]
        for case in cases:
            with self.subTest(direction=case[0], n=case[2]):
                # Arrange
                unit: Unit = backward(case[1], case[2]) if case[0] == "beq atrás" else forward(case[1], case[2])

                # Act
                generate(unit)

                # Assert
                self.assertEqual([e.msg for e in unit.errors], [] if case[3] is None else [case[3]])

    def test_jump_into_data_is_out_of_range(self) -> None:
        # Arrange
        unit: Unit = build('.data\nmsg: .string "x"\n.text\nj msg')

        # Act
        generate(unit)

        # Assert
        self.assertEqual(len(unit.errors), 1)
        self.assertIn("fuera de rango", unit.errors[0].msg)

    def test_la_backward(self) -> None:
        # Arrange
        la: Statement = Statement(2, (), "la", (Operand("reg", 10), sym("back")))
        unit: Unit = padded(Statement(1, ("back",), "nop", ()), 1023, la)

        # Act
        image: Image = generate(unit)

        # Assert
        self.assertEqual((unit.instrs[-2].addr, word_at(image, 1024), word_at(image, 1025)), (
            0x1000, 0xFFFFF517, 0x00050513,
        ))
        self.assertEqual(unit.errors, [])

    def test_call_recomposes_distance(self) -> None:
        # Arrange
        # auipc en 0x0, jalr en 0x4, 69998 nop desde 0x8: f queda en 8 + 4·69998 = 280000
        unit: Unit = padded(Statement(1, (), "call", (sym("f"),)), 69998, Statement(2, ("f",), "nop", ()))

        # Act
        image: Image = generate(unit)

        # Assert
        hi: int = word_at(image, 0) >> 12
        lo: int = (word_at(image, 1) >> 20) - ((word_at(image, 1) >> 31) << 12)
        self.assertEqual(unit.symtab["f"], 280000)
        self.assertEqual((hi << 12) + lo, 280000)
        self.assertEqual(unit.errors, [])

    def test_layout_not_ok_skips_range_checks(self) -> None:
        # Arrange
        cases: list[tuple[str, Unit, list[str]]] = [
            ("rango", replace(forward("beq", 1023), layout_ok=False), []),
            ("indefinida", replace(build("beq x1, x2, nowhere"), layout_ok=False), ["etiqueta 'nowhere' no definida"]),
        ]
        case: tuple[str, Unit, list[str]]
        for case in cases:
            with self.subTest(case=case[0]):
                # Act
                generate(case[1])

                # Assert
                self.assertEqual([e.msg for e in case[1].errors], case[2])

    def test_data_round_trip_without_padding(self) -> None:
        # Arrange
        unit: Unit = build(".data\n.byte " + ", ".join(str(b) for b in range(0x61, 0x6B)))

        # Act
        image: Image = generate(unit)

        # Assert
        self.assertEqual(image.data, b"abcdefghij")
        self.assertEqual(image.text, b"")
