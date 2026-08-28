from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from .second_distillation import (
    SecondDistillationState,
    calculator_context,
    owned_second_distillation,
)
from .second_distillation_keyboards import second_distillation_input_keyboard

router = Router()

BLEND_INPUT_TEXT = (
    "🧪 <b>Средняя крепость</b>\n\n"
    "Введите объём и крепость каждой части с новой строки.\n"
    "Формат: <code>объём крепость</code>\n\n"
    "Например:\n"
    "<code>2,5 48\n"
    "1,5 32</code>"
)


@router.callback_query(
    F.data.regexp(
        r"^(process:second-distillation-calc:\d+|calculators:second-distillation):blend$"
    )
)
async def blend_calculator_start_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    context = calculator_context(callback.data or "")
    if context is None:
        return
    process_id, _mode = context

    await state.clear()
    if process_id is not None:
        async with session_factory() as session:
            process = await owned_second_distillation(
                session,
                process_id,
                callback.from_user.id,
            )
        if process is None:
            return

    await state.set_state(SecondDistillationState.waiting_calc_value)
    await state.update_data(
        process_id=process_id,
        calc_mode="blend",
        calc_step="pairs",
    )
    await callback.message.edit_text(
        BLEND_INPUT_TEXT,
        reply_markup=second_distillation_input_keyboard(process_id),
    )
