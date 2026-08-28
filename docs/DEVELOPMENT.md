# Local development

## 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

## 2. PostgreSQL

Для локальной разработки нужна запущенная PostgreSQL.

Пример создания отдельного пользователя и БД:

```bash
createuser -P distiller
createdb -O distiller distiller_bot
```

В `.env.example` используется строка подключения:

```text
postgresql+asyncpg://distiller:distiller@localhost:5432/distiller_bot
```

Пароль в `DATABASE_URL` должен совпадать с тем, который был указан при создании пользователя PostgreSQL.

## 3. Environment

```bash
cp .env.example .env
```

Заполнить:

```text
BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://...
```

Файл `.env` не коммитится.

## 4. Миграции

Создать/обновить схему БД:

```bash
alembic upgrade head
```

После изменения SQLAlchemy-моделей новая миграция создаётся так:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Важно: сначала проверять сгенерированный файл миграции, и только потом применять его.

## 5. Запуск

```bash
python -m distiller_bot.main
```

После запуска `/start` автоматически создаёт пользователя в PostgreSQL и показывает главное inline-меню.

## 6. Проверки

```bash
ruff check .
pytest
```

На текущем раннем этапе тестов ещё может не быть. Они будут добавляться вместе с бизнес-логикой MVP.
