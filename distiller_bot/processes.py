import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import (
    process_calculators_keyboard,
    process_card_keyboard,
    process_completed_keyboard,
    process_input_cancel_keyboard,
    process_list_keyboard,
    process_measurement_type_keyboard,
    process_stage_keyboard,
)
from .models import Drink, DrinkEvent, Measurement, User
from .process_stages import (
    STAGE_TITLES,
    stage_actions_for_stage,
    stage_icon,
    stage_type_for_title,
)
from .sugar_wash import result_from_event_data

router = Router()

PROCESS_CALCULATORS_TEXT = (
    "🧮 <b>Калькуляторы</b>\n\n"
    "Здесь будут доступны расчёты, подходящие для текущего этапа."
)
NOTE_PREVIEW_LIMIT = 500

MEASUREMENT_TYPES: dict[str, dict[str, str]] = {
    "temperature": {
        "icon": "🌡",
        "label": "Температура",
        "unit": "°C",
        "example": "24 °C",
    },
    "abv": {
        "icon": "🥃",
        "label": "Крепость",
        "unit": "%",
        "example": "42 %",
    },
    "volume": {
        "icon": "💧",
        "label": "Объём",
        "unit": "л",
        "example": "18 л",
    },
}

DEFAULT_MEASUREMENT_ORDER = ["temperature", "abv", "volume"]
STAGE_MEASUREMENT_ORDER: dict[str, list[str]] = {
    "preparation": ["volume", "temperature", "abv"],
    "fermentation": ["temperature", "volume", "abv"],
    "distillation": ["abv", "volume", "temperature"],
    "drink_preparation": ["abv", "volume", "temperature"],
    "bottling": ["abv", "volume", "temperature"],
}

STAGE_QUICK_MEASUREMENTS: dict[str, list[tuple[str, str]]] = {
    "preparation": [],
    "fermentation": [
        ("temperature", "🌡 Температура"),
        ("volume", "💧 Объём"),
    ],
    "distillation": [
        ("abv", "🥃 Крепость"),
        ("volume", "💧 Объём"),
    ],
    "drink_preparation": [
        ("abv", "🥃 Текущая крепость"),
        ("volume", "💧 Объём"),
    ],
    "bottling": [
        ("abv", "🥃 Итоговая крепость"),
        ("volume", "💧 Итоговый объём"),
    ],
}

LEGACY_MEASUREMENT_STAGE_TYPES: dict[str, str] = {
    "Разбавление": "drink_preparation",
    "Выдержка": "drink_preparation",
    "Готово": "bottling",
}

VALUE_RE = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*(.*?)\s*$")


class ProcessState(StatesGroup):
    waiting_name = State()
    choosing_stage = State()
    waiting_custom_stage = State()
    waiting_rename = State()
    waiting_measurement_label = State()
    waiting_measurement_value = State()
    waiting_note = State()


def process_short_label(process: Drink) -> str:
    stage = process.current_stage or "Этап не указан"
    label = f"{stage_icon(process.current_stage)} {process.name} · {stage.lower()}"
    return label if len(label) <= 60 else f"{label[:57]}…"


def format_decimal(value: Decimal) -> str:
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


def measurement_display(measurement: Measurement) -> str:
    config = MEASUREMENT_TYPES.get(measurement.measurement_type)
    if config is None:
        icon = "📐"
        label = measurement.label or "Замер"
    else:
        icon = config["icon"]
        label = measurement.label or config["label"]

    unit = f" {escape(measurement.unit)}" if measurement.unit else ""
    return f"{icon} {escape(label)}: {format_decimal(measurement.value)}{unit}"


def note_preview(note: DrinkEvent | None) -> str | None:
    if note is None or not note.text:
        return None

    text = note.text.strip()
    if len(text) > NOTE_PREVIEW_LIMIT:
        text = f"{text[: NOTE_PREVIEW_LIMIT - 1].rstrip()}…"
    return escape(text)


