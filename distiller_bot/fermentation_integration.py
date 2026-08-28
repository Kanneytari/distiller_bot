from .keyboards import PROCESS_ACTION_CALLBACKS


PROCESS_ACTION_CALLBACKS.update(
    {
        "fermentation_temperature": "process:fermentation-temperature:{process_id}",
        "fermentation_brix": "process:fermentation-brix:{process_id}",
    }
)
