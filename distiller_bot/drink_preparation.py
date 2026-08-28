from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .drink_preparation_keyboards import (
    drink_preparation_input_keyboard,
    drink_preparation_keyboard,
    drink_preparation_result_keyboard,
    global_drink_preparation_input_keyboard,
    global_drink_preparation_keyboard,
    global_drink_preparation_result_keyboard,
)
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import get_owned_process, render_process_list
from .second_distillation import (
    dilution_result,
    format_decimal,
    get_cuts,
    round_abv,
    round_amount,
    summarize_cuts,
)

router = Router()

MAX_VOLUME_L = Decimal("10000")
MAX_ABV = Decimal("100")


@dataclass(frozen=True, slots=True)
class DrinkSource:
    volume_l: Decimal
    abv: Decimal
    absolute_alcohol_l: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class PreparedDrink:
    source_volume_l: Decimal
    source_abv: Decimal
    target_abv: Decimal
    water_l: Decimal
    final_volume_l: Decimal
    absolute_alcohol_l: Decimal
    source: str


class DrinkPreparationState(StatesGroup):
    waiting_source_volume = State()
    waiting_source_abv = State()
    waiting_target_abv = State()


def parse_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def source_from_values(volume_l: Decimal, abv: Decimal, source: str) -> DrinkSource:
    volume_l = round_amount(volume_l)
    abv = round_abv(abv)
    return DrinkSource(
        volume_l=volume_l,
        abv=abv,
        absolute_alcohol_l=round_amount(volume_l * abv / Decimal("100")),
        source=source,
    )


def result_from_data(data: dict | None) -> PreparedDrink | None:
    if not data:
        return None
    try:
        result = PreparedDrink(
            source_volume_l=Decimal(str(data["source_volume_l"])),
            source_abv=Decimal(str(data["source_abv"])),
            target_abv=Decimal(str(data["target_abv"])),
            water_l=Decimal(str(data["water_l"])),
            final_volume_l=Decimal(str(data["final_volume_l"])),
            absolute_alcohol_l=Decimal(str(data["absolute_alcohol_l"])),
            source=str(data.get("source") or "saved"),
        )
    except (KeyError, InvalidOperation, TypeError):
        return None
    values = (
        result.source_volume_l,
        result.source_abv,
        result.target_abv,
        result.water_l,
        result.final_volume_l,
        result.absolute_alcohol_l,
    )
    if not all(value.is_finite() for value in values):
        return None
    return result


async def get_second_distillation_body(
    session: AsyncSession,
    process_id: int,
) -> DrinkSource | None:
    cuts = await get_cuts(session, process_id)
    hearts = [cut for cut in cuts if cut.fraction == "hearts"]
    if not hearts:
        return None
    volume_l, abv, absolute_alcohol_l = summarize_cuts(hearts)
    if volume_l <= 0 or abv <= 0:
        return None
    return DrinkSource(
        volume_l=volume_l,
        abv=abv,
        absolute_alcohol_l=absolute_alcohol_l,
        source="second_distillation",
    )


async def get_saved_result(session: AsyncSession, process_id: int) -> PreparedDrink | None:
    query = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "drink_preparation_result",
        )
        .order_by(DrinkEvent.id.desc())
        .limit(1)
    )
    event = query.scalar_one_or_none()
    return result_from_data(event.data if event is not None else None)


async def get_original_source(session: AsyncSession, process_id: int) -> DrinkSource | None:
    body = await get_second_distillation_body(session, process_id)
    if body is not None:
        return body
    saved = await get_saved_result(session, process_id)
    if saved is None:
        return None
    return source_from_values(saved.source_volume_l, saved.source_abv, saved.source)


def drink_preparation_text(
    source: DrinkSource | None,
    result: PreparedDrink | None,
) -> str:
    lines = ["💧 <b>Подготовка напитка</b>"]
    if source is None:
        lines.extend(
            [
                "",
                "Данные второй перегонки не найдены.",
                "Можно указать исходный объём и крепость вручную.",
            ]
        )
    else:
        title = "🥃 <b>После второй перегонки</b>" if source.source == "second_distillation" else "🥃 <b>Исходный спирт</b>"
        lines.extend(
            [
                "",
                title,
                f"🟢 Тело: {format_decimal(source.volume_l)} л · {format_decimal(source.abv)}%",
                f"💧 Абсолютный спирт: {format_decimal(source.absolute_alcohol_l)} л",
            ]
        )

    if result is not None:
        lines.extend(
            [
                "",
                "🍶 <b>Подготовленный напиток</b>",
                f"💧 Объём: {format_decimal(result.final_volume_l)} л",
                f"📈 Крепость: {format_decimal(result.target_abv)}%",
                f"🚰 Добавлено воды: {format_decimal(result.water_l)} л",
                f"💧 Абсолютный спирт: {format_decimal(result.absolute_alcohol_l)} л",
            ]
        )
    return "\n".join(lines)


