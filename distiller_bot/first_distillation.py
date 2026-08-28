from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .alcoholometry import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C, correct_alcoholmeter_abv
from .first_distillation_keyboards import (
    first_distillation_calculator_input_keyboard,
    first_distillation_calculators_keyboard,
    first_distillation_container_keyboard,
    first_distillation_delete_keyboard,
    first_distillation_input_keyboard,
    first_distillation_keyboard,
)
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import get_owned_process, render_process_list

router = Router()

MAX_VOLUME_L = Decimal("10000")
MAX_ABV = Decimal("100")
PAIR_RE = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*[; xх×]+\s*([+-]?\d+(?:[.,]\d+)?)\s*%?\s*$")


@dataclass(frozen=True, slots=True)
class ReceivingContainer:
    container_id: int
    volume_l: Decimal
    observed_abv: Decimal
    temperature_c: Decimal
    corrected_abv: Decimal
    absolute_alcohol_l: Decimal


class FirstDistillationState(StatesGroup):
    waiting_volume = State()
    waiting_abv = State()
    waiting_temperature = State()
    waiting_edit_value = State()
    waiting_calc_value = State()


def parse_decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_positive_decimal(text: str) -> Decimal | None:
    value = parse_decimal(text)
    return value if value is not None and value > 0 else None


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


def make_container(
    container_id: int,
    volume_l: Decimal,
    observed_abv: Decimal,
    temperature_c: Decimal,
) -> ReceivingContainer:
    corrected_abv = correct_alcoholmeter_abv(observed_abv, temperature_c)
    return ReceivingContainer(
        container_id=container_id,
        volume_l=round_amount(volume_l),
        observed_abv=round_abv(observed_abv),
        temperature_c=temperature_c.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        corrected_abv=corrected_abv,
        absolute_alcohol_l=absolute_alcohol_l(volume_l, corrected_abv),
    )


