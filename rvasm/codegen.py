import struct
from dataclasses import replace

from rvasm.isa import ENCODERS, RANGES, SPEC, Spec, hi_lo
from rvasm.model import AsmError, Diagnostic, Fixup, Image, Instr, Reloc, Unit


def lookup(unit: Unit, symbol: str) -> int:
    if symbol not in unit.symtab:
        raise AsmError(f"etiqueta '{symbol}' no definida")
    return unit.symtab[symbol]


def resolve(unit: Unit, ins: Instr, spec: Spec, reloc: Reloc) -> int:
    off: int = lookup(unit, reloc.symbol) - reloc.anchor
    if reloc.kind == "hi":
        return hi_lo(off).hi
    if reloc.kind == "lo":
        return hi_lo(off).lo
    if not unit.layout_ok:
        return off
    if off % 2:
        raise AsmError(f"destino '{reloc.symbol}' de '{ins.mnem}' en dirección impar")
    bounds: tuple[int, int] = RANGES["pcrel_b" if spec.fmt == "B" else "pcrel_j"]
    if not bounds[0] <= off <= bounds[1]:
        raise AsmError(
            f"destino '{reloc.symbol}' de '{ins.mnem}' a {off:+d} bytes fuera de rango [{bounds[0]}, {bounds[1]}]"
        )
    return off


def report(unit: Unit, diag: Diagnostic) -> None:
    # el auipc y su compañera, o dos operandos de un .word, comparten etiqueta: sin esto el error saldría repetido
    if not unit.errors or unit.errors[-1] != diag:
        unit.errors.append(diag)


def immediate(unit: Unit, ins: Instr, spec: Spec) -> int:
    if ins.reloc is None:
        return ins.imm
    try:
        return resolve(unit, ins, spec, ins.reloc)
    except AsmError as e:
        report(unit, Diagnostic(ins.line, str(e)))
        return 0


def generate(unit: Unit) -> Image:
    """Codifica las instrucciones y aplica los fixups de .data; los errores se agregan a unit.errors."""
    text: bytearray = bytearray()
    ins: Instr
    for ins in unit.instrs:
        spec: Spec = SPEC[ins.mnem]
        text += ENCODERS[spec.fmt](spec, replace(ins, imm=immediate(unit, ins, spec))).to_bytes(4, "little")
    fix: Fixup
    for fix in unit.fixups:
        try:
            struct.pack_into("<I", unit.data, fix.offset, lookup(unit, fix.symbol) & 0xFFFFFFFF)
        except AsmError as e:
            report(unit, Diagnostic(fix.line, str(e)))
    return Image(bytes(text), bytes(unit.data))
