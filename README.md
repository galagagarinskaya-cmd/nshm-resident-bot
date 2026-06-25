# НШМ Резидент Бот

Telegram-бот для управления закрытым клубом резидентов НШМ VK.

## Функции

1. **Приветствие новичков** - автоматическое сообщение при присоединении
2. **Согласие с правилами** - пошаговое принятие правил сообщества
3. **Блокировка доступа** - ограничение прав до согласия с правилами
4. **Опрос резидентов** - сбор данных через 3 дня после присоединения
5. **Синхронизация с Google Sheets** - обновление реестра резидентов
6. **Admin Panel** - управление ботом и просмотр данных
7. **Поздравления с ДР** - автоматические поздравления

## Установка

### 1. Клонирование и подготовка
```bash
cd nshm_bot
python -m venv venv
source venv/bin/activate  # macOS/Linux
# или
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 2. Конфигурация

Скопируй `.env.example` в `.env`:
```bash
cp .env.example .env
```

Заполни `.env` файл:
- `TELEGRAM_TOKEN` - токен бота от BotFather
- `TELEGRAM_CHAT_ID` - ID группы (получить через @userinfobot)
- `TELEGRAM_ADMIN_IDS` - ID администраторов через запятую
- `GOOGLE_CREDENTIALS_PATH` - путь к JSON-файлу сервис-аккаунта

### 3. Google Sheets Setup

1. Скопируй JSON-файл сервис-аккаунта в папку проекта (или укажи правильный путь в `.env`)
2. Откройте Google Sheets таблицу и дайте доступ сервис-аккаунту (email из JSON):
   - Нажми "Share"
   - Вставь email из JSON
   - Дай права "Editor"

### 4. Запуск локально

```bash
python main.py
```

### 5. Развертывание на Railway

1. Инициализируй git репозиторий:
```bash
git init
git add .
git commit -m "Initial commit"
```

2. Подключи Railway:
```bash
railway login
railway init
```

3. Установи переменные окружения в Railway:
```bash
railway variables set TELEGRAM_TOKEN=your_token
railway variables set TELEGRAM_CHAT_ID=your_chat_id
railway variables set TELEGRAM_ADMIN_IDS=admin_id_1,admin_id_2
railway variables set GOOGLE_CREDENTIALS_PATH=/credentials.json
```

4. Загрузи JSON с учетными данными Google в Railway

5. Задепло й:
```bash
railway up
```

## Структура проекта

```
nshm_bot/
├── main.py              # Основной файл бота
├── config.py            # Конфигурация
├── database.py          # Работа с SQLite БД
├── sheets_service.py    # Работа с Google Sheets API
├── survey.py            # Логика опроса
├── requirements.txt     # Зависимости
├── Procfile             # Для Railway
└── .env.example         # Пример конфигурации
```

## API Sheets

Бот ожидает следующие вкладки в Google Sheets:

### Вкладка "Резиденты"
Основная таблица с данными резидентов (столбцы из ТЗ)

### Вкладка "Правила"
| Номер | Заголовок | Текст |
|-------|-----------|-------|
| 1 | ЧАСТЬ 1 — ОБЩЕНИЕ | ... |
| 2 | ЧАСТЬ 2 — РЕКЛАМА И ССЫЛКИ | ... |
| ... | ... | ... |

### Вкладка "Контент"
| Блок | ID | Текст |
|------|----|----|
| Кружок | glasha | Текст от Гали... |
| Кружок | roma | Текст от Ромы... |
| ... | ... | ... |

### Вкладка "Опрос"
| Номер блока | Вопрос | Тип |
|-------------|--------|-----|
| 1 | Как тебя зовут... | text |
| 1 | Когда ДР... | text |
| ... | ... | ... |

## Команды бота

- `/start` - Начать взаимодействие с ботом
- `/status` - Проверить статус (админам)
- `/stats` - Статистика (админам)

## Обработка ошибок

Все ошибки логируются в `bot.log`. Проверяй логи для отладки:
```bash
tail -f bot.log
```

## TODO

- [ ] Полная интеграция с опросом
- [ ] Admin Panel на Flask
- [ ] Поздравления с ДР
- [ ] Синхронизация ответов в Sheets
- [ ] Расписание отправки опросов
- [ ] Обработка команды "Назад" в опросе

## Поддержка

Для вопросов - свяжись с командой НШМ VK.