def container_from_data(data: dict | None) -> ReceivingContainer | None:
    if not data or data.get("action") == "delete":
        return None
    try:
        return make_container(
            int(data["container_id"]),
            Decimal(str(data["volume_l"])),
            Decimal(str(data["observed_abv"])),
            Decimal(str(data["temperature_c"])),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


def container_data(container: ReceivingContainer, *, source: str) -> dict[str, object]:
    return {
        "stage": "Первая перегонка",
        "action": "upsert",
        "source": source,
        "container_id": container.container_id,
        "volume_l": str(container.volume_l),
        "observed_abv": str(container.observed_abv),
        "temperature_c": str(container.temperature_c),
        "corrected_abv": str(container.corrected_abv),
        "absolute_alcohol_l": str(container.absolute_alcohol_l),
    }


def summarize(containers: list[ReceivingContainer]) -> tuple[Decimal, Decimal, Decimal]:
    total_volume = round_amount(sum((item.volume_l for item in containers), Decimal("0")))
    total_aa = round_amount(sum((item.absolute_alcohol_l for item in containers), Decimal("0")))
    average_abv = (
        round_abv(total_aa / total_volume * Decimal("100"))
        if total_volume > 0
        else Decimal("0")
    )
    return total_volume, average_abv, total_aa


def container_line(item: ReceivingContainer) -> str:
    return (
        f"🫙 {item.container_id}. {format_decimal(item.volume_l)} л · "
        f"{format_decimal(item.observed_abv)}% · {format_decimal(item.temperature_c)} °C "
        f"-> ~{format_decimal(item.corrected_abv)}%"
    )


def containers_text(containers: list[ReceivingContainer], legacy: DrinkEvent | None = None) -> str:
    lines = ["⚗️ <b>Первая перегонка</b>", "", "🫙 <b>Приёмные ёмкости</b>"]
    if not containers:
        lines.extend(["", "Ёмкости пока не добавлены.", "Добавляйте их по мере сбора спирта-сырца."])
        if legacy is not None and legacy.data:
            try:
                volume = Decimal(str(legacy.data["low_wines_volume_l"]))
                abv = Decimal(str(legacy.data["low_wines_abv"]))
                lines.extend([
                    "",
                    "<b>Ранее записанный итог:</b>",
                    f"🥃 {format_decimal(volume)} л · 📈 {format_decimal(abv)}%",
                ])
            except (KeyError, InvalidOperation, TypeError):
                pass
        return "\n".join(lines)

    lines.append("")
    lines.extend(container_line(item) for item in containers)
    total_volume, average_abv, total_aa = summarize(containers)
    lines.extend([
        "",
        "<b>Сводка по ёмкостям:</b>",
        f"🫙 Ёмкостей: {len(containers)} · 💧 {format_decimal(total_volume)} л",
        f"📈 Средняя крепость при 20 °C: ~{format_decimal(average_abv)}%",
        f"💧 Абсолютный спирт: ~{format_decimal(total_aa)} л",
    ])
    return "\n".join(lines)


def container_text(item: ReceivingContainer) -> str:
    return (
        f"🫙 <b>Ёмкость {item.container_id}</b>\n\n"
        f"💧 Объём: <b>{format_decimal(item.volume_l)} л</b>\n"
        f"📈 Спиртометр: <b>{format_decimal(item.observed_abv)}%</b>\n"
        f"🌡 Температура: <b>{format_decimal(item.temperature_c)} °C</b>\n"
        f"✅ Крепость при 20 °C: <b>~{format_decimal(item.corrected_abv)}%</b>\n"
        f"💧 Абсолютный спирт: <b>~{format_decimal(item.absolute_alcohol_l)} л</b>"
    )


async def get_containers(session: AsyncSession, process_id: int) -> list[ReceivingContainer]:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "first_distillation_container",
        )
        .order_by(DrinkEvent.id.asc())
    )
    current: dict[int, ReceivingContainer] = {}
    for event in result.scalars():
        data = event.data or {}
        try:
            container_id = int(data["container_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if data.get("action") == "delete":
            current.pop(container_id, None)
            continue
        container = container_from_data(data)
        if container is not None:
            current[container_id] = container
    return [current[key] for key in sorted(current)]


async def get_legacy_result(session: AsyncSession, process_id: int) -> DrinkEvent | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "first_distillation_result",
        )
        .order_by(DrinkEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_container(
    session: AsyncSession,
    *,
    process_id: int,
    container: ReceivingContainer,
    source: str,
) -> None:
    session.add(DrinkEvent(
        drink_id=process_id,
        event_type="first_distillation_container",
        title=f"Ёмкость {container.container_id}",
        data=container_data(container, source=source),
    ))
    await session.commit()
    await save_summary(session, process_id)


async def save_summary(session: AsyncSession, process_id: int) -> None:
    containers = await get_containers(session, process_id)
    total_volume, average_abv, total_aa = summarize(containers)
    session.add(DrinkEvent(
        drink_id=process_id,
        event_type="first_distillation_summary",
        title="Сводка первой перегонки",
        data={
            "stage": "Первая перегонка",
            "container_count": len(containers),
            "total_volume_l": str(total_volume),
            "average_abv": str(average_abv),
            "absolute_alcohol_l": str(total_aa),
        },
    ))
    await session.commit()


async def delete_container(session: AsyncSession, process_id: int, container_id: int) -> None:
    session.add(DrinkEvent(
        drink_id=process_id,
        event_type="first_distillation_container",
        title=f"Удалена ёмкость {container_id}",
        data={"stage": "Первая перегонка", "action": "delete", "container_id": container_id},
    ))
    await session.commit()
    await save_summary(session, process_id)


def next_container_id(containers: list[ReceivingContainer]) -> int:
    return max((item.container_id for item in containers), default=0) + 1


async def show_containers(callback: CallbackQuery, state: FSMContext, session_factory, process_id: int) -> None:
    if callback.message is None:
        return
    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)
        containers = await get_containers(session, process_id) if process is not None else []
        legacy = await get_legacy_result(session, process_id) if process is not None else None
    if process is None:
        await state.clear()
        await render_process_list(callback, session_factory)
        return
    await state.clear()
    await callback.message.edit_text(
        containers_text(containers, legacy),
        reply_markup=first_distillation_keyboard(
            process_id,
            [(item.container_id, f"🫙 {item.container_id}") for item in containers],
        ),
    )


@router.callback_query(F.data.regexp(r"^process:first-distillation:\d+$"))
async def first_distillation_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await show_containers(callback, state, session_factory, process_id)


@router.callback_query(F.data.startswith("process:first-distillation-add:"))
async def add_container_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await state.clear()
    await state.set_state(FirstDistillationState.waiting_volume)
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        "🫙 <b>Новая приёмная ёмкость</b>\n\n"
        "Какой объём дистиллята в ёмкости?\n"
        "Введите литры, например <code>2,5</code>.",
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_volume)
async def add_volume_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    value = parse_positive_decimal(message.text)
    if value is None or value > MAX_VOLUME_L:
        await message.answer("Введите объём от 0 до 10 000 л.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    await state.update_data(volume_l=str(value))
    await state.set_state(FirstDistillationState.waiting_abv)
    await message.answer(
        "📈 Какое показание спиртометра?\nВведите процент, например <code>48</code>.",
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_abv)
async def add_abv_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    value = parse_decimal(message.text)
    if value is None or not Decimal("0") <= value <= MAX_ABV:
        await message.answer("Введите показание спиртометра от 0 до 100 %.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    await state.update_data(observed_abv=str(value))
    await state.set_state(FirstDistillationState.waiting_temperature)
    await message.answer(
        "🌡 Какая температура пробы?\n"
        "Введите °C, например <code>24</code>. При 20 °C поправка равна нулю.",
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_temperature)
async def add_temperature_handler(message: Message, state: FSMContext, session_factory) -> None:
    if message.from_user is None or message.text is None:
        return
    temperature = parse_decimal(message.text)
    if temperature is None or not MIN_TEMPERATURE_C <= temperature <= MAX_TEMPERATURE_C:
        await message.answer("Для расчёта укажите температуру от -20 до 40 °C.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    try:
        volume_l = Decimal(str(data["volume_l"]))
        observed_abv = Decimal(str(data["observed_abv"]))
    except (KeyError, InvalidOperation):
        await state.clear()
        return
    async with session_factory() as session:
        process = await get_owned_process(session, process_id, message.from_user.id)
        if process is None or stage_type_for_title(process.current_stage) != "first_distillation":
            await state.clear()
            await message.answer("Процесс не находится на этапе первой перегонки.")
            return
        containers = await get_containers(session, process_id)
        container = make_container(next_container_id(containers), volume_l, observed_abv, temperature)
        await save_container(session, process_id=process_id, container=container, source="create")
    await state.clear()
    await message.answer(
        f"✅ Ёмкость добавлена\n\n{container_text(container)}",
        reply_markup=first_distillation_container_keyboard(process_id, container.container_id),
    )


@router.callback_query(F.data.startswith("process:first-distillation-container:"))
async def container_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    process_id, container_id = int(parts[2]), int(parts[3])
    async with session_factory() as session:
        containers = await get_containers(session, process_id)
    item = next((item for item in containers if item.container_id == container_id), None)
    if item is None:
        await show_containers(callback, state, session_factory, process_id)
        return
    await state.clear()
    await callback.message.edit_text(
        container_text(item),
        reply_markup=first_distillation_container_keyboard(process_id, container_id),
    )


@router.callback_query(F.data.startswith("process:first-distillation-edit:"))
async def edit_container_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    process_id, container_id, field = int(parts[2]), int(parts[3]), parts[4]
    if field not in {"volume", "abv", "temperature"}:
        return
    async with session_factory() as session:
        containers = await get_containers(session, process_id)
    item = next((item for item in containers if item.container_id == container_id), None)
    if item is None:
        return
    current = {
        "volume": f"{format_decimal(item.volume_l)} л",
        "abv": f"{format_decimal(item.observed_abv)}%",
        "temperature": f"{format_decimal(item.temperature_c)} °C",
    }[field]
    title = {"volume": "💧 Объём", "abv": "📈 Спиртометр", "temperature": "🌡 Температура"}[field]
    await state.clear()
    await state.set_state(FirstDistillationState.waiting_edit_value)
    await state.update_data(process_id=process_id, container_id=container_id, edit_field=field)
    await callback.message.edit_text(
        f"{title}\n\nСейчас: <b>{current}</b>.\nВведите новое значение.",
        reply_markup=first_distillation_input_keyboard(process_id),
    )


@router.message(FirstDistillationState.waiting_edit_value)
async def edit_container_value_handler(message: Message, state: FSMContext, session_factory) -> None:
    if message.from_user is None or message.text is None:
        return
    data = await state.get_data()
    process_id, container_id, field = data.get("process_id"), data.get("container_id"), data.get("edit_field")
    if not isinstance(process_id, int) or not isinstance(container_id, int) or field not in {"volume", "abv", "temperature"}:
        await state.clear()
        return
    value = parse_decimal(message.text)
    if value is None:
        await message.answer("Введите число.")
        return
    if field == "volume" and not Decimal("0") < value <= MAX_VOLUME_L:
        await message.answer("Введите объём от 0 до 10 000 л.")
        return
    if field == "abv" and not Decimal("0") <= value <= MAX_ABV:
        await message.answer("Введите показание спиртометра от 0 до 100 %.")
        return
    if field == "temperature" and not MIN_TEMPERATURE_C <= value <= MAX_TEMPERATURE_C:
        await message.answer("Введите температуру от -20 до 40 °C.")
        return
    async with session_factory() as session:
        containers = await get_containers(session, process_id)
        item = next((item for item in containers if item.container_id == container_id), None)
        if item is None:
            await state.clear()
            await message.answer("Ёмкость не найдена.")
            return
        volume_l, observed_abv, temperature = item.volume_l, item.observed_abv, item.temperature_c
        if field == "volume": volume_l = value
        elif field == "abv": observed_abv = value
        else: temperature = value
        updated = make_container(container_id, volume_l, observed_abv, temperature)
        await save_container(session, process_id=process_id, container=updated, source=f"edit_{field}")
    await state.clear()
    await message.answer(
        f"✅ Данные пересчитаны\n\n{container_text(updated)}",
        reply_markup=first_distillation_container_keyboard(process_id, container_id),
    )


@router.callback_query(F.data.startswith("process:first-distillation-delete:"))
async def delete_container_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    process_id, container_id = int(parts[2]), int(parts[3])
    await state.clear()
    await callback.message.edit_text(
        f"🗑 <b>Удалить ёмкость {container_id}?</b>\n\nЭто действие уберёт её из сводки первой перегонки.",
        reply_markup=first_distillation_delete_keyboard(process_id, container_id),
    )


@router.callback_query(F.data.startswith("process:first-distillation-delete-confirm:"))
async def delete_container_confirm_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    process_id, container_id = int(parts[3]), int(parts[4])
    async with session_factory() as session:
        await delete_container(session, process_id, container_id)
    await show_containers(callback, state, session_factory, process_id)


def calculator_menu_text() -> str:
    return (
        "⚗️ <b>Калькуляторы первой перегонки</b>\n\n"
        "🌡 Поправка спиртометра - приводит показание к 20 °C.\n"
        "💧 Абсолютный спирт - считает литры чистого спирта.\n"
        "🧪 Средняя крепость - объединяет несколько объёмов разной крепости."
    )


@router.callback_query(F.data.regexp(r"^process:first-distillation-calculators:\d+$"))
async def process_calculators_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await state.clear()
    await callback.message.edit_text(calculator_menu_text(), reply_markup=first_distillation_calculators_keyboard(process_id))


@router.callback_query(F.data == "calculators:first-distillation")
async def global_calculators_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await callback.message.edit_text(calculator_menu_text(), reply_markup=first_distillation_calculators_keyboard())


@router.callback_query(F.data.regexp(r"^process:first-distillation-calc:\d+:(correction|absolute|blend)$"))
async def process_calculator_start(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    await start_calculator(callback, state, int(parts[2]), parts[3])


@router.callback_query(F.data.regexp(r"^calculators:first-distillation:(correction|absolute|blend)$"))
async def global_calculator_start(callback: CallbackQuery, state: FSMContext) -> None:
    await start_calculator(callback, state, None, (callback.data or "").rsplit(":", 1)[-1])


async def start_calculator(callback: CallbackQuery, state: FSMContext, process_id: int | None, kind: str) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await state.set_state(FirstDistillationState.waiting_calc_value)
    await state.update_data(calc_process_id=process_id, calc_kind=kind, calc_step="first")
    if kind == "correction":
        text = "🌡 <b>Поправка спиртометра</b>\n\nВведите показание спиртометра, % об."
    elif kind == "absolute":
        text = "💧 <b>Абсолютный спирт</b>\n\nВведите объём жидкости в литрах."
    else:
        text = (
            "🧪 <b>Средняя крепость</b>\n\n"
            "Введите каждую часть с новой строки в формате <code>объём крепость</code>.\n"
            "Например:\n<code>2,5 48\n2,5 32\n1,8 18</code>\n\n"
            "Используйте крепость, уже приведённую к 20 °C."
        )
    await callback.message.edit_text(text, reply_markup=first_distillation_calculator_input_keyboard(process_id))


def parse_blend(text: str) -> list[tuple[Decimal, Decimal]] | None:
    parts: list[tuple[Decimal, Decimal]] = []
    for line in (line.strip() for line in text.splitlines() if line.strip()):
        match = PAIR_RE.match(line.replace(" ", " x ", 1) if ";" not in line and "x" not in line.lower() and "×" not in line and "х" not in line.lower() else line)
        if match is None:
            tokens = line.replace(";", " ").split()
            if len(tokens) != 2:
                return None
            raw_volume, raw_abv = tokens
        else:
            raw_volume, raw_abv = match.group(1), match.group(2)
        volume = parse_positive_decimal(raw_volume)
        abv = parse_decimal(raw_abv)
        if volume is None or abv is None or not Decimal("0") <= abv <= MAX_ABV:
            return None
        parts.append((volume, abv))
    return parts if len(parts) >= 2 else None


@router.message(FirstDistillationState.waiting_calc_value)
async def calculator_value_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    kind, step, process_id = data.get("calc_kind"), data.get("calc_step"), data.get("calc_process_id")
    if kind == "blend":
        blend = parse_blend(message.text)
        if blend is None:
            await message.answer("Введите минимум две строки: <code>объём крепость</code>.")
            return
        total_volume = sum((volume for volume, _ in blend), Decimal("0"))
        total_aa = sum((volume * abv / Decimal("100") for volume, abv in blend), Decimal("0"))
        average = round_abv(total_aa / total_volume * Decimal("100"))
        await state.clear()
        await message.answer(
            "🧪 <b>Средняя крепость</b>\n\n"
            f"💧 Общий объём: <b>{format_decimal(round_amount(total_volume))} л</b>\n"
            f"📈 Средняя крепость: <b>~{format_decimal(average)}%</b>\n"
            f"💧 Абсолютный спирт: <b>~{format_decimal(round_amount(total_aa))} л</b>",
            reply_markup=first_distillation_calculators_keyboard(process_id if isinstance(process_id, int) else None),
        )
        return
    value = parse_decimal(message.text)
    if value is None:
        await message.answer("Введите число.")
        return
    if kind == "correction":
        if step == "first":
            if not Decimal("0") <= value <= MAX_ABV:
                await message.answer("Введите показание от 0 до 100 %.")
                return
            await state.update_data(calc_step="temperature", calc_abv=str(value))
            await message.answer("🌡 Введите температуру пробы, °C.")
            return
        if not MIN_TEMPERATURE_C <= value <= MAX_TEMPERATURE_C:
            await message.answer("Введите температуру от -20 до 40 °C.")
            return
        observed = Decimal(str(data.get("calc_abv")))
        corrected = correct_alcoholmeter_abv(observed, value)
        await state.clear()
        await message.answer(
            "🌡 <b>Поправка спиртометра</b>\n\n"
            f"Показание: {format_decimal(observed)}% при {format_decimal(value)} °C\n"
            f"✅ При 20 °C: <b>~{format_decimal(corrected)}%</b>\n\n"
            "Расчёт предназначен для водно-спиртовой смеси.",
            reply_markup=first_distillation_calculators_keyboard(process_id if isinstance(process_id, int) else None),
        )
        return
    if kind == "absolute":
        if step == "first":
            if value <= 0 or value > MAX_VOLUME_L:
                await message.answer("Введите положительный объём до 10 000 л.")
                return
            await state.update_data(calc_step="abv", calc_volume=str(value))
            await message.answer("📈 Введите крепость, % об.")
            return
        if not Decimal("0") <= value <= MAX_ABV:
            await message.answer("Введите крепость от 0 до 100 %.")
            return
        volume = Decimal(str(data.get("calc_volume")))
        aa = absolute_alcohol_l(volume, value)
        await state.clear()
        await message.answer(
            "💧 <b>Абсолютный спирт</b>\n\n"
            f"Объём: {format_decimal(volume)} л · Крепость: {format_decimal(value)}%\n"
            f"✅ АС: <b>~{format_decimal(aa)} л</b>",
            reply_markup=first_distillation_calculators_keyboard(process_id if isinstance(process_id, int) else None),
        )