def dilution_preview_text(source: DrinkSource, target_abv: Decimal) -> tuple[str, PreparedDrink]:
    water_l, final_volume_l, absolute_alcohol_l = dilution_result(
        source.volume_l,
        source.abv,
        target_abv,
    )
    result = PreparedDrink(
        source_volume_l=source.volume_l,
        source_abv=source.abv,
        target_abv=round_abv(target_abv),
        water_l=water_l,
        final_volume_l=final_volume_l,
        absolute_alcohol_l=absolute_alcohol_l,
        source=source.source,
    )
    text = (
        "💧 <b>Разбавление спирта</b>\n\n"
        f"Исходно: <b>{format_decimal(source.volume_l)} л · {format_decimal(source.abv)}%</b>\n"
        f"Цель: <b>{format_decimal(result.target_abv)}%</b>\n\n"
        f"🚰 Добавить воды: <b>~{format_decimal(result.water_l)} л</b>\n"
        f"🍶 Получится: <b>~{format_decimal(result.final_volume_l)} л · {format_decimal(result.target_abv)}%</b>\n"
        f"💧 Абсолютный спирт: <b>~{format_decimal(result.absolute_alcohol_l)} л</b>\n\n"
        "ℹ️ Расчёт объёма приблизительный: при смешивании воды и спирта итоговый объём может немного отличаться."
    )
    return text, result


async def save_result(
    session: AsyncSession,
    *,
    process_id: int,
    result: PreparedDrink,
) -> None:
    session.add(
        DrinkEvent(
            drink_id=process_id,
            event_type="drink_preparation_result",
            title="Подготовлен напиток",
            data={
                "stage": "Подготовка напитка",
                "source": result.source,
                "source_volume_l": str(result.source_volume_l),
                "source_abv": str(result.source_abv),
                "target_abv": str(result.target_abv),
                "water_l": str(result.water_l),
                "final_volume_l": str(result.final_volume_l),
                "absolute_alcohol_l": str(result.absolute_alcohol_l),
            },
        )
    )
    await session.commit()


async def owned_process(session: AsyncSession, process_id: int, telegram_id: int):
    process = await get_owned_process(session, process_id, telegram_id)
    if process is None or stage_type_for_title(process.current_stage) != "drink_preparation":
        return None
    return process


async def show_drink_preparation(callback: CallbackQuery, state: FSMContext, session_factory, process_id: int) -> None:
    if callback.message is None:
        return
    async with session_factory() as session:
        process = await owned_process(session, process_id, callback.from_user.id)
        if process is None:
            await state.clear()
            await render_process_list(callback, session_factory)
            return
        source = await get_original_source(session, process_id)
        result = await get_saved_result(session, process_id)
    await state.clear()
    await callback.message.edit_text(
        drink_preparation_text(source, result),
        reply_markup=drink_preparation_keyboard(process_id),
    )


@router.callback_query(F.data.regexp(r"^process:drink-preparation:\d+$"))
async def drink_preparation_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await show_drink_preparation(callback, state, session_factory, process_id)


