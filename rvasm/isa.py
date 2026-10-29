from collections.abc import Callable
from typing import Final, NamedTuple, TypeAlias

from rvasm.model import HiLo, Instr

TEXT_BASE: Final[int] = 0x00000000
DATA_BASE: Final[int] = 0x10000000

REGISTERS: Final[dict[str, int]] = {f"x{n}": n for n in range(32)} | {
    "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
    "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9,
    "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15, "a6": 16, "a7": 17,
    "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22, "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
    "t3": 28, "t4": 29, "t5": 30, "t6": 31,
}


class Spec(NamedTuple):
    fmt: str
    opcode: int
    funct3: int
    funct7: int
    shape: str


SPEC: Final[dict[str, Spec]] = {
    "add": Spec("R", 0x33, 0, 0x00, "rrr"),
    "sub": Spec("R", 0x33, 0, 0x20, "rrr"),
    "sll": Spec("R", 0x33, 1, 0x00, "rrr"),
    "slt": Spec("R", 0x33, 2, 0x00, "rrr"),
    "sltu": Spec("R", 0x33, 3, 0x00, "rrr"),
    "xor": Spec("R", 0x33, 4, 0x00, "rrr"),
    "srl": Spec("R", 0x33, 5, 0x00, "rrr"),
    "sra": Spec("R", 0x33, 5, 0x20, "rrr"),
    "or": Spec("R", 0x33, 6, 0x00, "rrr"),
    "and": Spec("R", 0x33, 7, 0x00, "rrr"),
    "addi": Spec("I", 0x13, 0, 0, "rri"),
    "slti": Spec("I", 0x13, 2, 0, "rri"),
    "sltiu": Spec("I", 0x13, 3, 0, "rri"),
    "xori": Spec("I", 0x13, 4, 0, "rri"),
    "ori": Spec("I", 0x13, 6, 0, "rri"),
    "andi": Spec("I", 0x13, 7, 0, "rri"),
    "slli": Spec("I", 0x13, 1, 0x00, "rrs"),
    "srli": Spec("I", 0x13, 5, 0x00, "rrs"),
    "srai": Spec("I", 0x13, 5, 0x20, "rrs"),
    "lb": Spec("I", 0x03, 0, 0, "rm"),
    "lh": Spec("I", 0x03, 1, 0, "rm"),
    "lw": Spec("I", 0x03, 2, 0, "rm"),
    "lbu": Spec("I", 0x03, 4, 0, "rm"),
    "lhu": Spec("I", 0x03, 5, 0, "rm"),
    "jalr": Spec("I", 0x67, 0, 0, "jalr"),
    "ecall": Spec("I", 0x73, 0, 0, "none"),
    "ebreak": Spec("I", 0x73, 0, 0, "none"),
    "sb": Spec("S", 0x23, 0, 0, "sm"),
    "sh": Spec("S", 0x23, 1, 0, "sm"),
    "sw": Spec("S", 0x23, 2, 0, "sm"),
    "beq": Spec("B", 0x63, 0, 0, "rrb"),
    "bne": Spec("B", 0x63, 1, 0, "rrb"),
    "blt": Spec("B", 0x63, 4, 0, "rrb"),
    "bge": Spec("B", 0x63, 5, 0, "rrb"),
    "bltu": Spec("B", 0x63, 6, 0, "rrb"),
    "bgeu": Spec("B", 0x63, 7, 0, "rrb"),
    "lui": Spec("U", 0x37, 0, 0, "ru"),
    "auipc": Spec("U", 0x17, 0, 0, "ru"),
    "jal": Spec("J", 0x6F, 0, 0, "rj"),
}

Signature: TypeAlias = tuple[tuple[str, str], ...]

SIGNATURES: Final[dict[str, tuple[Signature, ...]]] = {
    "rrr": ((("reg", "rd"), ("reg", "rs1"), ("reg", "rs2")),),
    "rri": ((("reg", "rd"), ("reg", "rs1"), ("imm12", "imm")),),
    "rrs": ((("reg", "rd"), ("reg", "rs1"), ("shamt", "imm")),),
    "rm": (
        (("reg", "rd"), ("mem", "off(rs1)")),
        (("reg", "rd"), ("sym", "símbolo")),
    ),
    "sm": (
        (("reg", "rs2"), ("mem", "off(rs1)")),
        (("reg", "rs2"), ("sym", "símbolo"), ("reg", "rt")),
    ),
    "rrb": ((("reg", "rs1"), ("reg", "rs2"), ("sym", "etiqueta")),),
    "ru": ((("reg", "rd"), ("uimm20", "imm20")),),
    "rj": (
        (("reg", "rd"), ("sym", "etiqueta")),
        (("sym", "etiqueta"),),
    ),
    "jalr": (
        (("reg", "rd"), ("mem", "off(rs1)")),
        (("reg", "rd"), ("reg", "rs1"), ("imm12", "imm")),
        (("reg", "rs1"),),
        (("reg", "rd"), ("reg", "rs1")),
    ),
    "none": ((),),
}

