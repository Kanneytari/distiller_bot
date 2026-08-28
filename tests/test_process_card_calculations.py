from distiller_bot.models import Drink, DrinkEvent
from distiller_bot.processes import process_card_text


def make_process() -> Drink:
    return Drink(
        user_id=1,
        name="Сахарная брага",
        current_stage="Подготовка",
        status="active",
    )


def test_process_card_shows_latest_saved_sugar_wash_calculation() -> None:
    process = make_process()
    calculation = DrinkEvent(
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
    setattr(process, "_latest_sugar_wash_calculation", calculation)

    text = process_card_text(process)

    assert "🧮 <b>Сохранённый расчёт:</b>" in text
    assert "💧 Вода: 21.94 л · 🍬 Сахар: 5.1 кг" in text
    assert "🪣 Объём: 25 л · 📈 Потенциальная крепость: ~12%" in text


def test_process_card_ignores_broken_saved_calculation() -> None:
    process = make_process()
    calculation = DrinkEvent(
        drink_id=1,
        event_type="sugar_wash_calculation",
        title="Расчёт сахарной браги",
        data={"water_l": "not-a-number"},
    )
    setattr(process, "_latest_sugar_wash_calculation", calculation)

    text = process_card_text(process)

    assert "Сохранённый расчёт" not in text
