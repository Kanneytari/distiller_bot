from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import process_calculators_keyboard
from .models import DrinkEvent
from .preparation_composition import save_preparation_composition
from .preparation_keyboards import (
    process_sugar_wash_fermentable_keyboard,
    process_sugar_wash_input_keyboard,
    process_sugar_wash_menu_keyboard,
    process_sugar_wash_result_keyboard,
)
from .process_stages import stage_type_for_title
from .processes import get_owned_process, render_process_list
from .sugar_wash import (
    DEFAULT_FERMENTABLE,
    SugarWashResult,
    calculate_by_sugar,
    calculate_by_volume,
    calculate_from_composition,
    format_decimal,
    normalize_fermentable,
    result_from_event_data,
    result_text,
)

router = Router()

MAX_INPUT_VOLUME_L = Decimal("10000")
MAX_INPUT_FERMENTABLE_KG = Decimal("1000")
MAX_TARGET_ABV = Decimal("25")


class SugarWashState(StatesGroup):
    waiting_value = State()
    result_ready = State()


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


def compact_result_text(result: SugarWashResult) -> str:
    return (
        f"🍬 {result.fermentable_label} · ⚖️ {format_decimal(result.sugar_kg)} кг\n"
        f"💧 {format_decimal(result.water_l)} л · 🪣 {format_decimal(result.volume_l)} л · "
        f"📈 ~{format_decimal(result.potential_abv)}%"
    )


