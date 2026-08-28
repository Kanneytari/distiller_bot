from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import (
    process_calculators_keyboard,
    sugar_wash_input_keyboard,
    sugar_wash_menu_keyboard,
    sugar_wash_result_keyboard,
)
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import get_owned_process, render_process_list
from .sugar_wash import (
    SugarWashResult,
    calculate_by_sugar,
    calculate_by_volume,
    calculate_from_composition,
    format_decimal,
    result_text,
)

router = Router()

MAX_INPUT_VOLUME_L = Decimal("10000")
MAX_INPUT_SUGAR_KG = Decimal("1000")
MAX_TARGET_ABV = Decimal("25")


class SugarWashState(StatesGroup):
    waiting_value = State()
    result_ready = State()


def parse_positive_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    return value if value > 0 else None


def result_from_data(data: dict[str, object] | None) -> SugarWashResult | None:
    if not data:
        return None
    try:
        return SugarWashResult(
            mode=str(data["mode"]),
            water_l=Decimal(str(data["water_l"])),
            sugar_kg=Decimal(str(data["sugar_kg"])),
            volume_l=Decimal(str(data["volume_l"])),
            potential_abv=Decimal(str(data["potential_abv"])),
        )
    except (KeyError, InvalidOperation):
        return None


def compact_result_text(result: SugarWashResult) -> str:
    return (
        f"💧 {format_decimal(result.water_l)} л · "
        f"🍬 {format_decimal(result.sugar_kg)} кг\n"
        f"🪣 {format_decimal(result.volume_l)} л · "
        f"📈 ~{format_decimal(result.potential_abv)}%"
    )


async def get_latest_sugar_wash_calculation(
    session: AsyncSession,
    process_id: int,
) -> DrinkEvent | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "sugar_wash_calculation",
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
) -> None:
    data = result.as_event_data()
    data["stage"] = "Подготовка"
    session.add(
        DrinkEvent(
            drink_id=process_id,
            event_type="sugar_wash_calculation",
            title="Расчёт сахарной браги",
            data=data,
        )
    )
    await session.commit()


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
        result_text(result),
        reply_markup=sugar_wash_result_keyboard(process_id),
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
            await get_latest_sugar_wash_calculation(session, process_id)
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
            "Расчёт сахарной браги доступен на этапе 🧰 Подготовка.",
            reply_markup=process_calculators_keyboard(process.id),
        )
        return

    if mode is None:
        await state.clear()
        text = (
            "🧮 <b>Сахарная брага</b>\n\n"
            "Выберите, от каких данных хотите считать:\n\n"
            "🪣 <b>По объёму</b> — знаю желаемый объём браги.\n"
            "🍬 <b>По сахару</b> — знаю, сколько сахара есть.\n"
            "📈 <b>Проверить состав</b> — уже знаю сахар и воду."
        )
        latest_result = result_from_data(latest_event.data if latest_event else None)
        if latest_result is not None:
            text += (
                "\n\n<b>Последний сохранённый расчёт:</b>\n"
                f"{compact_result_text(latest_result)}"
            )
        await callback.message.edit_text(
            text,
            reply_markup=sugar_wash_menu_keyboard(process.id),
        )
        return

    if mode not in {"volume", "sugar", "check"}:
        return

    await state.clear()
    await state.set_state(SugarWashState.waiting_value)
    await state.update_data(process_id=process_id, calc_mode=mode)

    if mode == "volume":
        await state.update_data(calc_step="volume")
        prompt = (
            "🪣 <b>Расчёт по объёму</b>\n\n"
            "Какой итоговый объём браги хотите получить?\n"
            "Введите число в литрах, например <code>25</code>."
        )
    else:
        await state.update_data(calc_step="sugar")
        title = "🍬 Расчёт по сахару" if mode == "sugar" else "📈 Проверка состава"
        prompt = (
            f"<b>{title}</b>\n\n"
            "Сколько сахара используете?\n"
            "Введите количество в килограммах, например <code>6</code>."
        )

    await callback.message.edit_text(
        prompt,
        reply_markup=sugar_wash_input_keyboard(process_id),
    )


@router.message(SugarWashState.waiting_value)
async def sugar_wash_value_handler(
    message: Message,
    state: FSMContext,
) -> None:
    if message.text is None:
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    mode = data.get("calc_mode")
    step = data.get("calc_step")
    if not isinstance(process_id, int) or not isinstance(mode, str) or not isinstance(step, str):
        await state.clear()
        return

    value = parse_positive_decimal(message.text)
    if value is None:
        await message.answer("Введите положительное число. Например: <code>25</code> или <code>5,5</code>.")
        return

    if step in {"volume", "water"} and value > MAX_INPUT_VOLUME_L:
        await message.answer("Для MVP укажите объём не больше 10 000 л.")
        return
    if step == "sugar" and value > MAX_INPUT_SUGAR_KG:
        await message.answer("Для MVP укажите не больше 1 000 кг сахара.")
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
            reply_markup=sugar_wash_input_keyboard(process_id),
        )
        return

    if mode == "sugar" and step == "sugar":
        await state.update_data(sugar_kg=str(value), calc_step="target_abv")
        await message.answer(
            "📈 Какую потенциальную крепость хотите заложить?\n"
            "Введите процент, например <code>12</code>.",
            reply_markup=sugar_wash_input_keyboard(process_id),
        )
        return

    if mode == "check" and step == "sugar":
        await state.update_data(sugar_kg=str(value), calc_step="water")
        await message.answer(
            "💧 Сколько воды используете?\n"
            "Введите количество в литрах, например <code>25</code>.",
            reply_markup=sugar_wash_input_keyboard(process_id),
        )
        return

    if step == "target_abv" and value < Decimal("1"):
        await message.answer("Укажите потенциальную крепость от 1 до 25 %.")
        return

    result: SugarWashResult | None = None
    if mode == "volume" and step == "target_abv":
        volume_l = Decimal(str(data.get("volume_l")))
        result = calculate_by_volume(volume_l, value)
    elif mode == "sugar" and step == "target_abv":
        sugar_kg = Decimal(str(data.get("sugar_kg")))
        result = calculate_by_sugar(sugar_kg, value)
    elif mode == "check" and step == "water":
        sugar_kg = Decimal(str(data.get("sugar_kg")))
        result = calculate_from_composition(value, sugar_kg)

    if result is None:
        await state.clear()
        return

    await show_result(message, state, process_id, result)


@router.callback_query(F.data.startswith("process:sugar-wash-save:"))
async def sugar_wash_save_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    try:
        process_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    data = await state.get_data()
    state_process_id = data.get("process_id")
    result = result_from_data(data.get("sugar_wash_result"))
    if state_process_id != process_id or result is None:
        await state.clear()
        await callback.message.edit_text(
            "Расчёт больше не доступен для сохранения. Выполните его заново.",
            reply_markup=sugar_wash_menu_keyboard(process_id),
        )
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        if process is None:
            await state.clear()
            await render_process_list(callback, session_factory)
            return
        if stage_type_for_title(process.current_stage) != "preparation":
            await state.clear()
            await callback.message.edit_text(
                "Расчёт не сохранён: процесс уже не находится на этапе подготовки.",
                reply_markup=process_calculators_keyboard(process.id),
            )
            return
        await save_sugar_wash_calculation(session, process_id=process.id, result=result)

    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Расчёт сохранён в процессе</b>\n\n{result_text(result)}",
        reply_markup=sugar_wash_menu_keyboard(process_id),
    )
