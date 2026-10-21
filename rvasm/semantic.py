from dataclasses import replace
from typing import Final, NamedTuple

from rvasm.isa import (
    DATA_BASE,
    FIXED_IMM,
    PSEUDOS,
    RANGES,
    REGISTERS,
    SIGNATURES,
    SPEC,
    TEXT_BASE,
    Signature,
    hi_lo,
    to_signed32,
)
from rvasm.model import AsmError, Diagnostic, Fixup, HiLo, Instr, Operand, OperandKind, Reloc, Statement, Unit

ACCEPTS: Final[dict[str, OperandKind]] = {
    "reg": "reg", "imm12": "num", "shamt": "num", "uimm20": "num", "li": "num", "mem": "mem", "sym": "sym",
}
EXPECTED: Final[dict[str, str]] = {
    "reg": "un registro", "imm12": "un inmediato", "shamt": "un inmediato", "uimm20": "un inmediato",
    "li": "un inmediato", "mem": "desplazamiento(registro)", "sym": "una etiqueta",
}
FOUND: Final[dict[OperandKind, str]] = {
    "reg": "el registro '{}'", "num": "el inmediato {}", "sym": "la etiqueta '{}'",
    "mem": "el acceso a memoria '{}'", "str": "la cadena {}",
}
DATA_SIZES: Final[dict[str, int]] = {".byte": 1, ".half": 2, ".word": 4}

# pseudo de una palabra -> (base, rd, rs1, rs2, imm); un campo es un nombre de la firma o un registro fijo
TEMPLATES: Final[dict[str, tuple[str, str, str, str, int]]] = {
    "nop": ("addi", "x0", "x0", "x0", 0),
    "mv": ("addi", "rd", "rs", "x0", 0),
    "not": ("xori", "rd", "rs", "x0", -1),
    "neg": ("sub", "rd", "x0", "rs", 0),
    "seqz": ("sltiu", "rd", "rs", "x0", 1),
    "snez": ("sltu", "rd", "x0", "rs", 0),
    "sltz": ("slt", "rd", "rs", "x0", 0),
    "sgtz": ("slt", "rd", "x0", "rs", 0),
    "beqz": ("beq", "x0", "rs", "x0", 0),
    "bnez": ("bne", "x0", "rs", "x0", 0),
    "blez": ("bge", "x0", "x0", "rs", 0),
    "bgez": ("bge", "x0", "rs", "x0", 0),
    "bltz": ("blt", "x0", "rs", "x0", 0),
    "bgtz": ("blt", "x0", "x0", "rs", 0),
    "bgt": ("blt", "x0", "rt", "rs", 0),
    "ble": ("bge", "x0", "rt", "rs", 0),
    "bgtu": ("bltu", "x0", "rt", "rs", 0),
    "bleu": ("bgeu", "x0", "rt", "rs", 0),
    "j": ("jal", "x0", "x0", "x0", 0),
    "jr": ("jalr", "x0", "rs", "x0", 0),
    "ret": ("jalr", "x0", "x1", "x0", 0),
}


class Bound(NamedTuple):
    ints: dict[str, int]
    symbol: str


def show(op: Operand) -> str:
    if isinstance(op.value, bytes):
        return '"' + op.value.decode("utf-8", "replace") + '"'
    if op.kind == "reg":
        return f"x{op.value}"
    if op.kind == "mem":
        return f"{op.value}(x{op.base})"
    return str(op.value)


def mismatch(index: int, mnem: str, expected: str, op: Operand) -> AsmError:
    return AsmError(f"operando {index} de '{mnem}' debe ser {expected}, se encontró {FOUND[op.kind].format(show(op))}")


def match(mnem: str, alternatives: tuple[Signature, ...], args: tuple[Operand, ...]) -> Signature:
    same: list[Signature] = [alt for alt in alternatives if len(alt) == len(args)]
    if not same:
        lists: list[str] = ["(" + ", ".join(slot[1] for slot in alt) + ")" for alt in alternatives]
        wanted: str = f"{len(alternatives[0])} operandos {lists[0]}" if len(lists) == 1 else " o ".join(lists)
        raise AsmError(f"'{mnem}' espera {wanted}, se dieron {len(args)}")
    alt: Signature
    for alt in same:
        if all(ACCEPTS[alt[i][0]] == args[i].kind for i in range(len(args))):
            return alt
    index: int
    for index in range(len(args)):
        kind: str = same[0][index][0]
        if ACCEPTS[kind] != args[index].kind:
            if kind == "reg" and args[index].kind == "sym":
                raise AsmError(f"registro inexistente '{show(args[index])}'")
            raise mismatch(index + 1, mnem, EXPECTED[kind], args[index])
    raise AssertionError("unreachable")