@router.callback_query(F.data.startswith("process:drink-preparation-dilute:"))
async def dilute_start(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await owned_process(session, process_id, callback.from_user.id)
        source = await get_original_source(session, process_id) if process is not None else None
    if process is None:
        return

    await state.clear()
    await state.update_data(mode="process", process_id=process_id)
    if source is None:
        await state.set_state(DrinkPreparationState.waiting_source_volume)
        await callback.message.edit_text(
            "💧 <b>Разбавление спирта</b>\n\n"
            "Данных второй перегонки нет. Введите исходный объём спирта в литрах.",
            reply_markup=drink_preparation_input_keyboard(process_id),
        )
        return

    await state.update_data(
        source_volume_l=str(source.volume_l),
        source_abv=str(source.abv),
        source_kind=source.source,
    )
    await state.set_state(DrinkPreparationState.waiting_target_abv)
    await callback.message.edit_text(
        "💧 <b>Разбавление спирта</b>\n\n"
        f"Исходно: <b>{format_decimal(source.volume_l)} л · {format_decimal(source.abv)}%</b>\n\n"
        "До какой крепости хотите разбавить? Например: <code>40</code>.",
        reply_markup=drink_preparation_input_keyboard(process_id),
    )


@router.message(DrinkPreparationState.waiting_source_volume)
async def source_volume_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    volume_l = parse_decimal(message.text)
    if volume_l is None or volume_l <= 0 or volume_l > MAX_VOLUME_L:
        await message.answer("Введите объём больше 0 и не больше 10000 л.")
        return
    await state.update_data(source_volume_l=str(round_amount(volume_l)))
    await state.set_state(DrinkPreparationState.waiting_source_abv)
    await message.answer("Введите исходную крепость в %. Например: <code>72.4</code>.")


@router.message(DrinkPreparationState.waiting_source_abv)
async def source_abv_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    abv = parse_decimal(message.text)
    if abv is None or not Decimal("0") < abv <= MAX_ABV:
        await message.answer("Крепость должна быть больше 0 и не больше 100%.")
        return
    await state.update_data(source_abv=str(round_abv(abv)), source_kind="manual")
    await state.set_state(DrinkPreparationState.waiting_target_abv)
    await message.answer("До какой крепости хотите разбавить? Например: <code>40</code>.")


@router.message(DrinkPreparationState.waiting_target_abv)
async def target_abv_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    target_abv = parse_decimal(message.text)
    data = await state.get_data()
    try:
        source = source_from_values(
            Decimal(str(data["source_volume_l"])),
            Decimal(str(data["source_abv"])),
            str(data.get("source_kind") or "manual"),
        )
    except (KeyError, InvalidOperation):
        await state.clear()
        await message.answer("Не удалось восстановить исходные данные. Откройте расчёт заново.")
        return
    if target_abv is None or target_abv <= 0 or target_abv > source.abv:
        await message.answer(
            f"Введите крепость больше 0 и не выше исходных {format_decimal(source.abv)}%."
        )
        return

    text, result = dilution_preview_text(source, target_abv)
    mode = data.get("mode")
    await state.update_data(
        target_abv=str(result.target_abv),
        water_l=str(result.water_l),
        final_volume_l=str(result.final_volume_l),
        absolute_alcohol_l=str(result.absolute_alcohol_l),
    )
    if mode == "global":
        await state.clear()
        await message.answer(text, reply_markup=global_drink_preparation_result_keyboard())
        return

    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    await message.answer(text, reply_markup=drink_preparation_result_keyboard(process_id))


@router.callback_query(F.data.startswith("process:drink-preparation-save:"))
async def save_result_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    data = await state.get_data()
    if data.get("process_id") != process_id:
        await state.clear()
        await callback.message.edit_text("Расчёт устарел. Откройте разбавление заново.")
        return
    try:
        result = PreparedDrink(
            source_volume_l=Decimal(str(data["source_volume_l"])),
            source_abv=Decimal(str(data["source_abv"])),
            target_abv=Decimal(str(data["target_abv"])),
            water_l=Decimal(str(data["water_l"])),
            final_volume_l=Decimal(str(data["final_volume_l"])),
            absolute_alcohol_l=Decimal(str(data["absolute_alcohol_l"])),
            source=str(data.get("source_kind") or "manual"),
        )
    except (KeyError, InvalidOperation):
        await state.clear()
        return

    async with session_factory() as session:
        process = await owned_process(session, process_id, callback.from_user.id)
        if process is None:
            await state.clear()
            return
        await save_result(session, process_id=process_id, result=result)
        source = await get_original_source(session, process_id)
        saved = await get_saved_result(session, process_id)

    await state.clear()
    await callback.message.edit_text(
        "✅ Результат сохранён\n\n" + drink_preparation_text(source, saved),
        reply_markup=drink_preparation_keyboard(process_id),
    )


@router.callback_query(F.data == "calculators:drink-preparation")
async def global_category_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            "💧 <b>Подготовка напитка</b>\n\nКалькулятор разбавления спирта до нужной крепости.",
            reply_markup=global_drink_preparation_keyboard(),
        )


@router.callback_query(F.data == "calculators:drink-preparation:dilution")
async def global_dilution_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await state.update_data(mode="global")
    await state.set_state(DrinkPreparationState.waiting_source_volume)
    await callback.message.edit_text(
        "💧 <b>Разбавление спирта</b>\n\nВведите исходный объём спирта в литрах.",
        reply_markup=global_drink_preparation_input_keyboard(),
    )
