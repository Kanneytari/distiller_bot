from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .equipment import router as equipment_router
from .keyboards import back_to_menu_keyboard, main_menu_keyboard
from .models import User
from .processes import router as processes_router

router = Router()
router.include_router(processes_router)
router.include_router(equipment_router)


async def ensure_user(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            session.add(
                User(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                )
            )
            await session.commit()
            return

        user.username = message.from_user.username
        user.first_name = message.from_user.first_name
        await session.commit()


def main_menu_text() -> str:
    return "🥃 <b>Distiller Bot</b>\n\nЧто хотите сделать?"


@router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    await ensure_user(message, session_factory)
    await message.answer(main_menu_text(), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def main_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text(main_menu_text(), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.in_({"menu:recipes", "menu:calculators"}))
async def section_placeholder_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()

    section = (callback.data or "").removeprefix("menu:")
    titles = {
        "recipes": "📖 Рецепты",
        "calculators": "🧮 Калькуляторы",
    }
    title = titles.get(section)
    if title is None or callback.message is None:
        return

    await callback.message.edit_text(
        f"<b>{title}</b>\n\nРаздел готов к дальнейшей реализации MVP.",
        reply_markup=back_to_menu_keyboard(),
    )
