import unittest
from typing import Final

from rvasm.cli import AsmResult, assemble_lines
from rvasm.isa import ENCODERS, FIXED_IMM, SPEC, Spec
from rvasm.listing import fields, listing
from rvasm.model import Instr

HEADER: Final[str] = (
    "| línea | dirección | fuente | instr | hex | fmt | opcode | rd | funct3 | rs1 | rs2 | funct7 | imm |\n"
    + "|" + "---|" * 13 + "\n"
)

PROGRAM: Final[list[str]] = [
    "main: sw ra, 28(sp)",
    "li a0, 0x12345678",
    "loop: beq a0, a1, main",
    "slli t0, t1, 3",
]

FORMAT_FIELDS: Final[dict[str, set[str]]] = {
    "R": {"opcode", "rd", "funct3", "rs1", "rs2", "funct7"},
    "I": {"opcode", "rd", "funct3", "rs1", "imm"},
    "S": {"opcode", "funct3", "rs1", "rs2", "imm"},
    "B": {"opcode", "funct3", "rs1", "rs2", "imm"},
    "U": {"opcode", "rd", "imm"},
    "J": {"opcode", "rd", "imm"},
}

IMM_WIDTH: Final[dict[str, int]] = {"I": 12, "S": 12, "B": 13, "U": 20, "J": 21}
IMM_SAMPLE: Final[dict[str, int]] = {"I": -5, "S": -9, "B": -20, "U": 0x12345, "J": -100}


def cell(value: int, width: int) -> str:
    return f"{value:0{width}b} (0x{value:x})"


def row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |\n"


def build(mnem: str) -> Instr:
    spec: Spec = SPEC[mnem]
    imm: int = {"rrs": 3, "none": FIXED_IMM.get(mnem, 0)}.get(spec.shape, IMM_SAMPLE.get(spec.fmt, 0))
    return Instr(1, mnem, rd=5, rs1=6, rs2=7, imm=imm)


class FieldsTest(unittest.TestCase):
    def test_every_mnemonic_round_trips(self) -> None:
        # Arrange
        mnem: str
        for mnem in SPEC:
            with self.subTest(mnem=mnem):
                spec: Spec = SPEC[mnem]
                ins: Instr = build(mnem)
                word: int = ENCODERS[spec.fmt](spec, ins)
                expected: dict[str, str] = {
                    "opcode": cell(spec.opcode, 7),
                    "rd": cell(5, 5),
                    "funct3": cell(spec.funct3, 3),
                    "rs1": cell(6, 5),
                    "rs2": cell(7, 5),
                    "funct7": cell(spec.funct7, 7),
                }
                names: set[str] = set(FORMAT_FIELDS[spec.fmt])
                if spec.shape == "rrs":
                    names |= {"funct7"}
                    expected.update(imm=cell(3, 5))
                else:
                    width: int = IMM_WIDTH.get(spec.fmt, 0)
                    expected.update(imm=cell(ins.imm & (1 << width) - 1, width))

                # Act
                found: dict[str, str] = fields(spec, word)

                # Assert
                self.assertEqual(set(found), names)
                name: str
                for name in names:
                    self.assertEqual(found[name], expected[name], name)

    def test_srai_shows_funct7_and_ebreak_imm(self) -> None:
        # Arrange
        srai: Spec = SPEC["srai"]
        ebreak: Spec = SPEC["ebreak"]

        # Act
        shift: dict[str, str] = fields(srai, ENCODERS["I"](srai, build("srai")))
        trap: dict[str, str] = fields(ebreak, ENCODERS["I"](ebreak, build("ebreak")))

        # Assert
        self.assertEqual(shift["funct7"], "0100000 (0x20)")
        self.assertEqual(trap["imm"], "000000000001 (0x1)")

    def test_unknown_format_raises(self) -> None:
        # Arrange
        spec: Spec = Spec("X", 0, 0, 0, "none")

        # Act / Assert
        with self.assertRaises(ValueError):
            fields(spec, 0)


class ListingTest(unittest.TestCase):
    def test_golden_table(self) -> None:
        # Arrange
        result: AsmResult = assemble_lines(PROGRAM)
        expected: str = (
            HEADER
            + row(["1", "0x00000000", "`` main: sw ra, 28(sp) ``", "sw", "00112e23", "S", "0100011 (0x23)", "",
                   "010 (0x2)", "00010 (0x2)", "00001 (0x1)", "", "000000011100 (0x1c)"])
            + row(["2", "0x00000004", "`` li a0, 0x12345678 ``", "lui", "12345537", "U", "0110111 (0x37)",
                   "01010 (0xa)", "", "", "", "", "00010010001101000101 (0x12345)"])
            + row(["2", "0x00000008", "`` li a0, 0x12345678 ``", "addi", "67850513", "I", "0010011 (0x13)",
                   "01010 (0xa)", "000 (0x0)", "01010 (0xa)", "", "", "011001111000 (0x678)"])
            + row(["3", "0x0000000c", "`` loop: beq a0, a1, main ``", "beq", "feb50ae3", "B", "1100011 (0x63)", "",
                   "000 (0x0)", "01010 (0xa)", "01011 (0xb)", "", "1111111110100 (0x1ff4)"])
            + row(["4", "0x00000010", "`` slli t0, t1, 3 ``", "slli", "00331293", "I", "0010011 (0x13)",
                   "00101 (0x5)", "001 (0x1)", "00110 (0x6)", "", "0000000 (0x0)", "00011 (0x3)"])
        )

        # Act
        table: str = listing(PROGRAM, result.instrs, result.image.text)

        # Assert
        self.assertEqual(table, expected)

    def test_label_only_line_has_no_row(self) -> None:
        # Arrange
        lines: list[str] = ["start:", "nop"]
        result: AsmResult = assemble_lines(lines)

        # Act
        table: str = listing(lines, result.instrs, result.image.text)

        # Assert
        self.assertEqual(table.count("\n"), 3)
        self.assertIn("| 2 | 0x00000000 | `` nop `` | addi |", table)

    def test_pipe_is_escaped_and_cr_is_stripped(self) -> None:
        # Arrange
        lines: list[str] = ["  nop # a|b\r"]
        result: AsmResult = assemble_lines(lines)

        # Act
        table: str = listing(lines, result.instrs, result.image.text)

        # Assert
        self.assertIn("`` nop # a\\|b ``", table)
        self.assertNotIn("\r", table)

    def test_backtick_run_widens_code_span_delimiter(self) -> None:
        # Arrange
        lines: list[str] = ["addi x1,x0,1 # a``b"]
        result: AsmResult = assemble_lines(lines)

        # Act
        table: str = listing(lines, result.instrs, result.image.text)

        # Assert
        self.assertIn("``` addi x1,x0,1 # a``b ```", table)

    def test_empty_text_has_only_header(self) -> None:
        # Arrange / Act
        table: str = listing([], [], b"")

        # Assert
        self.assertEqual(table, HEADER)
