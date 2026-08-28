from pathlib import Path


EM_DASH = chr(0x2014)
SOURCE_DIR = Path(__file__).resolve().parents[1] / "distiller_bot"


def test_bot_source_does_not_use_em_dash() -> None:
    violations: list[str] = []

    for path in sorted(SOURCE_DIR.glob("*.py")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if EM_DASH in line:
                violations.append(f"{path.name}:{line_number}")

    assert not violations, (
        "Unicode em dash (U+2014) is forbidden in bot source. "
        "Use '-' instead. Found: " + ", ".join(violations)
    )
