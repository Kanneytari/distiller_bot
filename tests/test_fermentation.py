from decimal import Decimal

import distiller_bot.fermentation_integration  # noqa: F401
from distiller_bot.calculator_keyboards import calculators_menu_keyboard
from distiller_bot.fermentation import refractometer_result_text
from distiller_bot.keyboards import process_card_keyboard
from distiller_bot.process_stages import stage_actions_for_stage
from distiller_bot.refractometer import calculate_refractometer, corrected_final_sg


def button_pairs(markup) -> list[tuple[str, str | None]]:
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def test_fermentation_stage_is_lightweight() -> None:
    actions = stage_actions_for_stage("Брожение")

    assert [(action.key, action.label) for action in actions] == [
        ("fermentation_temperature", "🌡 Температура"),
        ("fermentation_brix", "🧪 Крепость по Brix"),
        ("note", "📝 Заметка"),
        ("complete_stage", "✅ Завершить брожение"),
    ]


def test_fermentation_card_uses_dedicated_callbacks() -> None:
    actions = [(action.key, action.label) for action in stage_actions_for_stage("Брожение")]
    buttons = button_pairs(process_card_keyboard(42, actions))

    assert ("🌡 Температура", "process:fermentation-temperature:42") in buttons
    assert ("🧪 Крепость по Brix", "process:fermentation-brix:42") in buttons
    assert all(text != "📏 Добавить измерение" for text, _callback in buttons)
    assert all(callback != "process:calculators:42" for _text, callback in buttons)


def test_refractometer_start_reading_has_zero_alcohol() -> None:
    result = calculate_refractometer(Decimal("20"), Decimal("20"))

    assert result.current_abv == Decimal("0.0")
    assert result.corrected_sg == result.original_sg


def test_refractometer_corrects_reading_after_fermentation() -> None:
    result = calculate_refractometer(Decimal("20"), Decimal("8"))

    assert result.original_sg == Decimal("1.083")
    assert result.corrected_sg == Decimal("1.003")
    assert result.potential_abv == Decimal("11.5")
    assert result.current_abv == Decimal("11.1")


def test_refractometer_rejects_current_brix_above_initial() -> None:
    try:
        corrected_final_sg(Decimal("12"), Decimal("13"))
    except ValueError:
        pass
    else:
        raise AssertionError("Current Brix above initial Brix must be rejected")


def test_result_text_explains_brix_and_wort_sg() -> None:
    text = refractometer_result_text(calculate_refractometer(Decimal("20"), Decimal("8")))

    assert "Потенциальная крепость" in text
    assert "Оценка крепости" in text
    assert "Wort SG" in text
    assert "Расчёт ориентировочный" in text


def test_global_calculators_include_fermentation() -> None:
    buttons = button_pairs(calculators_menu_keyboard())

    assert ("🫧 Брожение", "calculators:fermentation") in buttons
