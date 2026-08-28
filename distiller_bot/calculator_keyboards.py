from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def calculators_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧰 Подготовка браги", callback_data="calculators:preparation")
    builder.button(text="⚗️ Первая перегонка", callback_data="calculators:first-distillation")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def preparation_calculators_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🍬 Сахар / глюкоза / фруктоза", callback_data="calculators:sugar-wash")
    builder.button(text="← К калькуляторам", callback_data="menu:calculators")
    builder.button(text="🏠 Меню", callback_data="menu:main")
    builder.adjust(1, 2)
    return builder.as_markup()


# Старые функции оставлены для совместимости импортов; актуальные клавиатуры
# самого калькулятора находятся в preparation_keyboards.py.
def global_sugar_wash_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪣 По объёму", callback_data="calculators:sugar-wash:volume")
    builder.button(text="⚖️ По количеству сырья", callback_data="calculators:sugar-wash:sugar")
    builder.button(text="📈 Проверить состав", callback_data="calculators:sugar-wash:check")
    builder.button(text="← Подготовка браги", callback_data="calculators:preparation")
    builder.adjust(1)
    return builder.as_markup()


def global_sugar_wash_input_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder(); builder.button(text="❌ Отмена", callback_data="calculators:sugar-wash"); return builder.as_markup()


def global_sugar_wash_result_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder(); builder.button(text="↩️ Новый расчёт", callback_data="calculators:sugar-wash"); builder.button(text="← Подготовка браги", callback_data="calculators:preparation"); builder.adjust(1); return builder.as_markup()
