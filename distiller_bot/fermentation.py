from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .fermentation_keyboards import (
    fermentation_calculators_keyboard,
    fermentation_input_keyboard,
    fermentation_result_keyboard,
)
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import (
    create_measurement,
    get_latest_note,
    get_owned_process,
    process_card_markup,
    process_card_text,
    render_process_list,
)
from .refractometer import MAX_BRIX, RefractometerResult, calculate_refractometer

router = Router()

MIN_TEMPERATURE_C = Decimal("-20")
MAX_TEMPERATURE_C = Decimal("80")


class FermentationState(StatesGroup):
    waiting_temperature = State()
    waiting_initial_brix = State()
    waiting_current_brix = State()


def parse_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", ".").replace("°Bx", "").replace("Bx", "").strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def refractometer_result_text(result: RefractometerResult) -> str:
    return (
        "🧪 <b>Крепость по Brix</b>\n\n"
        "<b>До брожения</b>\n"
        f"🔹 Brix: <b>{format_decimal(result.initial_brix)} °Bx</b>\n"
        f"🔹 Расчётная OG: <b>~{format_decimal(result.original_sg)}</b>\n"
        f"🔹 Потенциальная крепость: <b>~{format_decimal(result.potential_abv)}%</b>\n\n"
        "<b>Текущее состояние</b>\n"
        f"🔹 Brix: <b>{format_decimal(result.current_brix)} °Bx</b>\n"
        f"🔹 Скорректированная SG: <b>~{format_decimal(result.corrected_sg)}</b>\n"
        f"🍷 Оценка крепости: <b>~{format_decimal(result.current_abv)}%</b>\n\n"
        "ℹ️ После начала брожения спирт искажает показания рефрактометра. "
        "Используйте значения со шкалы Brix, а не Wort SG. Расчёт ориентировочный."
    )


async def get_fermentation_process(
    session: AsyncSession,
    process_id: int,
    telegram_id: int,
):
    process = await get_owned_process(session, process_id, telegram_id)
    if process is None or stage_type_for_title(process.current_stage) != "fermentation":
        return None
    return process


@router.callback_query(F.data == "calculators:fermentation")
async def fermentation_calculators_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await callback.message.edit_text(
        "🫧 <b>Брожение</b>\n\n"
        "Расчёт крепости по показаниям рефрактометра до и во время брожения.",
        reply_markup=fermentation_calculators_keyboard(),
    )


@router.callback_query(F.data.regexp(r"^process:fermentation-temperature:\d+$"))
async def fermentation_temperature_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await get_fermentation_process(session, process_id, callback.from_user.id)
    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.update_data(process_id=process_id)
    await state.set_state(FermentationState.waiting_temperature)
    await callback.message.edit_text(
        "🌡 <b>Температура брожения</b>\n\n"
        "Введите температуру в °C, например <code>24</code>.",
        reply_markup=fermentation_input_keyboard(process_id),
    )


@router.message(FermentationState.waiting_temperature)
async def fermentation_temperature_value_handler(
    message: Message,
    state: FSMContext,
    session_factory,
) -> None:
    if message.from_user is None or message.text is None:
        return
    value = parse_decimal(message.text.replace("°C", "").replace("C", ""))
    if value is None or not MIN_TEMPERATURE_C <= value <= MAX_TEMPERATURE_C:
        await message.answer("Введите температуру от -20 до 80 °C.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    async with session_factory() as session:
        process = await get_fermentation_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден или этап уже изменён.")
            return
        measurement = await create_measurement(
            session,
            process=process,
            measurement_type="temperature",
            label="Температура",
            value=value,
            unit="°C",
        )
        latest_note = await get_latest_note(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Температура сохранена\n\n{process_card_text(process, measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )


@router.callback_query(F.data == "calculators:fermentation-brix")
@router.callback_query(F.data.regexp(r"^process:fermentation-brix:\d+$"))
async def fermentation_brix_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    process_id: int | None = None
    if (callback.data or "").startswith("process:"):
        process_id = int((callback.data or "").rsplit(":", 1)[-1])
        async with session_factory() as session:
            process = await get_fermentation_process(session, process_id, callback.from_user.id)
        if process is None:
            await state.clear()
            await render_process_list(callback, session_factory)
            return

    await state.clear()
    await state.update_data(process_id=process_id)
    await state.set_state(FermentationState.waiting_initial_brix)
    await callback.message.edit_text(
        "🧪 <b>Крепость по Brix</b>\n\n"
        "Введите показание рефрактометра <b>до начала брожения</b> по шкале Brix.\n"
        "Например: <code>20</code>.\n\n"
        "Шкалу Wort SG после начала брожения для этого расчёта не используем.",
        reply_markup=fermentation_input_keyboard(process_id),
    )


@router.message(FermentationState.waiting_initial_brix)
async def fermentation_initial_brix_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    value = parse_decimal(message.text)
    if value is None or not Decimal("0") < value <= MAX_BRIX:
        await message.answer("Введите начальный Brix от 0 до 50, например <code>20</code>.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    await state.update_data(initial_brix=str(value))
    await state.set_state(FermentationState.waiting_current_brix)
    await message.answer(
        "Теперь введите <b>текущее или конечное</b> показание по шкале Brix.\n"
        "Например: <code>8</code>.",
        reply_markup=fermentation_input_keyboard(process_id if isinstance(process_id, int) else None),
    )


@router.message(FermentationState.waiting_current_brix)
async def fermentation_current_brix_handler(
    message: Message,
    state: FSMContext,
    session_factory,
) -> None:
    if message.text is None:
        return
    current_brix = parse_decimal(message.text)
    data = await state.get_data()
    try:
        initial_brix = Decimal(str(data["initial_brix"]))
    except (KeyError, InvalidOperation):
        await state.clear()
        return

    if current_brix is None or not Decimal("0") <= current_brix <= initial_brix:
        await message.answer(
            "Текущее значение должно быть от 0 до начального Brix. "
            f"Начальное значение: {format_decimal(initial_brix)} °Bx."
        )
        return

    result = calculate_refractometer(initial_brix, current_brix)
    process_id = data.get("process_id")

    if isinstance(process_id, int) and message.from_user is not None:
        async with session_factory() as session:
            process = await get_fermentation_process(session, process_id, message.from_user.id)
            if process is None:
                await state.clear()
                await message.answer("Процесс не найден или этап уже изменён.")
                return
            session.add(
                DrinkEvent(
                    drink_id=process.id,
                    event_type="fermentation_refractometer",
                    title="Крепость по Brix",
                    data={
                        "stage": process.current_stage,
                        "initial_brix": str(result.initial_brix),
                        "current_brix": str(result.current_brix),
                        "original_sg": str(result.original_sg),
                        "corrected_sg": str(result.corrected_sg),
                        "potential_abv": str(result.potential_abv),
                        "current_abv": str(result.current_abv),
                        "method": "novotny_refractometer",
                    },
                )
            )
            await session.commit()

    await state.clear()
    await message.answer(
        refractometer_result_text(result),
        reply_markup=fermentation_result_keyboard(process_id if isinstance(process_id, int) else None),
    )
