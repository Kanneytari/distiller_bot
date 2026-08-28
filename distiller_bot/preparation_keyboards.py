from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


FERMENTABLE_BUTTONS = (
    ("🍬 Сахар", "sucrose"),
    ("🧪 Глюкоза", "glucose"),
    ("🧪 Фруктоза", "fructose"),
)


def preparation_composition_keyboard(
    process_id: int,
    *,
    has_composition: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_composition:
        builder.button(
            text="🍬 Сырьё",
            callback_data=f"process:composition-edit:{process_id}:fermentable",
        )
        builder.button(
            text="⚖️ Количество",
            callback_data=f"process:composition-edit:{process_id}:amount",
        )
        builder.button(
            text="💧 Вода",
            callback_data=f"process:composition-edit:{process_id}:water",
        )
        builder.button(
            text="🪣 Объём",
            callback_data=f"process:composition-edit:{process_id}:volume",
        )
        builder.button(
            text="📈 Крепость",
            callback_data=f"process:composition-edit:{process_id}:abv",
        )
        builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
        builder.adjust(2, 2, 1, 1)
    else:
        builder.button(
            text="➕ Задать состав",
            callback_data=f"process:composition-start:{process_id}",
        )
        builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
        builder.adjust(1)
    return builder.as_markup()


def composition_fermentable_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, key in FERMENTABLE_BUTTONS:
        builder.button(
            text=label,
            callback_data=f"process:composition-material:{process_id}:{key}",
        )
    builder.button(text="❌ Отмена", callback_data=f"process:composition:{process_id}")
    builder.adjust(1)
    return builder.as_markup()


def composition_input_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"process:composition:{process_id}")
    return builder.as_markup()


def process_sugar_wash_menu_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🪣 По объёму",
        callback_data=f"process:sugar-wash:{process_id}:volume",
    )
    builder.button(
        text="⚖️ По количеству сырья",
        callback_data=f"process:sugar-wash:{process_id}:sugar",
    )
    builder.button(
        text="📈 Проверить состав",
        callback_data=f"process:sugar-wash:{process_id}:check",
    )
    builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(1)
    return builder.as_markup()


def process_sugar_wash_fermentable_keyboard(
    process_id: int,
    mode: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, key in FERMENTABLE_BUTTONS:
        builder.button(
            text=label,
            callback_data=f"process:sugar-wash-material:{process_id}:{mode}:{key}",
        )
    builder.button(text="❌ Отмена", callback_data=f"process:sugar-wash:{process_id}")
    builder.adjust(1)
    return builder.as_markup()


def process_sugar_wash_input_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"process:sugar-wash:{process_id}")
    return builder.as_markup()


def process_sugar_wash_result_keyboard(process_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать состав", callback_data=f"process:composition:{process_id}")
    builder.button(text="↩️ Новый расчёт", callback_data=f"process:sugar-wash:{process_id}")
    builder.button(text="← К процессу", callback_data=f"process:view:{process_id}")
    builder.adjust(1, 2)
    return builder.as_markup()


def global_sugar_wash_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪣 По объёму", callback_data="calculators:sugar-wash:volume")
    builder.button(text="⚖️ По количеству сырья", callback_data="calculators:sugar-wash:sugar")
    builder.button(text="📈 Проверить состав", callback_data="calculators:sugar-wash:check")
    builder.button(text="← Подготовка браги", callback_data="calculators:preparation")
    builder.adjust(1)
    return builder.as_markup()


def global_sugar_wash_fermentable_keyboard(mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, key in FERMENTABLE_BUTTONS:
        builder.button(
            text=label,
            callback_data=f"calculators:sugar-wash-material:{mode}:{key}",
        )
    builder.button(text="❌ Отмена", callback_data="calculators:sugar-wash")
    builder.adjust(1)
    return builder.as_markup()


def global_sugar_wash_input_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="calculators:sugar-wash")
    return builder.as_markup()


def global_sugar_wash_result_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Новый расчёт", callback_data="calculators:sugar-wash")
    builder.button(text="← Подготовка браги", callback_data="calculators:preparation")
    builder.adjust(1)
    return builder.as_markup()
