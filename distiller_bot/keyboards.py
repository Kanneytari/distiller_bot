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
