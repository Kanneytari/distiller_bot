from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .calculator_keyboards import (
    global_sugar_wash_input_keyboard,
    global_sugar_wash_menu_keyboard,
    global_sugar_wash_result_keyboard,
)
from .sugar_wash import (
    SugarWashResult,
    calculate_by_sugar,
    calculate_by_volume,
    calculate_from_composition,
    result_text,
)

router = Router()

MAX_INPUT_VOLUME_L = Decimal("10000")
MAX_INPUT_SUGAR_KG = Decimal("1000")
MAX_TARGET_ABV = Decimal("25")


class GlobalSugarWashState(StatesGroup):
    waiting_value = State()


def parse_positive_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value


def decimal_from_state(data: dict[str, object], key: str) -> Decimal | None:
    raw_value = data.get(key)
    if raw_value is None:
        return None
    try:
        value = Decimal(str(raw_value))
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None


def calculation_prompt(mode: str) -> tuple[str, str]:
    if mode == "volume":
        return (
            "volume",
            "🪣 <b>Расчёт по объёму</b>\n\n"
            "Какой итоговый объём браги хотите получить?\n"
            "Введите число в литрах, например <code>25</code>.",
        )

    title = "🍬 Расчёт по сахару" if mode == "sugar" else "📈 Проверка состава"
    return (
        "sugar",
        f"<b>{title}</b>\n\n"
        "Сколько сахара используете?\n"
        "Введите количество в килограммах, например <code>6</code>.",
    )


@router.callback_query(F.data.startswith("calculators:sugar-wash"))
async def global_sugar_wash_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    parts = (callback.data or "").split(":")
    if len(parts) not in {2, 3}:
        return

    mode = parts[2] if len(parts) == 3 else None
    if mode is None:
        await state.clear()
        await callback.message.edit_text(
            "🧮 <b>Сахарная брага</b>\n\n"
            "Выберите, от каких данных хотите считать:\n\n"
            "🪣 <b>По объёму</b> — знаю желаемый объём браги.\n"
            "🍬 <b>По сахару</b> — знаю, сколько сахара есть.\n"
            "📈 <b>Проверить состав</b> — уже знаю сахар и воду.",
            reply_markup=global_sugar_wash_menu_keyboard(),
        )
        return

    if mode not in {"volume", "sugar", "check"}:
        return

    step, prompt = calculation_prompt(mode)
    await state.clear()
    await state.set_state(GlobalSugarWashState.waiting_value)
    await state.update_data(calc_mode=mode, calc_step=step)
    await callback.message.edit_text(prompt, reply_markup=global_sugar_wash_input_keyboard())


@router.message(GlobalSugarWashState.waiting_value)
async def global_sugar_wash_value_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    data = await state.get_data()
    mode = data.get("calc_mode")
    step = data.get("calc_step")
    if not isinstance(mode, str) or not isinstance(step, str):
        await state.clear()
        return

    value = parse_positive_decimal(message.text)
    if value is None:
        await message.answer(
            "Введите положительное число. Например: <code>25</code> или <code>5,5</code>."
        )
        return

    if step in {"volume", "water"} and value > MAX_INPUT_VOLUME_L:
        await message.answer("Для MVP укажите объём не больше 10 000 л.")
        return
    if step == "sugar" and value > MAX_INPUT_SUGAR_KG:
        await message.answer("Для MVP укажите не больше 1 000 кг сахара.")
        return
    if step == "target_abv" and (value < Decimal("1") or value > MAX_TARGET_ABV):
        await message.answer("Укажите потенциальную крепость от 1 до 25 %.")
        return

    if mode == "volume" and step == "volume":
        await state.update_data(volume_l=str(value), calc_step="target_abv")
        await message.answer(
            "📈 Какую потенциальную крепость хотите заложить?\n"
            "Введите процент, например <code>12</code>.\n\n"
            "Это расчётная цель, а не гарантированная фактическая крепость.",
            reply_markup=global_sugar_wash_input_keyboard(),
        )
        return

    if mode == "sugar" and step == "sugar":
        await state.update_data(sugar_kg=str(value), calc_step="target_abv")
        await message.answer(
            "📈 Какую потенциальную крепость хотите заложить?\n"
            "Введите процент, например <code>12</code>.",
            reply_markup=global_sugar_wash_input_keyboard(),
        )
        return

    if mode == "check" and step == "sugar":
        await state.update_data(sugar_kg=str(value), calc_step="water")
        await message.answer(
            "💧 Сколько воды используете?\n"
            "Введите количество в литрах, например <code>25</code>.",
            reply_markup=global_sugar_wash_input_keyboard(),
        )
        return

    result: SugarWashResult | None = None
    if mode == "volume" and step == "target_abv":
        volume_l = decimal_from_state(data, "volume_l")
        if volume_l is not None:
            result = calculate_by_volume(volume_l, value)
    elif mode == "sugar" and step == "target_abv":
        sugar_kg = decimal_from_state(data, "sugar_kg")
        if sugar_kg is not None:
            result = calculate_by_sugar(sugar_kg, value)
    elif mode == "check" and step == "water":
        sugar_kg = decimal_from_state(data, "sugar_kg")
        if sugar_kg is not None:
            result = calculate_from_composition(value, sugar_kg)

    if result is None:
        await state.clear()
        await message.answer("Не удалось восстановить данные расчёта. Запустите его заново.")
        return

    await state.clear()
    await message.answer(
        result_text(result),
        reply_markup=global_sugar_wash_result_keyboard(),
    )
