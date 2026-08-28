from decimal import Decimal

import distiller_bot.second_distillation_integration  # noqa: F401
from distiller_bot.second_distillation import SpiritCharge
from distiller_bot.second_distillation_integration import second_distillation_text_with_source


def charge(volume: str, abv: str, aa: str, source: str) -> SpiritCharge:
    return SpiritCharge(
        volume_l=Decimal(volume),
        abv=Decimal(abv),
        absolute_alcohol_l=Decimal(aa),
        source=source,
    )


def test_second_distillation_screen_shows_first_distillation_source() -> None:
    first_charge = charge("6.80", "35.9", "2.44", "first_distillation")
    current_charge = charge("8.14", "30.0", "2.44", "manual")

    text = second_distillation_text_with_source(first_charge, current_charge, [])

    assert "🥃 <b>Спирт-сырец после первой перегонки</b>" in text
    assert "💧 Объём: <b>6.8 л</b>" in text
    assert "📈 Средняя крепость: <b>35.9%</b>" in text
    assert "💧 Абсолютный спирт: <b>2.44 л</b>" in text
    assert "🛢 Загрузка: 8.14 л · 30% · АС 2.44 л" in text


def test_second_distillation_screen_stays_unchanged_without_first_result() -> None:
    current_charge = charge("8.14", "30.0", "2.44", "manual")

    text = second_distillation_text_with_source(None, current_charge, [])

    assert "Спирт-сырец после первой перегонки" not in text
    assert "🛢 Загрузка: 8.14 л · 30% · АС 2.44 л" in text
