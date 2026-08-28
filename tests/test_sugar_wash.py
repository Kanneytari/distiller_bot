from decimal import Decimal

from distiller_bot.keyboards import (
    process_card_keyboard,
    sugar_wash_menu_keyboard,
    sugar_wash_result_keyboard,
)
from distiller_bot.preparation_calculators import parse_positive_decimal
from distiller_bot.preparation_composition import parse_positive_decimal as parse_composition_decimal
from distiller_bot.process_stages import stage_actions_for_stage
from distiller_bot.sugar_wash import (
    calculate_by_sugar,
    calculate_by_volume,
    calculate_from_composition,
    result_text,
)


def test_calculate_sugar_wash_by_target_volume() -> None:
    result = calculate_by_volume(Decimal("25"), Decimal("12"))

    assert result.sugar_kg == Decimal("5.10")
    assert result.water_l == Decimal("21.94")
    assert result.volume_l == Decimal("25.00")
    assert result.potential_abv == Decimal("12.0")


def test_calculate_sugar_wash_by_available_sugar() -> None:
    result = calculate_by_sugar(Decimal("5.1"), Decimal("12"))

    assert result.sugar_kg == Decimal("5.10")
    assert result.water_l == Decimal("21.94")
    assert result.volume_l == Decimal("25.00")
    assert result.potential_abv == Decimal("12.0")


def test_check_composition_matches_forward_calculation() -> None:
    result = calculate_from_composition(Decimal("21.94"), Decimal("5.1"))

    assert result.volume_l == Decimal("25.00")
    assert result.potential_abv == Decimal("12.0")


def test_high_potential_abv_shows_warning() -> None:
    result = calculate_by_volume(Decimal("25"), Decimal("20"))

    text = result_text(result)

    assert "Сахарная нагрузка высокая" in text
    assert "Фактическая крепость зависит" in text


def test_numeric_input_accepts_comma_and_rejects_non_finite_values() -> None:
    assert parse_positive_decimal("5,5") == Decimal("5.5")
    assert parse_positive_decimal("0") is None
    assert parse_positive_decimal("NaN") is None
    assert parse_positive_decimal("Infinity") is None


def test_manual_composition_uses_same_numeric_rules() -> None:
    assert parse_composition_decimal("21,9") == Decimal("21.9")
    assert parse_composition_decimal("0") is None
    assert parse_composition_decimal("NaN") is None


def test_preparation_calculator_routes_to_sugar_wash_mvp() -> None:
    actions = [
        (action.key, action.label)
        for action in stage_actions_for_stage("Подготовка")
    ]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]
    calculators = next(button for button in buttons if button.text == "🧮 Калькуляторы")

    assert calculators.callback_data == "process:sugar-wash:42"


def test_other_stage_calculator_keeps_existing_placeholder_route() -> None:
    actions = [
        (action.key, action.label)
        for action in stage_actions_for_stage("Брожение")
    ]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]
    calculators = next(button for button in buttons if button.text == "🧮 Калькуляторы")

    assert calculators.callback_data == "process:calculators:42"


def test_sugar_wash_menu_has_three_modes_and_back_to_process() -> None:
    markup = sugar_wash_menu_keyboard(42)
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]

    assert callbacks == [
        "process:sugar-wash:42:volume",
        "process:sugar-wash:42:sugar",
        "process:sugar-wash:42:check",
        "process:view:42",
    ]


def test_process_calculation_result_is_applied_without_save_button() -> None:
    markup = sugar_wash_result_keyboard(42)
    buttons = [button for row in markup.inline_keyboard for button in row]

    assert all(button.text != "💾 Сохранить" for button in buttons)
    assert [button.callback_data for button in buttons] == [
        "process:sugar-wash:42",
        "process:view:42",
    ]
