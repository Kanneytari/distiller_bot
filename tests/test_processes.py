from decimal import Decimal

import distiller_bot.fermentation_integration  # noqa: F401
import distiller_bot.second_distillation_integration  # noqa: F401
import distiller_bot.drink_preparation_integration  # noqa: F401
from distiller_bot.keyboards import process_calculators_keyboard, process_card_keyboard
from distiller_bot.models import Drink, DrinkEvent, Measurement
from distiller_bot.process_stages import stage_actions_for_stage, stage_icon, stage_type_for_title
from distiller_bot.processes import (
    NOTE_PREVIEW_LIMIT,
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
        "✏️ Состав",
        "📝 Заметка",
        "🧮 Калькуляторы",
        "✅ Завершить этап",
    ]


def test_fermentation_actions_replace_preparation_actions() -> None:
    assert stage_icon("Брожение") == "🫧"
    assert action_labels("Брожение") == [
        "🌡 Температура",
        "🧪 Крепость по Brix",
        "📝 Заметка",
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
        "💧 Разбавление",
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


def test_preparation_composition_routes_to_current_process() -> None:
    actions = [(action.key, action.label) for action in stage_actions_for_stage("Подготовка")]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]

    composition = next(button for button in buttons if button.text == "✏️ Состав")
    assert composition.callback_data == "process:composition:42"


def test_fermentation_keyboard_routes_dedicated_actions() -> None:
    actions = [(action.key, action.label) for action in stage_actions_for_stage("Брожение")]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]

    temperature = next(button for button in buttons if button.text == "🌡 Температура")
    brix = next(button for button in buttons if button.text == "🧪 Крепость по Brix")
    assert temperature.callback_data == "process:fermentation-temperature:42"
    assert brix.callback_data == "process:fermentation-brix:42"


def test_drink_preparation_keyboard_routes_dilution() -> None:
    actions = [
        (action.key, action.label)
        for action in stage_actions_for_stage("Подготовка напитка")
    ]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]

    dilution = next(button for button in buttons if button.text == "💧 Разбавление")
    assert dilution.callback_data == "process:drink-preparation:42"


def test_calculators_placeholder_has_back_to_drink() -> None:
    assert PROCESS_CALCULATORS_TEXT == (
        "🧮 <b>Калькуляторы</b>\n\n"
        "Здесь будут доступны расчёты, подходящие для текущего этапа."
    )

    markup = process_calculators_keyboard(42)
    button = markup.inline_keyboard[0][0]
    assert button.text == "← К напитку"
    assert button.callback_data == "process:view:42"


def test_fermentation_measurements_only_offer_temperature() -> None:
    types = measurement_types_for_stage("Брожение")

    assert [measurement_type for measurement_type, _label in types] == ["temperature"]


def test_no_stage_offers_density_measurement() -> None:
    for stage in ["Подготовка", "Брожение", "Перегонка", "Подготовка напитка", "Розлив"]:
        assert all(
            measurement_type != "density"
            for measurement_type, _label in measurement_types_for_stage(stage)
        )


def test_repeated_distillation_keeps_distillation_measurement_order() -> None:
    types = measurement_types_for_stage("Перегонка #2")

    assert [measurement_type for measurement_type, _label in types[:2]] == ["abv", "volume"]


def test_quick_measurements_change_with_stage() -> None:
    assert quick_measurements_for_stage("Подготовка") == []
    assert quick_measurements_for_stage("Брожение") == []
    assert quick_measurements_for_stage("Подготовка напитка") == []
    assert quick_measurements_for_stage("Готово") == [
        ("abv", "🥃 Итоговая крепость"),
        ("volume", "💧 Итоговый объём"),
    ]


def test_custom_stage_has_no_forced_quick_measurements() -> None:
    assert quick_measurements_for_stage("Мой этап") == []


def test_preparation_card_has_no_measurement_hint() -> None:
    process = make_process(name="Сахарная брага", stage="Подготовка")

    text = process_card_text(process)

    assert "Сейчас может пригодиться:" not in text


def test_fermentation_card_has_no_redundant_measurement_hint() -> None:
    process = make_process(name="Сахарная брага", stage="Брожение")

    text = process_card_text(process)

    assert "Сейчас может пригодиться:" not in text


def test_measurement_value_accepts_comma_and_default_unit() -> None:
    parsed = parse_measurement_value("24,5", "°C")

    assert parsed == (Decimal("24.5"), "°C")


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
        measurement_type="temperature",
        value=Decimal("24.0000"),
        unit="°C",
        label="Температура",
    )

    text = process_card_text(process, measurement)

    assert "Последний замер:" in text
    assert "🌡 Температура: 24 °C" in text


def test_process_card_shows_latest_note_and_escapes_it() -> None:
    process = make_process(name="Сахарная брага", stage="Брожение")
    note = DrinkEvent(
        drink_id=1,
        event_type="note",
        title="Заметка",
        text="Проверить <температуру> завтра",
    )

    text = process_card_text(process, latest_note=note)

    assert "📝 <b>Последняя заметка:</b>" in text
    assert "Проверить &lt;температуру&gt; завтра" in text


def test_process_card_truncates_long_note_preview() -> None:
    process = make_process(name="Сахарная брага", stage="Брожение")
    note = DrinkEvent(
        drink_id=1,
        event_type="note",
        title="Заметка",
        text="А" * (NOTE_PREVIEW_LIMIT + 100),
    )

    text = process_card_text(process, latest_note=note)
    note_block = text.split("📝 <b>Последняя заметка:</b>\n", 1)[1].split("\n\n", 1)[0]

    assert len(note_block) == NOTE_PREVIEW_LIMIT
    assert note_block.endswith("…")
