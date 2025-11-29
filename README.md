# Telegram Channel Users Scanner and Cleaner

Инструмент для сканирования и удаления удаленных аккаунтов (deleted accounts) из Telegram каналов. Оптимизирован для работы с каналами с миллионами подписчиков.

## Особенности

- Двухэтапный подход: сначала выгрузка всех участников, затем анализ и удаление
- Оптимизация для больших каналов: пакетная обработка, минимальное потребление RAM
- Безопасное удаление: предварительный просмотр, подтверждение, откат действий
- Возобновление операций: чекпоинты для прерванных процессов
- Подробная отчетность: CSV, JSON, текстовые отчеты
- Гибкая аналитика: поиск deleted accounts по разным паттернам

## Архитектура

```
project/
├── main.py                    # Основной скрипт с меню
├── config.py                  # Конфигурация и API ключи
├── database.py               # SQLite база данных
├── exporter.py               # Выгрузка участников
├── analyzer.py               # Анализ удаленных аккаунтов
├── deleter.py                # Безопасное удаление
├── reporter.py               # Генерация отчетов
├── checkpoint_manager.py     # Управление чекпоинтами
├── .env.example              # Шаблон конфигурации
└── requirements.txt          # Зависимости
```

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/xsa-dev/py-dir-fake-users-from-channel.git
cd py-dir-fake-users-from-channel
```

### 2. Установка зависимостей

#### Вариант A: Установка через uv (рекомендуется)

```bash
# Установка uv (если еще не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Установка зависимостей проекта
uv sync

# Запуск приложения
uv run python run.py
```

Или через Makefile:

```bash
make install  # установить зависимости через uv
make start    # запустить приложение
```

#### Вариант B: Установка через pip

```bash
# Активация виртуального окружения
python -m venv .venv
source .venv/bin/activate  # Для Windows: .venv\Scripts\activate

# Установка зависимостей
pip install -e .
```

### 3. Получение API ключей Telegram

1. Перейдите на [my.telegram.org](https://my.telegram.org)
2. Войдите под своим аккаунтом
3. Перейдите в "API development tools"
4. Создайте новое приложение
5. Сохраните `api_id` и `api_hash`

### 4. Настройка

Скопируйте шаблон конфигурации:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл:

```env
# Telegram API Configuration
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
PHONE_NUMBER=+79991234567

# Database Configuration
DATABASE_NAME=channel_users.db

# Export Configuration (оптимизировано для больших каналов)
BATCH_SIZE=2000
CHECKPOINT_INTERVAL=10000
REQUEST_DELAY=0.033  # ~30 запросов в секунду

# Channel Configuration
CHANNEL_USERNAME=@your_channel

# Deletion Configuration
DELETE_BATCH_SIZE=100
DELETE_DELAY=0.1
DELETE_CONFIRMATION=true
```

## Использование

### Запуск приложения

#### Через uv (рекомендуется):

```bash
uv run python run.py
```

#### Через Makefile:

```bash
make install  # установить зависимости через uv
make start    # запустить приложение
```

#### Через pip (если использовали pip для установки):

```bash
python run.py
```

### Основной workflow

#### 1. Экспорт участников канала

```
1. Экспортировать участников канала
   → Введите имя канала (@channel_name)
   → Ожидание завершения (для 1М пользователей: 2-4 часа)
```

#### 2. Анализ удаленных аккаунтов

```
2. Анализировать удаленные аккаунты
   → Автоматический поиск по паттернам
   → Показ результатов анализа
   → Сохранение отчетов
```

#### 3. Удаление пользователей

```
4. Удалить пользователей
   → Предпросмотр кандидатов
   → Подтверждение удаления
   → Пакетное удаление с паузами
