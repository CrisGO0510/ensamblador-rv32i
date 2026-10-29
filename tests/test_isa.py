import unittest

from rvasm.isa import (
    ENCODERS,
    FIXED_IMM,
    PSEUDOS,
    REGISTERS,
    SIGNATURES,
    SPEC,
    Signature,
    Spec,
    hi_lo,
    to_signed32,
)
from rvasm.model import HiLo, Instr


def encode(instr: Instr) -> int:
    spec: Spec = SPEC[instr.mnem]
    return ENCODERS[spec.fmt](spec, instr)


def sign_extend(value: int, bits: int) -> int:
    return value - (1 << bits) if value >> (bits - 1) & 1 else value


def decode_b(word: int) -> int:
    raw: int = (
        (word >> 31 & 1) << 12 | (word >> 7 & 1) << 11 | (word >> 25 & 0x3F) << 5 | (word >> 8 & 0xF) << 1
    )
    return sign_extend(raw, 13)


def decode_j(word: int) -> int:
    raw: int = (
        (word >> 31 & 1) << 20 | (word >> 12 & 0xFF) << 12 | (word >> 20 & 1) << 11 | (word >> 21 & 0x3FF) << 1
    )
    return sign_extend(raw, 21)


class TableTest(unittest.TestCase):
    def test_table_sizes(self) -> None:
        # Arrange
        expected: list[int] = [39, 25]

        # Act
        sizes: list[int] = [len(SPEC), len(PSEUDOS)]

        # Assert
        self.assertEqual(sizes, expected)

    def test_registers_cover_numeric_and_abi_names(self) -> None:
        # Arrange
        cases: list[tuple[str, int]] = [
            ("fp", 8), ("s0", 8), ("zero", 0), ("ra", 1), ("sp", 2),
            ("t6", 31), ("a7", 17), ("s11", 27), ("x0", 0), ("x31", 31),
        ]
        case: tuple[str, int]
        for case in cases:
            with self.subTest(name=case[0]):
                # Act
                number: int = REGISTERS[case[0]]

                # Assert
                self.assertEqual(number, case[1])

    def test_registers_count(self) -> None:
        # Arrange
        abi: int = len(["zero", "ra", "sp", "gp", "tp", "fp"]) + 7 + 12 + 8

        # Act
        count: int = len(REGISTERS)

        # Assert
        self.assertEqual(count, 32 + abi)

    def test_every_shape_fmt_and_kind_is_known(self) -> None:
        # Arrange
        kinds: set[str] = {"reg", "imm12", "shamt", "uimm20", "mem", "sym", "li"}
        signatures: list[Signature] = [s for alts in SIGNATURES.values() for s in alts] + [
            p.signature for p in PSEUDOS.values()
        ]

        # Act
        missing_shapes: list[str] = [m for m in SPEC if SPEC[m].shape not in SIGNATURES]
        missing_fmts: list[str] = [m for m in SPEC if SPEC[m].fmt not in ENCODERS]
        unknown_kinds: list[str] = [arg[0] for s in signatures for arg in s if arg[0] not in kinds]

        # Assert
        self.assertEqual(missing_shapes, [])
        self.assertEqual(missing_fmts, [])
        self.assertEqual(unknown_kinds, [])