def check_range(kind: str, value: int, mnem: str) -> None:
    bounds: tuple[int, int] = RANGES[kind]
    if bounds[0] <= value <= bounds[1]:
        return
    what: str = {"shamt": "desplazamiento", "uimm20": f"inmediato de '{mnem}'"}.get(kind, "inmediato")
    raise AsmError(f"{what} {value} fuera de rango [{bounds[0]}, {bounds[1]}]")


def bind(mnem: str, alt: Signature, args: tuple[Operand, ...]) -> Bound:
    ints: dict[str, int] = {}
    symbols: list[str] = []
    index: int
    for index in range(len(alt)):
        kind: str = alt[index][0]
        op: Operand = args[index]
        if kind == "sym":
            symbols.append(str(op.value))
        elif kind == "mem":
            check_range("imm12", int(op.value), mnem)
            ints |= {"imm": int(op.value), "rs1": int(op.base or 0)}
        else:
            if kind != "reg":
                check_range(kind, int(op.value), mnem)
            ints |= {alt[index][1] if kind == "reg" else "imm": int(op.value)}
    return Bound(ints, symbols[0] if symbols else "")


def expand_li(line: int, rd: int, value: int) -> list[Instr]:
    signed: int = to_signed32(value)
    if RANGES["imm12"][0] <= signed <= RANGES["imm12"][1]:
        return [Instr(line, "addi", rd=rd, imm=signed)]
    parts: HiLo = hi_lo(signed)
    upper: Instr = Instr(line, "lui", rd=rd, imm=parts.hi)
    if parts.lo == 0:
        return [upper]
    return [upper, Instr(line, "addi", rd=rd, rs1=rd, imm=parts.lo)]


def far(line: int, mnem: str, symbol: str, anchor: int, base: int, rd: int, rs2: int) -> list[Instr]:
    return [
        Instr(line, "auipc", rd=base, reloc=Reloc("hi", symbol, anchor)),
        Instr(line, mnem, rd=rd, rs1=base, rs2=rs2, reloc=Reloc("lo", symbol, anchor)),
    ]


def far_form(mnem: str, args: tuple[Operand, ...]) -> bool:
    return mnem in SPEC and SPEC[mnem].shape in ("rm", "sm") and len(args) >= 2 and args[1].kind == "sym"


def expand(stmt: Statement, mnem: str, anchor: int) -> list[Instr]:
    line: int = stmt.line
    shape: str = SPEC[mnem].shape if mnem in SPEC else "pseudo"
    if shape == "sm" and len(stmt.args) == 2 and far_form(mnem, stmt.args):
        names: str = ", ".join(field[1] for field in SIGNATURES["sm"][1])
        raise AsmError(f"'{mnem}' con símbolo espera 3 operandos ({names}), se dieron 2")
    alternatives: tuple[Signature, ...] = SIGNATURES[shape] if mnem in SPEC else (PSEUDOS[mnem].signature,)
    bound: Bound = bind(mnem, match(mnem, alternatives, stmt.args), stmt.args)
    ints: dict[str, int] = bound.ints
    symbol: str = bound.symbol
    pcrel: Reloc | None = Reloc("pcrel", symbol, anchor) if symbol else None
    if far_form(mnem, stmt.args) and shape == "rm":
        return far(line, mnem, symbol, anchor, ints["rd"], ints["rd"], 0)
    if far_form(mnem, stmt.args):
        return far(line, mnem, symbol, anchor, ints["rt"], 0, ints["rs2"])
    if mnem in SPEC:
        return [
            Instr(
                line, mnem, rd=ints.get("rd", 1 if shape in ("rj", "jalr") else 0), rs1=ints.get("rs1", 0),
                rs2=ints.get("rs2", 0), imm=ints.get("imm", FIXED_IMM.get(mnem, 0)), reloc=pcrel,
            )
        ]
    if mnem == "li":
        return expand_li(line, ints["rd"], ints["imm"])
    if mnem == "la":
        return far(line, "addi", symbol, anchor, ints["rd"], ints["rd"], 0)
    if mnem == "call":
        return far(line, "jalr", symbol, anchor, 1, 1, 0)
    if mnem == "tail":
        return far(line, "jalr", symbol, anchor, 6, 0, 0)
    template: tuple[str, str, str, str, int] = TEMPLATES[mnem]
    fields: list[int] = [ints[name] if name in ints else REGISTERS[name] for name in template[1:4]]
    return [Instr(line, template[0], rd=fields[0], rs1=fields[1], rs2=fields[2], imm=template[4], reloc=pcrel)]


