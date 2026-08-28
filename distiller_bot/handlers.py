from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .keyboards import back_to_menu_keyboard, main_menu_keyboard
from .models import User

router = Router()


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
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await ensure_user(message, session_factory)
    await message.answer(main_menu_text(), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def main_menu_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(main_menu_text(), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("menu:"))
async def section_placeholder_handler(callback: CallbackQuery) -> None:
    await callback.answer()

    section = (callback.data or "").removeprefix("menu:")
    titles = {
        "drinks": "🥃 Напитки",
        "recipes": "📖 Рецепты",
        "calculators": "🧮 Калькуляторы",
        "equipment": "⚙️ Оборудование",
    }
    title = titles.get(section)
    if title is None or callback.message is None:
        return

    await callback.message.edit_text(
        f"<b>{title}</b>\n\nРаздел готов к дальнейшей реализации MVP.",
        reply_markup=back_to_menu_keyboard(),
    )
