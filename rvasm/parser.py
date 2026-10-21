import re
from typing import Final

from rvasm.isa import REGISTERS
from rvasm.lexer import parse_num
from rvasm.model import AsmError, Operand, Statement, Token, TokenKind

ESCAPE_RE: Final[re.Pattern[str]] = re.compile(r'\\(?:([ntr"\\])|([0-7]{1,3})|x([0-9a-fA-F]{2})|.)|[^\\]+')
SIMPLE_ESCAPES: Final[dict[str, int]] = {"n": 10, "t": 9, "r": 13, '"': 34, "\\": 92}


def decode_string(literal: str) -> bytes:
    out: bytearray = bytearray()
    mo: re.Match[str]
    for mo in ESCAPE_RE.finditer(literal[1:-1]):
        piece: str = mo.group()
        simple: str | None = mo.group(1)
        octal: str | None = mo.group(2)
        hexa: str | None = mo.group(3)
        if simple is not None:
            out.append(SIMPLE_ESCAPES[simple])
        elif octal is not None and int(octal, 8) <= 0xFF:
            out.append(int(octal, 8))
        elif hexa is not None:
            out.append(int(hexa, 16))
        elif piece[0] == "\\":
            raise AsmError(f"secuencia de escape desconocida '{piece}'")
        else:
            out += piece.encode("utf-8")
    return bytes(out)


def malformed(token: Token) -> AsmError:
    return AsmError(f"línea mal formada cerca de '{token.text}'")


def parse_group(group: list[Token]) -> Operand:
    kinds: list[TokenKind] = [t.kind for t in group]
    start: int = 1 if kinds[:1] == ["NUM"] else 0
    if kinds[start:] == ["LPAREN", "IDENT", "RPAREN"]:
        base: str = group[start + 1].text
        if base not in REGISTERS:
            raise AsmError(f"registro inexistente '{base}'")
        return Operand("mem", parse_num(group[0].text) if start else 0, REGISTERS[base])
    if kinds[0] not in ("IDENT", "NUM", "STRING"):
        raise malformed(group[0])
    if len(group) > 1:
        raise malformed(group[1])
    token: Token = group[0]
    if token.kind == "NUM":
        return Operand("num", parse_num(token.text))
    if token.kind == "STRING":
        return Operand("str", decode_string(token.text))
    if token.text in REGISTERS:
        return Operand("reg", REGISTERS[token.text])
    return Operand("sym", token.text)


def parse(line_no: int, tokens: list[Token]) -> Statement:
    labels: list[str] = []
    pos: int = 0
    while pos + 1 < len(tokens) and tokens[pos].kind == "IDENT" and tokens[pos + 1].kind == "COLON":
        labels.append(tokens[pos].text)
        pos += 2
    if pos == len(tokens):
        return Statement(line_no, tuple(labels), None, ())
    if tokens[pos].kind != "IDENT":
        raise malformed(tokens[pos])
    mnem: str = tokens[pos].text.lower()
    rest: list[Token] = tokens[pos + 1 :]
    args: list[Operand] = []
    group: list[Token] = []
    token: Token
    for token in rest:
        if token.kind != "COMMA":
            group.append(token)
        elif not group:
            raise malformed(token)
        else:
            args.append(parse_group(group))
            group.clear()
    if group:
        args.append(parse_group(group))
    elif rest:
        raise malformed(rest[-1])
    return Statement(line_no, tuple(labels), mnem, tuple(args))