def reserved_size(stmt: Statement, mnem: str) -> int | None:
    args: tuple[Operand, ...] = stmt.args
    if mnem in SPEC:
        return 8 if far_form(mnem, args) else 4
    if mnem == "li":
        valid: bool = len(args) == 2 and args[1].kind == "num"
        if not valid or not RANGES["li"][0] <= int(args[1].value) <= RANGES["li"][1]:
            return None
        return 4 * len(expand_li(stmt.line, 0, int(args[1].value)))
    if mnem in PSEUDOS:
        return PSEUDOS[mnem].nominal_size
    return None


def instruction(stmt: Statement, mnem: str, section: str, pc: dict[str, int], unit: Unit) -> None:
    try:
        if mnem not in SPEC and mnem not in PSEUDOS:
            raise AsmError(f"instrucción inválida '{mnem}'")
        if section != ".text":
            raise AsmError(f"'{mnem}' solo es válido en .text")
        instrs: list[Instr] = expand(stmt, mnem, pc[".text"])
    except AsmError:
        size: int | None = reserved_size(stmt, mnem)
        unit.layout_ok &= size is not None
        pc[".text"] += 4 if size is None and mnem == "li" else size or 0
        raise
    ins: Instr
    for ins in instrs:
        unit.instrs.append(replace(ins, addr=pc[".text"]))
        pc[".text"] += 4


def datum(stmt: Statement, mnem: str, index: int, op: Operand, unit: Unit) -> bytes:
    if mnem == ".word" and op.kind == "sym":
        unit.fixups.append(Fixup(stmt.line, len(unit.data), str(op.value)))
        return bytes(4)
    if mnem == ".string":
        if not isinstance(op.value, bytes):
            raise mismatch(index, mnem, "una cadena", op)
        return op.value + b"\0"
    if op.kind != "num":
        raise mismatch(index, mnem, "un número o una etiqueta" if mnem == ".word" else "un número", op)
    size: int = DATA_SIZES[mnem]
    bounds: tuple[int, int] = RANGES[mnem[1:]]
    value: int = int(op.value)
    if not bounds[0] <= value <= bounds[1]:
        raise AsmError(f"valor {value} fuera de rango para {mnem} [{bounds[0]}, {bounds[1]}]")
    return (value & ((1 << 8 * size) - 1)).to_bytes(size, "little")


def directive(stmt: Statement, mnem: str, sections: list[str], pc: dict[str, int], unit: Unit) -> None:
    if mnem in (".text", ".data"):
        if stmt.args:
            raise AsmError(f"línea mal formada cerca de '{show(stmt.args[0])}'")
        sections.append(mnem)
        return
    if mnem in (".globl", ".global"):
        return
    if mnem not in DATA_SIZES and mnem != ".string":
        raise AsmError(f"directiva '{mnem}' desconocida")
    if sections[-1] != ".data":
        raise AsmError(f"'{mnem}' solo es válido en .data")
    if not stmt.args:
        raise AsmError(f"línea mal formada cerca de '{mnem}'")
    index: int
    for index in range(len(stmt.args)):
        chunk: bytes = datum(stmt, mnem, index + 1, stmt.args[index], unit)
        unit.data += chunk
        pc[".data"] += len(chunk)


def define_labels(stmt: Statement, address: int, defined_at: dict[str, int], unit: Unit) -> None:
    dups: list[str] = []
    label: str
    for label in stmt.labels:
        if label in defined_at:
            dups.append(label)
        else:
            defined_at |= {label: stmt.line}
            unit.symtab |= {label: address}
    if dups:
        raise AsmError(f"etiqueta '{dups[0]}' duplicada (primera definición en la línea {defined_at[dups[0]]})")


def analyze(statements: list[Statement | None]) -> Unit:
    unit: Unit = Unit()
    # lista que solo crece porque la regla de tipado prohíbe reasignar; la sección vigente es la última
    sections: list[str] = [".text"]
    pc: dict[str, int] = {".text": TEXT_BASE, ".data": DATA_BASE}
    defined_at: dict[str, int] = {}
    stmt: Statement | None
    for stmt in statements:
        unit.layout_ok &= stmt is not None
        if stmt is None:
            continue
        try:
            define_labels(stmt, pc[sections[-1]], defined_at, unit)
        except AsmError as e:
            unit.errors.append(Diagnostic(stmt.line, str(e)))
        if stmt.mnem is None:
            continue
        try:
            if stmt.mnem.startswith("."):
                directive(stmt, stmt.mnem, sections, pc, unit)
            else:
                instruction(stmt, stmt.mnem, sections[-1], pc, unit)
        except AsmError as e:
            unit.errors.append(Diagnostic(stmt.line, str(e)))
    return unit
