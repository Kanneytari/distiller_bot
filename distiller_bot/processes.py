from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import (
    process_card_keyboard,
    process_input_cancel_keyboard,
    process_list_keyboard,
    process_stage_keyboard,
)
from .models import Drink, DrinkEvent, User

router = Router()

STAGES: dict[str, str] = {
    "preparation": "Подготовка",
    "fermentation": "Брожение",
    "distillation": "Перегонка",
    "dilution": "Разбавление",
    "aging": "Выдержка",
    "ready": "Готово",
}

STAGE_ICONS: dict[str, str] = {
    "Подготовка": "🧰",
    "Брожение": "🟡",
    "Перегонка": "🔥",
    "Разбавление": "💧",
    "Выдержка": "🪵",
    "Готово": "✅",
}


class ProcessState(StatesGroup):
    waiting_name = State()
    choosing_stage = State()
    waiting_custom_stage = State()
    waiting_rename = State()


def stage_icon(stage: str | None) -> str:
    if stage is None:
        return "🧪"
    return STAGE_ICONS.get(stage, "🧪")


def process_short_label(process: Drink) -> str:
    stage = process.current_stage or "Этап не указан"
    label = f"{stage_icon(process.current_stage)} {process.name} · {stage.lower()}"
    return label if len(label) <= 60 else f"{label[:57]}…"


def process_card_text(process: Drink) -> str:
    stage = process.current_stage or "Не указан"
    created_at = process.created_at.strftime("%d.%m.%Y") if process.created_at else "—"
    return (
        f"🧪 <b>{escape(process.name)}</b>\n\n"
        f"Этап: {stage_icon(process.current_stage)} {escape(stage)}\n"
        f"Добавлено: {created_at}"
    )


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
    return result.scalar_one_or_none()


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
            "Можно добавить процесс на любом этапе — от брожения до готового продукта."
        )

    items = [(process.id, process_short_label(process)) for process in processes]
    await callback.message.edit_text(text, reply_markup=process_list_keyboard(items))


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

    stage = STAGES.get(stage_key)
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
            reply_markup=process_card_keyboard(process.id),
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

        await state.clear()
        await callback.message.edit_text(
            process_card_text(process),
            reply_markup=process_card_keyboard(process.id),
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
        else:
            await state.clear()
            return

    await state.clear()
    await message.answer(
        process_card_text(process),
        reply_markup=process_card_keyboard(process.id),
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

    try:
        process_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    async with session_factory() as session:
        process = await get_owned_process(session, process_id, callback.from_user.id)

    if process is None:
        await render_process_list(callback, session_factory)
        return

    await callback.message.edit_text(
        process_card_text(process),
        reply_markup=process_card_keyboard(process.id),
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

    try:
        process_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
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
        f"✏️ <b>Переименовать процесс</b>\n\n"
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

    await state.clear()
    await message.answer(
        f"✅ Процесс переименован\n\n{process_card_text(process)}",
        reply_markup=process_card_keyboard(process.id),
    )


@router.callback_query(F.data.startswith("process:change-stage:"))
async def process_change_stage_handler(
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
        await render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.update_data(mode="change", process_id=process_id)
    await state.set_state(ProcessState.choosing_stage)
    await callback.message.edit_text(
        f"🔄 <b>{escape(process.name)}</b>\n\nВыберите новый этап:",
        reply_markup=process_stage_keyboard(process_id),
    )
