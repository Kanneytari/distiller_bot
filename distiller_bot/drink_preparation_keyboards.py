from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def drink_preparation_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💧 Разбавить", callback_data=f"process:drink-preparation-dilute:{process_id}")
    builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(1)
    return builder.as_markup()


def drink_preparation_input_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"process:drink-preparation:{process_id}")
    return builder.as_markup()


def drink_preparation_result_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сохранить результат", callback_data=f"process:drink-preparation-save:{process_id}")
    builder.button(text="↩️ Изменить крепость", callback_data=f"process:drink-preparation-dilute:{process_id}")
    builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(1, 2)
    return builder.as_markup()


def global_drink_preparation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💧 Разбавление спирта", callback_data="calculators:drink-preparation:dilution")
    builder.button(text="🔙 К калькуляторам", callback_data="menu:calculators")
    builder.adjust(1)
    return builder.as_markup()


def global_drink_preparation_input_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="calculators:drink-preparation")
    return builder.as_markup()


def global_drink_preparation_result_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Новый расчёт", callback_data="calculators:drink-preparation:dilution")
    builder.button(text="🔙 К калькуляторам", callback_data="menu:calculators")
    builder.adjust(1)
    return builder.as_markup()
