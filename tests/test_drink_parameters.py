from distiller_bot.drink_parameters import (
    delete_confirmation_keyboard,
    drink_card_text,
    parameters_keyboard,
    parameters_text,
)
from distiller_bot.keyboards import main_menu_keyboard, process_card_keyboard, process_list_keyboard
from distiller_bot.models import Drink, DrinkEvent
from distiller_bot.process_stages import stage_actions_for_stage


def button_pairs(markup) -> list[tuple[str, str | None]]:
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def make_drink() -> Drink:
    return Drink(
        user_id=1,
        name="Самогон",
        current_stage="Подготовка",
        status="active",
    )


def test_main_menu_uses_drinks_and_whiskey_icon() -> None:
    buttons = button_pairs(main_menu_keyboard())

    assert ("🥃 Мои напитки", "menu:drinks") in buttons
    assert all("процесс" not in text.lower() for text, _callback in buttons)


def test_drink_list_add_button_uses_new_terminology() -> None:
    buttons = button_pairs(process_list_keyboard([]))

    assert ("➕ Добавить напиток", "process:add") in buttons


def test_stage_card_has_parameters_instead_of_name_and_note() -> None:
    actions = [(action.key, action.label) for action in stage_actions_for_stage("Подготовка")]
    buttons = button_pairs(process_card_keyboard(42, actions))

    assert ("⚙️ Параметры", "process:parameters:42") in buttons
    assert ("🔙 Напитки", "menu:drinks") in buttons
    assert all(text not in {"✏️ Имя", "📝 Заметка"} for text, _callback in buttons)


def test_parameters_contains_name_note_delete_and_back() -> None:
    buttons = button_pairs(parameters_keyboard(42))

    assert buttons == [
        ("✏️ Название", "process:parameters:rename:42"),
        ("📝 Заметка", "process:parameters:note:42"),
        ("🗑 Удалить", "process:parameters:delete:42"),
        ("🔙 К напитку", "process:view:42"),
    ]


def test_delete_requires_explicit_confirmation() -> None:
    buttons = button_pairs(delete_confirmation_keyboard(42))

    assert buttons == [
        ("🗑 Да, удалить", "process:parameters:delete-confirm:42"),
        ("🔙 Отмена", "process:parameters:42"),
    ]


def test_drink_card_uses_whiskey_instead_of_flask() -> None:
    text = drink_card_text(make_drink())

    assert text.startswith("🥃 <b>Самогон</b>")
    assert not text.startswith("🧪")


def test_parameters_show_latest_note() -> None:
    note = DrinkEvent(
        drink_id=1,
        event_type="note",
        title="Заметка",
        text="Проверить завтра",
    )

    text = parameters_text(make_drink(), note)

    assert "⚙️ <b>Параметры напитка</b>" in text
    assert "🥃 <b>Самогон</b>" in text
    assert "Проверить завтра" in text
