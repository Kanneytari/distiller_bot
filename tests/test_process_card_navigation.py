from distiller_bot.keyboards import process_card_keyboard
from distiller_bot.models import Drink, DrinkEvent
from distiller_bot.process_stages import stage_actions_for_stage
from distiller_bot.processes import process_card_text


def button_pairs(stage: str) -> list[tuple[str, str | None]]:
    actions = [(action.key, action.label) for action in stage_actions_for_stage(stage)]
    markup = process_card_keyboard(42, actions)
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def test_preparation_card_hides_raw_material_prefix() -> None:
    process = Drink(
        user_id=1,
        name="Сахарная брага",
        current_stage="Подготовка",
        status="active",
    )
    composition = DrinkEvent(
        drink_id=1,
        event_type="preparation_composition",
        title="Состав браги",
        data={
            "fermentable": "sucrose",
            "fermentable_kg": "5.1",
            "sugar_kg": "5.1",
            "water_l": "21.94",
            "volume_l": "25",
            "potential_abv": "12",
        },
    )
    setattr(process, "_latest_preparation_composition", composition)

    text = process_card_text(process)

    assert "Сырьё:" not in text
    assert "Сахар · ⚖️ 5.1 кг" in text


def test_regular_stage_uses_next_stage_and_has_no_manual_stage_button() -> None:
    buttons = button_pairs("Подготовка")

    assert ("➡️ Следующий этап", "process:complete-stage:42") in buttons
    assert all(text != "🔄 Этап" for text, _callback in buttons)
    assert all(callback != "process:change-stage:42" for _text, callback in buttons)


def test_bottling_finishes_process_instead_of_showing_next_stage() -> None:
    buttons = button_pairs("Розлив")

    assert ("✅ Завершить процесс", "process:complete:42") in buttons
    assert all(text != "➡️ Следующий этап" for text, _callback in buttons)
