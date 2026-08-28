from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


DEFAULT_FERMENTABLE = "sucrose"
FERMENTABLE_VOLUME_L_PER_KG = Decimal("0.6")
HIGH_POTENTIAL_ABV = Decimal("18")

# Текущая MVP-модель для сахарозы использует 17 г/л на 1% потенциальной крепости.
# Для глюкозы и фруктозы масса скорректирована относительно теоретического выхода
# этанола: ~0.538 г/г для сахарозы и ~0.511 г/г для моносахаридов.
FERMENTABLES: dict[str, dict[str, str | Decimal]] = {
    "sucrose": {
        "label": "Сахар",
        "g_per_l_per_abv": Decimal("17"),
    },
    "glucose": {
        "label": "Глюкоза",
        "g_per_l_per_abv": Decimal("17.9"),
    },
    "fructose": {
        "label": "Фруктоза",
        "g_per_l_per_abv": Decimal("17.9"),
    },
}


@dataclass(frozen=True, slots=True)
class SugarWashResult:
    mode: str
    water_l: Decimal
    sugar_kg: Decimal
    volume_l: Decimal
    potential_abv: Decimal
    fermentable: str = DEFAULT_FERMENTABLE

    @property
    def fermentable_kg(self) -> Decimal:
        """Neutral name for the legacy sugar_kg field."""
        return self.sugar_kg

    @property
    def fermentable_label(self) -> str:
        return fermentable_label(self.fermentable)

    def as_event_data(self) -> dict[str, str]:
        coefficient = grams_per_l_per_abv(self.fermentable)
        return {
            "mode": self.mode,
            "fermentable": self.fermentable,
            "water_l": str(self.water_l),
            # sugar_kg и старые coefficient-ключи оставлены для обратной совместимости.
            "sugar_kg": str(self.sugar_kg),
            "fermentable_kg": str(self.sugar_kg),
            "volume_l": str(self.volume_l),
            "potential_abv": str(self.potential_abv),
            "g_per_l_per_abv": str(coefficient),
            "fermentable_volume_l_per_kg": str(FERMENTABLE_VOLUME_L_PER_KG),
            "sugar_g_per_l_per_abv": str(coefficient),
            "sugar_volume_l_per_kg": str(FERMENTABLE_VOLUME_L_PER_KG),
        }


def normalize_fermentable(value: object) -> str:
    key = str(value or DEFAULT_FERMENTABLE)
    return key if key in FERMENTABLES else DEFAULT_FERMENTABLE


def fermentable_label(fermentable: str) -> str:
    config = FERMENTABLES[normalize_fermentable(fermentable)]
    return str(config["label"])


def grams_per_l_per_abv(fermentable: str) -> Decimal:
    config = FERMENTABLES[normalize_fermentable(fermentable)]
    return Decimal(str(config["g_per_l_per_abv"]))


def result_from_event_data(data: dict[str, object] | None) -> SugarWashResult | None:
    if not data:
        return None

    raw_amount = data.get("fermentable_kg", data.get("sugar_kg"))
    if raw_amount is None:
        return None

    try:
        result = SugarWashResult(
            mode=str(data.get("mode", "check")),
            water_l=Decimal(str(data["water_l"])),
            sugar_kg=Decimal(str(raw_amount)),
            volume_l=Decimal(str(data["volume_l"])),
            potential_abv=Decimal(str(data["potential_abv"])),
            fermentable=normalize_fermentable(data.get("fermentable")),
        )
    except (KeyError, InvalidOperation, TypeError):
        return None

    values = (result.water_l, result.sugar_kg, result.volume_l, result.potential_abv)
    return result if all(value.is_finite() and value > 0 for value in values) else None


