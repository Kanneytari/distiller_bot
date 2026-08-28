from distiller_bot.models import Drink, DrinkEvent
from distiller_bot.processes import process_card_text


def make_process() -> Drink:
    return Drink(
        user_id=1,
        name="Брага",
        current_stage="Подготовка",
        status="active",
    )


def test_process_card_shows_selected_fermentable_in_composition() -> None:
    process = make_process()
    composition = DrinkEvent(
        drink_id=1,
        event_type="preparation_composition",
        title="Состав браги",
        data={
            "fermentable": "glucose",
            "fermentable_kg": "5.37",
            "water_l": "21.78",
            "volume_l": "25.00",
            "potential_abv": "12.0",
        },
    )
    setattr(process, "_latest_preparation_composition", composition)

    text = process_card_text(process)

    assert "🍬 <b>Состав браги:</b>" in text
    assert "Глюкоза · ⚖️ 5.37 кг" in text
    assert "Сырьё:" not in text
    assert "💧 Вода: 21.78 л · 🪣 Объём: 25 л" in text
    assert "📈 Потенциальная крепость: ~12%" in text
    assert "Сохранённый расчёт" not in text


def test_process_card_accepts_legacy_saved_calculation_as_sucrose_composition() -> None:
    process = make_process()
    legacy_calculation = DrinkEvent(
        drink_id=1,
        event_type="sugar_wash_calculation",
        title="Расчёт сахарной браги",
        data={
            "water_l": "21.94",
            "sugar_kg": "5.10",
            "volume_l": "25.00",
            "potential_abv": "12.0",
        },
    )
    setattr(process, "_latest_preparation_composition", legacy_calculation)

    text = process_card_text(process)

    assert "🍬 <b>Состав браги:</b>" in text
    assert "Сахар · ⚖️ 5.1 кг" in text
    assert "Сырьё:" not in text


def test_process_card_ignores_broken_preparation_composition() -> None:
    process = make_process()
    composition = DrinkEvent(
        drink_id=1,
        event_type="preparation_composition",
        title="Состав браги",
        data={"water_l": "not-a-number"},
    )
    setattr(process, "_latest_preparation_composition", composition)

    text = process_card_text(process)

    assert "Состав браги" not in text
