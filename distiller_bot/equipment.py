from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import (
    equipment_card_keyboard,
    equipment_delete_keyboard,
    equipment_edit_keyboard,
    equipment_input_cancel_keyboard,
    equipment_list_keyboard,
    equipment_type_keyboard,
)
from .models import Equipment, User

router = Router()

EQUIPMENT_TYPES: dict[str, tuple[str, str]] = {
    "still": ("🛢", "Перегонный куб"),
    "fermenter": ("🪣", "Ферментер"),
    "column": ("🧱", "Колонна"),
    "heater": ("🔥", "Нагрев"),
    "other": ("⚙️", "Другое"),
}

CAPACITY_TYPES = {"still", "fermenter"}
POWER_TYPES = {"heater"}


class EquipmentState(StatesGroup):
    adding_value = State()
    editing_value = State()


def format_number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def equipment_type_title(equipment_type: str) -> str:
    icon, title = EQUIPMENT_TYPES.get(equipment_type, ("⚙️", "Оборудование"))
    return f"{icon} {title}"


def equipment_short_label(item: Equipment) -> str:
    icon, _ = EQUIPMENT_TYPES.get(item.equipment_type, ("⚙️", "Оборудование"))
    details: list[str] = []
    capacity = format_number(item.capacity_l)
    power = format_number(item.power_kw)
    if capacity is not None:
        details.append(f"{capacity} л")
    if power is not None:
        details.append(f"{power} кВт")
    suffix = f" · {' · '.join(details)}" if details else ""
    return f"{icon} {item.name}{suffix}"


