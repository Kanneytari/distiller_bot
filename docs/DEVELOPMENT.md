# Local development

Для локального запуска не нужна отдельная СУБД. SQLite хранит все данные в одном файле `distiller_bot.db`, который создаётся автоматически при первом запуске.

## 1. Скачать проект

Если репозитория ещё нет локально:

```bash
git clone https://github.com/Kanneytari/distiller_bot.git
cd distiller_bot
```

Если репозиторий уже скачан:

```bash
cd distiller_bot
git pull
```

## 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

При следующих запусках виртуальное окружение создавать заново не нужно. Достаточно:

```bash
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

## 3. Environment

```bash
cp .env.example .env
```

Открой `.env` и укажи токен Telegram-бота:

```text
BOT_TOKEN=...
DATABASE_URL=sqlite+aiosqlite:///distiller_bot.db
```

`DATABASE_URL` можно не менять. Файл `.env` не коммитится.

## 4. Запуск

```bash
python -m distiller_bot.main
```

При запуске бот автоматически:

1. создаёт `distiller_bot.db`, если файла ещё нет;
2. создаёт недостающие таблицы;
3. запускает Telegram polling.

После `/start` пользователь автоматически сохраняется в SQLite и получает главное inline-меню.

Остановить бота:

```text
Ctrl + C
```

## 5. Проверки

```bash
ruff check .
pytest
```

На раннем этапе тестов может быть мало или не быть совсем.

## 6. Полный сброс локальной базы

Для разработки можно полностью удалить локальные данные:

```bash
rm -f distiller_bot.db distiller_bot.db-shm distiller_bot.db-wal
```

При следующем запуске чистая база создастся автоматически.
