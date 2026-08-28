import ast
from pathlib import Path


EM_DASH = chr(0x2014)
SOURCE_DIR = Path(__file__).resolve().parents[1] / "distiller_bot"


def test_ui_strings_do_not_use_em_dash() -> None:
    violations: list[str] = []

    for path in sorted(SOURCE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if EM_DASH in node.value:
                violations.append(f"{path.name}:{node.lineno}")

    assert not violations, (
        "Unicode em dash (U+2014) is forbidden in bot string literals. "
        "Use '-' instead. Found: " + ", ".join(violations)
    )
