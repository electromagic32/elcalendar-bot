# Elcalendar Bot

Telegram-бот календарь с Mini App. Позволяет создавать и редактировать события в группе и получать напоминания.

## Возможности

- Создание и редактирование событий через Mini App
- Просмотр предстоящих и прошедших событий
- Несколько напоминаний на одно событие
- Повторные напоминания с настраиваемым интервалом
- Удаление событий из Mini App
- В группах: команда `/cal` автоматически удаляется через 7 секунд (бот должен быть администратором)

## Стек

- **Python 3.12** — aiogram 3, FastAPI, SQLAlchemy async
- **PostgreSQL** — хранение событий и напоминаний
- **APScheduler** — проверка напоминаний каждые 30 секунд
- **Docker + docker-compose** — деплой

## Установка

### 1. Создай бота

Открой [@BotFather](https://t.me/BotFather), выполни `/newbot`, скопируй токен и username.

### 2. Настрой окружение

```bash
cp .env.example .env
nano .env
```

```env
BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BOT_USERNAME=MyCalendarBot
DB_PASSWORD=придумай_пароль
TIMEZONE=Europe/Moscow
WEBAPP_URL=https://<твой-домен>/cal/
HOME_GROUP_ID=-1001234567890  # chat_id группы для whitelist (0 = без ограничений)
```

### 3. Запусти

```bash
docker compose up -d --build
```

Бот и API поднимаются в одном контейнере на порту `8080`.

## Команды бота

| Команда | Описание |
|---------|----------|
| `/cal` | Открыть Mini App (в группах — ссылка в личку, сообщения удаляются через 7 сек) |

## Mini App

Доступна по адресу `https://<твой-домен>/cal/`.

Требует HTTPS. Для раздачи используется Caddy (конфиг в `../vaultwarden/Caddyfile`).

**Возможности:**
- Создание и редактирование событий (тап на карточку)
- Переключение между предстоящими и прошедшими событиями
- Несколько напоминаний на событие, каждое с повтором и интервалом

## Ограничение доступа

Бот поддерживает whitelist по членству в группе. Только участники указанной группы могут использовать бота и Mini App.

```env
HOME_GROUP_ID=-1001234567890
```

- `0` (по умолчанию) — доступ для всех
- Участники с статусом `member`, `administrator`, `creator` — получают доступ
- Вышедшие из группы — теряют доступ автоматически

Узнать `chat_id` группы можно из БД: `SELECT DISTINCT chat_id FROM events;`

## Staging-окружение

Для тестирования без влияния на production используется отдельный стек.

```bash
# Создай .env.dev с токеном тестового бота
cp .env.example .env.dev
nano .env.dev  # BOT_USERNAME, WEBAPP_URL=.../cal-dev/, DB_NAME=calbot_dev, DB_HOST=db-dev

docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
```

Staging поднимается на порту `8081`, Caddy роутит `/cal-dev/*` → `8081`.

При пуше в ветку `dev` GitHub Actions автоматически деплоит staging.

## CI/CD

| Ветка | Действие |
|-------|----------|
| `dev` | Деплой на staging (`/cal-dev/`) |
| `main` | Деплой на production (`/cal/`) |

Workflow-файлы: `.github/workflows/deploy.yml`, `.github/workflows/deploy-dev.yml`.

## Структура проекта

```
├── bot.py                        # Хендлеры, планировщик напоминаний
├── api.py                        # FastAPI — REST API для Mini App
├── db.py                         # Модели SQLAlchemy, CRUD
├── config.py                     # Настройки из .env
├── utils.py                      # Форматирование дат
├── webapp/
│   └── index.html                # Telegram Mini App (vanilla JS)
├── docker-compose.yml            # Production
├── docker-compose.dev.yml        # Staging
├── Dockerfile
└── .github/workflows/
    ├── deploy.yml                # CD → main
    └── deploy-dev.yml            # CD → dev
```