Encoder: TypeAlias = Callable[[Spec, Instr], int]


def encode_r(spec: Spec, ins: Instr) -> int:
    return spec.funct7 << 25 | ins.rs2 << 20 | ins.rs1 << 15 | spec.funct3 << 12 | ins.rd << 7 | spec.opcode


def encode_i(spec: Spec, ins: Instr) -> int:
    return (
        spec.funct7 << 25 | (ins.imm & 0xFFF) << 20 | ins.rs1 << 15 | spec.funct3 << 12 | ins.rd << 7 | spec.opcode
    )


def encode_s(spec: Spec, ins: Instr) -> int:
    return (
        (ins.imm >> 5 & 0x7F) << 25 | ins.rs2 << 20 | ins.rs1 << 15 | spec.funct3 << 12
        | (ins.imm & 0x1F) << 7 | spec.opcode
    )


def encode_b(spec: Spec, ins: Instr) -> int:
    return (
        (ins.imm >> 12 & 1) << 31 | (ins.imm >> 5 & 0x3F) << 25 | ins.rs2 << 20 | ins.rs1 << 15
        | spec.funct3 << 12 | (ins.imm >> 1 & 0xF) << 8 | (ins.imm >> 11 & 1) << 7 | spec.opcode
    )


def encode_u(spec: Spec, ins: Instr) -> int:
    return (ins.imm & 0xFFFFF) << 12 | ins.rd << 7 | spec.opcode


def encode_j(spec: Spec, ins: Instr) -> int:
    return (
        (ins.imm >> 20 & 1) << 31 | (ins.imm >> 1 & 0x3FF) << 21 | (ins.imm >> 11 & 1) << 20
        | (ins.imm >> 12 & 0xFF) << 12 | ins.rd << 7 | spec.opcode
    )


ENCODERS: Final[dict[str, Encoder]] = {
    "R": encode_r, "I": encode_i, "S": encode_s, "B": encode_b, "U": encode_u, "J": encode_j,
}

RANGES: Final[dict[str, tuple[int, int]]] = {
    "imm12": (-2048, 2047),
    "shamt": (0, 31),
    "uimm20": (0, 1048575),
    "pcrel_b": (-4096, 4094),
    "pcrel_j": (-1048576, 1048574),
    "byte": (-128, 255),
    "half": (-32768, 65535),
    "word": (-2147483648, 4294967295),
    "li": (-2147483648, 4294967295),
}

FIXED_IMM: Final[dict[str, int]] = {"ebreak": 1}


class Pseudo(NamedTuple):
    signature: Signature
    # en 'li' es solo el mínimo: la semántica decide si ocupa 4 u 8
    nominal_size: int


PSEUDOS: Final[dict[str, Pseudo]] = {
    "nop": Pseudo((), 4),
    "mv": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "not": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "neg": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "seqz": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "snez": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "sltz": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "sgtz": Pseudo((("reg", "rd"), ("reg", "rs")), 4),
    "beqz": Pseudo((("reg", "rs"), ("sym", "etiqueta")), 4),
    "bnez": Pseudo((("reg", "rs"), ("sym", "etiqueta")), 4),
    "blez": Pseudo((("reg", "rs"), ("sym", "etiqueta")), 4),
    "bgez": Pseudo((("reg", "rs"), ("sym", "etiqueta")), 4),
    "bltz": Pseudo((("reg", "rs"), ("sym", "etiqueta")), 4),
    "bgtz": Pseudo((("reg", "rs"), ("sym", "etiqueta")), 4),
    "bgt": Pseudo((("reg", "rs"), ("reg", "rt"), ("sym", "etiqueta")), 4),
    "ble": Pseudo((("reg", "rs"), ("reg", "rt"), ("sym", "etiqueta")), 4),
    "bgtu": Pseudo((("reg", "rs"), ("reg", "rt"), ("sym", "etiqueta")), 4),
    "bleu": Pseudo((("reg", "rs"), ("reg", "rt"), ("sym", "etiqueta")), 4),
    "j": Pseudo((("sym", "etiqueta"),), 4),
    "jr": Pseudo((("reg", "rs"),), 4),
    "ret": Pseudo((), 4),
    "li": Pseudo((("reg", "rd"), ("li", "imm")), 4),
    "la": Pseudo((("reg", "rd"), ("sym", "símbolo")), 8),
    "call": Pseudo((("sym", "etiqueta"),), 8),
    "tail": Pseudo((("sym", "etiqueta"),), 8),
}


def to_signed32(v: int) -> int:
    u: int = v & 0xFFFFFFFF
    return u - (1 << 32) if u & 0x80000000 else u


def hi_lo(v: int) -> HiLo:
    return HiLo(((v + 0x800) >> 12) & 0xFFFFF, ((v + 0x800) & 0xFFF) - 0x800)
