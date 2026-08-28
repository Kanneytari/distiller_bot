from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def first_distillation_keyboard(
    process_id: int,
    *,
    has_result: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_result:
        builder.button(
            text="🥃 Объём СС",
            callback_data=f"process:first-distillation-edit:{process_id}:volume",
        )
        builder.button(
            text="📈 Крепость",
            callback_data=f"process:first-distillation-edit:{process_id}:abv",
        )
        builder.button(
            text="🔄 Записать заново",
            callback_data=f"process:first-distillation-start:{process_id}",
        )
        builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
        builder.adjust(2, 1, 1)
    else:
        builder.button(
            text="➕ Записать результат",
            callback_data=f"process:first-distillation-start:{process_id}",
        )
        builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
        builder.adjust(1)
    return builder.as_markup()


def first_distillation_input_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отмена",
        callback_data=f"process:first-distillation:{process_id}",
    )
    return builder.as_markup()
