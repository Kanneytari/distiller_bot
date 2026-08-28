from decimal import Decimal

from distiller_bot.keyboards import process_calculators_keyboard, process_card_keyboard
from distiller_bot.models import Drink, Measurement
from distiller_bot.process_stages import stage_actions_for_stage, stage_icon, stage_type_for_title
from distiller_bot.processes import (
    PROCESS_CALCULATORS_TEXT,
    format_decimal,
    measurement_types_for_stage,
    parse_measurement_value,
    process_card_text,
    process_short_label,
    quick_measurements_for_stage,
)


def make_process(*, name: str, stage: str) -> Drink:
    return Drink(user_id=1, name=name, current_stage=stage, status="active")


def action_labels(stage: str) -> list[str]:
    return [action.label for action in stage_actions_for_stage(stage)]


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


def test_preparation_process_has_contextual_actions() -> None:
    process = make_process(name="Сахарная брага", stage="Подготовка")

    text = process_card_text(process)

    assert "Этап: 🧰 Подготовка" in text
    assert action_labels("Подготовка") == [
        "📏 Добавить данные",
        "📝 Заметка",
        "🧮 Калькуляторы",
        "✅ Завершить этап",
    ]


def test_fermentation_actions_replace_preparation_actions() -> None:
    assert stage_icon("Брожение") == "🫧"
    assert action_labels("Брожение") == [
        "📏 Добавить измерение",
        "📝 Заметка",
        "🧮 Калькуляторы",
        "✅ Завершить брожение",
    ]


def test_distillation_actions_are_contextual() -> None:
    assert stage_icon("Перегонка") == "⚗️"
    assert action_labels("Перегонка") == [
        "📏 Записать результат",
        "📝 Заметка",
        "🧮 Калькуляторы",
        "✅ Завершить перегонку",
    ]


def test_repeated_distillation_uses_same_stage_type_without_unique_stage_assumption() -> None:
    assert stage_type_for_title("Перегонка #1") == "distillation"
    assert stage_type_for_title("Перегонка #2") == "distillation"
    assert action_labels("Перегонка #2") == action_labels("Перегонка")


def test_drink_preparation_action_order_matches_ui_spec() -> None:
    assert action_labels("Подготовка напитка") == [
        "📏 Параметры напитка",
        "🧮 Калькуляторы",
        "📝 Заметка",
        "✅ Завершить этап",
    ]


def test_bottling_has_no_calculators_and_can_finish_process() -> None:
    assert stage_icon("Розлив") == "🍾"
    assert action_labels("Розлив") == [
        "📏 Записать результат",
        "📝 Заметка",
        "✅ Завершить процесс",
    ]


def test_process_keyboard_routes_calculators_to_current_process() -> None:
    actions = [(action.key, action.label) for action in stage_actions_for_stage("Брожение")]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]

    calculators = next(button for button in buttons if button.text == "🧮 Калькуляторы")
    assert calculators.callback_data == "process:calculators:42"


def test_calculators_placeholder_has_back_to_process() -> None:
    assert PROCESS_CALCULATORS_TEXT == (
        "🧮 <b>Калькуляторы</b>\n\n"
        "Здесь будут доступны расчёты, подходящие для текущего этапа."
    )

    markup = process_calculators_keyboard(42)
    button = markup.inline_keyboard[0][0]
    assert button.text == "← К процессу"
    assert button.callback_data == "process:view:42"


def test_fermentation_prioritizes_density_and_temperature() -> None:
    types = measurement_types_for_stage("Брожение")

    assert [measurement_type for measurement_type, _label in types[:2]] == [
        "density",
        "temperature",
    ]


def test_repeated_distillation_keeps_distillation_measurement_order() -> None:
    types = measurement_types_for_stage("Перегонка #2")

    assert [measurement_type for measurement_type, _label in types[:2]] == ["abv", "volume"]


def test_quick_measurements_change_with_stage() -> None:
    assert quick_measurements_for_stage("Подготовка") == [
        ("volume", "💧 Объём"),
        ("density", "📏 Начальная плотность"),
    ]
    assert quick_measurements_for_stage("Брожение") == [
        ("density", "📏 Плотность"),
        ("temperature", "🌡 Температура"),
    ]
    assert quick_measurements_for_stage("Готово") == [
        ("abv", "🥃 Итоговая крепость"),
        ("volume", "💧 Итоговый объём"),
    ]


def test_custom_stage_has_no_forced_quick_measurements() -> None:
    assert quick_measurements_for_stage("Мой этап") == []


def test_process_card_shows_contextual_suggestions() -> None:
    process = make_process(name="Сахарная брага", stage="Брожение")

    text = process_card_text(process)

    assert "Сейчас может пригодиться:" in text
    assert "📏 Плотность · 🌡 Температура" in text


def test_measurement_value_accepts_comma_and_default_unit() -> None:
    parsed = parse_measurement_value("1,026", "SG")

    assert parsed == (Decimal("1.026"), "SG")


def test_measurement_value_accepts_explicit_unit() -> None:
    parsed = parse_measurement_value("42 %", "%")

    assert parsed == (Decimal("42"), "%")


def test_whole_number_measurement_keeps_trailing_zeroes() -> None:
    assert format_decimal(Decimal("40")) == "40"
    assert format_decimal(Decimal("100")) == "100"
    assert format_decimal(Decimal("40.5000")) == "40.5"


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
