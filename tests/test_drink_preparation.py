from decimal import Decimal

import distiller_bot.drink_preparation_integration  # noqa: F401
from distiller_bot.calculator_keyboards import calculators_menu_keyboard
from distiller_bot.drink_preparation import (
    DrinkSource,
    PreparedDrink,
    dilution_preview_text,
    drink_preparation_text,
)
from distiller_bot.drink_preparation_integration import drink_preparation_context_block
from distiller_bot.keyboards import process_card_keyboard
from distiller_bot.models import Drink
from distiller_bot.process_stages import stage_actions_for_stage


def button_pairs(markup) -> list[tuple[str, str | None]]:
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def source() -> DrinkSource:
    return DrinkSource(
        volume_l=Decimal("2.70"),
        abv=Decimal("72.4"),
        absolute_alcohol_l=Decimal("1.95"),
        source="second_distillation",
    )


def result() -> PreparedDrink:
    return PreparedDrink(
        source_volume_l=Decimal("2.70"),
        source_abv=Decimal("72.4"),
        target_abv=Decimal("40.0"),
        water_l=Decimal("2.19"),
        final_volume_l=Decimal("4.89"),
        absolute_alcohol_l=Decimal("1.95"),
        source="second_distillation",
    )


def test_dilution_to_40_percent() -> None:
    text, calculated = dilution_preview_text(source(), Decimal("40"))

    assert calculated.water_l == Decimal("2.19")
    assert calculated.final_volume_l == Decimal("4.89")
    assert calculated.absolute_alcohol_l == Decimal("1.95")
    assert "Добавить воды: <b>~2.19 л</b>" in text
    assert "~4.89 л · 40%" in text


def test_drink_preparation_screen_shows_source_and_saved_result() -> None:
    text = drink_preparation_text(source(), result())

    assert "🥃 <b>После второй перегонки</b>" in text
    assert "🟢 Тело: 2.7 л · 72.4%" in text
    assert "🍶 <b>Подготовленный напиток</b>" in text
    assert "📈 Крепость: 40%" in text
    assert "🚰 Добавлено воды: 2.19 л" in text


def test_process_card_context_shows_second_distillation_body() -> None:
    process = Drink(
        user_id=1,
        name="Самогон",
        current_stage="Подготовка напитка",
        status="active",
    )
    setattr(process, "_second_distillation_body", source())
    setattr(process, "_drink_preparation_result", result())

    block = drink_preparation_context_block(process)

    assert block is not None
    assert "🥃 <b>Результат второй перегонки:</b>" in block
    assert "🟢 Тело: 2.7 л · 📈 72.4%" in block
    assert "🍶 <b>Подготовленный напиток:</b>" in block
    assert "💧 4.89 л · 📈 40%" in block


def test_drink_preparation_card_routes_to_dilution() -> None:
    actions = [
        (action.key, action.label)
        for action in stage_actions_for_stage("Подготовка напитка")
    ]
    buttons = button_pairs(process_card_keyboard(42, actions))

    assert ("💧 Разбавление", "process:drink-preparation:42") in buttons
    assert all(text != "📏 Параметры напитка" for text, _callback in buttons)


def test_global_calculators_include_drink_preparation() -> None:
    buttons = button_pairs(calculators_menu_keyboard())

    assert (
        "💧 Подготовка напитка",
        "calculators:drink-preparation",
    ) in buttons
