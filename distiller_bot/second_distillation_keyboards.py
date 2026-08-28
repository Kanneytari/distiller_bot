from collections.abc import Iterable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def second_distillation_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛢 Загрузка", callback_data=f"process:second-distillation-charge:{process_id}")
    builder.button(text="🫙 Отборы", callback_data=f"process:second-distillation-cuts:{process_id}")
    builder.button(
        text="🧮 Калькуляторы",
        callback_data=f"process:second-distillation-calculators:{process_id}",
    )
    builder.button(text="🔙 К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def second_distillation_charge_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💧 Разбавление спирта",
        callback_data=f"process:second-distillation-dilution:{process_id}",
    )
    builder.button(
        text="✏️ Ввести вручную",
        callback_data=f"process:second-distillation-charge-manual:{process_id}",
    )
    builder.button(
        text="🔙 Вторая перегонка",
        callback_data=f"process:second-distillation:{process_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def second_distillation_cuts_keyboard(
    process_id: int,
    items: Iterable[tuple[int, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Добавить ёмкость",
        callback_data=f"process:second-distillation-cut-add:{process_id}",
    )
    count = 0
    for cut_id, label in items:
        builder.button(
            text=label,
            callback_data=f"process:second-distillation-cut:{process_id}:{cut_id}",
        )
        count += 1
    builder.button(
        text="🔙 Вторая перегонка",
        callback_data=f"process:second-distillation:{process_id}",
    )
    builder.adjust(1, *([3] * ((count + 2) // 3)), 1)
    return builder.as_markup()


def second_distillation_cut_keyboard(process_id: int, cut_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💧 Объём",
        callback_data=f"process:second-distillation-cut-edit:{process_id}:{cut_id}:volume",
    )
    builder.button(
        text="📈 Спиртометр",
        callback_data=f"process:second-distillation-cut-edit:{process_id}:{cut_id}:abv",
    )
    builder.button(
        text="🌡 Температура",
        callback_data=f"process:second-distillation-cut-edit:{process_id}:{cut_id}:temperature",
    )
    builder.button(
        text="🏷 Фракция",
        callback_data=f"process:second-distillation-fraction:{process_id}:{cut_id}",
    )
    builder.button(
        text="🗑 Удалить",
        callback_data=f"process:second-distillation-cut-delete:{process_id}:{cut_id}",
    )
    builder.button(
        text="🔙 Отборы",
        callback_data=f"process:second-distillation-cuts:{process_id}",
    )
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def second_distillation_fraction_keyboard(process_id: int, cut_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in (
        ("heads", "🔴 Головы"),
        ("hearts", "🟢 Тело"),
        ("tails", "🔵 Хвосты"),
        ("unknown", "⚪ Не определено"),
    ):
        builder.button(
            text=label,
            callback_data=f"process:second-distillation-fraction-set:{process_id}:{cut_id}:{key}",
        )
    builder.button(
        text="🔙 К ёмкости",
        callback_data=f"process:second-distillation-cut:{process_id}:{cut_id}",
    )
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def second_distillation_delete_keyboard(process_id: int, cut_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Да, удалить",
        callback_data=f"process:second-distillation-cut-delete-confirm:{process_id}:{cut_id}",
    )
    builder.button(
        text="🔙 Отмена",
        callback_data=f"process:second-distillation-cut:{process_id}:{cut_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def second_distillation_input_keyboard(process_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_data = (
        f"process:second-distillation:{process_id}"
        if process_id is not None
        else "calculators:second-distillation"
    )
    builder.button(text="❌ Отмена", callback_data=callback_data)
    return builder.as_markup()


def second_distillation_calculators_keyboard(
    process_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prefix = (
        f"process:second-distillation-calc:{process_id}"
        if process_id is not None
        else "calculators:second-distillation"
    )
    builder.button(text="💧 Разбавление спирта", callback_data=f"{prefix}:dilution")
    builder.button(text="✂️ Головы и хвосты", callback_data=f"{prefix}:cuts")
    builder.button(text="🌡 Поправка спиртометра", callback_data=f"{prefix}:correction")
    builder.button(text="💧 Абсолютный спирт", callback_data=f"{prefix}:absolute")
    builder.button(text="🧪 Средняя крепость", callback_data=f"{prefix}:blend")
    if process_id is not None:
        builder.button(
            text="🔙 Вторая перегонка",
            callback_data=f"process:second-distillation:{process_id}",
        )
    else:
        builder.button(text="🔙 К калькуляторам", callback_data="menu:calculators")
    builder.adjust(1)
    return builder.as_markup()
