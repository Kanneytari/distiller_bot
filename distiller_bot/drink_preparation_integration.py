from . import drink_preparation as drink_preparation_module
from . import processes as processes_module
from .process_stages import stage_type_for_title


processes_module.STAGE_QUICK_MEASUREMENTS["drink_preparation"] = []
processes_module.STAGE_MEASUREMENT_ORDER["drink_preparation"] = []

_original_get_owned_process = processes_module.get_owned_process
_original_change_process_stage = processes_module.change_process_stage
_original_process_card_text = processes_module.process_card_text


async def attach_drink_preparation_context(session, process):
    if process is None or stage_type_for_title(process.current_stage) != "drink_preparation":
        return process
    source = await drink_preparation_module.get_second_distillation_body(session, process.id)
    result = await drink_preparation_module.get_saved_result(session, process.id)
    setattr(process, "_second_distillation_body", source)
    setattr(process, "_drink_preparation_result", result)
    return process


async def get_owned_process_with_drink_preparation(session, process_id: int, telegram_id: int):
    process = await _original_get_owned_process(session, process_id, telegram_id)
    return await attach_drink_preparation_context(session, process)


async def change_process_stage_with_drink_preparation(session, *, process, stage: str):
    process = await _original_change_process_stage(session, process=process, stage=stage)
    return await attach_drink_preparation_context(session, process)


def drink_preparation_context_block(process) -> str | None:
    source = getattr(process, "_second_distillation_body", None)
    result = getattr(process, "_drink_preparation_result", None)
    if source is None and result is None:
        return None

    lines: list[str] = []
    if source is not None:
        lines.extend(
            [
                "🥃 <b>Результат второй перегонки:</b>",
                f"🟢 Тело: {drink_preparation_module.format_decimal(source.volume_l)} л · "
                f"📈 {drink_preparation_module.format_decimal(source.abv)}%",
                f"💧 Абсолютный спирт: {drink_preparation_module.format_decimal(source.absolute_alcohol_l)} л",
            ]
        )
    if result is not None:
        if lines:
            lines.append("")
        lines.extend(
            [
                "🍶 <b>Подготовленный напиток:</b>",
                f"💧 {drink_preparation_module.format_decimal(result.final_volume_l)} л · "
                f"📈 {drink_preparation_module.format_decimal(result.target_abv)}%",
                f"🚰 Добавлено воды: {drink_preparation_module.format_decimal(result.water_l)} л",
            ]
        )
    return "\n".join(lines)


def process_card_text_with_drink_preparation(
    process,
    latest_measurement=None,
    latest_note=None,
) -> str:
    text = _original_process_card_text(process, latest_measurement, latest_note)
    if stage_type_for_title(process.current_stage) != "drink_preparation":
        return text

    context_block = drink_preparation_context_block(process)
    if context_block is None:
        return text

    latest_composition = getattr(process, "_latest_preparation_composition", None)
    composition_text = processes_module.preparation_composition_display(latest_composition)
    if composition_text is not None:
        composition_block = f"🍬 <b>Состав браги:</b>\n{composition_text}"
        return text.replace(
            composition_block,
            f"{composition_block}\n\n{context_block}",
            1,
        )

    parts = text.split("\n\n", 2)
    if len(parts) >= 2:
        remainder = f"\n\n{parts[2]}" if len(parts) == 3 else ""
        return f"{parts[0]}\n\n{parts[1]}\n\n{context_block}{remainder}"
    return f"{text}\n\n{context_block}"


processes_module.get_owned_process = get_owned_process_with_drink_preparation
processes_module.change_process_stage = change_process_stage_with_drink_preparation
processes_module.process_card_text = process_card_text_with_drink_preparation
