from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import processes as processes_module
from .keyboards import process_list_keyboard, process_stage_keyboard
from .models import Drink
from .process_stages import STAGE_TITLES, stage_icon

router = Router()


class DrinkUiState(StatesGroup):
    waiting_name = State()
    choosing_stage = State()
    waiting_rename = State()
    waiting_note = State()


def parameters_keyboard(process_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Название", callback_data=f"process:parameters:rename:{process_id}")
    builder.button(text="📝 Заметка", callback_data=f"process:parameters:note:{process_id}")
    builder.button(text="🗑 Удалить", callback_data=f"process:parameters:delete:{process_id}")
    builder.button(text="🔙 К напитку", callback_data=f"process:view:{process_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def delete_confirmation_keyboard(process_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Да, удалить",
        callback_data=f"process:parameters:delete-confirm:{process_id}",
    )
    builder.button(text="🔙 Отмена", callback_data=f"process:parameters:{process_id}")
    builder.adjust(1)
    return builder.as_markup()


def parameters_text(process: Drink, latest_note=None) -> str:
    lines = [
        "⚙️ <b>Параметры напитка</b>",
        "",
        f"🥃 <b>{escape(process.name)}</b>",
        f"Этап: {stage_icon(process.current_stage)} {escape(process.current_stage or 'Не указан')}",
    ]
    preview = processes_module.note_preview(latest_note)
    lines.extend(["", "📝 <b>Последняя заметка:</b>", preview or "Нет заметок."])
    return "\n".join(lines)


_original_process_card_text = processes_module.process_card_text


def drink_card_text(process, latest_measurement=None, latest_note=None) -> str:
    text = _original_process_card_text(process, latest_measurement, latest_note)
    if text.startswith("🧪 <b>"):
        return "🥃 <b>" + text[len("🧪 <b>") :]
    return text


async def render_drink_list(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.message is None:
        return

    async with session_factory() as session:
        user = await processes_module.get_user(session, callback.from_user.id)
        if user is None:
            await callback.message.edit_text("Сначала запустите бота командой /start.")
            return
        result = await session.execute(
            select(Drink)
            .where(Drink.user_id == user.id, Drink.status == "active")
            .order_by(Drink.created_at.desc(), Drink.id.desc())
        )
        drinks = list(result.scalars())

    if drinks:
        text = "🥃 <b>Мои напитки</b>\n\nВыберите напиток или добавьте новый."
    else:
        text = (
            "🥃 <b>Мои напитки</b>\n\n"
            "Здесь можно вести приготовления от состава браги до готового напитка.\n\n"
            "Напиток можно добавить на любом этапе."
        )

    items = [(drink.id, processes_module.process_short_label(drink)) for drink in drinks]
    await callback.message.edit_text(text, reply_markup=process_list_keyboard(items))


processes_module.process_card_text = drink_card_text
processes_module.render_process_list = render_drink_list


@router.callback_query(F.data == "process:add")
async def drink_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(DrinkUiState.waiting_name)
    if callback.message is None:
        return
    await callback.message.edit_text(
        "🥃 <b>Новый напиток</b>\n\n"
        "Как назовём напиток? Название нужно только для того, чтобы потом легко его найти.\n\n"
        "Например:\n"
        "• Самогон\n"
        "• Яблочный дистиллят\n"
        "• Кальвадос",
        reply_markup=processes_module.process_input_cancel_keyboard(),
    )


@router.message(DrinkUiState.waiting_name)
async def drink_name_handler(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    name = message.text.strip()
    if not name:
        await message.answer("Введите название напитка.")
        return
    if len(name) > 255:
        await message.answer("Название слишком длинное. Используйте не больше 255 символов.")
        return

    await state.update_data(name=name)
    await state.set_state(DrinkUiState.choosing_stage)
    await message.answer("На каком этапе вы сейчас?", reply_markup=process_stage_keyboard())


@router.callback_query(DrinkUiState.choosing_stage, F.data.startswith("process:stage:"))
async def drink_stage_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    stage_key = (callback.data or "").rsplit(":", 1)[-1]
    stage = STAGE_TITLES.get(stage_key)
    if stage is None:
        return
    data = await state.get_data()
    name = data.get("name")
    if not isinstance(name, str):
        await state.clear()
        return

    async with session_factory() as session:
        user = await processes_module.get_user(session, callback.from_user.id)
        if user is None:
            await state.clear()
            await callback.message.edit_text("Сначала запустите бота командой /start.")
            return
        process = await processes_module.create_process(
            session,
            user_id=user.id,
            name=name,
            stage=stage,
        )

    await state.clear()
    await callback.message.edit_text(
        f"✅ Напиток добавлен\n\n{processes_module.process_card_text(process)}",
        reply_markup=processes_module.process_card_markup(process),
    )


@router.callback_query(F.data.regexp(r"^process:parameters:\d+$"))
async def parameters_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])

    async with session_factory() as session:
        process = await processes_module.get_owned_process(session, process_id, callback.from_user.id)
        latest_note = (
            await processes_module.get_latest_note(session, process_id)
            if process is not None
            else None
        )

    if process is None:
        await processes_module.render_process_list(callback, session_factory)
        return
    await callback.message.edit_text(
        parameters_text(process, latest_note),
        reply_markup=parameters_keyboard(process_id),
    )


@router.callback_query(F.data.regexp(r"^process:parameters:rename:\d+$"))
async def rename_start_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await processes_module.get_owned_process(session, process_id, callback.from_user.id)
    if process is None:
        await processes_module.render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.set_state(DrinkUiState.waiting_rename)
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        "✏️ <b>Название напитка</b>\n\n"
        f"Сейчас: <b>{escape(process.name)}</b>\n\n"
        "Введите новое название.",
        reply_markup=parameters_keyboard(process_id),
    )


