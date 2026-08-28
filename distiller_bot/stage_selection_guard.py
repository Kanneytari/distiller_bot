from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .keyboards import process_stage_keyboard


router = Router()

BLOCKED_STAGE_CALLBACKS = {
    "process:stage:custom",
    "process:stage:distillation",
    "process:stage:dilution",
    "process:stage:aging",
    "process:stage:ready",
}


@router.callback_query(F.data.in_(BLOCKED_STAGE_CALLBACKS))
async def blocked_stage_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == "process:stage:distillation":
        alert_text = "Перегонка теперь разделена на первую и вторую. Выберите нужный этап."
    else:
        alert_text = "Выберите один из доступных этапов."

    await callback.answer(alert_text, show_alert=True)
    if callback.message is None:
        return

    data = await state.get_data()
    mode = data.get("mode")
    if mode not in {"create", "change"}:
        return

    process_id = data.get("process_id")
    keyboard_process_id = (
        process_id if mode == "change" and isinstance(process_id, int) else None
    )
    await callback.message.edit_text(
        "Выберите один из доступных этапов.",
        reply_markup=process_stage_keyboard(keyboard_process_id),
    )
