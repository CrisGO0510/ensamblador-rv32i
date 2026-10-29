import dataclasses
import unittest
from typing import get_args

from rvasm.model import (
    AsmError,
    Diagnostic,
    Fixup,
    HiLo,
    Image,
    Instr,
    Operand,
    OperandKind,
    Reloc,
    RelocKind,
    Statement,
    Token,
    TokenKind,
    Unit,
)


class ModelTest(unittest.TestCase):
    def test_named_tuples_have_the_planned_fields(self) -> None:
        # Arrange
        token: Token = Token(TokenKind.IDENT, "addi")
        operand: Operand = Operand("mem", 8, base=2)
        reloc: Reloc = Reloc("pcrel", "loop", 0x10)
        fixup: Fixup = Fixup(3, 4, "msg")
        diag: Diagnostic = Diagnostic(7, "error")
        hilo: HiLo = HiLo(1, -2)
        image: Image = Image(b"\x13", b"\x00")

        # Act
        fields: list[tuple[str, ...]] = [
            token._fields, operand._fields, reloc._fields, fixup._fields,
            diag._fields, hilo._fields, image._fields,
        ]

        # Assert
        self.assertEqual(fields, [
            ("kind", "text"),
            ("kind", "value", "base"),
            ("kind", "symbol", "anchor"),
            ("line", "offset", "symbol"),
            ("line", "msg"),
            ("hi", "lo"),
            ("text", "data"),
        ])

    def test_kind_literals_list_every_value(self) -> None:
        # Act
        counts: list[int] = [len(TokenKind), len(get_args(OperandKind)), len(get_args(RelocKind))]

        # Assert
        self.assertEqual(counts, [7, 5, 3])

    def test_unit_starts_with_layout_ok(self) -> None:
        # Arrange
        unit: Unit = Unit()

        # Act
        layout_ok: bool = unit.layout_ok

        # Assert
        self.assertIs(layout_ok, True)

    def test_units_do_not_share_instrs(self) -> None:
        # Arrange
        first: Unit = Unit()
        second: Unit = Unit()

        # Act
        first.instrs.append(Instr(line=1, mnem="add"))

        # Assert
        self.assertIsNot(first.instrs, second.instrs)
        self.assertEqual(second.instrs, [])

    def test_statement_is_immutable(self) -> None:
        # Arrange
        stmt: Statement = Statement(1, ("main",), "addi", (Operand("reg", 1),))

        # Act
        # Assert
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(stmt, "line", 2)

    def test_asm_error_is_an_exception(self) -> None:
        # Arrange
        error: AsmError = AsmError("registro inválido")

        # Act
        message: str = str(error)

        # Assert
        self.assertIsInstance(error, Exception)
        self.assertEqual(message, "registro inválido")