class EncoderTest(unittest.TestCase):
    def test_measured_words(self) -> None:
        # Arrange
        cases: list[tuple[Instr, int]] = [
            (Instr(1, "auipc", rd=10, imm=0x10000), 0x10000517),
            (Instr(1, "addi", rd=10, rs1=10, imm=4), 0x00450513),
            (Instr(1, "auipc", rd=11, imm=0x10000), 0x10000597),
            (Instr(1, "lw", rd=11, rs1=11, imm=-8), 0xFF85A583),
            (Instr(1, "lui", rd=12, imm=0x12346), 0x12346637),
            (Instr(1, "addi", rd=12, rs1=12, imm=-1), 0xFFF60613),
            (Instr(1, "beq", rs1=11, rs2=0, imm=8), 0x00058463),
            (Instr(1, "jal", rd=0, imm=-4), 0xFFDFF06F),
            (Instr(1, "jal", rd=0, imm=0), 0x0000006F),
            (Instr(1, "srai", rd=10, rs1=10, imm=31), 0x41F55513),
            (Instr(1, "addi", rd=10, rs1=0, imm=10), 0x00A00513),
            (Instr(1, "beq", rs1=10, rs2=0, imm=16), 0x00050863),
            (Instr(1, "add", rd=11, rs1=11, rs2=10), 0x00A585B3),
            (Instr(1, "addi", rd=10, rs1=10, imm=-1), 0xFFF50513),
            (Instr(1, "jal", rd=0, imm=-12), 0xFF5FF06F),
            (Instr(1, "sw", rs2=10, rs1=2, imm=-4), 0xFEA12E23),
            (Instr(1, "sub", rd=10, rs1=11, rs2=12), 0x40C58533),
            (Instr(1, "ecall"), 0x00000073),
            (Instr(1, "ebreak", imm=FIXED_IMM["ebreak"]), 0x00100073),
            (Instr(1, "beq", rs1=1, rs2=2, imm=2048), 0x002080E3),
            (Instr(1, "beq", rs1=1, rs2=2, imm=-4096), 0x80208063),
        ]
        case: tuple[Instr, int]
        for case in cases:
            with self.subTest(instr=case[0]):
                # Act
                word: int = encode(case[0])

                # Assert
                self.assertEqual(word, case[1], f"{word:08x}")

    def test_branch_offsets_round_trip(self) -> None:
        # Arrange
        offsets: list[int] = [-4096, -4094, -2, 0, 2, 4094]
        imm: int
        for imm in offsets:
            with self.subTest(imm=imm):
                # Act
                decoded: int = decode_b(encode(Instr(1, "beq", imm=imm)))

                # Assert
                self.assertEqual(decoded, imm)

    def test_jump_offsets_round_trip(self) -> None:
        # Arrange
        offsets: list[int] = [-1048576, -2, 0, 2, 1048574]
        imm: int
        for imm in offsets:
            with self.subTest(imm=imm):
                # Act
                decoded: int = decode_j(encode(Instr(1, "jal", imm=imm)))

                # Assert
                self.assertEqual(decoded, imm)


class ArithmeticTest(unittest.TestCase):
    def test_hi_lo_recombines_to_the_value(self) -> None:
        # Arrange
        values: list[int] = [
            0, 1, 0x7FF, 0x800, 0xFFF, 0x1000, 0x12345FFF, 0x7FFFF800, 0x7FFFFFFF,
            -1, -2048, -2049, -0x80000000, 0x10000004, 0x0FFFFFF8,
        ]
        v: int
        for v in values:
            with self.subTest(v=v):
                # Act
                parts: HiLo = hi_lo(v)

                # Assert
                self.assertTrue(-2048 <= parts.lo <= 2047)
                self.assertTrue(0 <= parts.hi <= 0xFFFFF)
                self.assertEqual(((parts.hi << 12) + parts.lo) & 0xFFFFFFFF, v & 0xFFFFFFFF)

    def test_hi_lo_specific_values(self) -> None:
        # Arrange
        cases: list[tuple[int, HiLo]] = [
            (0x12345FFF, HiLo(0x12346, -1)),
            (0x10000004, HiLo(0x10000, 4)),
            (0x0FFFFFF8, HiLo(0x10000, -8)),
        ]
        case: tuple[int, HiLo]
        for case in cases:
            with self.subTest(v=case[0]):
                # Act
                parts: HiLo = hi_lo(case[0])

                # Assert
                self.assertEqual(parts, case[1])

    def test_to_signed32(self) -> None:
        # Arrange
        cases: list[tuple[int, int]] = [
            (0xFFFFFFFF, -1), (0x7FFFFFFF, 0x7FFFFFFF), (0x80000000, -0x80000000), (5, 5),
        ]
        case: tuple[int, int]
        for case in cases:
            with self.subTest(v=case[0]):
                # Act
                result: int = to_signed32(case[0])

                # Assert
                self.assertEqual(result, case[1])