def equipment_card_text(item: Equipment) -> str:
    lines = [f"<b>{equipment_type_title(item.equipment_type)}</b>", "", f"Название: {item.name}"]

    capacity = format_number(item.capacity_l)
    if capacity is not None:
        lines.append(f"Объём: {capacity} л")

    power = format_number(item.power_kw)
    if power is not None:
        lines.append(f"Мощность: {power} кВт")

    return "\n".join(lines)


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_owned_equipment(
    session: AsyncSession,
    equipment_id: int,
    telegram_id: int,
) -> Equipment | None:
    result = await session.execute(
        select(Equipment)
        .join(User, Equipment.user_id == User.id)
        .where(Equipment.id == equipment_id, User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def render_equipment_list(
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
            select(Equipment)
            .where(Equipment.user_id == user.id)
            .order_by(Equipment.created_at.asc(), Equipment.id.asc())
        )
        equipment = list(result.scalars())

    if not equipment:
        text = (
            "⚙️ <b>Оборудование</b>\n\n"
            "Добавьте своё оборудование один раз - бот сможет учитывать его "
            "в расчётах и рецептах.\n\n"
            "Это необязательно: без профиля остальные функции тоже работают."
        )
    else:
        text = "⚙️ <b>Моё оборудование</b>\n\nВыберите устройство:"

    items = [(item.id, equipment_short_label(item)) for item in equipment]
    await callback.message.edit_text(text, reply_markup=equipment_list_keyboard(items))


@router.callback_query(F.data == "menu:equipment")
async def equipment_list_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    await render_equipment_list(callback, session_factory)


@router.callback_query(F.data == "equipment:add")
async def equipment_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            "➕ <b>Оборудование</b>\n\nЧто хотите добавить?",
            reply_markup=equipment_type_keyboard(),
        )


@router.callback_query(F.data.startswith("equipment:add:"))
async def equipment_add_type_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    equipment_type = (callback.data or "").rsplit(":", 1)[-1]
    if equipment_type not in EQUIPMENT_TYPES:
        return

    await state.set_state(EquipmentState.adding_value)
    await state.update_data(equipment_type=equipment_type)

    if equipment_type in CAPACITY_TYPES:
        prompt = f"{equipment_type_title(equipment_type)}\n\nУкажите объём, л"
    elif equipment_type in POWER_TYPES:
        prompt = f"{equipment_type_title(equipment_type)}\n\nУкажите мощность, кВт"
    else:
        prompt = f"{equipment_type_title(equipment_type)}\n\nКак назовём это оборудование?"

    await callback.message.edit_text(prompt, reply_markup=equipment_input_cancel_keyboard())


@router.message(EquipmentState.adding_value)
async def equipment_add_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    data = await state.get_data()
    equipment_type = data.get("equipment_type")
    if equipment_type not in EQUIPMENT_TYPES:
        await state.clear()
        return

    capacity_l: Decimal | None = None
    power_kw: Decimal | None = None

    if equipment_type in CAPACITY_TYPES or equipment_type in POWER_TYPES:
        try:
            value = Decimal(message.text.strip().replace(",", "."))
        except InvalidOperation:
            await message.answer(
                "Введите число, например <b>37</b> или <b>3.5</b>.",
                reply_markup=equipment_input_cancel_keyboard(),
            )
            return
        if value <= 0:
            await message.answer(
                "Значение должно быть больше нуля.",
                reply_markup=equipment_input_cancel_keyboard(),
            )
            return

        if equipment_type in CAPACITY_TYPES:
            capacity_l = value
        else:
            power_kw = value
        name = EQUIPMENT_TYPES[equipment_type][1]
    else:
        name = message.text.strip()
        if not name:
            await message.answer(
                "Введите название оборудования.",
                reply_markup=equipment_input_cancel_keyboard(),
            )
            return
        if len(name) > 255:
            await message.answer(
                "Название слишком длинное. Используйте не больше 255 символов.",
                reply_markup=equipment_input_cancel_keyboard(),
            )
            return

    async with session_factory() as session:
        user = await get_user(session, message.from_user.id)
        if user is None:
            await state.clear()
            await message.answer("Сначала запустите бота командой /start.")
            return

        item = Equipment(
            user_id=user.id,
            name=name,
            equipment_type=equipment_type,
            capacity_l=capacity_l,
            power_kw=power_kw,
            properties={},
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)

    await state.clear()
    await message.answer(
        f"✅ Оборудование добавлено\n\n{equipment_card_text(item)}",
        reply_markup=equipment_card_keyboard(item.id),
    )


@router.callback_query(F.data.startswith("equipment:view:"))
async def equipment_view_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return

    try:
        equipment_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    async with session_factory() as session:
        item = await get_owned_equipment(session, equipment_id, callback.from_user.id)

    if item is None:
        await render_equipment_list(callback, session_factory)
        return

    await callback.message.edit_text(
        equipment_card_text(item),
        reply_markup=equipment_card_keyboard(item.id),
    )


@router.callback_query(F.data.startswith("equipment:edit:"))
async def equipment_edit_handler(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    try:
        equipment_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    async with session_factory() as session:
        item = await get_owned_equipment(session, equipment_id, callback.from_user.id)

    if item is None:
        await render_equipment_list(callback, session_factory)
        return

    await callback.message.edit_text(
        f"✏️ <b>Изменить</b>\n\n{equipment_short_label(item)}\n\nЧто изменить?",
        reply_markup=equipment_edit_keyboard(
            item.id,
            can_edit_capacity=item.equipment_type in CAPACITY_TYPES,
            can_edit_power=item.equipment_type in POWER_TYPES,
        ),
    )


@router.callback_query(F.data.startswith("equipment:field:"))
async def equipment_edit_field_handler(
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
        equipment_id = int(parts[2])
    except ValueError:
        return
    field = parts[3]

    async with session_factory() as session:
        item = await get_owned_equipment(session, equipment_id, callback.from_user.id)

    if item is None:
        await render_equipment_list(callback, session_factory)
        return

    allowed_fields = {"name"}
    if item.equipment_type in CAPACITY_TYPES:
        allowed_fields.add("capacity")
    if item.equipment_type in POWER_TYPES:
        allowed_fields.add("power")
    if field not in allowed_fields:
        return

    prompts = {
        "name": "Введите новое название",
        "capacity": "Укажите новый объём, л",
        "power": "Укажите новую мощность, кВт",
    }

    await state.set_state(EquipmentState.editing_value)
    await state.update_data(equipment_id=equipment_id, field=field)
    await callback.message.edit_text(
        f"✏️ <b>{item.name}</b>\n\n{prompts[field]}",
        reply_markup=equipment_input_cancel_keyboard(equipment_id),
    )


@router.message(EquipmentState.editing_value)
async def equipment_edit_value_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or message.text is None:
        return

    data = await state.get_data()
    equipment_id = data.get("equipment_id")
    field = data.get("field")
    if not isinstance(equipment_id, int) or field not in {"name", "capacity", "power"}:
        await state.clear()
        return

    raw_value = message.text.strip()

    async with session_factory() as session:
        item = await get_owned_equipment(session, equipment_id, message.from_user.id)
        if item is None:
            await state.clear()
            await message.answer("Оборудование не найдено.")
            return

        if field == "name":
            if not raw_value:
                await message.answer(
                    "Введите название оборудования.",
                    reply_markup=equipment_input_cancel_keyboard(equipment_id),
                )
                return
            if len(raw_value) > 255:
                await message.answer(
                    "Название слишком длинное. Используйте не больше 255 символов.",
                    reply_markup=equipment_input_cancel_keyboard(equipment_id),
                )
                return
            item.name = raw_value
        else:
            try:
                value = Decimal(raw_value.replace(",", "."))
            except InvalidOperation:
                await message.answer(
                    "Введите число, например <b>37</b> или <b>3.5</b>.",
                    reply_markup=equipment_input_cancel_keyboard(equipment_id),
                )
                return
            if value <= 0:
                await message.answer(
                    "Значение должно быть больше нуля.",
                    reply_markup=equipment_input_cancel_keyboard(equipment_id),
                )
                return

            if field == "capacity":
                item.capacity_l = value
            else:
                item.power_kw = value

        await session.commit()
        await session.refresh(item)

    await state.clear()
    await message.answer(
        f"✅ Изменения сохранены\n\n{equipment_card_text(item)}",
        reply_markup=equipment_card_keyboard(item.id),
    )


@router.callback_query(F.data.startswith("equipment:delete:"))
async def equipment_delete_handler(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    try:
        equipment_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    async with session_factory() as session:
        item = await get_owned_equipment(session, equipment_id, callback.from_user.id)

    if item is None:
        await render_equipment_list(callback, session_factory)
        return

    await callback.message.edit_text(
        f"🗑 <b>Удалить оборудование?</b>\n\n{equipment_short_label(item)}\n\n"
        "Это действие нельзя отменить.",
        reply_markup=equipment_delete_keyboard(item.id),
    )


@router.callback_query(F.data.startswith("equipment:delete-confirm:"))
async def equipment_delete_confirm_handler(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    try:
        equipment_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        return

    async with session_factory() as session:
        item = await get_owned_equipment(session, equipment_id, callback.from_user.id)
        if item is not None:
            await session.delete(item)
            await session.commit()

    await render_equipment_list(callback, session_factory)
