# Data Model — PostgreSQL

Цель модели данных — поддержать свободный сценарий использования Distiller Bot.

Ключевое ограничение архитектуры: **напиток не обязан быть связан с рецептом, оборудованием или полным технологическим циклом**. Пользователь может начать вести запись на любом этапе.

## Общие принципы

- PostgreSQL — основная БД.
- SQLAlchemy 2 — ORM.
- Alembic — миграции.
- asyncpg — PostgreSQL driver.
- Для основных сущностей используем обычные реляционные поля.
- JSONB используем только там, где структура действительно может сильно различаться, например для дополнительных параметров оборудования или данных отдельных событий.
- Не использовать PostgreSQL ENUM для пользовательских этапов и категорий: значения должны расширяться без тяжёлых миграций.
- Все даты храним как timezone-aware timestamps.

---

# 1. users

Профиль Telegram-пользователя.

Поля:

- `id` — внутренний PK;
- `telegram_id` — уникальный Telegram ID;
- `username` — nullable;
- `first_name` — nullable;
- `created_at`;
- `updated_at`.

Профиль создаётся автоматически при первом `/start`.

---

# 2. equipment

Сохранённое оборудование пользователя.

Поля:

- `id`;
- `user_id` → users;
- `name` — пользовательское название;
- `equipment_type` — строка: still, fermenter, column, heater, other;
- `capacity_l` — nullable;
- `power_kw` — nullable;
- `properties` — JSONB для дополнительных параметров;
- `created_at`;
- `updated_at`.

Почему часть параметров вынесена отдельно: объём и мощность часто нужны для расчётов и фильтрации, поэтому их удобнее хранить нормальными колонками. Редкие специфические свойства можно хранить в `properties`.

Один пользователь может иметь несколько единиц оборудования одного типа.

---

# 3. recipes

Встроенные и пользовательские рецепты.

Поля:

- `id`;
- `owner_user_id` → users, nullable для встроенных рецептов;
- `source_type` — system / user;
- `name`;
- `description` — nullable;
- `category` — nullable строка;
- `base_volume_l` — nullable;
- `is_draft`;
- `created_at`;
- `updated_at`.

`owner_user_id = NULL` + `source_type = system` означает встроенный рецепт.

---

# 4. recipe_ingredients

Ингредиенты рецепта.

Поля:

- `id`;
- `recipe_id` → recipes;
- `name`;
- `amount` — numeric, nullable;
- `unit` — nullable;
- `position` — порядок отображения.

Ингредиент допускается сохранить даже без точного количества — это полезно для пользовательских черновиков.

---

# 5. recipe_steps

Краткие шаги рецепта.

Поля:

- `id`;
- `recipe_id` → recipes;
- `title` — nullable;
- `description`;
- `position`.

Эти шаги информационные. Они не создают обязательный workflow для напитка.

---

# 6. saved_recipes

Связь пользователя с сохранёнными рецептами.

Поля:

- `user_id` → users;
- `recipe_id` → recipes;
- `created_at`.

Уникальное ограничение:

`(user_id, recipe_id)`.

---

# 7. drinks

Главная пользовательская рабочая сущность.

Поля:

- `id`;
- `user_id` → users;
- `name`;
- `recipe_id` → recipes, nullable;
- `current_stage` — строка, nullable;
- `status` — active / completed / archived;
- `started_at` — nullable;
- `completed_at` — nullable;
- `created_at`;
- `updated_at`.

Важно:

- `recipe_id` необязателен;
- `current_stage` не является жёстким ENUM;
- пользователь может создать запись сразу с этапом `выдержка`, `перегонка`, `готово` или собственным значением;
- отсутствие предыдущих этапов не считается ошибкой.

---

# 8. drink_equipment

Необязательная связь напитка с оборудованием.

Поля:

- `drink_id` → drinks;
- `equipment_id` → equipment;
- `role` — nullable строка, например fermentation / distillation / heating / other.

Уникальное ограничение:

`(drink_id, equipment_id)`.

Так напиток может использовать несколько единиц оборудования, а оборудование может использоваться в разных напитках.

---

# 9. measurements

Структурированные замеры напитка.

Поля:

- `id`;
- `drink_id` → drinks;
- `measurement_type` — temperature / density / abv / volume / custom;
- `value` — numeric;
- `unit` — строка;
- `label` — nullable, используется для custom;
- `measured_at`;
- `created_at`.

