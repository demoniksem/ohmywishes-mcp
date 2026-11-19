# ohmywishes-mcp

[![CI](https://github.com/demoniksem/ohmywishes-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/demoniksem/ohmywishes-mcp/actions/workflows/ci.yml)

MCP-сервер (Model Context Protocol) для [ohmywishes.com](https://ohmywishes.com) — вишлистов и желаний. Даёт ИИ-агенту доступ к вашим спискам: создать желание, прикрепить фото, разложить по спискам, забронировать подарок в чужом вишлисте.

Один файл, только стандартная библиотека Python, без зависимостей.

> **Неофициальный.** Сервер работает с публичным веб-API сервиса (`api.ohmywishes.com`). API не имеет формальной документации, поэтому эндпоинты и поля могут измениться без предупреждения. Проект не связан с ohmywishes и не поддерживается ими.

## Возможности

- **14 инструментов** по stdio: профиль, списки, желания, фото, брони, плюс сырой `omw_api` — вызов любого эндпоинта, если готового инструмента не хватает
- **Безопасное обновление**: `omw_update_wish` и `omw_update_wishlist` сначала читают объект, накладывают ваши поля и только потом отправляют полный `PUT`, которого требует API. Иначе сервис молча стирает всё, что вы не передали
- **Без зависимостей и установки**: `python3 server.py`
- Подходит любому MCP-клиенту: Hermes, Claude Desktop, Cursor, собственные клиенты

## Требования

- Python 3.10+
- Аккаунт на ohmywishes.com

## Как получить токен

API авторизуется JWT-токеном, который веб-приложение получает при входе.

1. Войдите на <https://ohmywishes.com>
2. Откройте DevTools (`F12`) → вкладка **Network** (Сеть)
3. Не закрывая панель, включите **Preserve log** (Сохранять журнал), перезагрузите страницу и полистайте список или меню профиля
4. Откройте любой запрос к `api.ohmywishes.com` и посмотрите его **URL** — в нём будет `?token=eyJ...`
5. Скопируйте значение после `token=` (это JWT из трёх частей через точку)

Положите токен туда, откуда сервер его прочитает:

```bash
mkdir -p ~/.config/ohmywishes
printf '%s' 'ВСТАВЬТЕ_ТОКЕН' > ~/.config/ohmywishes/token
chmod 600 ~/.config/ohmywishes/token
```

Или передайте через переменную окружения: `OMW_TOKEN=... python3 server.py`.

> Токен даёт полный доступ к аккаунту и живёт около года. Относитесь к нему как к паролю: не коммитьте, не вставляйте в чаты, ставьте `chmod 600`.

## Установка и запуск

```bash
git clone https://github.com/demoniksem/ohmywishes-mcp.git
cd ohmywishes-mcp
python3 server.py --help          # проверить, что токен найден
python3 server.py                 # stdio MCP-сервер (ждёт JSON-RPC на stdin)
```

Переменные окружения:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `OMW_TOKEN` | — | JWT, приоритетнее файла |
| `OMW_TOKEN_FILE` | `~/.config/ohmywishes/token` | Файл с JWT |
| `OMW_BASE_URL` | `https://api.ohmywishes.com` | Базовый URL API |
| `OMW_TIMEOUT` | `60` | Таймаут HTTP, секунды |

## Настройка клиента

**Hermes** (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  ohmywishes:
    command: python3
    args:
      - /абсолютный/путь/до/ohmywishes-mcp/server.py
    enabled: true
```

Или через CLI: `hermes mcp add ohmywishes --command python3 --args /абсолютный/путь/до/server.py`

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ohmywishes": {
      "command": "python3",
      "args": ["/абсолютный/путь/до/ohmywishes-mcp/server.py"]
    }
  }
}
```

Готовые файлы: [`examples/hermes-config.yaml`](examples/hermes-config.yaml), [`examples/claude-desktop.json`](examples/claude-desktop.json).

## Инструменты

| Инструмент | Что делает |
|---|---|
| `omw_whoami` | Текущий аккаунт: id, username, счётчики. Быстрая проверка токена |
| `omw_list_wishlists` | Свои списки желаний с видимостью и количеством желаний |
| `omw_list_wishes` | Свои желания с пагинацией: `all`, `private`, `reserved`, `fulfilled` |
| `omw_get_wish` | Одно желание по id (цена, ссылка, фото, привязка к спискам, флаги брони) |
| `omw_create_wish` | Создать желание: обязателен `title`, опционально `private`, `description`, `price`, `currency`, `link`, `wish_lists` |
| `omw_update_wish` | Обновить желание, не затирая остальные поля |
| `omw_delete_wish` | Удалить желание |
| `omw_set_wish_picture` | Загрузить локальный файл как фото желания |
| `omw_create_wishlist` | Создать список: обязателен `title`, `visibility` = `inherit` / `private` / `followers` |
| `omw_update_wishlist` | Обновить список, не затирая остальные поля |
| `omw_delete_wishlist` | Удалить список |
| `omw_reserve_wish` | Забронировать чужое желание (владелец увидит, что оно занято) |
| `omw_unreserve_wish` | Снять свою бронь |
| `omw_api` | Сырой запрос: любой метод и путь под `/api/v2` или `/api/v3` |

## Особенности API, которые стоит знать

Собрано при разборе API — объясняет большую часть сюрпризов:

- **Токен принимается только как query-параметр** (`?token=...`). Заголовок `Authorization: Bearer` отбивается с `403 security.invalid_access_token`, cookie и варианты `X-Token` дают `401`.
- **`PUT` по желанию заменяет объект целиком.** Если не передать `wish_lists`, желание отвяжется от списков. Ради этого и сделаны инструменты `omw_update_*`.
- **Видимость желания выводится из флага `private`**; поле `visibility` у желания игнорируется.
- **У видимости списков своё перечисление**: `inherit`, `private`, `followers`. Значения вроде `public` или `link` возвращают 400.
- **Неизвестные поля молча игнорируются**, а не отбиваются ошибкой — опечатка выглядит как «поле ничего не делает».
- **К ссылкам сервис дописывает `?utm_source=ohmywishes`**.
- **`price` — просто число**, валюта лежит отдельным полем (34 валюты, по умолчанию `RUB`).
- **Своё желание забронировать нельзя** (400).
- Ответы бывают двух форм: голый массив для списков желаний и `{"items": [...]}` / `{"item": {...}}` в остальных местах.

## Безопасность

- Сервер не логирует токен и отправляет его только на `api.ohmywishes.com`.
- Все записи идут от аккаунта-владельца токена — режима «только чтение» или dry-run нет.
- Тестовые объекты создаются по-настоящему: убирайте их через `omw_delete_wish` и `omw_delete_wishlist`.

## Лицензия

MIT — см. [LICENSE](LICENSE).

---

English version: [README.en.md](README.en.md)
