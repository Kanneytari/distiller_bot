from collections.abc import Iterable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
    builder.button(text="🟡 Брожение", callback_data="process:stage:fermentation")
    builder.button(text="🔥 Перегонка", callback_data="process:stage:distillation")
    builder.button(text="💧 Разбавление", callback_data="process:stage:dilution")
    builder.button(text="🪵 Выдержка", callback_data="process:stage:aging")
    builder.button(text="✅ Готово", callback_data="process:stage:ready")
    builder.button(text="✏️ Другой этап", callback_data="process:stage:custom")
    callback_data = f"process:view:{process_id}" if process_id is not None else "menu:drinks"
    builder.button(text="❌ Отмена", callback_data=callback_data)
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def process_card_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Переименовать", callback_data=f"process:rename:{process_id}")
    builder.button(text="🔄 Изменить этап", callback_data=f"process:change-stage:{process_id}")
    builder.button(text="← Мои процессы", callback_data="menu:drinks")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def process_input_cancel_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_data = f"process:view:{process_id}" if process_id is not None else "menu:drinks"
    builder.button(text="❌ Отмена", callback_data=callback_data)
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
    callback_data = f"equipment:view:{equipment_id}" if equipment_id is not None else "menu:equipment"
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()