def preparation_composition_display(composition: DrinkEvent | None) -> str | None:
    result = result_from_event_data(composition.data if composition is not None else None)
    if result is None:
        return None

    return (
        f"{result.fermentable_label} · "
        f"⚖️ {format_decimal(result.sugar_kg)} кг\n"
        f"💧 Вода: {format_decimal(result.water_l)} л · "
        f"🪣 Объём: {format_decimal(result.volume_l)} л\n"
        f"📈 Потенциальная крепость: ~{format_decimal(result.potential_abv)}%"
    )


def measurement_stage_type(stage: str | None) -> str | None:
    stage_type = stage_type_for_title(stage)
    if stage_type is not None:
        return stage_type
    if stage is None:
        return None
    return LEGACY_MEASUREMENT_STAGE_TYPES.get(stage)


def quick_measurements_for_stage(stage: str | None) -> list[tuple[str, str]]:
    stage_type = measurement_stage_type(stage)
    return list(STAGE_QUICK_MEASUREMENTS.get(stage_type or "", []))


def process_card_text(
    process: Drink,
    latest_measurement: Measurement | None = None,
    latest_note: DrinkEvent | None = None,
) -> str:
    stage = process.current_stage or "Не указан"
    created_at = process.created_at.strftime("%d.%m.%Y") if process.created_at else "-"
    text = (
        f"🧪 <b>{escape(process.name)}</b>\n\n"
        f"Этап: {stage_icon(process.current_stage)} {escape(stage)}\n"
        f"Добавлено: {created_at}"
    )

    latest_composition = getattr(process, "_latest_preparation_composition", None)
    composition_text = preparation_composition_display(latest_composition)
    if composition_text is not None:
        text += f"\n\n🍬 <b>Состав браги:</b>\n{composition_text}"

    if latest_measurement is not None:
        text += f"\n\nПоследний замер:\n{measurement_display(latest_measurement)}"

    preview = note_preview(latest_note)
    if preview is not None:
        text += f"\n\n📝 <b>Последняя заметка:</b>\n{preview}"

    quick_measurements = quick_measurements_for_stage(process.current_stage)
    if quick_measurements:
        labels = " · ".join(label for _measurement_type, label in quick_measurements)
        text += f"\n\n<b>Сейчас может пригодиться:</b>\n{labels}"

    return text


def process_card_markup(process: Drink):
    actions = [
        (action.key, action.label)
        for action in stage_actions_for_stage(process.current_stage)
    ]
    return process_card_keyboard(process.id, actions)


def measurement_types_for_stage(stage: str | None) -> list[tuple[str, str]]:
    stage_type = measurement_stage_type(stage)
    order = STAGE_MEASUREMENT_ORDER.get(stage_type or "", DEFAULT_MEASUREMENT_ORDER)
    return [
        (
            measurement_type,
            f"{MEASUREMENT_TYPES[measurement_type]['icon']} "
            f"{MEASUREMENT_TYPES[measurement_type]['label']}",
        )
        for measurement_type in order
    ]


def parse_measurement_value(text: str, default_unit: str) -> tuple[Decimal, str] | None:
    match = VALUE_RE.match(text)
    if match is None:
        return None

    try:
        value = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None

    unit = match.group(2).strip() or default_unit
    if len(unit) > 50:
        return None
    return value, unit


def measurement_value_error(measurement_type: str, value: Decimal) -> str | None:
    if measurement_type == "abv" and not (Decimal("0") <= value <= Decimal("100")):
        return "Крепость должна быть от 0 до 100 %."
    if measurement_type == "volume" and value <= 0:
        return "Значение должно быть больше нуля."
    return None


def callback_process_id(callback: CallbackQuery) -> int | None:
    try:
        return int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return None


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_owned_process(
    session: AsyncSession,
    process_id: int,
    telegram_id: int,
) -> Drink | None:
    result = await session.execute(
        select(Drink)
        .join(User, Drink.user_id == User.id)
        .where(Drink.id == process_id, User.telegram_id == telegram_id)
    )
    process = result.scalar_one_or_none()
    if process is None:
        return None

    composition_result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process.id,
            DrinkEvent.event_type.in_(("preparation_composition", "sugar_wash_calculation")),
        )
        .order_by(DrinkEvent.created_at.desc(), DrinkEvent.id.desc())
        .limit(1)
    )
    setattr(
        process,
        "_latest_preparation_composition",
        composition_result.scalar_one_or_none(),
    )
    return process


