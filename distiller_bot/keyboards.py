from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🥃 Напитки", callback_data="menu:drinks")
    builder.button(text="📖 Рецепты", callback_data="menu:recipes")
    builder.button(text="🧮 Калькуляторы", callback_data="menu:calculators")
    builder.button(text="⚙️ Оборудование", callback_data="menu:equipment")
    builder.adjust(2, 2)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Меню", callback_data="menu:main")
    return builder.as_markup()
