from distiller_bot.keyboards import process_card_keyboard, process_stage_keyboard
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


def test_process_card_returns_to_drinks() -> None:
    buttons = button_pairs("Подготовка")

    assert ("🔙 Напитки", "menu:drinks") in buttons
    assert all("Процессы" not in text for text, _callback in buttons)


def test_process_card_collapses_name_and_note_into_parameters() -> None:
    buttons = button_pairs("Подготовка")

    assert ("⚙️ Параметры", "process:parameters:42") in buttons
    assert all(text != "✏️ Имя" for text, _callback in buttons)
    assert all(text != "📝 Заметка" for text, _callback in buttons)


def test_stage_selector_only_offers_predefined_stages() -> None:
    markup = process_stage_keyboard(42)
    buttons = [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]

    assert buttons == [
        ("🧰 Подготовка", "process:stage:preparation"),
        ("🫧 Брожение", "process:stage:fermentation"),
        ("⚗️ Первая перегонка", "process:stage:first_distillation"),
        ("⚗️ Вторая перегонка", "process:stage:second_distillation"),
        ("💧 Подготовка напитка", "process:stage:drink_preparation"),
        ("🍾 Розлив", "process:stage:bottling"),
        ("❌ Отмена", "process:view:42"),
    ]
    assert all(callback != "process:stage:custom" for _text, callback in buttons)
    assert all(callback != "process:stage:distillation" for _text, callback in buttons)


def test_first_distillation_has_containers_and_dedicated_calculators() -> None:
    buttons = button_pairs("Первая перегонка")

    assert ("🫙 Ёмкости", "process:first-distillation:42") in buttons
    assert (
        "🧮 Калькуляторы",
        "process:first-distillation-calculators:42",
    ) in buttons
    assert ("➡️ Следующий этап", "process:complete-stage:42") in buttons


def test_bottling_can_return_to_any_stage_instead_of_finishing_process() -> None:
    buttons = button_pairs("Розлив")

    assert ("🔄 Выбрать этап", "process:change-stage:42") in buttons
    assert all(text != "✅ Завершить процесс" for text, _callback in buttons)
    assert all(callback != "process:complete:42" for _text, callback in buttons)
