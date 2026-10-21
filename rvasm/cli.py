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


def main(argv: list[str]) -> int:
    flags: list[str] = [a for a in argv[1:] if a.startswith("--")]
    positional: list[str] = [a for a in argv[1:] if not a.startswith("--")]
    if any(f not in ("--datos", "--listado") for f in flags) or len(positional) not in (2, 3):
        print(USAGE, file=sys.stderr)
        return 2
    if "--datos" in flags and len(positional) == 3:
        print("assembler.py: error: --datos y un tercer argumento no van juntos", file=sys.stderr)
        return 2
    source: str = positional[0]
    outputs: list[str] = positional[1:]
    kinds: list[str] = ["text", "data"][:len(outputs)]
    base: str = outputs[0].removesuffix(".hex")
    if "--datos" in flags:
        outputs.append(base + ".data.hex")
        kinds.append("data")
    if "--listado" in flags:
        outputs.append(base + ".md")
        kinds.append("listing")
    path: str
    for path in outputs:
        if Path(path).resolve() == Path(source).resolve():
            print(f"assembler.py: error: la salida '{path}' es el mismo archivo que la entrada", file=sys.stderr)
            return 2
    i: int
    j: int
    for i in range(len(outputs)):
        for j in range(i + 1, len(outputs)):
            if Path(outputs[i]).resolve() == Path(outputs[j]).resolve():
                print(f"assembler.py: error: las salidas '{outputs[i]}' y '{outputs[j]}' son el mismo archivo", file=sys.stderr)
                return 2
    try:
        text: str = Path(source).read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"assembler.py: error: no se puede leer '{source}': {e.strerror or str(e)}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print(f"assembler.py: error: no se puede leer '{source}': no es UTF-8 válido", file=sys.stderr)
        return 2
    lines: list[str] = text.split("\n")
    result: AsmResult = assemble_lines(lines)
    if result.errors:
        undeleted: list[str] = []
        diag: Diagnostic
        for diag in result.errors:
            print(f"{source}:{diag.line}: error: {diag.msg}", file=sys.stderr)
        for path in outputs:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError as e:
                print(f"assembler.py: error: no se puede borrar '{path}': {e.strerror or str(e)}", file=sys.stderr)
                undeleted.append(path)
        return 2 if undeleted else 1
    rendered: dict[str, str] = {
        "text": words_text(result.image.text),
        "data": words_text(result.image.data),
        "listing": listing(lines, result.instrs, result.image.text) if "--listado" in flags else "",
    }
    index: int
    for index in range(len(outputs)):
        try:
            Path(outputs[index]).write_text(rendered[kinds[index]], encoding="utf-8")
        except OSError as e:
            print(
                f"assembler.py: error: no se puede escribir '{outputs[index]}': {e.strerror or str(e)}",
                file=sys.stderr,
            )
            # una salida a medias no debe quedar junto a las demás
            for path in outputs[:index]:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
            return 2
    return 0
