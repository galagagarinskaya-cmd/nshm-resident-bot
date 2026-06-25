# Развертывание на Railway

## Предварительная подготовка

### Checklist перед развертыванием:
- [ ] Google Sheets таблица инициализирована (вкладки: Резиденты, Правила, Контент, Опрос)
- [ ] Боту дан доступ к Google Sheets (Share → email сервис-аккаунта)
- [ ] credentials.json скопирован в папку проекта
- [ ] .env файл заполнен (TOKEN, CHAT_ID, ADMIN_IDS)
- [ ] Бот добавлен как админ в группу (для ограничения прав)
- [ ] requirements.txt актуален

---

## Шаг 1: Инициализация Git репозитория

```bash
cd "/Users/gala/Бот Креативный отдел/nshm_bot"

# Инициализируем git
git init

# Добавляем все файлы (кроме .gitignore)
git add .

# Создаем первый коммит
git commit -m "Initial commit: NSHM resident bot setup"
```

---

## Шаг 2: Создание Railway проекта

```bash
# Установи Railway CLI
# macOS: brew install railway
# Linux: npm install -g @railway/cli
# Windows: npm install -g @railway/cli

# Логинись в Railway
railway login

# Инициализируй новый проект
railway init

# Выбери опции:
# - Project name: nshm-bot
# - Environment: production
```

---

## Шаг 3: Добавление переменных окружения в Railway

```bash
# Через CLI
railway variables set TELEGRAM_TOKEN=<твой_токен>
railway variables set TELEGRAM_CHAT_ID=<id_группы>
railway variables set TELEGRAM_ADMIN_IDS=<id_админа1>,<id_админа2>

# Или через Dashboard:
# 1. Открой https://railway.app
# 2. Выбери свой проект
# 3. Settings → Variables
# 4. Добавь переменные вручную
```

---

## Шаг 4: Загрузка Google Credentials

### Вариант A: Через Railway Dashboard (рекомендуется)

1. Откройся credentials.json в текстовом редакторе
2. Скопируй весь JSON
3. В Railway Dashboard → Variables → добавь:
   - Name: `GOOGLE_CREDENTIALS_JSON`
   - Value: <вся_содержимое_json>

### Вариант B: Через файл

1. В Railway загрузи credentials.json в File Storage
2. Обновь переменную: `GOOGLE_CREDENTIALS_PATH=/files/credentials.json`

---

## Шаг 5: Развертывание

```bash
# Отправь код на Railway
railway up

# Или используй Git
git remote add railway <railway-git-url>
git push railway main
```

Проверь статус:
```bash
railway status
```

---

## Шаг 6: Проверка логов

```bash
# Смотри логи бота
railway logs

# Или через Dashboard → Deployments → View logs
```

---

## Шаг 7: Проверка работы

1. Отправь сообщение в группу или боту
2. Проверь логи на Railway
3. Проверь Admin Panel (если задеплоена): `<railway-domain>/`

---

## Команды Railway CLI

```bash
# Проверить статус
railway status

# Смотреть логи
railway logs

# Посмотреть переменные
railway variables

# Обновить переменную
railway variables set VAR_NAME=value

# Развернуть изменения
railway up

# Открыть Dashboard
railway open
```

---

## Troubleshooting

### Бот не отвечает
```bash
# Проверь логи
railway logs

# Проверь переменные окружения
railway variables

# Убедись что token правильный
```

### Ошибки с Google Sheets
```bash
# Проверь что credentials.json правильный
# Проверь что боту дан доступ к таблице
# Проверь ID таблицы в config.py
```

### Проблемы с базой данных
```bash
# Включи SQLite persistence в Railway
# Или используй PostgreSQL (платно)
```

---

## Масштабирование

Когда нужно большше мощности:
1. Railway → Project Settings → Plan
2. Выбери Premium план
3. Добавь PostgreSQL для надежности
4. Обнови config.py для использования PostgreSQL

---

## Мониторинг

Рекомендуемые метрики:
- CPU usage
- Memory usage
- Network requests
- Error rate

Смотри в Railway Dashboard → Analytics

---

## Откаты

Если что-то сломалось:
```bash
# Откатись на предыдущий deployment
railway deployments

# Выбери нужный deployment
railway deployments --rollback <deployment-id>
```

---

## Что дальше?

После успешного развертывания:
1. Добавь бота в группу резидентов
2. Проверь что приветствие отправляется новичкам
3. Тестируй согласие с правилами
4. Проверь опрос через 3 дня
5. Мониторь Admin Panel
