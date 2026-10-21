import ast
import unittest
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def source_files() -> list[Path]:
    return (
        [ROOT / "assembler.py"]
        + sorted((ROOT / "rvasm").rglob("*.py"))
        + sorted((ROOT / "tests").rglob("*.py"))
    )


def unannotated_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    positional: list[ast.arg] = node.args.posonlyargs + node.args.args
    skip: int = 1 if positional and positional[0].arg in ("self", "cls") else 0
    starred: list[ast.arg] = [a for a in (node.args.vararg, node.args.kwarg) if a is not None]
    candidates: list[ast.arg] = positional[skip:] + node.args.kwonlyargs + starred
    return [a.arg for a in candidates if a.annotation is None]


def violations(source: str, name: str) -> list[str]:
    found: list[tuple[int, str]] = []
    node: ast.AST
    for node in ast.walk(ast.parse(source, filename=name)):
        if isinstance(node, ast.Assign):
            found.append((node.lineno, "asignación sin anotación"))
        elif isinstance(node, ast.Lambda):
            found.append((node.lineno, "lambda"))
        elif isinstance(node, ast.NamedExpr):
            found.append((node.lineno, "operador walrus"))
        elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, (ast.Tuple, ast.List)):
            found.append((node.lineno, "desempaquetado en for"))
        elif isinstance(node, ast.comprehension) and isinstance(node.target, (ast.Tuple, ast.List)):
            found.append((node.target.lineno, "desempaquetado en comprensión"))
        elif isinstance(node, ast.withitem) and isinstance(node.optional_vars, (ast.Tuple, ast.List)):
            found.append((node.optional_vars.lineno, "desempaquetado en with"))
        elif isinstance(node, ast.MatchSequence):
            found.append((node.lineno, "desempaquetado en match"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is None:
                found.append((node.lineno, f"{node.name} sin anotación de retorno"))
            missing: list[str] = unannotated_args(node)
            if missing:
                found.append((node.lineno, f"{node.name} sin anotar: {', '.join(missing)}"))
        elif isinstance(node, ast.Name) and node.id == "Any":
            found.append((node.lineno, "uso de Any"))
        elif isinstance(node, ast.Attribute) and node.attr == "Any":
            found.append((node.lineno, "uso de Any"))
        elif isinstance(node, ast.alias) and node.name == "Any":
            found.append((node.lineno, "import de Any"))
    return [f"{name}:{v[0]}: {v[1]}" for v in sorted(found)]


class TypingGateTest(unittest.TestCase):
    def test_rules_flag_exactly_the_forbidden_forms(self) -> None:
        # Arrange
        cases: list[tuple[str, int]] = [
            ("x = 1\n", 1),
            ("f: object = lambda: 0\n", 1),
            ("a: int\nb: int\nfor a, b in []:\n    pass\n", 1),
            ("c: list[int] = [p for p, q in []]\n", 1),
            ("def h(x: int):\n    pass\n", 1),
            ("def g(x) -> None:\n    pass\n", 1),
            ("x: Any = 0\n", 1),
            ("from typing import Any\n", 1),
            ("if (n := 1):\n    pass\n", 1),
            ("with open('f') as (a, b):\n    pass\n", 1),
            ("x: int\n", 0),
            ("x: int = 0\nx += 1\n", 0),
            ("with open('f') as f:\n    pass\n", 0),
            ("try:\n    pass\nexcept ValueError as e:\n    pass\n", 0),
            ("class C:\n    def m(self, z: int) -> None:\n        pass\n", 0),
            ("c: list[int] = [p for p in []]\n", 0),
        ]
        case: tuple[str, int]
        for case in cases:
            with self.subTest(source=case[0]):
                # Act
                found: list[str] = violations(case[0], "frag.py")

                # Assert
                self.assertEqual(len(found), case[1], "\n".join(found))

    def test_source_is_fully_annotated(self) -> None:
        # Arrange
        files: list[Path] = source_files()

        # Act
        found: list[str] = [
            v for f in files for v in violations(f.read_text(encoding="utf-8"), f.relative_to(ROOT).as_posix())
        ]

        # Assert
        self.assertEqual(len(found), 0, "\n".join(found))
