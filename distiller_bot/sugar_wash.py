from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


SUGAR_G_PER_L_PER_ABV = Decimal("17")
SUGAR_VOLUME_L_PER_KG = Decimal("0.6")
HIGH_POTENTIAL_ABV = Decimal("18")


@dataclass(frozen=True, slots=True)
class SugarWashResult:
    mode: str
    water_l: Decimal
    sugar_kg: Decimal
    volume_l: Decimal
    potential_abv: Decimal

    def as_event_data(self) -> dict[str, str]:
        return {
            "mode": self.mode,
            "water_l": str(self.water_l),
            "sugar_kg": str(self.sugar_kg),
            "volume_l": str(self.volume_l),
            "potential_abv": str(self.potential_abv),
            "sugar_g_per_l_per_abv": str(SUGAR_G_PER_L_PER_ABV),
            "sugar_volume_l_per_kg": str(SUGAR_VOLUME_L_PER_KG),
        }


def round_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_abv(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def calculate_by_volume(volume_l: Decimal, potential_abv: Decimal) -> SugarWashResult:
    sugar_kg = volume_l * potential_abv * SUGAR_G_PER_L_PER_ABV / Decimal("1000")
    water_l = volume_l - sugar_kg * SUGAR_VOLUME_L_PER_KG
    return SugarWashResult(
        mode="volume",
        water_l=round_amount(water_l),
        sugar_kg=round_amount(sugar_kg),
        volume_l=round_amount(volume_l),
        potential_abv=round_abv(potential_abv),
    )


def calculate_by_sugar(sugar_kg: Decimal, potential_abv: Decimal) -> SugarWashResult:
    volume_l = (
        sugar_kg * Decimal("1000") / (potential_abv * SUGAR_G_PER_L_PER_ABV)
    )
    water_l = volume_l - sugar_kg * SUGAR_VOLUME_L_PER_KG
    return SugarWashResult(
        mode="sugar",
        water_l=round_amount(water_l),
        sugar_kg=round_amount(sugar_kg),
        volume_l=round_amount(volume_l),
        potential_abv=round_abv(potential_abv),
    )


def calculate_from_composition(water_l: Decimal, sugar_kg: Decimal) -> SugarWashResult:
    volume_l = water_l + sugar_kg * SUGAR_VOLUME_L_PER_KG
    potential_abv = (
        sugar_kg * Decimal("1000") / (volume_l * SUGAR_G_PER_L_PER_ABV)
    )
    return SugarWashResult(
        mode="check",
        water_l=round_amount(water_l),
        sugar_kg=round_amount(sugar_kg),
        volume_l=round_amount(volume_l),
        potential_abv=round_abv(potential_abv),
    )


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def result_text(result: SugarWashResult) -> str:
    text = (
        "🧮 <b>Расчёт сахарной браги</b>\n\n"
        f"💧 Вода: <b>{format_decimal(result.water_l)} л</b>\n"
        f"🍬 Сахар: <b>{format_decimal(result.sugar_kg)} кг</b>\n"
        f"🪣 Ориентировочный объём: <b>{format_decimal(result.volume_l)} л</b>\n"
        f"📈 Потенциальная крепость: <b>~{format_decimal(result.potential_abv)}%</b>\n\n"
        "Расчёт ориентировочный. Фактическая крепость зависит от дрожжей "
        "и полноты сбраживания."
    )
    if result.potential_abv > HIGH_POTENTIAL_ABV:
        text += (
            "\n\n⚠️ Сахарная нагрузка высокая. Не все дрожжи смогут полностью "
            "сбродить такую концентрацию сахара."
        )
    return text
