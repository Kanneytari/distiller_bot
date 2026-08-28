from .keyboards import PROCESS_ACTION_CALLBACKS
from .processes import STAGE_MEASUREMENT_ORDER, STAGE_QUICK_MEASUREMENTS


PROCESS_ACTION_CALLBACKS.update(
    {
        "fermentation_temperature": "process:fermentation-temperature:{process_id}",
        "fermentation_brix": "process:fermentation-brix:{process_id}",
    }
)

STAGE_MEASUREMENT_ORDER["fermentation"] = ["temperature"]
STAGE_QUICK_MEASUREMENTS["fermentation"] = []