async def get_latest_preparation_composition(
    session: AsyncSession,
    process_id: int,
) -> DrinkEvent | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type.in_(("preparation_composition", "sugar_wash_calculation")),
        )
        .order_by(DrinkEvent.created_at.desc(), DrinkEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_sugar_wash_calculation(
    session: AsyncSession,
    *,
    process_id: int,
    result: SugarWashResult,
) -> DrinkEvent:
    data = result.as_event_data()
    data.update({"stage": "Подготовка", "source": "calculator"})
    event = DrinkEvent(
        drink_id=process_id,
        event_type="sugar_wash_calculation",
        title="Расчёт браги",
        data=data,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def show_result(
    message: Message,
    state: FSMContext,
    process_id: int,
    result: SugarWashResult,
) -> None:
    await state.set_state(SugarWashState.result_ready)
    await state.update_data(
        process_id=process_id,
        sugar_wash_result=result.as_event_data(),
    )
    await message.answer(
        f"✅ <b>Состав процесса обновлён</b>\n\n{result_text(result)}",
        reply_markup=process_sugar_wash_result_keyboard(process_id),
    )


def first_prompt(mode: str, fermentable_label: str) -> tuple[str, str]:
    if mode == "volume":
        return (
            "volume",
            "🪣 <b>Расчёт по объёму</b>\n\n"
            f"Сырьё: <b>{fermentable_label}</b>.\n"
            "Какой итоговый объём браги хотите получить?\n"
            "Введите число в литрах, например <code>25</code>.",
        )

    title = "⚖️ Расчёт по количеству сырья" if mode == "sugar" else "📈 Проверка состава"
    return (
        "amount",
        f"<b>{title}</b>\n\n"
        f"Сырьё: <b>{fermentable_label}</b>.\n"
        "Сколько используете? Введите количество в килограммах, например <code>6</code>.",
    )


@router.callback_query(F.data.startswith("process:sugar-wash:"))
async def sugar_wash_menu_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    parts = (callback.data or "").split(":")
    if len(parts) not in {3, 4}:
        return

    try:
        process_id = int(parts[2])
    except ValueError:
        return
    mode = parts[3] if len(parts) == 4 else None

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        latest_event = (
            await get_latest_preparation_composition(session, process_id)
            if process is not None
            else None
        )

    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return

    if stage_type_for_title(process.current_stage) != "preparation":
        await state.clear()
        await callback.message.edit_text(
            "🧮 <b>Калькуляторы</b>\n\n"
            "Расчёт браги доступен на этапе 🧰 Подготовка.",
            reply_markup=process_calculators_keyboard(process.id),
        )
        return

    if mode is None:
        await state.clear()
        text = (
            "🧮 <b>Расчёт браги</b>\n\n"
            "Выберите, от каких данных хотите считать:\n\n"
            "🪣 <b>По объёму</b> — знаю желаемый объём браги.\n"
            "⚖️ <b>По количеству сырья</b> — знаю, сколько сырья есть.\n"
            "📈 <b>Проверить состав</b> — уже знаю сырьё и воду."
        )
        latest_result = result_from_event_data(latest_event.data if latest_event else None)
        if latest_result is not None:
            text += "\n\n<b>Текущий состав:</b>\n" + compact_result_text(latest_result)
        await callback.message.edit_text(
            text,
            reply_markup=process_sugar_wash_menu_keyboard(process.id),
        )
        return

    if mode not in {"volume", "sugar", "check"}:
        return

    await state.clear()
    await state.update_data(process_id=process_id, calc_mode=mode)
    await callback.message.edit_text(
        "🍬 <b>Выберите сырьё</b>\n\n"
        "Для глюкозы и фруктозы расчёт учитывает их немного меньший "
        "теоретический выход этанола на килограмм по сравнению с сахарозой.",
        reply_markup=process_sugar_wash_fermentable_keyboard(process_id, mode),
    )


@router.callback_query(F.data.startswith("process:sugar-wash-material:"))
async def sugar_wash_material_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    try:
        process_id = int(parts[2])
    except ValueError:
        return
    mode = parts[3]
    fermentable = normalize_fermentable(parts[4])
    if mode not in {"volume", "sugar", "check"}:
        return

    await state.clear()
    await state.set_state(SugarWashState.waiting_value)
    await state.update_data(
        process_id=process_id,
        calc_mode=mode,
        fermentable=fermentable,
    )
    step, prompt = first_prompt(mode, result_from_event_data({
        "mode": "check",
        "water_l": "1",
        "fermentable_kg": "1",
        "volume_l": "1",
        "potential_abv": "1",
        "fermentable": fermentable,
    }).fermentable_label)
    await state.update_data(calc_step=step)
    await callback.message.edit_text(
        prompt,
        reply_markup=process_sugar_wash_input_keyboard(process_id),
    )


@router.message(SugarWashState.waiting_value)
async def sugar_wash_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    mode = data.get("calc_mode")
    step = data.get("calc_step")
    fermentable = normalize_fermentable(data.get("fermentable", DEFAULT_FERMENTABLE))
    if not isinstance(process_id, int) or not isinstance(mode, str) or not isinstance(step, str):
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
    if step == "amount" and value > MAX_INPUT_FERMENTABLE_KG:
        await message.answer("Для MVP укажите не больше 1 000 кг сырья.")
        return
    if step == "target_abv" and value > MAX_TARGET_ABV:
        await message.answer("Укажите потенциальную крепость от 1 до 25 %.")
        return

    if mode == "volume" and step == "volume":
        await state.update_data(volume_l=str(value), calc_step="target_abv")
        await message.answer(
            "📈 Какую потенциальную крепость хотите заложить?\n"
            "Введите процент, например <code>12</code>.\n\n"
            "Это расчётная цель, а не гарантированная фактическая крепость.",
            reply_markup=process_sugar_wash_input_keyboard(process_id),
        )
        return

    if mode == "sugar" and step == "amount":
        await state.update_data(amount_kg=str(value), calc_step="target_abv")
        await message.answer(
            "📈 Какую потенциальную крепость хотите заложить?\n"
            "Введите процент, например <code>12</code>.",
            reply_markup=process_sugar_wash_input_keyboard(process_id),
        )
        return

    if mode == "check" and step == "amount":
        await state.update_data(amount_kg=str(value), calc_step="water")
        await message.answer(
            "💧 Сколько воды используете?\n"
            "Введите количество в литрах, например <code>25</code>.",
            reply_markup=process_sugar_wash_input_keyboard(process_id),
        )
        return

    if step == "target_abv" and value < Decimal("1"):
        await message.answer("Укажите потенциальную крепость от 1 до 25 %.")
        return

    result: SugarWashResult | None = None
    if mode == "volume" and step == "target_abv":
        volume_l = decimal_from_state(data, "volume_l")
        if volume_l is not None:
            result = calculate_by_volume(volume_l, value, fermentable)
    elif mode == "sugar" and step == "target_abv":
        amount_kg = decimal_from_state(data, "amount_kg")
        if amount_kg is not None:
            result = calculate_by_sugar(amount_kg, value, fermentable)
    elif mode == "check" and step == "water":
        amount_kg = decimal_from_state(data, "amount_kg")
        if amount_kg is not None:
            result = calculate_from_composition(value, amount_kg, fermentable)

    if result is None:
        await state.clear()
        await message.answer("Не удалось восстановить данные расчёта. Запустите его заново.")
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден.")
            return
        if stage_type_for_title(process.current_stage) != "preparation":
            await state.clear()
            await message.answer("Процесс уже не находится на этапе подготовки.")
            return

        await save_sugar_wash_calculation(session, process_id=process.id, result=result)
        await save_preparation_composition(
            session,
            process_id=process.id,
            result=result,
            source="calculator",
        )

    await show_result(message, state, process_id, result)


# Совместимость со старыми сообщениями с кнопкой «Сохранить».
@router.callback_query(F.data.startswith("process:sugar-wash-save:"))
async def sugar_wash_save_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer("Теперь состав сохраняется автоматически.", show_alert=True)
