from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import DrinkEvent
from .preparation_keyboards import (
    composition_fermentable_keyboard,
    composition_input_keyboard,
    preparation_composition_keyboard,
)
from .process_stages import stage_type_for_title
from .processes import (
    get_owned_process,
    get_process_card_context,
    process_card_markup,
    process_card_text,
    render_process_list,
)
from .sugar_wash import (
    DEFAULT_FERMENTABLE,
    SugarWashResult,
    calculate_from_composition,
    fermentable_label,
    format_decimal,
    normalize_fermentable,
    recalculate_abv,
    recalculate_amount,
    recalculate_fermentable,
    recalculate_volume,
    recalculate_water,
    result_from_event_data,
)

router = Router()

MAX_INPUT_WATER_L = Decimal("10000")
MAX_INPUT_FERMENTABLE_KG = Decimal("1000")
MAX_TARGET_ABV = Decimal("25")


class PreparationCompositionState(StatesGroup):
    choosing_fermentable = State()
    waiting_amount = State()
    waiting_water = State()
    waiting_edit_value = State()


def parse_positive_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value


def current_composition(process) -> SugarWashResult | None:
    event = getattr(process, "_latest_preparation_composition", None)
    return result_from_event_data(event.data if event is not None else None)


def composition_text(result: SugarWashResult | None) -> str:
    if result is None:
        return (
            "🍬 <b>Состав браги</b>\n\n"
            "Состав пока не задан. Укажите сырьё, его количество и воду - "
            "объём и потенциальную крепость бот рассчитает автоматически."
        )

    return (
        "🍬 <b>Состав браги</b>\n\n"
        f"Сырьё: <b>{result.fermentable_label}</b>\n"
        f"⚖️ Количество: <b>{format_decimal(result.sugar_kg)} кг</b>\n"
        f"💧 Вода: <b>{format_decimal(result.water_l)} л</b>\n"
        f"🪣 Объём: <b>{format_decimal(result.volume_l)} л</b>\n"
        f"📈 Потенциальная крепость: <b>~{format_decimal(result.potential_abv)}%</b>\n\n"
        "Измените любой параметр - связанные показатели будут пересчитаны."
    )


def result_error(result: SugarWashResult) -> str | None:
    if result.potential_abv > MAX_TARGET_ABV:
        return (
            "При таком составе потенциальная крепость получается выше 25 %. "
            "Для MVP уменьшите количество сырья или добавьте больше воды."
        )
    if result.water_l <= 0:
        return "Расчёт даёт неположительный объём воды. Измените параметры."
    return None


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
        event_type="preparation_composition",
        title="Состав браги",
        data=data,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def show_composition(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    process_id: int,
) -> None:
    if callback.message is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return

    result = current_composition(process)
    await state.clear()
    await callback.message.edit_text(
        composition_text(result),
        reply_markup=preparation_composition_keyboard(
            process.id,
            has_composition=result is not None,
        ),
    )


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
        await callback.message.edit_text("Состав браги редактируется на этапе 🧰 Подготовка.")
        return

    result = current_composition(process)
    await state.clear()
    await callback.message.edit_text(
        composition_text(result),
        reply_markup=preparation_composition_keyboard(
            process_id,
            has_composition=result is not None,
        ),
    )


