from . import processes as processes_module
from . import second_distillation as second_distillation_module
from .keyboards import PROCESS_ACTION_CALLBACKS
from .process_stages import stage_type_for_title


PROCESS_ACTION_CALLBACKS.update(
    {
        "second_distillation": "process:second-distillation:{process_id}",
        "second_distillation_calculators": "process:second-distillation-calculators:{process_id}",
    }
)


_original_get_owned_process = processes_module.get_owned_process
_original_change_process_stage = processes_module.change_process_stage
_original_process_card_text = processes_module.process_card_text


def first_distillation_source_block(first_charge) -> str | None:
    if first_charge is None:
        return None
    return (
        "🥃 <b>Результат первой перегонки:</b>\n"
        f"💧 Спирт-сырец: {second_distillation_module.format_decimal(first_charge.volume_l)} л · "
        f"📈 {second_distillation_module.format_decimal(first_charge.abv)}%\n"
        f"💧 Абсолютный спирт: {second_distillation_module.format_decimal(first_charge.absolute_alcohol_l)} л"
    )


async def attach_first_distillation_source(session, process):
    if process is None or stage_type_for_title(process.current_stage) != "second_distillation":
        return process
    first_charge = await second_distillation_module.get_first_distillation_source(
        session,
        process.id,
    )
    setattr(process, "_first_distillation_charge", first_charge)
    return process


async def get_owned_process_with_first_source(session, process_id: int, telegram_id: int):
    process = await _original_get_owned_process(session, process_id, telegram_id)
    return await attach_first_distillation_source(session, process)


async def change_process_stage_with_first_source(session, *, process, stage: str):
    process = await _original_change_process_stage(session, process=process, stage=stage)
    return await attach_first_distillation_source(session, process)


def process_card_text_with_first_source(
    process,
    latest_measurement=None,
    latest_note=None,
) -> str:
    text = _original_process_card_text(process, latest_measurement, latest_note)
    if stage_type_for_title(process.current_stage) != "second_distillation":
        return text

    source_block = first_distillation_source_block(
        getattr(process, "_first_distillation_charge", None)
    )
    if source_block is None:
        return text

    latest_composition = getattr(process, "_latest_preparation_composition", None)
    composition_text = processes_module.preparation_composition_display(latest_composition)
    if composition_text is not None:
        composition_block = f"🍬 <b>Состав браги:</b>\n{composition_text}"
        return text.replace(
            composition_block,
            f"{composition_block}\n\n{source_block}",
            1,
        )

    parts = text.split("\n\n", 2)
    if len(parts) >= 2:
        remainder = f"\n\n{parts[2]}" if len(parts) == 3 else ""
        return f"{parts[0]}\n\n{parts[1]}\n\n{source_block}{remainder}"
    return f"{text}\n\n{source_block}"


processes_module.get_owned_process = get_owned_process_with_first_source
processes_module.change_process_stage = change_process_stage_with_first_source
processes_module.process_card_text = process_card_text_with_first_source


def second_distillation_text_with_source(first_charge, charge, cuts) -> str:
    base_text = second_distillation_module.second_distillation_text(charge, cuts)
    source_block = first_distillation_source_block(first_charge)
    if source_block is None:
        return base_text

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