async def get_latest_measurement(session: AsyncSession, process_id: int) -> Measurement | None:
    result = await session.execute(
        select(Measurement)
        .where(
            Measurement.drink_id == process_id,
            Measurement.measurement_type != "density",
        )
        .order_by(Measurement.measured_at.desc(), Measurement.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_latest_note(session: AsyncSession, process_id: int) -> DrinkEvent | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "note",
            DrinkEvent.text.is_not(None),
        )
        .order_by(DrinkEvent.created_at.desc(), DrinkEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_process_card_context(
    session: AsyncSession,
    process_id: int,
) -> tuple[Measurement | None, DrinkEvent | None]:
    return (
        await get_latest_measurement(session, process_id),
        await get_latest_note(session, process_id),
    )


async def create_process(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    stage: str,
) -> Drink:
    process = Drink(user_id=user_id, name=name, current_stage=stage, status="active")
    session.add(process)
    await session.flush()
    session.add(
        DrinkEvent(
            drink_id=process.id,
            event_type="created",
            title="Процесс добавлен",
            data={"stage": stage},
        )
    )
    await session.commit()
    await session.refresh(process)
    return process


async def change_process_stage(
    session: AsyncSession,
    *,
    process: Drink,
    stage: str,
) -> Drink:
    previous_stage = process.current_stage
    process.current_stage = stage
    session.add(
        DrinkEvent(
            drink_id=process.id,
            event_type="stage_changed",
            title="Изменён этап",
            data={"from": previous_stage, "to": stage},
        )
    )
    await session.commit()
    await session.refresh(process)
    return process


async def rename_process(
    session: AsyncSession,
    *,
    process: Drink,
    name: str,
) -> Drink:
    previous_name = process.name
    process.name = name
    session.add(
        DrinkEvent(
            drink_id=process.id,
            event_type="renamed",
            title="Процесс переименован",
            data={"from": previous_name, "to": name},
        )
    )
    await session.commit()
    await session.refresh(process)
    return process


async def create_measurement(
    session: AsyncSession,
    *,
    process: Drink,
    measurement_type: str,
    label: str,
    value: Decimal,
    unit: str,
) -> Measurement:
    measurement = Measurement(
        drink_id=process.id,
        measurement_type=measurement_type,
        value=value,
        unit=unit,
        label=label,
        measured_at=datetime.now(UTC),
    )
    session.add(measurement)
    await session.flush()
    session.add(
        DrinkEvent(
            drink_id=process.id,
            event_type="measurement_added",
            title="Добавлен замер",
            data={
                "measurement_type": measurement_type,
                "label": label,
                "value": str(value),
                "unit": unit,
            },
        )
    )
    await session.commit()
    await session.refresh(measurement)
    return measurement


async def create_process_note(
    session: AsyncSession,
    *,
    process: Drink,
    text: str,
) -> DrinkEvent:
    note = DrinkEvent(
        drink_id=process.id,
        event_type="note",
        title="Заметка",
        text=text,
        data={"stage": process.current_stage},
    )
    session.add(note)
    await session.commit()
    return note


async def complete_process(session: AsyncSession, *, process: Drink) -> Drink:
    process.status = "completed"
    process.completed_at = datetime.now(UTC)
    session.add(
        DrinkEvent(
            drink_id=process.id,
            event_type="completed",
            title="Процесс завершён",
            data={"stage": process.current_stage},
        )
    )
    await session.commit()
    await session.refresh(process)
    return process


async def render_process_list(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.message is None:
        return

    async with session_factory() as session:
        user = await get_user(session, callback.from_user.id)
        if user is None:
            await callback.message.edit_text("Сначала запустите бота командой /start.")
            return

        result = await session.execute(
            select(Drink)
            .where(Drink.user_id == user.id, Drink.status == "active")
            .order_by(Drink.created_at.desc(), Drink.id.desc())
        )
        processes = list(result.scalars())

    if processes:
        text = "🧪 <b>Мои процессы</b>\n\nВыберите процесс или добавьте новый."
    else:
        text = (
            "🧪 <b>Мои процессы</b>\n\n"
            "Здесь можно вести текущие приготовления: сохранять этапы, замеры, "
            "заметки и напоминания.\n\n"
            "Можно добавить процесс на любом этапе - от брожения до готового продукта."
        )

    items = [(process.id, process_short_label(process)) for process in processes]
    await callback.message.edit_text(text, reply_markup=process_list_keyboard(items))


async def show_stage_selector(
    callback: CallbackQuery,
    state: FSMContext,
    process: Drink,
    *,
    completed: bool,
) -> None:
    await state.clear()
    await state.update_data(mode="change", process_id=process.id)
    await state.set_state(ProcessState.choosing_stage)

    if completed:
        text = (
            f"✅ <b>{stage_icon(process.current_stage)} "
            f"{escape(process.current_stage or 'Этап')} завершён</b>\n\n"
            "Выберите следующий этап:"
        )
    else:
        text = f"🔄 <b>{escape(process.name)}</b>\n\nВыберите новый этап:"

    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=process_stage_keyboard(process.id),
        )


@router.callback_query(F.data == "menu:drinks")
async def process_list_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    await render_process_list(callback, session_factory)


@router.callback_query(F.data == "process:add")
async def process_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(ProcessState.waiting_name)
    if callback.message:
        await callback.message.edit_text(
            "➕ <b>Новый процесс</b>\n\n"
            "Как назовём процесс? Название нужно только для того, чтобы потом легко его найти.\n\n"
            "Например:\n"
            "• Сахарная брага\n"
            "• Спирт-сырец\n"
            "• Яблочный дистиллят\n"
            "• Кальвадос на выдержке",
            reply_markup=process_input_cancel_keyboard(),
        )


@router.message(ProcessState.waiting_name)
async def process_name_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    name = message.text.strip()
    if not name:
        await message.answer("Введите название процесса.")
        return
    if len(name) > 255:
        await message.answer("Название слишком длинное. Используйте не больше 255 символов.")
        return

    await state.update_data(mode="create", name=name)
    await state.set_state(ProcessState.choosing_stage)
    await message.answer(
        "На каком этапе вы сейчас?",
        reply_markup=process_stage_keyboard(),
    )


@router.callback_query(F.data.startswith("process:stage:"))
async def process_stage_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    stage_key = (callback.data or "").rsplit(":", 1)[-1]
    data = await state.get_data()
    mode = data.get("mode")

    if stage_key == "custom":
        if mode not in {"create", "change"}:
            return
        await state.set_state(ProcessState.waiting_custom_stage)
        process_id = data.get("process_id") if mode == "change" else None
        await callback.message.edit_text(
            "Введите свой текущий этап.",
            reply_markup=process_input_cancel_keyboard(process_id),
        )
        return

    stage = STAGE_TITLES.get(stage_key)
    if stage is None:
        return

    if mode == "create":
        name = data.get("name")
        if not isinstance(name, str):
            await state.clear()
            return

        async with session_factory() as session:
            user = await get_user(session, callback.from_user.id)
            if user is None:
                await state.clear()
                await callback.message.edit_text("Сначала запустите бота командой /start.")
                return
            process = await create_process(session, user_id=user.id, name=name, stage=stage)

        await state.clear()
        await callback.message.edit_text(
            f"✅ Процесс добавлен\n\n{process_card_text(process)}",
            reply_markup=process_card_markup(process),
        )
        return

    if mode == "change":
        process_id = data.get("process_id")
        if not isinstance(process_id, int):
            await state.clear()
            return

        async with session_factory() as session:
            process = await get_owned_process(session, process_id, callback.from_user.id)
            if process is None:
                await state.clear()
                await render_process_list(callback, session_factory)
                return
            process = await change_process_stage(session, process=process, stage=stage)
            latest_measurement, latest_note = await get_process_card_context(session, process.id)

        await state.clear()
        await callback.message.edit_text(
            process_card_text(process, latest_measurement, latest_note),
            reply_markup=process_card_markup(process),
        )


@router.message(ProcessState.waiting_custom_stage)
async def process_custom_stage_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    stage = message.text.strip()
    if not stage:
        await message.answer("Введите название этапа.")
        return
    if len(stage) > 100:
        await message.answer("Название этапа слишком длинное. Используйте не больше 100 символов.")
        return

    data = await state.get_data()
    mode = data.get("mode")

    async with session_factory() as session:
        if mode == "create":
            name = data.get("name")
            user = await get_user(session, message.from_user.id)
            if not isinstance(name, str) or user is None:
                await state.clear()
                await message.answer("Не удалось создать процесс. Откройте раздел заново.")
                return
            process = await create_process(session, user_id=user.id, name=name, stage=stage)
            latest_measurement = None
            latest_note = None
        elif mode == "change":
            process_id = data.get("process_id")
            if not isinstance(process_id, int):
                await state.clear()
                return
            process = await get_owned_process(session, process_id, message.from_user.id)
            if process is None:
                await state.clear()
                await message.answer("Процесс не найден.")
                return
            process = await change_process_stage(session, process=process, stage=stage)
            latest_measurement, latest_note = await get_process_card_context(session, process.id)
        else:
            await state.clear()
            return

    await state.clear()
    await message.answer(
        process_card_text(process, latest_measurement, latest_note),
        reply_markup=process_card_markup(process),
    )


@router.callback_query(F.data.startswith("process:view:"))
async def process_view_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        if process is not None:
            latest_measurement, latest_note = await get_process_card_context(session, process.id)
        else:
            latest_measurement = None
            latest_note = None

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await callback.message.edit_text(
        process_card_text(process, latest_measurement, latest_note),
        reply_markup=process_card_markup(process),
    )


@router.callback_query(F.data.startswith("process:measure:"))
async def process_measurement_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        f"➕ <b>Новый замер · {escape(process.name)}</b>\n\n"
        f"Этап: {stage_icon(process.current_stage)} "
        f"{escape(process.current_stage or 'Не указан')}\n\n"
        "Что измерили? Для текущего этапа наиболее типичные варианты показаны первыми.",
        reply_markup=process_measurement_type_keyboard(
            process_id,
            measurement_types_for_stage(process.current_stage),
        ),
    )


@router.callback_query(F.data.startswith("process:measure-type:"))
async def process_measurement_type_handler(
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
    measurement_type = parts[3]

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.update_data(process_id=process_id, measurement_type=measurement_type)

    if measurement_type == "custom":
        await state.set_state(ProcessState.waiting_measurement_label)
        await callback.message.edit_text(
            f"📐 <b>Другой замер · {escape(process.name)}</b>\n\n"
            "Что именно измерили? Например: pH или сахаристость.",
            reply_markup=process_input_cancel_keyboard(process_id),
        )
        return

    config = MEASUREMENT_TYPES.get(measurement_type)
    if config is None:
        await state.clear()
        return

    await state.update_data(
        measurement_label=config["label"],
        default_unit=config["unit"],
    )
    await state.set_state(ProcessState.waiting_measurement_value)
    await callback.message.edit_text(
        f"{config['icon']} <b>{config['label']} · {escape(process.name)}</b>\n\n"
        f"Введите значение. Например: <code>{escape(config['example'])}</code>.\n"
        f"Если единицу не указать, использую {escape(config['unit'])}.",
        reply_markup=process_input_cancel_keyboard(process_id),
    )


@router.message(ProcessState.waiting_measurement_label)
async def process_measurement_label_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    label = message.text.strip()
    if not label:
        await message.answer("Введите название замера.")
        return
    if len(label) > 255:
        await message.answer("Название слишком длинное. Используйте не больше 255 символов.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    await state.update_data(measurement_label=label, default_unit="")
    await state.set_state(ProcessState.waiting_measurement_value)
    await message.answer(
        "Введите числовое значение и, если нужно, единицу измерения.\n"
        "Например: <code>4.2</code> или <code>12 °Bx</code>.",
        reply_markup=process_input_cancel_keyboard(process_id),
    )


@router.message(ProcessState.waiting_measurement_value)
async def process_measurement_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    measurement_type = data.get("measurement_type")
    label = data.get("measurement_label")
    default_unit = data.get("default_unit", "")

    if not isinstance(process_id, int) or not isinstance(measurement_type, str):
        await state.clear()
        return
    if not isinstance(label, str) or not isinstance(default_unit, str):
        await state.clear()
        return

    parsed = parse_measurement_value(message.text, default_unit)
    if parsed is None:
        await message.answer(
            "Не понял значение. Введите число, при необходимости с единицей: "
            "например <code>24 °C</code> или <code>18 л</code>."
        )
        return

    value, unit = parsed
    error = measurement_value_error(measurement_type, value)
    if error is not None:
        await message.answer(error)
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден.")
            return
        measurement = await create_measurement(
            session,
            process=process,
            measurement_type=measurement_type,
            label=label,
            value=value,
            unit=unit,
        )
        latest_note = await get_latest_note(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Замер сохранён\n\n{process_card_text(process, measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )


@router.callback_query(F.data.startswith("process:note:"))
async def process_note_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.update_data(process_id=process_id)
    await state.set_state(ProcessState.waiting_note)
    await callback.message.edit_text(
        f"📝 <b>Заметка · {escape(process.name)}</b>\n\n"
        f"Этап: {stage_icon(process.current_stage)} "
        f"{escape(process.current_stage or 'Не указан')}\n\n"
        "Введите текст заметки.",
        reply_markup=process_input_cancel_keyboard(process_id),
    )


@router.message(ProcessState.waiting_note)
async def process_note_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    text = message.text.strip()
    if not text:
        await message.answer("Введите текст заметки.")
        return
    if len(text) > 3000:
        await message.answer("Заметка слишком длинная. Используйте не больше 3000 символов.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден.")
            return
        latest_note = await create_process_note(session, process=process, text=text)
        latest_measurement = await get_latest_measurement(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Заметка сохранена\n\n"
        f"{process_card_text(process, latest_measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )


@router.callback_query(F.data.startswith("process:calculators:"))
async def process_calculators_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await callback.message.edit_text(
        PROCESS_CALCULATORS_TEXT,
        reply_markup=process_calculators_keyboard(process.id),
    )


@router.callback_query(F.data.startswith("process:rename:"))
async def process_rename_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.update_data(process_id=process_id)
    await state.set_state(ProcessState.waiting_rename)
    await callback.message.edit_text(
        "✏️ <b>Переименовать процесс</b>\n\n"
        f"Текущее название: {escape(process.name)}\n\n"
        "Введите новое название.",
        reply_markup=process_input_cancel_keyboard(process_id),
    )


@router.message(ProcessState.waiting_rename)
async def process_rename_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    name = message.text.strip()
    if not name:
        await message.answer("Введите новое название процесса.")
        return
    if len(name) > 255:
        await message.answer("Название слишком длинное. Используйте не больше 255 символов.")
        return

    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Процесс не найден.")
            return
        process = await rename_process(session, process=process, name=name)
        latest_measurement, latest_note = await get_process_card_context(session, process.id)

    await state.clear()
    await message.answer(
        f"✅ Процесс переименован\n\n"
        f"{process_card_text(process, latest_measurement, latest_note)}",
        reply_markup=process_card_markup(process),
    )


@router.callback_query(F.data.startswith("process:complete-stage:"))
async def process_complete_stage_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await show_stage_selector(callback, state, process, completed=True)


@router.callback_query(F.data.startswith("process:change-stage:"))
async def process_change_stage_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await show_stage_selector(callback, state, process, completed=False)


@router.callback_query(F.data.startswith("process:complete:"))
async def process_complete_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return

    process_id = callback_process_id(callback)
    if process_id is None:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        if process is None:
            await render_process_list(callback, session_factory)
            return
        if stage_type_for_title(process.current_stage) != "bottling":
            latest_measurement, latest_note = await get_process_card_context(session, process.id)
        else:
            process = await complete_process(session, process=process)
            latest_measurement = None
            latest_note = None

    if process.status != "completed":
        await callback.message.edit_text(
            process_card_text(process, latest_measurement, latest_note),
            reply_markup=process_card_markup(process),
        )
        return

    await callback.message.edit_text(
        "✅ <b>Процесс завершён</b>\n\n"
        f"🧪 {escape(process.name)}\n"
        f"Этап: {stage_icon(process.current_stage)} "
        f"{escape(process.current_stage or 'Розлив')}",
        reply_markup=process_completed_keyboard(),
    )