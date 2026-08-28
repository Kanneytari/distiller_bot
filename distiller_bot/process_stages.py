from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StageAction:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class StageDefinition:
    title: str
    icon: str
    actions: tuple[StageAction, ...]


STAGE_DEFINITIONS: dict[str, StageDefinition] = {
    "preparation": StageDefinition(
        title="Подготовка",
        icon="🧰",
        actions=(
            StageAction("composition", "✏️ Состав"),
            StageAction("note", "📝 Заметка"),
            StageAction("sugar_wash", "🧮 Калькуляторы"),
            StageAction("complete_stage", "✅ Завершить этап"),
        ),
    ),
    "fermentation": StageDefinition(
        title="Брожение",
        icon="🫧",
        actions=(
            StageAction("measure", "📏 Добавить измерение"),
            StageAction("note", "📝 Заметка"),
            StageAction("calculators", "🧮 Калькуляторы"),
            StageAction("complete_stage", "✅ Завершить брожение"),
        ),
    ),
    "first_distillation": StageDefinition(
        title="Первая перегонка",
        icon="⚗️",
        actions=(
            StageAction("first_distillation_result", "✏️ Результат"),
            StageAction("note", "📝 Заметка"),
            StageAction("calculators", "🧮 Калькуляторы"),
            StageAction("complete_stage", "✅ Завершить первую перегонку"),
        ),
    ),
    "second_distillation": StageDefinition(
        title="Вторая перегонка",
        icon="⚗️",
        actions=(
            StageAction("measure", "📏 Записать результат"),
            StageAction("note", "📝 Заметка"),
            StageAction("calculators", "🧮 Калькуляторы"),
            StageAction("complete_stage", "✅ Завершить вторую перегонку"),
        ),
    ),
    # Legacy-тип нужен только для уже сохранённых процессов.
    # Новые клавиатуры больше не позволяют выбрать общую "Перегонку".
    "distillation": StageDefinition(
        title="Перегонка",
        icon="⚗️",
        actions=(
            StageAction("measure", "📏 Записать результат"),
            StageAction("note", "📝 Заметка"),
            StageAction("calculators", "🧮 Калькуляторы"),
            StageAction("complete_stage", "✅ Завершить перегонку"),
        ),
    ),
    "drink_preparation": StageDefinition(
        title="Подготовка напитка",
        icon="💧",
        actions=(
            StageAction("measure", "📏 Параметры напитка"),
            StageAction("calculators", "🧮 Калькуляторы"),
            StageAction("note", "📝 Заметка"),
            StageAction("complete_stage", "✅ Завершить этап"),
        ),
    ),
    "bottling": StageDefinition(
        title="Розлив",
        icon="🍾",
        actions=(
            StageAction("measure", "📏 Записать результат"),
            StageAction("note", "📝 Заметка"),
            StageAction("complete_process", "✅ Завершить процесс"),
        ),
    ),
}

# Старые callback-ключи оставлены только для совместимости со старыми данными.
# Новые клавиатуры используют только актуальные ключи этапов.
STAGE_TITLES: dict[str, str] = {
    "preparation": "Подготовка",
    "fermentation": "Брожение",
    "first_distillation": "Первая перегонка",
    "second_distillation": "Вторая перегонка",
    "distillation": "Перегонка",
    "drink_preparation": "Подготовка напитка",
    "bottling": "Розлив",
    "dilution": "Разбавление",
    "aging": "Выдержка",
    "ready": "Готово",
}

LEGACY_STAGE_TYPES: dict[str, str] = {
    "Разбавление": "drink_preparation",
    "Выдержка": "drink_preparation",
    "Готово": "bottling",
}

LEGACY_STAGE_ICONS: dict[str, str] = {
    "Разбавление": "💧",
    "Выдержка": "🪵",
    "Готово": "✅",
}

GENERIC_STAGE_ACTIONS: tuple[StageAction, ...] = (
    StageAction("measure", "📏 Добавить измерение"),
    StageAction("note", "📝 Заметка"),
    StageAction("calculators", "🧮 Калькуляторы"),
)


def stage_type_for_title(stage: str | None) -> str | None:
    """Resolve a stored stage title to its reusable stage type."""
    if not stage:
        return None

    legacy_type = LEGACY_STAGE_TYPES.get(stage)
    if legacy_type is not None:
        return legacy_type

    for stage_type, definition in STAGE_DEFINITIONS.items():
        if stage == definition.title:
            return stage_type

        prefix = f"{definition.title} #"
        suffix = stage.removeprefix(prefix)
        if stage.startswith(prefix) and suffix.isdigit():
            return stage_type

    return None


def stage_definition_for_title(stage: str | None) -> StageDefinition | None:
    stage_type = stage_type_for_title(stage)
    return STAGE_DEFINITIONS.get(stage_type) if stage_type is not None else None


def stage_icon(stage: str | None) -> str:
    definition = stage_definition_for_title(stage)
    if definition is not None:
        return definition.icon
    if stage is not None:
        return LEGACY_STAGE_ICONS.get(stage, "🧪")
    return "🧪"


def stage_actions_for_stage(stage: str | None) -> tuple[StageAction, ...]:
    definition = stage_definition_for_title(stage)
    return definition.actions if definition is not None else GENERIC_STAGE_ACTIONS
