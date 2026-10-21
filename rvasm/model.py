from dataclasses import dataclass, field
from typing import Literal, NamedTuple, TypeAlias

TokenKind: TypeAlias = Literal["IDENT", "NUM", "STRING", "COMMA", "COLON", "LPAREN", "RPAREN"]
OperandKind: TypeAlias = Literal["reg", "num", "sym", "mem", "str"]
RelocKind: TypeAlias = Literal["pcrel", "hi", "lo"]


class Token(NamedTuple):
    kind: TokenKind
    text: str
    col: int


class Operand(NamedTuple):
    kind: OperandKind
    value: int | str | bytes
    base: int | None = None


class Reloc(NamedTuple):
    kind: RelocKind
    symbol: str
    # dirección desde la que se mide: la propia instrucción en pcrel, la del auipc en hi/lo
    anchor: int


class Fixup(NamedTuple):
    line: int
    # posición dentro de Unit.data donde van los 4 bytes
    offset: int
    symbol: str


class Diagnostic(NamedTuple):
    line: int
    msg: str


class HiLo(NamedTuple):
    hi: int
    lo: int


class Image(NamedTuple):
    text: bytes
    data: bytes


@dataclass(frozen=True)
class Statement:
    line: int
    labels: tuple[str, ...]
    mnem: str | None
    args: tuple[Operand, ...]


@dataclass(slots=True)
class Instr:
    line: int
    mnem: str
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    imm: int = 0
    reloc: Reloc | None = None
    addr: int = 0
    size: int = 4


@dataclass(slots=True)
class Unit:
    instrs: list[Instr] = field(default_factory=list)
    data: bytearray = field(default_factory=bytearray)
    fixups: list[Fixup] = field(default_factory=list)
    symtab: dict[str, int] = field(default_factory=dict)
    errors: list[Diagnostic] = field(default_factory=list)
    layout_ok: bool = True


class AsmError(Exception):
    pass