def round_amount(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_abv(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def calculate_by_volume(
    volume_l: Decimal,
    potential_abv: Decimal,
    fermentable: str = DEFAULT_FERMENTABLE,
) -> SugarWashResult:
    fermentable = normalize_fermentable(fermentable)
    amount_kg = (
        volume_l * potential_abv * grams_per_l_per_abv(fermentable) / Decimal("1000")
    )
    water_l = volume_l - amount_kg * FERMENTABLE_VOLUME_L_PER_KG
    return SugarWashResult(
        mode="volume",
        water_l=round_amount(water_l),
        sugar_kg=round_amount(amount_kg),
        volume_l=round_amount(volume_l),
        potential_abv=round_abv(potential_abv),
        fermentable=fermentable,
    )


def calculate_by_sugar(
    sugar_kg: Decimal,
    potential_abv: Decimal,
    fermentable: str = DEFAULT_FERMENTABLE,
) -> SugarWashResult:
    fermentable = normalize_fermentable(fermentable)
    volume_l = (
        sugar_kg * Decimal("1000")
        / (potential_abv * grams_per_l_per_abv(fermentable))
    )
    water_l = volume_l - sugar_kg * FERMENTABLE_VOLUME_L_PER_KG
    return SugarWashResult(
        mode="sugar",
        water_l=round_amount(water_l),
        sugar_kg=round_amount(sugar_kg),
        volume_l=round_amount(volume_l),
        potential_abv=round_abv(potential_abv),
        fermentable=fermentable,
    )


def calculate_from_composition(
    water_l: Decimal,
    sugar_kg: Decimal,
    fermentable: str = DEFAULT_FERMENTABLE,
) -> SugarWashResult:
    fermentable = normalize_fermentable(fermentable)
    volume_l = water_l + sugar_kg * FERMENTABLE_VOLUME_L_PER_KG
    potential_abv = (
        sugar_kg * Decimal("1000")
        / (volume_l * grams_per_l_per_abv(fermentable))
    )
    return SugarWashResult(
        mode="check",
        water_l=round_amount(water_l),
        sugar_kg=round_amount(sugar_kg),
        volume_l=round_amount(volume_l),
        potential_abv=round_abv(potential_abv),
        fermentable=fermentable,
    )


def recalculate_fermentable(result: SugarWashResult, fermentable: str) -> SugarWashResult:
    """Keep target volume and potential ABV, recalculate ingredient quantities."""
    return calculate_by_volume(result.volume_l, result.potential_abv, fermentable)


def recalculate_amount(result: SugarWashResult, amount_kg: Decimal) -> SugarWashResult:
    """Keep water fixed, recalculate volume and potential ABV."""
    return calculate_from_composition(result.water_l, amount_kg, result.fermentable)


def recalculate_water(result: SugarWashResult, water_l: Decimal) -> SugarWashResult:
    """Keep fermentable amount fixed, recalculate volume and potential ABV."""
    return calculate_from_composition(water_l, result.sugar_kg, result.fermentable)


def recalculate_volume(result: SugarWashResult, volume_l: Decimal) -> SugarWashResult:
    """Keep potential ABV fixed, recalculate fermentable amount and water."""
    return calculate_by_volume(volume_l, result.potential_abv, result.fermentable)


def recalculate_abv(result: SugarWashResult, potential_abv: Decimal) -> SugarWashResult:
    """Keep target volume fixed, recalculate fermentable amount and water."""
    return calculate_by_volume(result.volume_l, potential_abv, result.fermentable)


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def result_text(result: SugarWashResult) -> str:
    text = (
        "🧮 <b>Расчёт браги</b>\n\n"
        f"🍬 Сырьё: <b>{result.fermentable_label}</b>\n"
        f"⚖️ Количество: <b>{format_decimal(result.sugar_kg)} кг</b>\n"
        f"💧 Вода: <b>{format_decimal(result.water_l)} л</b>\n"
        f"🪣 Ориентировочный объём: <b>{format_decimal(result.volume_l)} л</b>\n"
        f"📈 Потенциальная крепость: <b>~{format_decimal(result.potential_abv)}%</b>\n\n"
        "Расчёт ориентировочный. Фактическая крепость зависит от дрожжей "
        "и полноты сбраживания."
    )
    if result.potential_abv > HIGH_POTENTIAL_ABV:
        text += (
            "\n\n⚠️ Сахарная нагрузка высокая. Не все дрожжи смогут полностью "
            "сбродить такую концентрацию сырья."
        )
    return text
