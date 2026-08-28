from decimal import Decimal

from distiller_bot.models import Drink, Measurement
from distiller_bot.processes import (
    measurement_types_for_stage,
    parse_measurement_value,
    process_card_text,
    process_short_label,
)


def make_process(*, name: str, stage: str) -> Drink:
    return Drink(user_id=1, name=name, current_stage=stage, status="active")


def test_process_card_escapes_user_text() -> None:
    process = make_process(name="<Моя брага>", stage="Этап <1>")

    text = process_card_text(process)

    assert "&lt;Моя брага&gt;" in text
    assert "Этап &lt;1&gt;" in text


def test_process_button_label_is_short_enough() -> None:
    process = make_process(name="Очень длинное название " * 10, stage="Очень длинный этап " * 10)

    label = process_short_label(process)

    assert len(label) <= 60
    assert label.endswith("…")


def test_fermentation_prioritizes_density_and_temperature() -> None:
    types = measurement_types_for_stage("Брожение")

    assert [measurement_type for measurement_type, _label in types[:2]] == [
        "density",
        "temperature",
    ]


def test_measurement_value_accepts_comma_and_default_unit() -> None:
    parsed = parse_measurement_value("1,026", "SG")

    assert parsed == (Decimal("1.026"), "SG")


def test_measurement_value_accepts_explicit_unit() -> None:
    parsed = parse_measurement_value("42 %", "%")

    assert parsed == (Decimal("42"), "%")


def test_process_card_shows_latest_measurement() -> None:
    process = make_process(name="Сахарная брага", stage="Брожение")
    measurement = Measurement(
        drink_id=1,
        measurement_type="density",
        value=Decimal("1.0260"),
        unit="SG",
        label="Плотность",
    )

    text = process_card_text(process, measurement)

    assert "Последний замер:" in text
    assert "📏 Плотность: 1.026 SG" in text
