from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MAX_BRIX = Decimal("50")


@dataclass(frozen=True, slots=True)
class RefractometerResult:
    initial_brix: Decimal
    current_brix: Decimal
    original_sg: Decimal
    corrected_sg: Decimal
    potential_abv: Decimal
    current_abv: Decimal


def round_sg(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def round_abv(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def brix_to_sg(brix: Decimal) -> Decimal:
    if not Decimal("0") <= brix <= MAX_BRIX:
        raise ValueError("Brix must be between 0 and 50")
    return Decimal("1") + brix / (
        Decimal("258.6") - (brix / Decimal("258.2")) * Decimal("227.1")
    )


def corrected_final_sg(initial_brix: Decimal, current_brix: Decimal) -> Decimal:
    if not Decimal("0") < initial_brix <= MAX_BRIX:
        raise ValueError("Initial Brix must be between 0 and 50")
    if not Decimal("0") <= current_brix <= initial_brix:
        raise ValueError("Current Brix must be between 0 and initial Brix")
    if current_brix == initial_brix:
        return brix_to_sg(initial_brix)

    return (
        Decimal("1")
        + Decimal("0.00001335") * initial_brix**2
        - Decimal("0.00003239") * initial_brix * current_brix
        + Decimal("0.00002916") * current_brix**2
        - Decimal("0.002421") * initial_brix
        + Decimal("0.006219") * current_brix
    )


def abv_from_gravity(original_sg: Decimal, final_sg: Decimal) -> Decimal:
    if original_sg <= final_sg:
        return Decimal("0")
    value = (
        Decimal("76.08")
        * (original_sg - final_sg)
        / (Decimal("1.775") - original_sg)
        * (final_sg / Decimal("0.794"))
    )
    return max(value, Decimal("0"))


def calculate_refractometer(
    initial_brix: Decimal,
    current_brix: Decimal,
) -> RefractometerResult:
    original_sg_raw = brix_to_sg(initial_brix)
    corrected_sg_raw = corrected_final_sg(initial_brix, current_brix)

    return RefractometerResult(
        initial_brix=initial_brix,
        current_brix=current_brix,
        original_sg=round_sg(original_sg_raw),
        corrected_sg=round_sg(corrected_sg_raw),
        potential_abv=round_abv(abv_from_gravity(original_sg_raw, Decimal("1.000"))),
        current_abv=round_abv(abv_from_gravity(original_sg_raw, corrected_sg_raw)),
    )