@router.message(DrinkUiState.waiting_rename)
async def rename_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return
    name = message.text.strip()
    if not name:
        await message.answer("Введите новое название напитка.")
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
        process = await processes_module.get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Напиток не найден.")
            return
        process = await processes_module.rename_process(session, process=process, name=name)
        latest_note = await processes_module.get_latest_note(session, process_id)

    await state.clear()
    await message.answer(
        f"✅ Название обновлено\n\n{parameters_text(process, latest_note)}",
        reply_markup=parameters_keyboard(process_id),
    )


@router.callback_query(F.data.regexp(r"^process:parameters:note:\d+$"))
async def note_start_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await processes_module.get_owned_process(session, process_id, callback.from_user.id)
    if process is None:
        await processes_module.render_process_list(callback, session_factory)
        return

    await state.clear()
    await state.set_state(DrinkUiState.waiting_note)
    await state.update_data(process_id=process_id)
    await callback.message.edit_text(
        f"📝 <b>Заметка · {escape(process.name)}</b>\n\nВведите текст заметки.",
        reply_markup=parameters_keyboard(process_id),
    )


@router.message(DrinkUiState.waiting_note)
async def note_value_handler(
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
        process = await processes_module.get_owned_process(session, process_id, message.from_user.id)
        if process is None:
            await state.clear()
            await message.answer("Напиток не найден.")
            return
        latest_note = await processes_module.create_process_note(session, process=process, text=text)

    await state.clear()
    await message.answer(
        f"✅ Заметка сохранена\n\n{parameters_text(process, latest_note)}",
        reply_markup=parameters_keyboard(process_id),
    )


@router.callback_query(F.data.regexp(r"^process:parameters:delete:\d+$"))
async def delete_start_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])
    async with session_factory() as session:
        process = await processes_module.get_owned_process(session, process_id, callback.from_user.id)
    if process is None:
        await processes_module.render_process_list(callback, session_factory)
        return

    await callback.message.edit_text(
        "🗑 <b>Удалить напиток?</b>\n\n"
        f"🥃 <b>{escape(process.name)}</b>\n\n"
        "Будут удалены сам напиток и все связанные с ним данные. "
        "Это действие нельзя отменить.",
        reply_markup=delete_confirmation_keyboard(process_id),
    )


@router.callback_query(F.data.regexp(r"^process:parameters:delete-confirm:\d+$"))
async def delete_confirm_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    process_id = int((callback.data or "").rsplit(":", 1)[-1])

    async with session_factory() as session:
        process = await processes_module.get_owned_process(session, process_id, callback.from_user.id)
        if process is None:
            missing = True
        else:
            missing = False
            await session.delete(process)
            await session.commit()

    await processes_module.render_process_list(callback, session_factory)