Примеры:

- temperature / 24 / °C;
- density / 1.026 / SG;
- abv / 68 / %;
- volume / 4.3 / l.

Не складывать основные измерения только в JSONB: они пригодятся для истории, статистики и будущих графиков.

---

# 10. drink_events

Универсальный журнал событий напитка.

Поля:

- `id`;
- `drink_id` → drinks;
- `event_type` — created / stage_changed / note / calculation / completed / other;
- `title` — nullable;
- `text` — nullable;
- `data` — JSONB, nullable;
- `created_at`.

Примеры:

### Смена этапа

`event_type = stage_changed`

`data`:

```json
{
  "from": "брожение",
  "to": "перегонка"
}
```

### Результат калькулятора

`event_type = calculation`

`data`:

```json
{
  "calculator": "dilution",
  "initial_volume_l": 4.3,
  "initial_abv": 76,
  "target_abv": 42,
  "water_l": 3.48
}
```

JSONB здесь уместен, потому что данные разных типов событий имеют разную структуру.

Замеры при этом всё равно хранятся отдельно в `measurements`, а в журнале можно отображать их вместе с событиями через сервисный слой.

---

# 11. reminders

Напоминания пользователя.

Поля:

- `id`;
- `user_id` → users;
- `drink_id` → drinks, nullable;
- `text`;
- `remind_at`;
- `status` — pending / sent / cancelled;
- `created_at`;
- `sent_at` — nullable.

`drink_id` оставляем nullable, чтобы позже можно было использовать общие напоминания без изменения схемы.

---

# Связи

```text
users
 ├── equipment
 ├── recipes (user recipes)
 ├── saved_recipes ── recipes
 ├── drinks
 │    ├── measurements
 │    ├── drink_events
 │    ├── reminders
 │    └── drink_equipment ── equipment
 └── reminders

recipes
 ├── recipe_ingredients
 └── recipe_steps
```

---

# Что сознательно НЕ создаём отдельными таблицами в MVP

## Калькуляторы

Большинство расчётов stateless. Для них не нужна отдельная таблица.

Если пользователь хочет сохранить результат в напиток — создаётся `drink_event` типа `calculation`.

## Этапы производства

Не создаём обязательную таблицу workflow и не связываем напиток с последовательностью шагов.

Типовые этапы живут на уровне приложения как предлагаемые значения. Пользователь всегда может указать собственный этап.

## Категории рецептов

В MVP достаточно строки. Отдельный справочник имеет смысл только когда каталог станет достаточно большим.

## Запасы

Складской учёт не входит в MVP.

---

# Индексы MVP

Помимо PK и UNIQUE имеет смысл добавить:

- `users.telegram_id` UNIQUE;
- `equipment.user_id`;
- `recipes.owner_user_id`;
- `recipes.category`;
- `drinks.user_id`;
- `(drinks.user_id, drinks.status)`;
- `measurements.drink_id`;
- `(measurements.drink_id, measurements.measured_at)`;
- `drink_events.drink_id`;
- `(drink_events.drink_id, drink_events.created_at)`;
- `(reminders.status, reminders.remind_at)`.

Последний индекс особенно важен для фоновой задачи, которая выбирает ожидающие напоминания.

---

# Правила удаления

Предварительная стратегия:

- удаление пользователя → cascade его пользовательских данных;
- удаление напитка → cascade замеров, событий, связей с оборудованием и связанных напоминаний;
- удаление оборудования → удаляется только связь с напитками, сами напитки сохраняются;
- встроенные рецепты не удаляются пользователями;
- удаление пользовательского рецепта не должно удалять старые напитки: `drinks.recipe_id` становится NULL или рецепт переводится в архивный статус.

Перед реализацией это поведение нужно явно закрепить в моделях и миграциях.

---

# Почему эта схема подходит проекту

Она сохраняет главный принцип Distiller Bot:

**пользовательские данные важнее встроенной технологической модели.**

Можно создать напиток без рецепта, не добавлять оборудование, начать с любого этапа, сохранить произвольные заметки и пользоваться калькуляторами отдельно. При этом структурированные данные остаются достаточно нормализованными, чтобы позже добавить аналитику, графики, запасы и более умные подсказки без переписывания ядра БД.