```

### Оптимизации для больших каналов

- **Память**: < 300MB RAM для 1М пользователей
- **База данных**: SQLite с индексами для быстрых запросов
- **Пакетная обработка**: 2000 пользователей за раз
- **Лимиты API**: Умная обработка лимитов Telegram (30 запросов/сек)
- **Чекпоинты**: Возобновление после обрывов
- **Прогресс**: Детальный прогресс-бар с ETA

## Анализ удаленных аккаунтов

Система ищет аккаунты по следующим паттернам:

- `Deleted Account`
- `Deleted User`
- `user[numbers]`
- Пустые и дефолтные имена
- Отсутствие username

## Безопасность

- Предпросмотр перед удалением
- Подтверждение пользователя
- Резервные копии в БД
- Логирование всех операций
- Обработка ошибок без остановки
- Права администратора проверяются

## Отчеты

Система генерирует отчеты в форматах:

- **CSV**: Для анализа в Excel
- **JSON**: Для интеграции с другими системами
- **Текстовый**: Краткая сводка

Файлы сохраняются в папке `reports/`.

## Командная строка

Также можно использовать отдельные модули:

```python
# Прямое использование в Python
from exporter import TelegramExporter
from analyzer import DeletedUserAnalyzer
from deleter import TelegramUserDeleter

async def scan_channel():
    # Инициализация
    client = TelegramClient('session', api_id, api_hash)
    db = DatabaseManager('users.db')
    await db.init_database()

    # Экспорт
    exporter = TelegramExporter(client, db)
    stats = await exporter.export_channel_participants('@channel_name')

    # Анализ
    analyzer = DeletedUserAnalyzer(db)
    deleted = await analyzer.find_deleted_accounts()

    print(f"Найдено deleted accounts: {len(deleted)}")
```

## Troubleshooting

### Ошибки аутентификации
- Убедитесь, что API ID и API Hash верные
- Проверьте формат номера телефона (+79991234567)
- Для двухфакторной аутентификации потребуется пароль

### Проблемы с большими каналами
- Увеличьте `CHECKPOINT_INTERVAL` для большей стабильности
- Уменьшите `BATCH_SIZE` если возникают ошибки API
- Используйте премиум аккаунт для повышенных лимитов

### Ошибки удаления
- Проверьте права администратора в канале
- Убедитесь, что вы не были удалены из канала
- Некоторые типы каналов могут ограничивать удаление

## Требования

- Python 3.12+
- Telegram API ключи
- Права администратора в целевом канале (для удаления)
- Стабильное интернет-соединение

## Изменения

### Версия 0.1.0

#### Новые возможности
- Добавлена поддержка сохранения `photo_id` пользователей в базе данных
- Добавлена автоматическая миграция схемы БД для существующих баз данных
- Добавлены тесты для больших объемов данных (`test/test_database_large.py`)
  - Тест на 10,000 пользователей (запускается всегда)
  - Тест на 2,000,000 пользователей (требует `RUN_HEAVY_TESTS=1`)
- Добавлена команда `make test` для запуска тестов через uv

#### Улучшения
- Обновлены инструкции по установке: добавлена поддержка `uv` (рекомендуется)
- Улучшена обработка экспорта пользователей с поддержкой `photo_id`
- Улучшена миграция данных при перемещении пользователей в `deleted_users`

#### Документация
- Добавлен файл `LICENSE` с MIT лицензией
- Обновлены ссылки на репозиторий в `README.md` и `pyproject.toml`
- Добавлена секция "AI Assistance"
- Добавлены инструкции по установке через `uv` и `Makefile`

#### Технические изменения
- Добавлено поле `photo_id` в класс `User`
- Добавлен метод `_upgrade_schema()` для автоматической миграции схемы БД
- Обновлен метод `insert_users_batch()` для поддержки `photo_id`
- Обновлен метод `move_users_to_deleted()` с использованием `INSERT OR IGNORE`

## Лицензия

MIT License - см. [LICENSE](LICENSE) для деталей.

Репозиторий: https://github.com/xsa-dev/py-dir-fake-users-from-channel

## AI Assistance

AI-assisted code (ChatGPT, Claude, Cursor).

## Contributing

1. Fork the repository: https://github.com/xsa-dev/py-dir-fake-users-from-channel
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Support

При возникновении проблем:
1. Проверьте логи ошибок
2. Убедитесь в правильности конфигурации
3. Попробуйте с меньшими BATCH_SIZE
4. Используйте чекпоинты для возобновления

---

**Внимание**: Удаление пользователей — необратимая операция. Всегда делайте бэкапы и внимательно проверяйте списки перед удалением!
