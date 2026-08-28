# Source coefficients and model: OIML R 22 international alcoholometric tables.
# The alcoholometer correction implemented here assumes a soda-lime glass
# instrument graduated at the 20 C reference temperature.

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

REFERENCE_TEMPERATURE_C = Decimal("20")
MIN_TEMPERATURE_C = Decimal("-20")
MAX_TEMPERATURE_C = Decimal("40")

_A = (9.982012300e2,-1.929769495e2,3.891238958e2,-1.668103923e3,1.352215441e4,-8.829278388e4,3.062874042e5,-6.138381234e5,7.470172998e5,-5.478461354e5,2.234460334e5,-3.903285426e4)
_B = (-2.0618513e-1,-5.2682542e-3,3.6130013e-5,-3.8957702e-7,7.1693540e-9,-9.9739231e-11)
_C = (
(1.693443461530087e-1,-1.046914743455169e1,7.196353469546523e1,-7.047478054272792e2,3.924090430035045e3,-1.210164659068747e4,2.248646550400788e4,-2.605562982188164e4,1.852373922069467e4,-7.420201433430137e3,1.285617841998974e3),
(-1.193013005057010e-2,2.517399633803461e-1,-2.170575700536993,1.353034988843029e1,-5.029988758547014e1,1.096355666577570e2,-1.422753946421155e2,1.080435942856230e2,-4.414153236817392e1,7.442971530188783),
(-6.802995733503803e-4,1.876837790289664e-2,-2.002561813734156e-1,1.022992966719220,-2.895696483903638,4.810060584300675,-4.672147440794683,2.458043105903461,-5.411227621436812e-1),
(4.075376675622027e-6,-8.763058573471110e-6,6.515031360099368e-6,-1.515784836987210e-6),
(-2.788074354782409e-8,1.345612883493354e-8),
)

def _density(p: float, t: float) -> float:
    dt = t - 20.0
    value = sum(c * p**power for power, c in enumerate(_A))
    value += sum(c * dt ** (power + 1) for power, c in enumerate(_B))
    for t_power, coefficients in enumerate(_C, start=1):
        value += sum(c * p ** (p_power + 1) * dt**t_power for p_power, c in enumerate(coefficients))
    return value

def _q_from_p(p: float) -> float:
    return p * _density(p, 20.0) / _density(1.0, 20.0)

def _bisect(function) -> float:
    low, high = 0.0, 1.0
    low_value, high_value = function(low), function(high)
    if low_value == 0:
        return low
    if high_value == 0:
        return high
    if low_value * high_value > 0:
        raise ValueError("Value is outside the alcoholometric model range")
    for _ in range(80):
        middle = (low + high) / 2.0
        middle_value = function(middle)
        if low_value * middle_value <= 0:
            high = middle
        else:
            low = middle
            low_value = middle_value
    return (low + high) / 2.0

def _p_from_q(q: float) -> float:
    return _bisect(lambda p: _q_from_p(p) - q)

def correct_alcoholmeter_abv(observed_abv: Decimal, temperature_c: Decimal) -> Decimal:
    if not Decimal("0") <= observed_abv <= Decimal("100"):
        raise ValueError("Alcoholmeter reading must be between 0 and 100 %")
    if not MIN_TEMPERATURE_C <= temperature_c <= MAX_TEMPERATURE_C:
        raise ValueError("Temperature must be between -20 and 40 C")
    q = float(observed_abv / Decimal("100"))
    t = float(temperature_c)
    density_20 = _density(_p_from_q(q), 20.0)
    density_t = density_20 * (1.0 - 25e-6 * (t - 20.0))
    p = _bisect(lambda candidate: _density(candidate, t) - density_t)
    corrected = Decimal(str(_q_from_p(p) * 100.0))
    return corrected.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
