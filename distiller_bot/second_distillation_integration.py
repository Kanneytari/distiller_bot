from . import second_distillation as second_distillation_module
from .keyboards import PROCESS_ACTION_CALLBACKS


PROCESS_ACTION_CALLBACKS.update(
    {
        "second_distillation": "process:second-distillation:{process_id}",
        "second_distillation_calculators": "process:second-distillation-calculators:{process_id}",
    }
)


def second_distillation_text_with_source(first_charge, charge, cuts) -> str:
    base_text = second_distillation_module.second_distillation_text(charge, cuts)
    if first_charge is None:
        return base_text

    source_block = (
        "🥃 <b>Спирт-сырец после первой перегонки</b>\n"
        f"💧 Объём: <b>{second_distillation_module.format_decimal(first_charge.volume_l)} л</b>\n"
        f"📈 Средняя крепость: <b>{second_distillation_module.format_decimal(first_charge.abv)}%</b>\n"
        f"💧 Абсолютный спирт: <b>{second_distillation_module.format_decimal(first_charge.absolute_alcohol_l)} л</b>"
    )

    header = "⚗️ <b>Вторая перегонка</b>\n\n"
    if base_text.startswith(header):
        return header + source_block + "\n\n" + base_text[len(header) :]
    return source_block + "\n\n" + base_text


async def show_second_distillation_with_source(
    callback,
    state,
    session_factory,
    process_id: int,
) -> None:
    if callback.message is None:
        return

    async with session_factory() as session:
        process = await second_distillation_module.owned_second_distillation(
            session,
            process_id,
            callback.from_user.id,
        )
        if process is None:
            await state.clear()
            await second_distillation_module.render_process_list(callback, session_factory)
            return

        first_charge = await second_distillation_module.get_first_distillation_source(
            session,
            process_id,
        )
        charge = await second_distillation_module.get_effective_charge(session, process_id)
        cuts = await second_distillation_module.get_cuts(session, process_id)

    await state.clear()
    await callback.message.edit_text(
        second_distillation_text_with_source(first_charge, charge, cuts),
        reply_markup=second_distillation_module.second_distillation_keyboard(process_id),
    )


second_distillation_module.show_second_distillation = show_second_distillation_with_source
