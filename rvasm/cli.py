import sys
from operator import attrgetter
from pathlib import Path
from typing import Final, NamedTuple

from rvasm.codegen import generate
from rvasm.lexer import tokenize
from rvasm.model import AsmError, Diagnostic, Image, Statement, Unit
from rvasm.parser import parse
from rvasm.semantic import analyze

USAGE: Final[str] = "uso: python assembler.py programa.asm programa.hex [programa.data.hex]"


class AsmResult(NamedTuple):
    image: Image
    errors: list[Diagnostic]


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
    return AsmResult(image, sorted(errors + unit.errors, key=attrgetter("line")))


def write_words(path: str, data: bytes) -> None:
    Path(path).write_text("".join(w + "\n" for w in pack_words(data)), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(USAGE, file=sys.stderr)
        return 2
    source: str = argv[1]
    outputs: list[str] = argv[2:]
    path: str
    for path in outputs:
        if Path(path).resolve() == Path(source).resolve():
            print(f"assembler.py: error: la salida '{path}' es el mismo archivo que la entrada", file=sys.stderr)
            return 2
    if len(outputs) == 2 and Path(outputs[0]).resolve() == Path(outputs[1]).resolve():
        print(f"assembler.py: error: las salidas '{outputs[0]}' y '{outputs[1]}' son el mismo archivo", file=sys.stderr)
        return 2
    try:
        text: str = Path(source).read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"assembler.py: error: no se puede leer '{source}': {e.strerror or str(e)}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print(f"assembler.py: error: no se puede leer '{source}': no es UTF-8 válido", file=sys.stderr)
        return 2
    result: AsmResult = assemble_lines(text.split("\n"))
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
    contents: list[bytes] = [result.image.text, result.image.data]
    index: int
    for index in range(len(outputs)):
        try:
            write_words(outputs[index], contents[index])
        except OSError as e:
            print(
                f"assembler.py: error: no se puede escribir '{outputs[index]}': {e.strerror or str(e)}",
                file=sys.stderr,
            )
            # un .hex sin su .data.hex dejaría una salida a medias
            for path in outputs[:index]:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
            return 2
    return 0
