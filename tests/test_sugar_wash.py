from decimal import Decimal

from distiller_bot.keyboards import process_card_keyboard
from distiller_bot.preparation_calculators import parse_positive_decimal
from distiller_bot.preparation_composition import parse_positive_decimal as parse_composition_decimal
from distiller_bot.preparation_keyboards import (
    process_sugar_wash_fermentable_keyboard,
    process_sugar_wash_menu_keyboard,
    process_sugar_wash_result_keyboard,
)
from distiller_bot.process_stages import stage_actions_for_stage
from distiller_bot.sugar_wash import (
    calculate_by_sugar,
    calculate_by_volume,
    calculate_from_composition,
    recalculate_abv,
    recalculate_amount,
    recalculate_fermentable,
    recalculate_volume,
    recalculate_water,
    result_from_event_data,
    result_text,
)


def button_callbacks(markup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_calculate_wash_by_target_volume_defaults_to_sucrose() -> None:
    result = calculate_by_volume(Decimal("25"), Decimal("12"))

    assert result.fermentable == "sucrose"
    assert result.sugar_kg == Decimal("5.10")
    assert result.water_l == Decimal("21.94")
    assert result.volume_l == Decimal("25.00")
    assert result.potential_abv == Decimal("12.0")


def test_glucose_and_fructose_require_more_mass_than_sucrose_for_same_target() -> None:
    sucrose = calculate_by_volume(Decimal("25"), Decimal("12"), "sucrose")
    glucose = calculate_by_volume(Decimal("25"), Decimal("12"), "glucose")
    fructose = calculate_by_volume(Decimal("25"), Decimal("12"), "fructose")

    assert sucrose.sugar_kg == Decimal("5.10")
    assert glucose.sugar_kg == Decimal("5.37")
    assert fructose.sugar_kg == Decimal("5.37")
    assert glucose.sugar_kg > sucrose.sugar_kg
    assert glucose.water_l == Decimal("21.78")


def test_calculate_wash_by_available_fermentable() -> None:
    result = calculate_by_sugar(Decimal("5.37"), Decimal("12"), "glucose")

    assert result.fermentable == "glucose"
    assert result.volume_l == Decimal("25.00")
    assert result.water_l == Decimal("21.78")


def test_check_composition_uses_selected_fermentable() -> None:
    glucose = calculate_from_composition(Decimal("21.78"), Decimal("5.37"), "glucose")
    sucrose = calculate_from_composition(Decimal("21.78"), Decimal("5.37"), "sucrose")

    assert glucose.volume_l == Decimal("25.00")
    assert glucose.potential_abv == Decimal("12.0")
    assert sucrose.potential_abv > glucose.potential_abv


def test_change_fermentable_keeps_target_volume_and_abv() -> None:
    original = calculate_by_volume(Decimal("25"), Decimal("12"), "sucrose")

    updated = recalculate_fermentable(original, "glucose")

    assert updated.fermentable == "glucose"
    assert updated.volume_l == Decimal("25.00")
    assert updated.potential_abv == Decimal("12.0")
    assert updated.sugar_kg == Decimal("5.37")
    assert updated.water_l == Decimal("21.78")


def test_edit_amount_keeps_water_and_recalculates_outputs() -> None:
    original = calculate_by_volume(Decimal("25"), Decimal("12"), "glucose")

    updated = recalculate_amount(original, Decimal("6"))

    assert updated.water_l == original.water_l
    assert updated.sugar_kg == Decimal("6.00")
    assert updated.volume_l != original.volume_l
    assert updated.potential_abv != original.potential_abv


def test_edit_water_keeps_amount_and_recalculates_outputs() -> None:
    original = calculate_by_volume(Decimal("25"), Decimal("12"), "glucose")

    updated = recalculate_water(original, Decimal("25"))

    assert updated.sugar_kg == original.sugar_kg
    assert updated.water_l == Decimal("25.00")
    assert updated.volume_l != original.volume_l
    assert updated.potential_abv != original.potential_abv


def test_edit_volume_keeps_abv_and_recalculates_ingredients() -> None:
    original = calculate_by_volume(Decimal("25"), Decimal("12"), "fructose")

    updated = recalculate_volume(original, Decimal("30"))

    assert updated.volume_l == Decimal("30.00")
    assert updated.potential_abv == original.potential_abv
    assert updated.sugar_kg == Decimal("6.44")
    assert updated.water_l == Decimal("26.13")


def test_edit_abv_keeps_volume_and_recalculates_ingredients() -> None:
    original = calculate_by_volume(Decimal("25"), Decimal("12"), "fructose")

    updated = recalculate_abv(original, Decimal("14"))

    assert updated.volume_l == original.volume_l
    assert updated.potential_abv == Decimal("14.0")
    assert updated.sugar_kg == Decimal("6.27")
    assert updated.water_l == Decimal("21.24")


def test_old_saved_composition_defaults_to_sucrose() -> None:
    result = result_from_event_data(
        {
            "mode": "check",
            "water_l": "21.94",
            "sugar_kg": "5.10",
            "volume_l": "25",
            "potential_abv": "12",
        }
    )

    assert result is not None
    assert result.fermentable == "sucrose"
    assert result.fermentable_label == "Сахар"


def test_high_potential_abv_shows_warning() -> None:
    result = calculate_by_volume(Decimal("25"), Decimal("20"), "glucose")

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


def test_preparation_calculator_routes_to_current_process() -> None:
    actions = [(action.key, action.label) for action in stage_actions_for_stage("Подготовка")]

    markup = process_card_keyboard(42, actions)
    buttons = [button for row in markup.inline_keyboard for button in row]
    calculators = next(button for button in buttons if button.text == "🧮 Калькуляторы")

    assert calculators.callback_data == "process:sugar-wash:42"


def test_process_wash_menu_has_three_modes() -> None:
    markup = process_sugar_wash_menu_keyboard(42)

    assert button_callbacks(markup) == [
        "process:sugar-wash:42:volume",
        "process:sugar-wash:42:sugar",
        "process:sugar-wash:42:check",
        "process:view:42",
    ]
    assert "⚖️ По количеству сырья" in button_texts(markup)


def test_process_calculator_offers_all_three_fermentables() -> None:
    markup = process_sugar_wash_fermentable_keyboard(42, "volume")

    assert button_texts(markup)[:3] == ["🍬 Сахар", "🧪 Глюкоза", "🧪 Фруктоза"]
    assert button_callbacks(markup)[:3] == [
        "process:sugar-wash-material:42:volume:sucrose",
        "process:sugar-wash-material:42:volume:glucose",
        "process:sugar-wash-material:42:volume:fructose",
    ]


def test_process_calculation_result_has_edit_composition_action() -> None:
    markup = process_sugar_wash_result_keyboard(42)

    assert "💾 Сохранить" not in button_texts(markup)
    assert button_callbacks(markup) == [
        "process:composition:42",
        "process:sugar-wash:42",
        "process:view:42",
    ]
