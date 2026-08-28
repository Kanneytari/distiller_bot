from decimal import Decimal

from distiller_bot.preparation_composition import composition_text
from distiller_bot.preparation_keyboards import (
    composition_fermentable_keyboard,
    preparation_composition_keyboard,
)
from distiller_bot.sugar_wash import calculate_by_volume


def button_callbacks(markup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def button_texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_empty_composition_offers_short_initial_flow() -> None:
    markup = preparation_composition_keyboard(42, has_composition=False)

    assert button_texts(markup) == ["➕ Задать состав", "← К процессу"]
    assert button_callbacks(markup) == [
        "process:composition-start:42",
        "process:view:42",
    ]


def test_existing_composition_exposes_all_editable_fields() -> None:
    markup = preparation_composition_keyboard(42, has_composition=True)

    assert button_texts(markup) == [
        "🍬 Сырьё",
        "⚖️ Количество",
        "💧 Вода",
        "🪣 Объём",
        "📈 Крепость",
        "← К процессу",
    ]
    assert button_callbacks(markup) == [
        "process:composition-edit:42:fermentable",
        "process:composition-edit:42:amount",
        "process:composition-edit:42:water",
        "process:composition-edit:42:volume",
        "process:composition-edit:42:abv",
        "process:view:42",
    ]


def test_composition_fermentable_selector_has_three_options() -> None:
    markup = composition_fermentable_keyboard(42)

    assert button_texts(markup)[:3] == ["🍬 Сахар", "🧪 Глюкоза", "🧪 Фруктоза"]
    assert button_callbacks(markup)[:3] == [
        "process:composition-material:42:sucrose",
        "process:composition-material:42:glucose",
        "process:composition-material:42:fructose",
    ]


def test_composition_text_uses_selected_fermentable() -> None:
    result = calculate_by_volume(Decimal("25"), Decimal("12"), "fructose")

    text = composition_text(result)

    assert "Сырьё: <b>Фруктоза</b>" in text
    assert "⚖️ Количество: <b>5.37 кг</b>" in text
    assert "💧 Вода: <b>21.78 л</b>" in text
    assert "🪣 Объём: <b>25 л</b>" in text
    assert "📈 Потенциальная крепость: <b>~12%</b>" in text
