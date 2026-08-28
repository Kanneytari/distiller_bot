from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def fermentation_calculators_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧪 Крепость по Brix", callback_data="calculators:fermentation-brix")
    builder.button(text="🔙 К калькуляторам", callback_data="menu:calculators")
    builder.adjust(1)
    return builder.as_markup()


def fermentation_input_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_data = f"process:view:{process_id}" if process_id is not None else "calculators:fermentation"
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()


def fermentation_result_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if process_id is not None:
        builder.button(text="↩️ Новый расчёт", callback_data=f"process:fermentation-brix:{process_id}")
        builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
    else:
        builder.button(text="↩️ Новый расчёт", callback_data="calculators:fermentation-brix")
        builder.button(text="🔙 Брожение", callback_data="calculators:fermentation")
    builder.adjust(1)
    return builder.as_markup()
