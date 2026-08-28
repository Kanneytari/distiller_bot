from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import process_input_cancel_keyboard
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import (
    get_owned_process,
    get_process_card_context,
    process_card_markup,
    process_card_text,
    render_process_list,
)
from .sugar_wash import SugarWashResult, calculate_from_composition

router = Router()

MAX_INPUT_WATER_L = Decimal("10000")
MAX_INPUT_SUGAR_KG = Decimal("1000")


class PreparationCompositionState(StatesGroup):
    waiting_sugar = State()
    waiting_water = State()


def parse_positive_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value


async def save_preparation_composition(
    session: AsyncSession,
    *,
    process_id: int,
    result: SugarWashResult,
    source: str,
) -> DrinkEvent:
    data = result.as_event_data()
    data.update({"stage": "Подготовка", "source": source})
    event = DrinkEvent(
        drink_id=process_id,
        event_type="sugar_wash_calculation",
        title="Состав сахарной браги",
        data=data,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.callback_query(F.data.startswith("process:composition:"))
async def preparation_composition_handler(
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

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return
    if stage_type_for_title(process.current_stage) != "preparation":
        await state.clear()
        await callback.message.edit_text(
            "Состав браги редактируется на этапе 🧰 Подготовка.",
            reply_markup=process_input_cancel_keyboard(process_id),
        )
        return

    await state.clear()
    await state.update_data(process_id=process_id)
    await state.set_state(PreparationCompositionState.waiting_sugar)
    await callback.message.edit_text(
        "🍬 <b>Состав браги</b>\n\n"
        "Сколько сахара используете?\n"
        "Введите количество в килограммах, например <code>5,1</code>.",
        reply_markup=process_input_cancel_keyboard(process_id),
    )


@router.message(PreparationCompositionState.waiting_sugar)
async def preparation_composition_sugar_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    sugar_kg = parse_positive_decimal(message.text)
    if sugar_kg is None:
        await message.answer("Введите положительное число, например <code>5,1</code>.")
        return
    if sugar_kg > MAX_INPUT_SUGAR_KG:
        await message.answer("Для MVP укажите не больше 1 000 кг сахара.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    await state.update_data(sugar_kg=str(sugar_kg))
    await state.set_state(PreparationCompositionState.waiting_water)
    await message.answer(
        "💧 Сколько воды используете?\n"
        "Введите количество в литрах, например <code>21,9</code>.",
        reply_markup=process_input_cancel_keyboard(process_id),
    )


@router.message(PreparationCompositionState.waiting_water)
async def preparation_composition_water_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    water_l = parse_positive_decimal(message.text)
    if water_l is None:
        await message.answer("Введите положительное число, например <code>21,9</code>.")
        return
    if water_l > MAX_INPUT_WATER_L:
        await message.answer("Для MVP укажите объём не больше 10 000 л.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    raw_sugar = data.get("sugar_kg")
    if not isinstance(process_id, int) or raw_sugar is None:
        await state.clear()
        return

    try:
        sugar_kg = Decimal(str(raw_sugar))
    except InvalidOperation:
        await state.clear()
        return
    if not sugar_kg.is_finite() or sugar_kg <= 0:
        await state.clear()
        return

    result = calculate_from_composition(water_l, sugar_kg)

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

        event = await save_preparation_composition(
            session,
            process_id=process.id,
            result=result,
            source="manual",
        )
        setattr(process, "_latest_sugar_wash_calculation", event)
        latest_measurement, latest_note = await get_process_card_context(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Состав обновлён\n\n{process_card_text(process, latest_measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )
