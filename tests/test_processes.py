from distiller_bot.models import Drink
from distiller_bot.processes import process_card_text, process_short_label


def make_process(*, name: str, stage: str) -> Drink:
    return Drink(user_id=1, name=name, current_stage=stage, status="active")


def test_process_card_escapes_user_text() -> None:
    process = make_process(name="<Моя брага>", stage="Этап <1>")

    text = process_card_text(process)

    assert "&lt;Моя брага&gt;" in text
    assert "Этап &lt;1&gt;" in text


def test_process_button_label_is_short_enough() -> None:
    process = make_process(name="Очень длинное название " * 10, stage="Очень длинный этап " * 10)

    label = process_short_label(process)

    assert len(label) <= 60
    assert label.endswith("…")
