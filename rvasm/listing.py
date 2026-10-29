import re
from typing import Final

from rvasm.isa import SPEC, Spec
from rvasm.model import Instr

COLUMNS: Final[tuple[str, ...]] = (
    "línea", "dirección", "fuente", "instr", "hex", "fmt",
    "opcode", "rd", "funct3", "rs1", "rs2", "funct7", "imm",
)

POSITIONS: Final[dict[str, tuple[int, int]]] = {
    "opcode": (0, 7), "rd": (7, 5), "funct3": (12, 3), "rs1": (15, 5), "rs2": (20, 5), "funct7": (25, 7),
}

FORMAT_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "R": ("opcode", "rd", "funct3", "rs1", "rs2", "funct7"),
    "I": ("opcode", "rd", "funct3", "rs1", "imm"),
    "S": ("opcode", "funct3", "rs1", "rs2", "imm"),
    "B": ("opcode", "funct3", "rs1", "rs2", "imm"),
    "U": ("opcode", "rd", "imm"),
    "J": ("opcode", "rd", "imm"),
}

# (bit en la palabra, ancho, bit en el imm)
IMM_SEGMENTS: Final[dict[str, tuple[tuple[int, int, int], ...]]] = {
    "I": ((20, 12, 0),),
    "S": ((7, 5, 0), (25, 7, 5)),
    "B": ((8, 4, 1), (25, 6, 5), (7, 1, 11), (31, 1, 12)),
    "U": ((12, 20, 0),),
    "J": ((21, 10, 1), (20, 1, 11), (12, 8, 12), (31, 1, 20)),
}

IMM_WIDTH: Final[dict[str, int]] = {"I": 12, "S": 12, "B": 13, "U": 20, "J": 21}

SHIFT_SHAPE: Final[str] = "rrs"
SHIFT_IMM_WIDTH: Final[int] = 5


def cell(value: int, width: int) -> str:
    return f"{value:0{width}b} (0x{value:x})"


def slice_bits(word: int, bit: int, width: int) -> int:
    return word >> bit & (1 << width) - 1


def fields(spec: Spec, word: int) -> dict[str, str]:
    if spec.fmt not in FORMAT_FIELDS:
        raise ValueError(f"formato desconocido '{spec.fmt}'")
    names: tuple[str, ...] = FORMAT_FIELDS[spec.fmt]
    is_shift: bool = spec.shape == SHIFT_SHAPE
    if is_shift:
        names += ("funct7",)
    found: dict[str, str] = {
        n: cell(slice_bits(word, POSITIONS[n][0], POSITIONS[n][1]), POSITIONS[n][1]) for n in names if n in POSITIONS
    }
    if "imm" in names:
        segments: tuple[tuple[int, int, int], ...] = ((20, SHIFT_IMM_WIDTH, 0),) if is_shift else IMM_SEGMENTS[spec.fmt]
        imm: int = 0
        seg: tuple[int, int, int]
        for seg in segments:
            imm |= slice_bits(word, seg[0], seg[1]) << seg[2]
        found.update(imm=cell(imm, SHIFT_IMM_WIDTH if is_shift else IMM_WIDTH[spec.fmt]))
    return found


def listing(lines: list[str], instrs: list[Instr], text: bytes) -> str:
    out: list[str] = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    index: int
    for index in range(len(instrs)):
        ins: Instr = instrs[index]
        spec: Spec = SPEC[ins.mnem]
        word: int = int.from_bytes(text[4 * index:4 * index + 4], "little")
        shown: dict[str, str] = fields(spec, word)
        source: str = lines[ins.line - 1].strip().replace("|", "\\|")
        fence: str = "`" * max(2, 1 + max((len(run) for run in re.findall("`+", source)), default=0))
        cells: list[str] = [
            str(ins.line), f"0x{ins.addr:08x}", f"{fence} {source} {fence}", ins.mnem, f"{word:08x}", spec.fmt,
        ]
        cells += [shown.get(name, "") for name in COLUMNS[6:]]
        out.append("| " + " | ".join(cells) + " |")
    return "".join(line + "\n" for line in out)
