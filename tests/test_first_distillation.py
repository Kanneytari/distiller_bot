from decimal import Decimal

from distiller_bot.alcoholometry import correct_alcoholmeter_abv
from distiller_bot.first_distillation import (
    absolute_alcohol_l,
    containers_text,
    make_container,
    parse_blend,
    summarize,
)
from distiller_bot.first_distillation_keyboards import first_distillation_calculators_keyboard
from distiller_bot.process_stages import stage_actions_for_stage, stage_type_for_title


def test_first_and_second_distillation_are_distinct_stages() -> None:
    assert stage_type_for_title("Первая перегонка") == "first_distillation"
    assert stage_type_for_title("Вторая перегонка") == "second_distillation"


def test_first_distillation_uses_receiving_containers() -> None:
    labels = [action.label for action in stage_actions_for_stage("Первая перегонка")]
    assert labels == [
        "🫙 Ёмкости",
        "📝 Заметка",
        "🧮 Калькуляторы",
        "✅ Завершить первую перегонку",
    ]


def test_temperature_correction_is_zero_at_reference_temperature() -> None:
    assert correct_alcoholmeter_abv(Decimal("40"), Decimal("20")) == Decimal("40.0")


def test_warm_sample_is_corrected_downward() -> None:
    corrected = correct_alcoholmeter_abv(Decimal("40"), Decimal("30"))
    assert corrected == Decimal("36.0")


def test_container_stores_corrected_strength_and_absolute_alcohol() -> None:
    container = make_container(1, Decimal("2.5"), Decimal("40"), Decimal("30"))
    assert container.corrected_abv == Decimal("36.0")
    assert container.absolute_alcohol_l == Decimal("0.90")


def test_summary_uses_absolute_alcohol_for_average_strength() -> None:
    containers = [
        make_container(1, Decimal("2"), Decimal("40"), Decimal("20")),
        make_container(2, Decimal("1"), Decimal("20"), Decimal("20")),
    ]
    total_volume, average_abv, total_aa = summarize(containers)
    assert total_volume == Decimal("3.00")
    assert total_aa == Decimal("1.00")
    assert average_abv == Decimal("33.3")


def test_absolute_alcohol_calculator() -> None:
    assert absolute_alcohol_l(Decimal("7.5"), Decimal("32")) == Decimal("2.40")


def test_blend_parser_accepts_multiple_receiving_containers() -> None:
    assert parse_blend("2,5 48\n2,5 32\n1,8 18") == [
        (Decimal("2.5"), Decimal("48")),
        (Decimal("2.5"), Decimal("32")),
        (Decimal("1.8"), Decimal("18")),
    ]


def test_first_distillation_text_uses_containers_not_jars() -> None:
    text = containers_text([make_container(1, Decimal("2.5"), Decimal("40"), Decimal("20"))])
    assert "Приёмные ёмкости" in text
    assert "Сводка по ёмкостям" in text
    assert "Банк" not in text
    assert "банк" not in text


def test_first_distillation_calculator_menu_has_all_mvp_tools() -> None:
    markup = first_distillation_calculators_keyboard(42)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels[:3] == [
        "🌡 Поправка спиртометра",
        "💧 Абсолютный спирт",
        "🧪 Средняя крепость",
    ]
