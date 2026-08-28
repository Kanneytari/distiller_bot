from decimal import Decimal

from distiller_bot.calculator_keyboards import (
    calculators_menu_keyboard,
    preparation_calculators_keyboard,
)
from distiller_bot.global_calculators import calculation_prompt, parse_positive_decimal
from distiller_bot.preparation_keyboards import (
    global_sugar_wash_fermentable_keyboard,
    global_sugar_wash_menu_keyboard,
    global_sugar_wash_result_keyboard,
)


def button_callbacks(markup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_calculators_are_grouped_by_stage() -> None:
    markup = calculators_menu_keyboard()

    assert button_texts(markup)[:3] == [
        "🧰 Подготовка браги",
        "🫧 Брожение",
        "⚗️ Первая перегонка",
    ]
    assert button_callbacks(markup)[:3] == [
        "calculators:preparation",
        "calculators:fermentation",
        "calculators:first-distillation",
    ]


def test_preparation_category_exposes_fermentable_wash_calculator() -> None:
    markup = preparation_calculators_keyboard()

    assert "🍬 Сахар / глюкоза / фруктоза" in button_texts(markup)
    assert "calculators:sugar-wash" in button_callbacks(markup)


def test_global_wash_has_same_three_modes() -> None:
    callbacks = button_callbacks(global_sugar_wash_menu_keyboard())

    assert callbacks[:3] == [
        "calculators:sugar-wash:volume",
        "calculators:sugar-wash:sugar",
        "calculators:sugar-wash:check",
    ]


def test_global_calculator_offers_three_fermentables() -> None:
    markup = global_sugar_wash_fermentable_keyboard("volume")

    assert button_texts(markup)[:3] == ["🍬 Сахар", "🧪 Глюкоза", "🧪 Фруктоза"]
    assert button_callbacks(markup)[:3] == [
        "calculators:sugar-wash-material:volume:sucrose",
        "calculators:sugar-wash-material:volume:glucose",
        "calculators:sugar-wash-material:volume:fructose",
    ]


def test_global_result_cannot_be_saved_without_process() -> None:
    markup = global_sugar_wash_result_keyboard()

    assert "💾 Сохранить" not in button_texts(markup)
    assert button_callbacks(markup) == [
        "calculators:sugar-wash",
        "calculators:preparation",
    ]


def test_global_input_accepts_comma_decimal() -> None:
    assert parse_positive_decimal("5,5") == Decimal("5.5")


def test_global_input_rejects_non_finite_values() -> None:
    assert parse_positive_decimal("NaN") is None
    assert parse_positive_decimal("Infinity") is None


def test_global_volume_mode_starts_with_volume_prompt_and_selected_raw_material() -> None:
    step, prompt = calculation_prompt("volume", "glucose")

    assert step == "volume"
    assert "итоговый объём браги" in prompt
    assert "Глюкоза" in prompt
