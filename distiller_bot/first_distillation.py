from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .first_distillation_keyboards import (
    first_distillation_input_keyboard,
    first_distillation_keyboard,
)
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import get_owned_process, render_process_list


router = Router()

MAX_VOLUME_L = Decimal("10000")
MAX_ABV = Decimal("100")


class FirstDistillationState(StatesGroup):
    waiting_volume = State()
    waiting_abv = State()
    waiting_edit_value = State()


def parse_positive_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value


def round_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_abv(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def absolute_alcohol_l(volume_l: Decimal, abv: Decimal) -> Decimal:
    return round_amount(volume_l * abv / Decimal("100"))


def result_from_event(event: DrinkEvent | None) -> tuple[Decimal, Decimal] | None:
    if event is None or not event.data:
        return None
    try:
        volume_l = Decimal(str(event.data["low_wines_volume_l"]))
        abv = Decimal(str(event.data["low_wines_abv"]))
    except (KeyError, InvalidOperation, TypeError):
        return None
    if not volume_l.is_finite() or not abv.is_finite():
        return None
    if volume_l <= 0 or abv <= 0 or abv > MAX_ABV:
        return None
    return volume_l, abv


def result_text(result: tuple[Decimal, Decimal] | None) -> str:
    if result is None:
        return (
            "⚗️ <b>Первая перегонка</b>\n\n"
            "Результат пока не записан.\n\n"
            "Сохраните объём и среднюю крепость полученного спирта-сырца. "
            "Количество абсолютного спирта бот рассчитает автоматически."
        )

    volume_l, abv = result
    aa_l = absolute_alcohol_l(volume_l, abv)
    return (
        "⚗️ <b>Первая перегонка</b>\n\n"
        f"🥃 Спирт-сырец: <b>{format_decimal(volume_l)} л</b>\n"
        f"📈 Крепость: <b>{format_decimal(abv)}%</b>\n"
        f"💧 Абсолютный спирт: <b>~{format_decimal(aa_l)} л</b>"
    )


async def get_latest_result(
    session: AsyncSession,
    process_id: int,
) -> DrinkEvent | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "first_distillation_result",
        )
        .order_by(DrinkEvent.created_at.desc(), DrinkEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_result(
    session: AsyncSession,
    *,
    process_id: int,
    volume_l: Decimal,
    abv: Decimal,
    source: str,
) -> DrinkEvent:
    volume_l = round_amount(volume_l)
    abv = round_abv(abv)
    aa_l = absolute_alcohol_l(volume_l, abv)
    event = DrinkEvent(
        drink_id=process_id,
        event_type="first_distillation_result",
        title="Результат первой перегонки",
        data={
            "stage": "Первая перегонка",
            "source": source,
            "low_wines_volume_l": str(volume_l),
            "low_wines_abv": str(abv),
            "absolute_alcohol_l": str(aa_l),
        },
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.callback_query(F.data.startswith("process:first-distillation:"))
async def first_distillation_handler(
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
        event = await get_latest_result(session, process_id) if process is not None else None

    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return

    if stage_type_for_title(process.current_stage) != "first_distillation":
        await state.clear()
        await callback.message.edit_text("Результат первой перегонки доступен только на этом этапе.")
        return

    result = result_from_event(event)
    await state.clear()
    await callback.message.edit_text(
        result_text(result),
        reply_markup=first_distillation_keyboard(process_id, has_result=result is not None),
    )


@router.callback_query(F.data.startswith("process:first-distillation-start:"))
async def first_distillation_start_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    try:
        process_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    await state.clear()
    await state.set_state(FirstDistillationState.waiting_volume)
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        "🥃 <b>Спирт-сырец</b>\n\n"
        "Какой объём получили после первой перегонки?\n"
        "Введите количество в литрах, например <code>7,5</code>.",
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_volume)
async def first_distillation_volume_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    volume_l = parse_positive_decimal(message.text)
    if volume_l is None:
        await message.answer("Введите положительное число, например <code>7,5</code>.")
        return
    if volume_l > MAX_VOLUME_L:
        await message.answer("Для MVP укажите объём не больше 10 000 л.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    await state.update_data(volume_l=str(volume_l))
    await state.set_state(FirstDistillationState.waiting_abv)
    await message.answer(
        "📈 Какая средняя крепость полученного спирта-сырца?\n"
        "Введите процент, например <code>32</code>.",
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_abv)
async def first_distillation_abv_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    abv = parse_positive_decimal(message.text)
    if abv is None or abv > MAX_ABV:
        await message.answer("Введите крепость от 0 до 100 %.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    raw_volume = data.get("volume_l")
    if not isinstance(process_id, int) or raw_volume is None:
        await state.clear()
        return

    try:
        volume_l = Decimal(str(raw_volume))
    except InvalidOperation:
        await state.clear()
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден.")
            return
        if stage_type_for_title(process.current_stage) != "first_distillation":
            await state.clear()
            await message.answer("Процесс уже не находится на этапе первой перегонки.")
            return
        event = await save_result(
            session,
            process_id=process.id,
            volume_l=volume_l,
            abv=abv,
            source="create",
        )

    result = result_from_event(event)
    await state.clear()
    await message.answer(
        f"✅ Результат сохранён\n\n{result_text(result)}",
        reply_markup=first_distillation_keyboard(process_id, has_result=True),
    )


@router.callback_query(F.data.startswith("process:first-distillation-edit:"))
async def first_distillation_edit_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    try:
        process_id = int(parts[2])
    except ValueError:
        return
    field = parts[3]
    if field not in {"volume", "abv"}:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        event = await get_latest_result(session, process_id) if process is not None else None

    result = result_from_event(event)
    if process is None or result is None:
        await state.clear()
        return

    volume_l, abv = result
    await state.clear()
    await state.set_state(FirstDistillationState.waiting_edit_value)
    await state.update_data(process_id=process_id, edit_field=field)

    if field == "volume":
        text = (
            "🥃 <b>Изменить объём спирта-сырца</b>\n\n"
            f"Сейчас: {format_decimal(volume_l)} л.\n"
            "Крепость останется прежней, абсолютный спирт пересчитается.\n\n"
            "Введите новый объём в литрах."
        )
    else:
        text = (
            "📈 <b>Изменить крепость спирта-сырца</b>\n\n"
            f"Сейчас: {format_decimal(abv)}%.\n"
            "Объём останется прежним, абсолютный спирт пересчитается.\n\n"
            "Введите новую крепость в процентах."
        )

    await callback.message.edit_text(
        text,
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_edit_value)
async def first_distillation_edit_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    value = parse_positive_decimal(message.text)
    if value is None:
        await message.answer("Введите положительное число.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    field = data.get("edit_field")
    if not isinstance(process_id, int) or field not in {"volume", "abv"}:
        await state.clear()
        return

    if field == "volume" and value > MAX_VOLUME_L:
        await message.answer("Для MVP укажите объём не больше 10 000 л.")
        return
    if field == "abv" and value > MAX_ABV:
        await message.answer("Введите крепость от 0 до 100 %.")
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        event = await get_latest_result(session, process_id) if process is not None else None
        result = result_from_event(event)
        if process is None or result is None:
            await state.clear()
            await message.answer("Результат первой перегонки не найден.")
            return
        if stage_type_for_title(process.current_stage) != "first_distillation":
            await state.clear()
            await message.answer("Процесс уже не находится на этапе первой перегонки.")
            return

        volume_l, abv = result
        if field == "volume":
            volume_l = value
        else:
            abv = value

        saved_event = await save_result(
            session,
            process_id=process.id,
            volume_l=volume_l,
            abv=abv,
            source=f"edit_{field}",
        )

    updated = result_from_event(saved_event)
    await state.clear()
    await message.answer(
        f"✅ Результат пересчитан\n\n{result_text(updated)}",
        reply_markup=first_distillation_keyboard(process_id, has_result=True),
    )
