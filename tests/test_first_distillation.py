from decimal import Decimal

from distiller_bot.first_distillation import absolute_alcohol_l, result_from_event, result_text
from distiller_bot.models import DrinkEvent
from distiller_bot.process_stages import stage_type_for_title


def test_first_and_second_distillation_are_distinct_stages() -> None:
    assert stage_type_for_title("Первая перегонка") == "first_distillation"
    assert stage_type_for_title("Вторая перегонка") == "second_distillation"


def test_absolute_alcohol_is_recalculated_from_volume_and_strength() -> None:
    assert absolute_alcohol_l(Decimal("7.5"), Decimal("32")) == Decimal("2.40")
    assert absolute_alcohol_l(Decimal("8"), Decimal("35")) == Decimal("2.80")


def test_first_distillation_result_event_is_rendered() -> None:
    event = DrinkEvent(
        drink_id=1,
        event_type="first_distillation_result",
        title="Результат первой перегонки",
        data={
            "low_wines_volume_l": "7.5",
            "low_wines_abv": "32",
            "absolute_alcohol_l": "2.4",
        },
    )

    result = result_from_event(event)
    text = result_text(result)

    assert result == (Decimal("7.5"), Decimal("32"))
    assert "🥃 Спирт-сырец: <b>7.5 л</b>" in text
    assert "📈 Крепость: <b>32%</b>" in text
    assert "💧 Абсолютный спирт: <b>~2.4 л</b>" in text


def test_invalid_saved_result_is_ignored() -> None:
    event = DrinkEvent(
        drink_id=1,
        event_type="first_distillation_result",
        title="Результат первой перегонки",
        data={"low_wines_volume_l": "NaN", "low_wines_abv": "32"},
    )

    assert result_from_event(event) is None
