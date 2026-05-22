# Elcalendar Bot

Telegram-бот календарь с Mini App. Позволяет создавать события в группе и получать напоминания.

## Возможности

- Создание событий через Mini App (кнопки, date picker)
- Создание событий через текстовый диалог (`/newevent`)
- Несколько напоминаний на одно событие
- Повторные напоминания с настраиваемым интервалом
- Удаление событий из Mini App

## Стек

- **Python 3.12** — aiogram 3, FastAPI, SQLAlchemy async
- **PostgreSQL** — хранение событий и напоминаний
- **APScheduler** — проверка напоминаний каждые 30 секунд
- **Docker + docker-compose** — деплой

## Установка

### 1. Создай бота

Открой [@BotFather](https://t.me/BotFather), выполни `/newbot`, скопируй токен.

### 2. Настрой окружение

```bash
cp .env.example .env
nano .env
```

```env
BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DB_PASSWORD=придумай_пароль
TIMEZONE=Europe/Moscow
```

### 3. Запусти

```bash
docker compose up -d --build
```

Бот и API поднимаются в одном контейнере на порту `8080`.

## Команды бота

| Команда | Описание |
|---------|----------|
| `/cal` | Открыть Mini App (в группах — ссылка в личку) |
| `/newevent` | Создать событие через диалог |
| `/events` | Список предстоящих событий |
| `/cancel` | Отменить текущий диалог |

## Mini App

Доступна по адресу `https://<твой-домен>/cal/`.

Требует HTTPS. Для раздачи используется Caddy (конфиг в `../vaultwarden/Caddyfile`).

**Структура напоминаний:**
- Одно событие может иметь несколько независимых напоминаний
- Каждое напоминание можно повторить N раз с заданным интервалом

## Структура проекта

```
├── bot.py          # Точка входа, хендлеры, планировщик
├── api.py          # FastAPI — REST API для Mini App
├── db.py           # Модели SQLAlchemy, CRUD
├── config.py       # Настройки из .env
├── utils.py        # Парсинг дат и времени
├── webapp/
│   └── index.html  # Telegram Mini App (vanilla JS)
├── Dockerfile
└── docker-compose.yml
```
