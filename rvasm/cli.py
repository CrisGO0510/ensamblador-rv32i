import sys
from operator import attrgetter
from pathlib import Path
from typing import Final, NamedTuple

from rvasm.codegen import generate
from rvasm.lexer import tokenize
from rvasm.listing import listing
from rvasm.model import AsmError, Diagnostic, Image, Instr, Statement, Unit
from rvasm.parser import parse
from rvasm.semantic import analyze

USAGE: Final[str] = "uso: python assembler.py programa.asm programa.hex [programa.data.hex] [--datos] [--listado]"


class AsmResult(NamedTuple):
    image: Image
    errors: list[Diagnostic]
    instrs: list[Instr]


def pack_words(data: bytes) -> list[str]:
    padded: bytes = data + bytes(-len(data) % 4)
    return [f"{int.from_bytes(padded[i:i + 4], 'little'):08x}" for i in range(0, len(padded), 4)]


def assemble_lines(lines: list[str]) -> AsmResult:
    statements: list[Statement | None] = []
    errors: list[Diagnostic] = []
    number: int
    for number in range(1, len(lines) + 1):
        try:
            statements.append(parse(number, tokenize(lines[number - 1])))
        except AsmError as e:
            errors.append(Diagnostic(number, str(e)))
            statements.append(None)
    unit: Unit = analyze(statements)
    image: Image = generate(unit)
    return AsmResult(image, sorted(errors + unit.errors, key=attrgetter("line")), unit.instrs)


def words_text(data: bytes) -> str:
    return "".join(w + "\n" for w in pack_words(data))


class CliError(Exception):
    pass


def reason(e: OSError) -> str:
    return e.strerror or str(e)


def parse_args(argv: list[str]) -> tuple[list[str], list[str]]:
    flags: list[str] = [a for a in argv[1:] if a.startswith("--")]
    positional: list[str] = [a for a in argv[1:] if not a.startswith("--")]
    if any(f not in ("--datos", "--listado") for f in flags) or len(positional) not in (2, 3):
        raise CliError(USAGE)
    if "--datos" in flags and len(positional) == 3:
        raise CliError("assembler.py: error: --datos y un tercer argumento no van juntos")
    return flags, positional


def plan_outputs(flags: list[str], outputs: list[str]) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = list(zip(outputs, ["text", "data"]))
    base: str = outputs[0].removesuffix(".hex")
    if "--datos" in flags:
        plan.append((base + ".data.hex", "data"))
    if "--listado" in flags:
        plan.append((base + ".md", "listing"))
    return plan


def check_distinct(source: str, outputs: list[str]) -> None:
    path: str
    for path in outputs:
        if Path(path).resolve() == Path(source).resolve():
            raise CliError(f"assembler.py: error: la salida '{path}' es el mismo archivo que la entrada")
    i: int
    j: int
    for i in range(len(outputs)):
        for j in range(i + 1, len(outputs)):
            if Path(outputs[i]).resolve() == Path(outputs[j]).resolve():
                raise CliError(f"assembler.py: error: las salidas '{outputs[i]}' y '{outputs[j]}' son el mismo archivo")


def read_source(source: str) -> str:
    try:
        return Path(source).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise CliError(f"assembler.py: error: no se puede leer '{source}': {reason(e)}")
    except UnicodeDecodeError:
        raise CliError(f"assembler.py: error: no se puede leer '{source}': no es UTF-8 válido")


def report_errors(source: str, errors: list[Diagnostic], outputs: list[str]) -> int:
    diag: Diagnostic
    for diag in errors:
        print(f"{source}:{diag.line}: error: {diag.msg}", file=sys.stderr)
    undeleted: list[str] = []
    path: str
    for path in outputs:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as e:
            print(f"assembler.py: error: no se puede borrar '{path}': {reason(e)}", file=sys.stderr)
            undeleted.append(path)
    return 2 if undeleted else 1


def write_outputs(plan: list[tuple[str, str]], rendered: dict[str, str]) -> None:
    index: int
    for index in range(len(plan)):
        try:
            Path(plan[index][0]).write_text(rendered[plan[index][1]], encoding="utf-8")
        except OSError as e:
            # una salida a medias no debe quedar junto a las demás
            done: tuple[str, str]
            for done in plan[:index]:
                try:
                    Path(done[0]).unlink(missing_ok=True)
                except OSError:
                    pass
            raise CliError(f"assembler.py: error: no se puede escribir '{plan[index][0]}': {reason(e)}")


def assemble_file(flags: list[str], positional: list[str]) -> int:
    source: str = positional[0]
    plan: list[tuple[str, str]] = plan_outputs(flags, positional[1:])
    outputs: list[str] = [entry[0] for entry in plan]
    check_distinct(source, outputs)
    lines: list[str] = read_source(source).split("\n")
    result: AsmResult = assemble_lines(lines)
    if result.errors:
        return report_errors(source, result.errors, outputs)
    write_outputs(plan, {
        "text": words_text(result.image.text),
        "data": words_text(result.image.data),
        "listing": listing(lines, result.instrs, result.image.text) if "--listado" in flags else "",
    })
    return 0


def main(argv: list[str]) -> int:
    try:
        return assemble_file(*parse_args(argv))
    except CliError as e:
        print(e, file=sys.stderr)
        return 2
