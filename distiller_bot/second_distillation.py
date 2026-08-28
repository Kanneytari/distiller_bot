from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .alcoholometry import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C, correct_alcoholmeter_abv
from .models import DrinkEvent
from .process_stages import stage_type_for_title
from .processes import get_owned_process, render_process_list
from .second_distillation_keyboards import (
    second_distillation_calculators_keyboard,
    second_distillation_charge_keyboard,
    second_distillation_cut_keyboard,
    second_distillation_cuts_keyboard,
    second_distillation_delete_keyboard,
    second_distillation_fraction_keyboard,
    second_distillation_input_keyboard,
    second_distillation_keyboard,
)

router = Router()

MAX_VOLUME_L = Decimal("10000")
MAX_ABV = Decimal("100")
RECOMMENDED_CHARGE_MIN_ABV = Decimal("25")
RECOMMENDED_CHARGE_MAX_ABV = Decimal("30")
MAX_RECOMMENDED_SAFE_CHARGE_ABV = Decimal("40")
DEFAULT_TARGET_ABV = Decimal("30")
HEADS_MIN_SHARE = Decimal("0.05")
HEADS_MAX_SHARE = Decimal("0.10")
TAILS_WATCH_ABV = Decimal("50")
TAILS_BEGINNER_ABV = Decimal("40")
PAIR_RE = re.compile(
    r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*[; xх×]+\s*([+-]?\d+(?:[.,]\d+)?)\s*%?\s*$"
)

FRACTIONS: dict[str, tuple[str, str]] = {
    "heads": ("🔴", "Головы"),
    "hearts": ("🟢", "Тело"),
    "tails": ("🔵", "Хвосты"),
    "unknown": ("⚪", "Не определено"),
}


@dataclass(frozen=True, slots=True)
class SpiritCharge:
    volume_l: Decimal
    abv: Decimal
    absolute_alcohol_l: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class SpiritCut:
    cut_id: int
    volume_l: Decimal
    observed_abv: Decimal
    temperature_c: Decimal
    corrected_abv: Decimal
    absolute_alcohol_l: Decimal
    fraction: str


class SecondDistillationState(StatesGroup):
    waiting_charge_volume = State()
    waiting_charge_abv = State()
    waiting_cut_volume = State()
    waiting_cut_abv = State()
    waiting_cut_temperature = State()
    waiting_cut_edit = State()
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