@router.callback_query(F.data.startswith("process:composition-start:"))
async def preparation_composition_start_handler(
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
    await state.set_state(PreparationCompositionState.choosing_fermentable)
    await state.update_data(process_id=process_id, composition_action="create")
    await callback.message.edit_text(
        "🍬 <b>Сырьё</b>\n\nЧто используете как основное сахарное сырьё?",
        reply_markup=composition_fermentable_keyboard(process_id),
    )


@router.callback_query(F.data.startswith("process:composition-edit:"))
async def preparation_composition_edit_handler(
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

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return
    result = current_composition(process)
    if result is None:
        await show_composition(callback, state, session_factory, process_id)
        return

    if field == "fermentable":
        await state.clear()
        await state.set_state(PreparationCompositionState.choosing_fermentable)
        await state.update_data(process_id=process_id, composition_action="edit_fermentable")
        await callback.message.edit_text(
            "🍬 <b>Изменить сырьё</b>\n\n"
            f"Сейчас: <b>{result.fermentable_label}</b>.\n"
            f"Сохраним объём {format_decimal(result.volume_l)} л и потенциальную крепость "
            f"~{format_decimal(result.potential_abv)}%, а количество сырья и воду пересчитаем.",
            reply_markup=composition_fermentable_keyboard(process_id),
        )
        return

    prompts = {
        "amount": (
            "⚖️ <b>Количество сырья</b>\n\n"
            f"Сейчас: {format_decimal(result.sugar_kg)} кг.\n"
            f"Вода останется {format_decimal(result.water_l)} л; объём и крепость пересчитаются.\n\n"
            "Введите новое количество в кг."
        ),
        "water": (
            "💧 <b>Количество воды</b>\n\n"
            f"Сейчас: {format_decimal(result.water_l)} л.\n"
            f"Количество сырья останется {format_decimal(result.sugar_kg)} кг; "
            "объём и крепость пересчитаются.\n\nВведите новый объём воды в литрах."
        ),
        "volume": (
            "🪣 <b>Итоговый объём</b>\n\n"
            f"Сейчас: {format_decimal(result.volume_l)} л.\n"
            f"Потенциальная крепость останется ~{format_decimal(result.potential_abv)}%; "
            "сырьё и вода пересчитаются.\n\nВведите новый объём в литрах."
        ),
        "abv": (
            "📈 <b>Потенциальная крепость</b>\n\n"
            f"Сейчас: ~{format_decimal(result.potential_abv)}%.\n"
            f"Объём останется {format_decimal(result.volume_l)} л; "
            "сырьё и вода пересчитаются.\n\nВведите новую крепость от 1 до 25 %."
        ),
    }
    prompt = prompts.get(field)
    if prompt is None:
        return

    await state.clear()
    await state.set_state(PreparationCompositionState.waiting_edit_value)
    await state.update_data(process_id=process_id, edit_field=field)
    await callback.message.edit_text(
        prompt,
        reply_markup=composition_input_keyboard(process_id),
    )


@router.callback_query(F.data.startswith("process:composition-material:"))
async def preparation_composition_material_handler(
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
    fermentable = normalize_fermentable(parts[3])

    data = await state.get_data()
    action = data.get("composition_action")

    if action == "create":
        await state.set_state(PreparationCompositionState.waiting_amount)
        await state.update_data(process_id=process_id, fermentable=fermentable)
        await callback.message.edit_text(
            f"⚖️ <b>{fermentable_label(fermentable)}</b>\n\n"
            "Сколько используете? Введите количество в килограммах, например <code>5,1</code>.",
            reply_markup=composition_input_keyboard(process_id),
        )
        return

    if action != "edit_fermentable":
        await state.clear()
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        if process is None:
            await state.clear()
            await render_process_list(callback, session_factory)
            return
        result = current_composition(process)
        if result is None:
            await state.clear()
            return
        updated = recalculate_fermentable(result, fermentable)
        event = await save_preparation_composition(
            session,
            process_id=process.id,
            result=updated,
            source="edit_fermentable",
        )
        setattr(process, "_latest_preparation_composition", event)

    await state.clear()
    await callback.message.edit_text(
        f"✅ Сырьё изменено\n\n{composition_text(updated)}",
        reply_markup=preparation_composition_keyboard(process_id, has_composition=True),
    )


@router.message(PreparationCompositionState.waiting_amount)
async def preparation_composition_amount_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    amount_kg = parse_positive_decimal(message.text)
    if amount_kg is None:
        await message.answer("Введите положительное число, например <code>5,1</code>.")
        return
    if amount_kg > MAX_INPUT_FERMENTABLE_KG:
        await message.answer("Для MVP укажите не больше 1 000 кг сырья.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    await state.update_data(amount_kg=str(amount_kg))
    await state.set_state(PreparationCompositionState.waiting_water)
    await message.answer(
        "💧 Сколько воды используете?\n"
        "Введите количество в литрах, например <code>21,9</code>.",
        reply_markup=composition_input_keyboard(process_id),
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
    raw_amount = data.get("amount_kg")
    fermentable = normalize_fermentable(data.get("fermentable", DEFAULT_FERMENTABLE))
    if not isinstance(process_id, int) or raw_amount is None:
        await state.clear()
        return

    try:
        amount_kg = Decimal(str(raw_amount))
    except InvalidOperation:
        await state.clear()
        return
    if not amount_kg.is_finite() or amount_kg <= 0:
        await state.clear()
        return

    result = calculate_from_composition(water_l, amount_kg, fermentable)
    error = result_error(result)
    if error is not None:
        await message.answer(error)
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

        event = await save_preparation_composition(
            session,
            process_id=process.id,
            result=result,
            source="manual",
        )
        setattr(process, "_latest_preparation_composition", event)
        latest_measurement, latest_note = await get_process_card_context(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Состав обновлён\n\n{process_card_text(process, latest_measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )


@router.message(PreparationCompositionState.waiting_edit_value)
async def preparation_composition_edit_value_handler(
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
    if not isinstance(process_id, int) or not isinstance(field, str):
        await state.clear()
        return

    if field == "amount" and value > MAX_INPUT_FERMENTABLE_KG:
        await message.answer("Для MVP укажите не больше 1 000 кг сырья.")
        return
    if field in {"water", "volume"} and value > MAX_INPUT_WATER_L:
        await message.answer("Для MVP укажите объём не больше 10 000 л.")
        return
    if field == "abv" and not (Decimal("1") <= value <= MAX_TARGET_ABV):
        await message.answer("Укажите потенциальную крепость от 1 до 25 %.")
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден.")
            return
        result = current_composition(process)
        if result is None:
            await state.clear()
            await message.answer("Состав не найден. Задайте его заново.")
            return

        if field == "amount":
            updated = recalculate_amount(result, value)
        elif field == "water":
            updated = recalculate_water(result, value)
        elif field == "volume":
            updated = recalculate_volume(result, value)
        elif field == "abv":
            updated = recalculate_abv(result, value)
        else:
            await state.clear()
            return

        error = result_error(updated)
        if error is not None:
            await message.answer(error)
            return

        event = await save_preparation_composition(
            session,
            process_id=process.id,
            result=updated,
            source=f"edit_{field}",
        )
        setattr(process, "_latest_preparation_composition", event)
        latest_measurement, latest_note = await get_process_card_context(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Состав пересчитан\n\n{process_card_text(process, latest_measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )
