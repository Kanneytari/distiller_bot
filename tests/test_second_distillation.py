from decimal import Decimal

import distiller_bot.second_distillation_integration  # noqa: F401
from distiller_bot.calculator_keyboards import calculators_menu_keyboard
from distiller_bot.keyboards import process_card_keyboard
from distiller_bot.process_stages import stage_actions_for_stage
from distiller_bot.second_distillation import (
    SpiritCut,
    charge_recommendation,
    cuts_guidance_text,
    dilution_result,
    grouped_summary,
    heads_guidance,
    summarize_cuts,
)
from distiller_bot.second_distillation_keyboards import second_distillation_calculators_keyboard


def button_pairs(markup) -> list[tuple[str, str | None]]:
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def make_cut(cut_id: int, volume: str, abv: str, fraction: str) -> SpiritCut:
    value = Decimal(abv)
    volume_l = Decimal(volume)
    return SpiritCut(
        cut_id=cut_id,
        volume_l=volume_l,
        observed_abv=value,
        temperature_c=Decimal("20"),
        corrected_abv=value,
        absolute_alcohol_l=(volume_l * value / Decimal("100")).quantize(Decimal("0.01")),
        fraction=fraction,
    )


def test_dilution_to_30_percent() -> None:
    water_l, final_volume_l, aa_l = dilution_result(
        Decimal("6.8"),
        Decimal("35.9"),
        Decimal("30"),
    )

    assert water_l == Decimal("1.34")
    assert final_volume_l == Decimal("8.14")
    assert aa_l == Decimal("2.44")


def test_beginner_charge_guidance_recommends_25_to_30_percent() -> None:
    guidance = charge_recommendation(Decimal("35"))

    assert "25-30%" in guidance
    assert "Удобная стартовая цель - 30%" in guidance
    assert "рекомендуемом" in charge_recommendation(Decimal("28"))


def test_charge_over_40_percent_gets_warning() -> None:
    assert "выше 40%" in charge_recommendation(Decimal("45"))


def test_heads_guidance_uses_five_to_ten_percent_of_absolute_alcohol() -> None:
    low, high = heads_guidance(Decimal("2.44"))

    assert low == Decimal("0.12")
    assert high == Decimal("0.24")


def test_heads_and_tails_guidance_exposes_beginner_thresholds() -> None:
    text = cuts_guidance_text(Decimal("2.44"))

    assert "5-10%" in text
    assert "50%" in text
    assert "40%" in text
    assert "не обязательные границы" in text


def test_cut_summary_is_weighted_by_absolute_alcohol() -> None:
    cuts = [
        make_cut(1, "1", "80", "hearts"),
        make_cut(2, "1", "60", "hearts"),
    ]

    volume_l, average_abv, aa_l = summarize_cuts(cuts)

    assert volume_l == Decimal("2.00")
    assert aa_l == Decimal("1.40")
    assert average_abv == Decimal("70.0")


def test_grouped_summary_keeps_heads_hearts_and_tails_separate() -> None:
    cuts = [
        make_cut(1, "0.2", "85", "heads"),
        make_cut(2, "1.0", "70", "hearts"),
        make_cut(3, "0.5", "40", "tails"),
    ]

    grouped = grouped_summary(cuts)

    assert grouped["heads"][0] == Decimal("0.20")
    assert grouped["hearts"][0] == Decimal("1.00")
    assert grouped["tails"][0] == Decimal("0.50")


def test_second_distillation_process_card_routes_to_dedicated_workflow() -> None:
    actions = [
        (action.key, action.label)
        for action in stage_actions_for_stage("Вторая перегонка")
    ]
    buttons = button_pairs(process_card_keyboard(42, actions))

    assert ("🫙 Отборы", "process:second-distillation:42") in buttons
    assert (
        "🧮 Калькуляторы",
        "process:second-distillation-calculators:42",
    ) in buttons


def test_global_calculators_include_second_distillation() -> None:
    buttons = button_pairs(calculators_menu_keyboard())

    assert ("⚗️ Вторая перегонка", "calculators:second-distillation") in buttons


def test_second_distillation_calculators_include_required_tools() -> None:
    texts = [text for text, _callback in button_pairs(second_distillation_calculators_keyboard())]

    assert texts[:5] == [
        "💧 Разбавление спирта",
        "✂️ Головы и хвосты",
        "🌡 Поправка спиртометра",
        "💧 Абсолютный спирт",
        "🧪 Средняя крепость",
    ]