def dilution_result(
    volume_l: Decimal,
    current_abv: Decimal,
    target_abv: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    if volume_l <= 0:
        raise ValueError("Volume must be positive")
    if not Decimal("0") < current_abv <= MAX_ABV:
        raise ValueError("Current strength must be between 0 and 100 %")
    if not Decimal("0") < target_abv <= MAX_ABV:
        raise ValueError("Target strength must be between 0 and 100 %")
    if target_abv > current_abv:
        raise ValueError("Water cannot increase alcohol strength")

    aa_l = absolute_alcohol_l(volume_l, current_abv)
    if target_abv == current_abv:
        return Decimal("0.00"), round_amount(volume_l), aa_l

    final_volume_l = round_amount(volume_l * current_abv / target_abv)
    water_l = round_amount(final_volume_l - volume_l)
    return water_l, final_volume_l, aa_l


def heads_guidance(absolute_alcohol: Decimal) -> tuple[Decimal, Decimal]:
    return (
        round_amount(absolute_alcohol * HEADS_MIN_SHARE),
        round_amount(absolute_alcohol * HEADS_MAX_SHARE),
    )


def charge_recommendation(abv: Decimal) -> str:
    if abv > MAX_RECOMMENDED_SAFE_CHARGE_ABV:
        return (
            "⚠️ Крепость выше 40%. Перед второй перегонкой такую загрузку следует разбавить. "
            "Для новичка ориентир - 25-30%, удобная цель - 30%."
        )
    if abv > RECOMMENDED_CHARGE_MAX_ABV:
        return (
            "💡 Для более понятного разделения фракций новичку стоит ориентироваться на 25-30%. "
            "Удобная стартовая цель - 30%."
        )
    if abv >= RECOMMENDED_CHARGE_MIN_ABV:
        return "✅ Крепость находится в рекомендуемом для новичка диапазоне 25-30%."
    return (
        "ℹ️ Крепость ниже ориентировочного диапазона 25-30%. "
        "Дополнительное разбавление обычно не требуется."
    )


def cuts_guidance_text(absolute_alcohol: Decimal) -> str:
    low, high = heads_guidance(absolute_alcohol)
    return (
        "✂️ <b>Ориентиры голов и хвостов</b>\n\n"
        f"💧 Абсолютный спирт в загрузке: <b>{format_decimal(absolute_alcohol)} л</b>\n\n"
        "🔴 <b>Головы</b>\n"
        f"Ориентир для новичка: <b>{format_decimal(low)}-{format_decimal(high)} л АС</b> "
        "(5-10% абсолютного спирта загрузки).\n\n"
        "🔵 <b>Хвосты</b>\n"
        f"Начинайте особенно внимательно оценивать отбор примерно с "
        f"<b>{format_decimal(TAILS_WATCH_ABV)}%</b> в струе. "
        f"<b>{format_decimal(TAILS_BEGINNER_ABV)}%</b> - консервативный ориентир для новичка.\n\n"
        "Это ориентиры для pot still, а не обязательные границы. "
        "Фактические переходы зависят от сырья, аппарата и органолептики."
    )


def charge_from_data(data: dict | None, *, fallback_source: str = "saved") -> SpiritCharge | None:
    if not data:
        return None
    try:
        volume_l = Decimal(str(data["volume_l"]))
        abv = Decimal(str(data["abv"]))
    except (KeyError, InvalidOperation, TypeError):
        return None
    if not volume_l.is_finite() or not abv.is_finite():
        return None
    if volume_l <= 0 or not Decimal("0") < abv <= MAX_ABV:
        return None
    return SpiritCharge(
        volume_l=round_amount(volume_l),
        abv=round_abv(abv),
        absolute_alcohol_l=absolute_alcohol_l(volume_l, abv),
        source=str(data.get("source") or fallback_source),
    )


def cut_from_data(data: dict | None) -> SpiritCut | None:
    if not data or data.get("action") == "delete":
        return None
    try:
        cut_id = int(data["cut_id"])
        volume_l = Decimal(str(data["volume_l"]))
        observed_abv = Decimal(str(data["observed_abv"]))
        temperature_c = Decimal(str(data["temperature_c"]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return None
    fraction = str(data.get("fraction") or "unknown")
    if fraction not in FRACTIONS:
        fraction = "unknown"
    try:
        corrected_abv = correct_alcoholmeter_abv(observed_abv, temperature_c)
    except ValueError:
        return None
    return SpiritCut(
        cut_id=cut_id,
        volume_l=round_amount(volume_l),
        observed_abv=round_abv(observed_abv),
        temperature_c=temperature_c.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        corrected_abv=corrected_abv,
        absolute_alcohol_l=absolute_alcohol_l(volume_l, corrected_abv),
        fraction=fraction,
    )


def cut_data(cut: SpiritCut, *, source: str) -> dict[str, object]:
    return {
        "stage": "Вторая перегонка",
        "action": "upsert",
        "source": source,
        "cut_id": cut.cut_id,
        "volume_l": str(cut.volume_l),
        "observed_abv": str(cut.observed_abv),
        "temperature_c": str(cut.temperature_c),
        "corrected_abv": str(cut.corrected_abv),
        "absolute_alcohol_l": str(cut.absolute_alcohol_l),
        "fraction": cut.fraction,
    }


def make_cut(
    cut_id: int,
    volume_l: Decimal,
    observed_abv: Decimal,
    temperature_c: Decimal,
    fraction: str = "unknown",
) -> SpiritCut:
    if fraction not in FRACTIONS:
        fraction = "unknown"
    corrected_abv = correct_alcoholmeter_abv(observed_abv, temperature_c)
    return SpiritCut(
        cut_id=cut_id,
        volume_l=round_amount(volume_l),
        observed_abv=round_abv(observed_abv),
        temperature_c=temperature_c.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        corrected_abv=corrected_abv,
        absolute_alcohol_l=absolute_alcohol_l(volume_l, corrected_abv),
        fraction=fraction,
    )


def summarize_cuts(cuts: list[SpiritCut]) -> tuple[Decimal, Decimal, Decimal]:
    total_volume = round_amount(sum((item.volume_l for item in cuts), Decimal("0")))
    total_aa = round_amount(sum((item.absolute_alcohol_l for item in cuts), Decimal("0")))
    average_abv = (
        round_abv(total_aa / total_volume * Decimal("100"))
        if total_volume > 0
        else Decimal("0")
    )
    return total_volume, average_abv, total_aa


def grouped_summary(cuts: list[SpiritCut]) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    return {
        fraction: summarize_cuts([item for item in cuts if item.fraction == fraction])
        for fraction in FRACTIONS
    }


def charge_text(charge: SpiritCharge | None) -> str:
    if charge is None:
        return (
            "🛢 <b>Загрузка второй перегонки</b>\n\n"
            "Данные первой перегонки не найдены. Введите объём и крепость спирта-сырца вручную."
        )
    return (
        "🛢 <b>Загрузка второй перегонки</b>\n\n"
        f"🥃 Спирт-сырец: <b>{format_decimal(charge.volume_l)} л</b>\n"
        f"📈 Крепость: <b>{format_decimal(charge.abv)}%</b>\n"
        f"💧 Абсолютный спирт: <b>{format_decimal(charge.absolute_alcohol_l)} л</b>\n\n"
        f"{charge_recommendation(charge.abv)}"
    )


def fraction_label(fraction: str) -> str:
    icon, label = FRACTIONS.get(fraction, FRACTIONS["unknown"])
    return f"{icon} {label}"


def cut_line(cut: SpiritCut) -> str:
    return (
        f"🫙 {cut.cut_id}. {format_decimal(cut.volume_l)} л · "
        f"~{format_decimal(cut.corrected_abv)}% · {fraction_label(cut.fraction)}"
    )


def cut_text(cut: SpiritCut) -> str:
    return (
        f"🫙 <b>Ёмкость {cut.cut_id}</b>\n\n"
        f"💧 Объём: <b>{format_decimal(cut.volume_l)} л</b>\n"
        f"📈 Спиртометр: <b>{format_decimal(cut.observed_abv)}%</b>\n"
        f"🌡 Температура: <b>{format_decimal(cut.temperature_c)} °C</b>\n"
        f"✅ Крепость при 20 °C: <b>~{format_decimal(cut.corrected_abv)}%</b>\n"
        f"💧 Абсолютный спирт: <b>~{format_decimal(cut.absolute_alcohol_l)} л</b>\n"
        f"🏷 Фракция: <b>{fraction_label(cut.fraction)}</b>"
    )


def cuts_text(cuts: list[SpiritCut]) -> str:
    lines = ["⚗️ <b>Отборы второй перегонки</b>"]
    if not cuts:
        lines.extend(["", "Приёмные ёмкости пока не добавлены."])
        return "\n".join(lines)

    lines.append("")
    lines.extend(cut_line(item) for item in cuts)
    grouped = grouped_summary(cuts)
    lines.extend(["", "<b>Сводка:</b>"])
    for fraction in ("heads", "hearts", "tails", "unknown"):
        volume_l, average_abv, aa_l = grouped[fraction]
        if volume_l <= 0:
            continue
        lines.append(
            f"{fraction_label(fraction)}: {format_decimal(volume_l)} л · "
            f"~{format_decimal(average_abv)}% · АС {format_decimal(aa_l)} л"
        )
    return "\n".join(lines)


def second_distillation_text(charge: SpiritCharge | None, cuts: list[SpiritCut]) -> str:
    lines = ["⚗️ <b>Вторая перегонка</b>", ""]
    if charge is None:
        lines.append("🛢 Загрузка: не указана")
    else:
        lines.append(
            f"🛢 Загрузка: {format_decimal(charge.volume_l)} л · "
            f"{format_decimal(charge.abv)}% · АС {format_decimal(charge.absolute_alcohol_l)} л"
        )
    lines.append(f"🫙 Отборы: {len(cuts)} ёмкостей")

    hearts = [item for item in cuts if item.fraction == "hearts"]
    if hearts:
        volume_l, average_abv, aa_l = summarize_cuts(hearts)
        lines.extend(
            [
                "",
                "🟢 <b>Тело:</b>",
                f"💧 {format_decimal(volume_l)} л · 📈 ~{format_decimal(average_abv)}%",
                f"💧 Абсолютный спирт: ~{format_decimal(aa_l)} л",
            ]
        )
    return "\n".join(lines)


async def get_first_distillation_source(
    session: AsyncSession,
    process_id: int,
) -> SpiritCharge | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "first_distillation_summary",
        )
        .order_by(DrinkEvent.id.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if event is not None and event.data:
        try:
            data = {
                "volume_l": event.data["total_volume_l"],
                "abv": event.data["average_abv"],
                "source": "first_distillation",
            }
            charge = charge_from_data(data)
            if charge is not None and charge.volume_l > 0:
                return charge
        except KeyError:
            pass

    legacy_result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "first_distillation_result",
        )
        .order_by(DrinkEvent.id.desc())
        .limit(1)
    )
    legacy = legacy_result.scalar_one_or_none()
    if legacy is None or not legacy.data:
        return None
    try:
        return charge_from_data(
            {
                "volume_l": legacy.data["low_wines_volume_l"],
                "abv": legacy.data["low_wines_abv"],
                "source": "first_distillation_legacy",
            }
        )
    except KeyError:
        return None


async def get_saved_charge(session: AsyncSession, process_id: int) -> SpiritCharge | None:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "second_distillation_charge",
        )
        .order_by(DrinkEvent.id.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    return charge_from_data(event.data if event is not None else None)


async def get_effective_charge(session: AsyncSession, process_id: int) -> SpiritCharge | None:
    return await get_saved_charge(session, process_id) or await get_first_distillation_source(
        session, process_id
    )


async def save_charge(
    session: AsyncSession,
    *,
    process_id: int,
    volume_l: Decimal,
    abv: Decimal,
    source: str,
) -> SpiritCharge:
    charge = SpiritCharge(
        volume_l=round_amount(volume_l),
        abv=round_abv(abv),
        absolute_alcohol_l=absolute_alcohol_l(volume_l, abv),
        source=source,
    )
    session.add(
        DrinkEvent(
            drink_id=process_id,
            event_type="second_distillation_charge",
            title="Загрузка второй перегонки",
            data={
                "stage": "Вторая перегонка",
                "source": source,
                "volume_l": str(charge.volume_l),
                "abv": str(charge.abv),
                "absolute_alcohol_l": str(charge.absolute_alcohol_l),
            },
        )
    )
    await session.commit()
    return charge


async def get_cuts(session: AsyncSession, process_id: int) -> list[SpiritCut]:
    result = await session.execute(
        select(DrinkEvent)
        .where(
            DrinkEvent.drink_id == process_id,
            DrinkEvent.event_type == "second_distillation_cut",
        )
        .order_by(DrinkEvent.id.asc())
    )
    current: dict[int, SpiritCut] = {}
    for event in result.scalars():
        data = event.data or {}
        try:
            cut_id = int(data["cut_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if data.get("action") == "delete":
            current.pop(cut_id, None)
            continue
        cut = cut_from_data(data)
        if cut is not None:
            current[cut_id] = cut
    return [current[key] for key in sorted(current)]


async def save_cut(
    session: AsyncSession,
    *,
    process_id: int,
    cut: SpiritCut,
    source: str,
) -> None:
    session.add(
        DrinkEvent(
            drink_id=process_id,
            event_type="second_distillation_cut",
            title=f"Отбор {cut.cut_id}",
            data=cut_data(cut, source=source),
        )
    )
    await session.flush()
    cuts = await get_cuts(session, process_id)
    total_volume, average_abv, total_aa = summarize_cuts(cuts)
    grouped = grouped_summary(cuts)
    session.add(
        DrinkEvent(
            drink_id=process_id,
            event_type="second_distillation_summary",
            title="Сводка второй перегонки",
            data={
                "stage": "Вторая перегонка",
                "container_count": len(cuts),
                "total_volume_l": str(total_volume),
                "average_abv": str(average_abv),
                "absolute_alcohol_l": str(total_aa),
                "hearts_volume_l": str(grouped["hearts"][0]),
                "hearts_abv": str(grouped["hearts"][1]),
                "hearts_absolute_alcohol_l": str(grouped["hearts"][2]),
            },
        )
    )
    await session.commit()


async def delete_cut(session: AsyncSession, process_id: int, cut_id: int) -> None:
    session.add(
        DrinkEvent(
            drink_id=process_id,
            event_type="second_distillation_cut",
            title=f"Удалён отбор {cut_id}",
            data={
                "stage": "Вторая перегонка",
                "action": "delete",
                "cut_id": cut_id,
            },
        )
    )
    await session.commit()


def next_cut_id(cuts: list[SpiritCut]) -> int:
    return max((item.cut_id for item in cuts), default=0) + 1


async def owned_second_distillation(
    session: AsyncSession,
    process_id: int,
    telegram_id: int,
):
    process = await get_owned_process(session, process_id, telegram_id)
    if process is None or stage_type_for_title(process.current_stage) != "second_distillation":
        return None
    return process


async def show_second_distillation(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
    process_id: int,
) -> None:
    if callback.message is None:
        return
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        if process is None:
            await state.clear()
            await render_process_list(callback, session_factory)
            return
        charge = await get_effective_charge(session, process_id)
        cuts = await get_cuts(session, process_id)
    await state.clear()
    await callback.message.edit_text(
        second_distillation_text(charge, cuts),
        reply_markup=second_distillation_keyboard(process_id),
    )


@router.callback_query(F.data.regexp(r"^process:second-distillation:\d+$"))
async def second_distillation_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await show_second_distillation(callback, state, session_factory, process_id)


@router.callback_query(F.data.startswith("process:second-distillation-charge:"))
async def charge_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        charge = await get_effective_charge(session, process_id) if process is not None else None
    if process is None:
        return
    await state.clear()
    await callback.message.edit_text(
        charge_text(charge),
        reply_markup=second_distillation_charge_keyboard(process_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-charge-manual:"))
async def manual_charge_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await state.clear()
    await state.set_state(SecondDistillationState.waiting_charge_volume)
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        "🛢 <b>Загрузка второй перегонки</b>\n\n"
        "Введите объём спирта-сырца в литрах, например <code>6,8</code>.",
        reply_markup=second_distillation_input_keyboard(process_id),
    )


@router.message(SecondDistillationState.waiting_charge_volume)
async def manual_charge_volume(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    volume_l = parse_positive_decimal(message.text)
    if volume_l is None or volume_l > MAX_VOLUME_L:
        await message.answer("Введите объём от 0 до 10 000 л.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    await state.update_data(volume_l=str(volume_l))
    await state.set_state(SecondDistillationState.waiting_charge_abv)
    await message.answer(
        "📈 Введите крепость спирта-сырца в процентах.",
        reply_markup=second_distillation_input_keyboard(process_id),
    )


@router.message(SecondDistillationState.waiting_charge_abv)
async def manual_charge_abv(message: Message, state: FSMContext, session_factory) -> None:
    if message.from_user is None or message.text is None:
        return
    abv = parse_positive_decimal(message.text)
    if abv is None or abv > MAX_ABV:
        await message.answer("Введите крепость от 0 до 100 %.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    try:
        volume_l = Decimal(str(data["volume_l"]))
    except (KeyError, InvalidOperation):
        await state.clear()
        return
    if not isinstance(process_id, int):
        await state.clear()
        return
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            return
        charge = await save_charge(
            session,
            process_id=process_id,
            volume_l=volume_l,
            abv=abv,
            source="manual",
        )
    await state.clear()
    await message.answer(
        f"✅ Загрузка сохранена\n\n{charge_text(charge)}",
        reply_markup=second_distillation_charge_keyboard(process_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-cuts:"))
async def cuts_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        cuts = await get_cuts(session, process_id) if process is not None else []
    if process is None:
        return
    await state.clear()
    items = [(item.cut_id, f"🫙 {item.cut_id}") for item in cuts]
    await callback.message.edit_text(
        cuts_text(cuts),
        reply_markup=second_distillation_cuts_keyboard(process_id, items),
    )


@router.callback_query(F.data.startswith("process:second-distillation-cut-add:"))
async def cut_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    await state.clear()
    await state.set_state(SecondDistillationState.waiting_cut_volume)
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        "🫙 <b>Новая приёмная ёмкость</b>\n\n"
        "Введите объём отбора в литрах, например <code>0,5</code>.",
        reply_markup=second_distillation_input_keyboard(process_id),
    )


@router.message(SecondDistillationState.waiting_cut_volume)
async def cut_volume_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    volume_l = parse_positive_decimal(message.text)
    if volume_l is None or volume_l > MAX_VOLUME_L:
        await message.answer("Введите объём от 0 до 10 000 л.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    await state.update_data(volume_l=str(volume_l))
    await state.set_state(SecondDistillationState.waiting_cut_abv)
    await message.answer(
        "📈 Какое показание спиртометра?",
        reply_markup=second_distillation_input_keyboard(process_id),
    )


@router.message(SecondDistillationState.waiting_cut_abv)
async def cut_abv_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    observed_abv = parse_decimal(message.text)
    if observed_abv is None or not Decimal("0") <= observed_abv <= MAX_ABV:
        await message.answer("Введите показание спиртометра от 0 до 100 %.")
        return
    data = await state.get_data()
    process_id = data.get("process_id")
    if not isinstance(process_id, int):
        await state.clear()
        return
    await state.update_data(observed_abv=str(observed_abv))
    await state.set_state(SecondDistillationState.waiting_cut_temperature)
    await message.answer(
        "🌡 Какая температура пробы? Введите °C, например <code>24</code>.",
        reply_markup=second_distillation_input_keyboard(process_id),
    )


@router.message(SecondDistillationState.waiting_cut_temperature)
async def cut_temperature_handler(message: Message, state: FSMContext, session_factory) -> None:
    if message.from_user is None or message.text is None:
        return
    temperature_c = parse_decimal(message.text)
    if temperature_c is None or not MIN_TEMPERATURE_C <= temperature_c <= MAX_TEMPERATURE_C:
        await message.answer("Введите температуру от -20 до 40 °C.")
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
        process = await owned_second_distillation(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            return
        cuts = await get_cuts(session, process_id)
        cut = make_cut(next_cut_id(cuts), volume_l, observed_abv, temperature_c)
        await save_cut(session, process_id=process_id, cut=cut, source="create")
    await state.clear()
    await message.answer(
        f"✅ Ёмкость добавлена\n\n{cut_text(cut)}",
        reply_markup=second_distillation_cut_keyboard(process_id, cut.cut_id),
    )


@router.callback_query(F.data.regexp(r"^process:second-distillation-cut:\d+:\d+$"))
async def cut_view_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    process_id, cut_id = int(parts[2]), int(parts[3])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        cuts = await get_cuts(session, process_id) if process is not None else []
    item = next((cut for cut in cuts if cut.cut_id == cut_id), None)
    if process is None or item is None:
        return
    await state.clear()
    await callback.message.edit_text(
        cut_text(item),
        reply_markup=second_distillation_cut_keyboard(process_id, cut_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-fraction:"))
async def fraction_menu_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    process_id, cut_id = int(parts[2]), int(parts[3])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
    if process is None:
        return
    await state.clear()
    await callback.message.edit_text(
        "🏷 <b>Фракция</b>\n\nК какой части отбора относится эта ёмкость?",
        reply_markup=second_distillation_fraction_keyboard(process_id, cut_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-fraction-set:"))
async def fraction_set_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    process_id, cut_id, fraction = int(parts[2]), int(parts[3]), parts[4]
    if fraction not in FRACTIONS:
        return
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        if process is None:
            return
        cuts = await get_cuts(session, process_id)
        item = next((cut for cut in cuts if cut.cut_id == cut_id), None)
        if item is None:
            return
        updated = make_cut(
            item.cut_id,
            item.volume_l,
            item.observed_abv,
            item.temperature_c,
            fraction,
        )
        await save_cut(session, process_id=process_id, cut=updated, source="fraction")
    await state.clear()
    await callback.message.edit_text(
        f"✅ Фракция изменена\n\n{cut_text(updated)}",
        reply_markup=second_distillation_cut_keyboard(process_id, cut_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-cut-edit:"))
async def cut_edit_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        return
    process_id, cut_id, field = int(parts[2]), int(parts[3]), parts[4]
    if field not in {"volume", "abv", "temperature"}:
        return
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        cuts = await get_cuts(session, process_id) if process is not None else []
    item = next((cut for cut in cuts if cut.cut_id == cut_id), None)
    if process is None or item is None:
        return
    current = {
        "volume": f"{format_decimal(item.volume_l)} л",
        "abv": f"{format_decimal(item.observed_abv)}%",
        "temperature": f"{format_decimal(item.temperature_c)} °C",
    }[field]
    title = {
        "volume": "💧 Объём",
        "abv": "📈 Спиртометр",
        "temperature": "🌡 Температура",
    }[field]
    await state.clear()
    await state.set_state(SecondDistillationState.waiting_cut_edit)
    await state.update_data(process_id=process_id, cut_id=cut_id, edit_field=field)
    await callback.message.edit_text(
        f"{title}\n\nСейчас: <b>{current}</b>.\nВведите новое значение.",
        reply_markup=second_distillation_input_keyboard(process_id),
    )


@router.message(SecondDistillationState.waiting_cut_edit)
async def cut_edit_value_handler(message: Message, state: FSMContext, session_factory) -> None:
    if message.from_user is None or message.text is None:
        return
    value = parse_decimal(message.text)
    if value is None:
        await message.answer("Введите число.")
        return
    data = await state.get_data()
    process_id, cut_id, field = data.get("process_id"), data.get("cut_id"), data.get("edit_field")
    if not isinstance(process_id, int) or not isinstance(cut_id, int):
        await state.clear()
        return
    if field == "volume" and not Decimal("0") < value <= MAX_VOLUME_L:
        await message.answer("Введите объём от 0 до 10 000 л.")
        return
    if field == "abv" and not Decimal("0") <= value <= MAX_ABV:
        await message.answer("Введите показание от 0 до 100 %.")
        return
    if field == "temperature" and not MIN_TEMPERATURE_C <= value <= MAX_TEMPERATURE_C:
        await message.answer("Введите температуру от -20 до 40 °C.")
        return
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, message.from_user.id)
        if process is None:
            return
        cuts = await get_cuts(session, process_id)
        item = next((cut for cut in cuts if cut.cut_id == cut_id), None)
        if item is None:
            return
        volume_l, observed_abv, temperature_c = item.volume_l, item.observed_abv, item.temperature_c
        if field == "volume":
            volume_l = value
        elif field == "abv":
            observed_abv = value
        else:
            temperature_c = value
        updated = make_cut(
            cut_id,
            volume_l,
            observed_abv,
            temperature_c,
            item.fraction,
        )
        await save_cut(session, process_id=process_id, cut=updated, source=f"edit_{field}")
    await state.clear()
    await message.answer(
        f"✅ Данные пересчитаны\n\n{cut_text(updated)}",
        reply_markup=second_distillation_cut_keyboard(process_id, cut_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-cut-delete:"))
async def cut_delete_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    process_id, cut_id = int(parts[2]), int(parts[3])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
    if process is None:
        return
    await state.clear()
    await callback.message.edit_text(
        f"🗑 <b>Удалить ёмкость {cut_id}?</b>",
        reply_markup=second_distillation_delete_keyboard(process_id, cut_id),
    )


@router.callback_query(F.data.startswith("process:second-distillation-cut-delete-confirm:"))
async def cut_delete_confirm_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        return
    process_id, cut_id = int(parts[2]), int(parts[3])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        if process is None:
            return
        await delete_cut(session, process_id, cut_id)
    await state.clear()
    await callback.message.edit_text(
        "✅ Ёмкость удалена.",
        reply_markup=second_distillation_keyboard(process_id),
    )


def calculators_text() -> str:
    return (
        "⚗️ <b>Калькуляторы второй перегонки</b>\n\n"
        "💧 Разбавление спирта - сколько воды добавить перед второй перегонкой.\n"
        "✂️ Головы и хвосты - ориентиры для новичка.\n"
        "🌡 Поправка спиртометра - крепость при 20 °C.\n"
        "💧 Абсолютный спирт - количество чистого спирта.\n"
        "🧪 Средняя крепость - сводный расчёт нескольких объёмов."
    )


@router.callback_query(F.data.regexp(r"^process:second-distillation-calculators:\d+$"))
async def process_calculators_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
    if process is None:
        return
    await state.clear()
    await callback.message.edit_text(
        calculators_text(),
        reply_markup=second_distillation_calculators_keyboard(process_id),
    )


@router.callback_query(F.data == "calculators:second-distillation")
async def global_calculators_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await callback.message.edit_text(
        calculators_text(),
        reply_markup=second_distillation_calculators_keyboard(),
    )


def calculator_context(callback_data: str) -> tuple[int | None, str] | None:
    process_match = re.fullmatch(r"process:second-distillation-calc:(\d+):(\w+)", callback_data)
    if process_match:
        return int(process_match.group(1)), process_match.group(2)
    global_match = re.fullmatch(r"calculators:second-distillation:(\w+)", callback_data)
    if global_match:
        return None, global_match.group(1)
    return None


@router.callback_query(
    F.data.regexp(r"^(process:second-distillation-calc:\d+|calculators:second-distillation):(dilution|cuts|correction|absolute|blend)$")
)
async def calculator_start_handler(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    context = calculator_context(callback.data or "")
    if context is None:
        return
    process_id, mode = context
    await state.clear()

    if process_id is not None:
        async with session_factory() as session:
            process = await owned_second_distillation(session, process_id, callback.from_user.id)
            charge = await get_effective_charge(session, process_id) if process is not None else None
        if process is None:
            return
    else:
        charge = None

    if mode == "cuts" and charge is not None:
        await callback.message.edit_text(
            cuts_guidance_text(charge.absolute_alcohol_l),
            reply_markup=second_distillation_calculators_keyboard(process_id),
        )
        return

    await state.set_state(SecondDistillationState.waiting_calc_value)
    await state.update_data(process_id=process_id, calc_mode=mode)

    if mode == "dilution" and charge is not None:
        await state.update_data(
            calc_step="target",
            volume_l=str(charge.volume_l),
            current_abv=str(charge.abv),
        )
        text = (
            "💧 <b>Разбавление спирта</b>\n\n"
            f"Сейчас: {format_decimal(charge.volume_l)} л · {format_decimal(charge.abv)}%.\n"
            "Для новичка рекомендуемый диапазон перед второй перегонкой - 25-30%.\n"
            "Введите целевую крепость. Удобная стартовая цель - <code>30</code>."
        )
    elif mode == "dilution":
        await state.update_data(calc_step="volume")
        text = "💧 <b>Разбавление спирта</b>\n\nВведите исходный объём в литрах."
    elif mode == "cuts":
        await state.update_data(calc_step="aa")
        text = "✂️ <b>Головы и хвосты</b>\n\nВведите объём абсолютного спирта в загрузке, л."
    elif mode == "correction":
        await state.update_data(calc_step="abv")
        text = "🌡 <b>Поправка спиртометра</b>\n\nВведите показание спиртометра, %."
    elif mode == "absolute":
        await state.update_data(calc_step="volume")
        text = "💧 <b>Абсолютный спирт</b>\n\nВведите объём раствора, л."
    else:
        await state.update_data(calc_step="pairs")
        text = (
            "🧪 <b>Средняя крепость</b>\n\n"
            "Введите объёмы и крепости по одному на строку в формате <code>2,5 x 48</code>."
        )
    await callback.message.edit_text(
        text,
        reply_markup=second_distillation_input_keyboard(process_id),
    )


def parse_blend_pairs(text: str) -> list[tuple[Decimal, Decimal]] | None:
    pairs: list[tuple[Decimal, Decimal]] = []
    for line in [part.strip() for part in text.splitlines() if part.strip()]:
        match = PAIR_RE.match(line)
        if match is None:
            return None
        volume_l = Decimal(match.group(1).replace(",", "."))
        abv = Decimal(match.group(2).replace(",", "."))
        if volume_l <= 0 or not Decimal("0") <= abv <= MAX_ABV:
            return None
        pairs.append((volume_l, abv))
    return pairs or None


@router.message(SecondDistillationState.waiting_calc_value)
async def calculator_value_handler(message: Message, state: FSMContext, session_factory) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    mode = data.get("calc_mode")
    step = data.get("calc_step")
    process_id = data.get("process_id")
    if mode not in {"dilution", "cuts", "correction", "absolute", "blend"}:
        await state.clear()
        return

    result_text: str | None = None

    if mode == "blend":
        pairs = parse_blend_pairs(message.text)
        if pairs is None:
            await message.answer("Используйте формат <code>2,5 x 48</code>, одна ёмкость на строку.")
            return
        total_volume = sum((volume for volume, _abv in pairs), Decimal("0"))
        total_aa = sum((volume * abv / Decimal("100") for volume, abv in pairs), Decimal("0"))
        average = round_abv(total_aa / total_volume * Decimal("100"))
        result_text = (
            "🧪 <b>Средняя крепость</b>\n\n"
            f"💧 Общий объём: <b>{format_decimal(round_amount(total_volume))} л</b>\n"
            f"📈 Средняя крепость: <b>~{format_decimal(average)}%</b>\n"
            f"💧 Абсолютный спирт: <b>~{format_decimal(round_amount(total_aa))} л</b>"
        )
    elif mode == "cuts":
        aa_l = parse_positive_decimal(message.text)
        if aa_l is None:
            await message.answer("Введите положительный объём абсолютного спирта.")
            return
        result_text = cuts_guidance_text(aa_l)
    else:
        value = parse_decimal(message.text)
        if value is None:
            await message.answer("Введите число.")
            return

        if mode == "correction":
            if step == "abv":
                if not Decimal("0") <= value <= MAX_ABV:
                    await message.answer("Введите показание от 0 до 100 %.")
                    return
                await state.update_data(calc_step="temperature", observed_abv=str(value))
                await message.answer("🌡 Введите температуру пробы, °C.")
                return
            if not MIN_TEMPERATURE_C <= value <= MAX_TEMPERATURE_C:
                await message.answer("Введите температуру от -20 до 40 °C.")
                return
            observed_abv = Decimal(str(data["observed_abv"]))
            corrected = correct_alcoholmeter_abv(observed_abv, value)
            result_text = (
                "🌡 <b>Поправка спиртометра</b>\n\n"
                f"Показание: {format_decimal(observed_abv)}% при {format_decimal(value)} °C\n"
                f"✅ При 20 °C: <b>~{format_decimal(corrected)}%</b>"
            )
        elif mode == "absolute":
            if step == "volume":
                if value <= 0:
                    await message.answer("Введите положительный объём.")
                    return
                await state.update_data(calc_step="abv", volume_l=str(value))
                await message.answer("📈 Введите крепость, %.")
                return
            if not Decimal("0") <= value <= MAX_ABV:
                await message.answer("Введите крепость от 0 до 100 %.")
                return
            volume_l = Decimal(str(data["volume_l"]))
            aa_l = absolute_alcohol_l(volume_l, value)
            result_text = (
                "💧 <b>Абсолютный спирт</b>\n\n"
                f"{format_decimal(volume_l)} л · {format_decimal(value)}%\n"
                f"💧 АС: <b>~{format_decimal(aa_l)} л</b>"
            )
        elif mode == "dilution":
            if step == "volume":
                if value <= 0:
                    await message.answer("Введите положительный объём.")
                    return
                await state.update_data(calc_step="current_abv", volume_l=str(value))
                await message.answer("📈 Введите текущую крепость, %.")
                return
            if step == "current_abv":
                if not Decimal("0") < value <= MAX_ABV:
                    await message.answer("Введите крепость от 0 до 100 %.")
                    return
                await state.update_data(calc_step="target", current_abv=str(value))
                await message.answer(
                    "Введите целевую крепость. Для новичка ориентир 25-30%, удобная цель - 30%."
                )
                return
            volume_l = Decimal(str(data["volume_l"]))
            current_abv = Decimal(str(data["current_abv"]))
            target_abv = value
            if not Decimal("0") < target_abv <= MAX_RECOMMENDED_SAFE_CHARGE_ABV:
                await message.answer("Для этого расчёта укажите целевую крепость от 0 до 40 %.")
                return
            if target_abv > current_abv:
                await message.answer("Добавлением воды нельзя повысить крепость.")
                return
            water_l, final_volume_l, aa_l = dilution_result(volume_l, current_abv, target_abv)
            recommendation = charge_recommendation(target_abv)
            result_text = (
                "💧 <b>Разбавление спирта</b>\n\n"
                f"Исходно: {format_decimal(volume_l)} л · {format_decimal(current_abv)}%\n"
                f"💧 Добавить воды: <b>~{format_decimal(water_l)} л</b>\n"
                f"🛢 После разбавления: <b>~{format_decimal(final_volume_l)} л · "
                f"{format_decimal(target_abv)}%</b>\n"
                f"💧 Абсолютный спирт: ~{format_decimal(aa_l)} л\n\n"
                f"{recommendation}"
            )
            if isinstance(process_id, int) and message.from_user is not None:
                async with session_factory() as session:
                    process = await owned_second_distillation(
                        session, process_id, message.from_user.id
                    )
                    if process is not None:
                        await save_charge(
                            session,
                            process_id=process_id,
                            volume_l=final_volume_l,
                            abv=target_abv,
                            source="dilution",
                        )
                        result_text = f"✅ Загрузка обновлена\n\n{result_text}"

    await state.clear()
    markup = second_distillation_calculators_keyboard(
        process_id if isinstance(process_id, int) else None
    )
    await message.answer(result_text or "Расчёт не выполнен.", reply_markup=markup)


@router.callback_query(F.data.startswith("process:second-distillation-dilution:"))
async def charge_dilution_shortcut(callback: CallbackQuery, state: FSMContext, session_factory) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await owned_second_distillation(session, process_id, callback.from_user.id)
        charge = await get_effective_charge(session, process_id) if process is not None else None
    if process is None:
        return
    if charge is None:
        await callback.message.edit_text(
            "Сначала укажите загрузку второй перегонки.",
            reply_markup=second_distillation_charge_keyboard(process_id),
        )
        return
    await state.clear()
    await state.set_state(SecondDistillationState.waiting_calc_value)
    await state.update_data(
        process_id=process_id,
        calc_mode="dilution",
        calc_step="target",
        volume_l=str(charge.volume_l),
        current_abv=str(charge.abv),
    )
    await callback.message.edit_text(
        "💧 <b>Разбавление спирта</b>\n\n"
        f"Сейчас: {format_decimal(charge.volume_l)} л · {format_decimal(charge.abv)}%.\n"
        "Рекомендуемый ориентир для новичка - 25-30%.\n"
        "Введите целевую крепость, например <code>30</code>.",
        reply_markup=second_distillation_input_keyboard(process_id),
    )
