from decimal import Decimal

import distiller_bot.second_distillation_integration  # noqa: F401
from distiller_bot.models import Drink
from distiller_bot.second_distillation import SpiritCharge
from distiller_bot.second_distillation_integration import (
    process_card_text_with_first_source,
    second_distillation_text_with_source,
)


def charge(volume: str, abv: str, aa: str, source: str) -> SpiritCharge:
    return SpiritCharge(
        volume_l=Decimal(volume),
        abv=Decimal(abv),
        absolute_alcohol_l=Decimal(aa),
        source=source,
    )


def process(stage: str = "Вторая перегонка") -> Drink:
    return Drink(user_id=1, name="Самогон", current_stage=stage, status="active")


def test_second_distillation_screen_shows_first_distillation_source() -> None:
    first_charge = charge("6.80", "35.9", "2.44", "first_distillation")
    current_charge = charge("8.14", "30.0", "2.44", "manual")

    text = second_distillation_text_with_source(first_charge, current_charge, [])

    assert "🥃 <b>Результат первой перегонки:</b>" in text
    assert "💧 Спирт-сырец: 6.8 л · 📈 35.9%" in text
    assert "💧 Абсолютный спирт: 2.44 л" in text
    assert "🛢 Загрузка: 8.14 л · 30% · АС 2.44 л" in text


def test_second_distillation_screen_stays_unchanged_without_first_result() -> None:
    current_charge = charge("8.14", "30.0", "2.44", "manual")

    text = second_distillation_text_with_source(None, current_charge, [])

    assert "Результат первой перегонки" not in text
    assert "🛢 Загрузка: 8.14 л · 30% · АС 2.44 л" in text


def test_main_process_card_shows_first_distillation_summary_on_second_stage() -> None:
    item = process()
    setattr(
        item,
        "_first_distillation_charge",
        charge("6.80", "35.9", "2.44", "first_distillation"),
    )

    text = process_card_text_with_first_source(item)

    assert "Этап: ⚗️ Вторая перегонка" in text
    assert "🥃 <b>Результат первой перегонки:</b>" in text
    assert "💧 Спирт-сырец: 6.8 л · 📈 35.9%" in text
    assert "💧 Абсолютный спирт: 2.44 л" in text


def test_main_process_card_hides_summary_without_first_result() -> None:
    text = process_card_text_with_first_source(process())

    assert "Результат первой перегонки" not in text
