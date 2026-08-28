from collections.abc import Iterable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def first_distillation_keyboard(
    process_id: int,
    containers: Iterable[tuple[int, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Добавить ёмкость",
        callback_data=f"process:first-distillation-add:{process_id}",
    )
    container_count = 0
    for container_id, label in containers:
        builder.button(
            text=label,
            callback_data=f"process:first-distillation-container:{process_id}:{container_id}",
        )
        container_count += 1
    builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")

    row_sizes = [1]
    remaining = container_count
    while remaining > 0:
        row_size = min(3, remaining)
        row_sizes.append(row_size)
        remaining -= row_size
    row_sizes.append(1)
    builder.adjust(*row_sizes)
    return builder.as_markup()


def first_distillation_container_keyboard(process_id: int, container_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💧 Объём",
        callback_data=f"process:first-distillation-edit:{process_id}:{container_id}:volume",
    )
    builder.button(
        text="📈 Спиртометр",
        callback_data=f"process:first-distillation-edit:{process_id}:{container_id}:abv",
    )
    builder.button(
        text="🌡 Температура",
        callback_data=f"process:first-distillation-edit:{process_id}:{container_id}:temperature",
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=f"process:first-distillation-delete:{process_id}:{container_id}",
    )
    builder.button(
        text="🔙 Ёмкости",
        callback_data=f"process:first-distillation:{process_id}",
    )
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def first_distillation_delete_keyboard(process_id: int, container_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Да, удалить",
        callback_data=f"process:first-distillation-delete-confirm:{process_id}:{container_id}",
    )
    builder.button(
        text="🔙 Отмена",
        callback_data=f"process:first-distillation-container:{process_id}:{container_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def first_distillation_input_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отмена",
        callback_data=f"process:first-distillation:{process_id}",
    )
    return builder.as_markup()


def first_distillation_calculators_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prefix = (
        f"process:first-distillation-calc:{process_id}"
        if process_id is not None
        else "calculators:first-distillation"
    )
    builder.button(text="🌡 Поправка спиртометра", callback_data=f"{prefix}:correction")
    builder.button(text="💧 Абсолютный спирт", callback_data=f"{prefix}:absolute")
    builder.button(text="🧪 Средняя крепость", callback_data=f"{prefix}:blend")
    if process_id is not None:
        builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
    else:
        builder.button(text="🔙 К калькуляторам", callback_data="menu:calculators")
    builder.adjust(1)
    return builder.as_markup()


def first_distillation_calculator_input_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_data = (
        f"process:first-distillation-calculators:{process_id}"
        if process_id is not None
        else "calculators:first-distillation"
    )
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()
