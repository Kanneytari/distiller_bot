from collections.abc import Iterable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


PROCESS_ACTION_CALLBACKS: dict[str, str] = {
    "measure": "process:measure:{process_id}",
    "composition": "process:composition:{process_id}",
    "note": "process:note:{process_id}",
    "calculators": "process:calculators:{process_id}",
    "sugar_wash": "process:sugar-wash:{process_id}",
    # Завершение обычного этапа переиспользует существующий выбор нового этапа.
    "complete_stage": "process:complete-stage:{process_id}",
    "complete_process": "process:complete:{process_id}",
}


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧪 Мои процессы", callback_data="menu:drinks")
    builder.button(text="📖 Рецепты", callback_data="menu:recipes")
    builder.button(text="🧮 Калькуляторы", callback_data="menu:calculators")
    builder.button(text="⚙️ Оборудование", callback_data="menu:equipment")
    builder.adjust(2, 2)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Меню", callback_data="menu:main")
    return builder.as_markup()


def process_list_keyboard(items: Iterable[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for process_id, label in items:
        builder.button(text=label, callback_data=f"process:view:{process_id}")
    builder.button(text="➕ Добавить процесс", callback_data="process:add")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def process_stage_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧰 Подготовка", callback_data="process:stage:preparation")
    builder.button(text="🫧 Брожение", callback_data="process:stage:fermentation")
    builder.button(text="⚗️ Перегонка", callback_data="process:stage:distillation")
    builder.button(
        text="💧 Подготовка напитка",
        callback_data="process:stage:drink_preparation",
    )
    builder.button(text="🍾 Розлив", callback_data="process:stage:bottling")
    builder.button(text="✏️ Другой этап", callback_data="process:stage:custom")
    callback_data = f"process:view:{process_id}" if process_id is not None else "menu:drinks"
    builder.button(text="❌ Отмена", callback_data=callback_data)
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def process_card_keyboard(
    process_id: int,
    stage_actions: Iterable[tuple[str, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    primary_actions: list[tuple[str, str]] = []
    secondary_actions: list[tuple[str, str]] = []
    completion_action: tuple[str, str] | None = None

    for action_key, label in stage_actions:
        if action_key in {"complete_stage", "complete_process"}:
            completion_action = (action_key, label)
        elif action_key in {"note", "calculators", "sugar_wash"}:
            secondary_actions.append((action_key, label))
        else:
            primary_actions.append((action_key, label))

    row_sizes: list[int] = []

    # Главное действие этапа (состав / замер / параметры / результат) остаётся заметным.
    for action_key, label in primary_actions:
        callback_template = PROCESS_ACTION_CALLBACKS.get(action_key)
        if callback_template is None:
            continue
        builder.button(
            text=label,
            callback_data=callback_template.format(process_id=process_id),
        )
        row_sizes.append(1)

    # Заметка и калькуляторы — компактные вторичные действия в одной строке.
    secondary_count = 0
    for action_key, label in secondary_actions:
        callback_template = PROCESS_ACTION_CALLBACKS.get(action_key)
        if callback_template is None:
            continue
        builder.button(
            text=label,
            callback_data=callback_template.format(process_id=process_id),
        )
        secondary_count += 1
    if secondary_count:
        row_sizes.append(secondary_count)

    # Переход к следующему этапу и переименование держим в одной компактной строке.
    compact_action_count = 1
    if completion_action is not None:
        action_key, _label = completion_action
        callback_template = PROCESS_ACTION_CALLBACKS.get(action_key)
        if callback_template is not None:
            button_text = (
                "➡️ Следующий этап"
                if action_key == "complete_stage"
                else "✅ Завершить процесс"
            )
            builder.button(
                text=button_text,
                callback_data=callback_template.format(process_id=process_id),
            )
            compact_action_count += 1

    builder.button(text="✏️ Имя", callback_data=f"process:rename:{process_id}")
    row_sizes.append(compact_action_count)

    # Навигация тоже не должна растягивать карточку по вертикали.
    builder.button(text="← Процессы", callback_data="menu:drinks")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    row_sizes.append(2)

    builder.adjust(*row_sizes)
    return builder.as_markup()


def process_measurement_type_keyboard(
    process_id: int,
    ordered_types: Iterable[tuple[str, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for measurement_type, label in ordered_types:
        builder.button(
            text=label,
            callback_data=f"process:measure-type:{process_id}:{measurement_type}",
        )
    builder.button(
        text="✏️ Другой замер",
        callback_data=f"process:measure-type:{process_id}:custom",
    )
    builder.button(text="❌ Отмена", callback_data=f"process:view:{process_id}")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def process_input_cancel_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_data = f"process:view:{process_id}" if process_id is not None else "menu:drinks"
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()


def process_calculators_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
    return builder.as_markup()


def sugar_wash_menu_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🪣 По объёму",
        callback_data=f"process:sugar-wash:{process_id}:volume",
    )
    builder.button(
        text="🍬 По сахару",
        callback_data=f"process:sugar-wash:{process_id}:sugar",
    )
    builder.button(
        text="📈 Проверить состав",
        callback_data=f"process:sugar-wash:{process_id}:check",
    )
    builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def sugar_wash_input_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"process:sugar-wash:{process_id}")
    return builder.as_markup()


def sugar_wash_result_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Новый расчёт", callback_data=f"process:sugar-wash:{process_id}")
    builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(2)
    return builder.as_markup()


def process_completed_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Мои процессы", callback_data="menu:drinks")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def equipment_list_keyboard(items: Iterable[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for equipment_id, label in items:
        builder.button(text=label, callback_data=f"equipment:view:{equipment_id}")
    builder.button(text="➕ Добавить", callback_data="equipment:add")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def equipment_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛢 Перегонный куб", callback_data="equipment:add:still")
    builder.button(text="🪣 Ферментер", callback_data="equipment:add:fermenter")
    builder.button(text="🧱 Колонна", callback_data="equipment:add:column")
    builder.button(text="🔥 Нагрев", callback_data="equipment:add:heater")
    builder.button(text="⚙️ Другое", callback_data="equipment:add:other")
    builder.button(text="← Назад", callback_data="menu:equipment")
    builder.adjust(1)
    return builder.as_markup()


def equipment_card_keyboard(equipment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить", callback_data=f"equipment:edit:{equipment_id}")
    builder.button(text="🗑 Удалить", callback_data=f"equipment:delete:{equipment_id}")
    builder.button(text="← Оборудование", callback_data="menu:equipment")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def equipment_edit_keyboard(
    equipment_id: int,
    *,
    can_edit_capacity: bool,
    can_edit_power: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Название", callback_data=f"equipment:field:{equipment_id}:name")
    if can_edit_capacity:
        builder.button(text="📏 Объём", callback_data=f"equipment:field:{equipment_id}:capacity")
    if can_edit_power:
        builder.button(text="⚡ Мощность", callback_data=f"equipment:field:{equipment_id}:power")
    builder.button(text="← Назад", callback_data=f"equipment:view:{equipment_id}")
    builder.adjust(1)
    return builder.as_markup()


def equipment_delete_keyboard(equipment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data=f"equipment:delete-confirm:{equipment_id}")
    builder.button(text="← Отмена", callback_data=f"equipment:view:{equipment_id}")
    builder.adjust(1)
    return builder.as_markup()


def equipment_input_cancel_keyboard(equipment_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_data = (
        f"equipment:view:{equipment_id}" if equipment_id is not None else "menu:equipment"
    )
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()
