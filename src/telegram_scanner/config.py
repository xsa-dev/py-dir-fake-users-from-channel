import os
from dotenv import load_dotenv
from typing import Optional
from pathlib import Path


class Config:
    """Класс для управления конфигурацией приложения"""

    def __init__(self, env_file: str = ".env"):
        # Загружаем переменные окружения из корня проекта
        # .env файл должен быть в корне проекта
        project_root = Path(__file__).parent.parent.parent
        env_path = project_root / env_file
        if env_path.exists():
            load_dotenv(env_path)

        # Telegram API настройки
        self.api_id: int = self._get_int_env("API_ID", default=0, required=True)
        self.api_hash: str = self._get_str_env("API_HASH", default=None, required=True)
        self.phone_number: str = self._get_str_env("PHONE_NUMBER", default=None, required=True)

        # Настройки базы данных
        self.database_name: str = self._get_str_env("DATABASE_NAME", "channel_users.db")

        # Настройки экспорта
        self.batch_size: int = self._get_int_env("BATCH_SIZE", 2000)
        self.checkpoint_interval: int = self._get_int_env("CHECKPOINT_INTERVAL", 10000)
        self.request_delay: float = self._get_float_env("REQUEST_DELAY", 0.033)  # ~30 запросов в секунду

        # Настройки канала
        self.channel_username: Optional[str] = self._get_str_env("CHANNEL_USERNAME", None)

        # Настройки удаления
        self.delete_batch_size: int = self._get_int_env("DELETE_BATCH_SIZE", 100)
        self.delete_delay: float = self._get_float_env("DELETE_DELAY", 0.1)
        self.delete_confirmation: bool = self._get_bool_env("DELETE_CONFIRMATION", True)

        # Настройки отчетов
        self.export_deleted_users: bool = self._get_bool_env("EXPORT_DELETED_USERS", True)

        # Дополнительные настройки
        self.session_name: str = "telegram_scanner_session"
        self.max_retries: int = self._get_int_env("MAX_RETRIES", 3)
        self.timeout: int = self._get_int_env("TIMEOUT", 30)

        # Пути к файлам
        # base_dir должен указывать на корень проекта, где находится .env файл
        self.base_dir = Path(__file__).parent.parent.parent  # src/telegram_scanner -> project root
        self.db_path = self.base_dir / self.database_name
        self.session_path = self.base_dir / f"{self.session_name}.session"

    def _get_str_env(self, key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
        """Получить строковую переменную окружения"""
        value = os.getenv(key, default)
        if required and not value:
            raise ValueError(f"Переменная окружения {key} обязательна для заполнения")
        return value

    def _get_int_env(self, key: str, default: int, required: bool = False) -> int:
        """Получить целочисленную переменную окружения"""
        value = os.getenv(key)
        if value is None:
            if required:
                raise ValueError(f"Переменная окружения {key} обязательна для заполнения")
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Переменная окружения {key} должна быть целым числом")

    def _get_float_env(self, key: str, default: float, required: bool = False) -> float:
        """Получить переменную окружения типа float"""
        value = os.getenv(key)
        if value is None:
            if required:
                raise ValueError(f"Переменная окружения {key} обязательна для заполнения")
            return default
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Переменная окружения {key} должна быть числом")

    def _get_bool_env(self, key: str, default: bool) -> bool:
        """Получить булеву переменную окружения"""
        value = os.getenv(key, str(default)).lower()
        return value in ('true', '1', 'yes', 'on')

    def validate(self) -> bool:
        """Проверить корректность конфигурации"""
        errors = []

        # Проверка API настроек
        if not self.api_id or self.api_id <= 0:
            errors.append("API_ID должен быть положительным числом")

        if not self.api_hash or len(self.api_hash) < 32:
            errors.append("API_HASH должен быть строкой не менее 32 символов")

        if not self.phone_number:
            errors.append("PHONE_NUMBER обязателен для заполнения")

        # Проверка настроек производительности
        if self.batch_size <= 0 or self.batch_size > 10000:
            errors.append("BATCH_SIZE должен быть в диапазоне 1-10000")

        if self.request_delay <= 0:
            errors.append("REQUEST_DELAY должен быть положительным числом")

        if self.checkpoint_interval <= 0:
            errors.append("CHECKPOINT_INTERVAL должен быть положительным числом")

        if errors:
            print("Ошибка в конфигурации:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True

    def print_config(self):
        """Вывести текущую конфигурацию"""
        print("\n=== Текущая конфигурация ===")
        print(f"API ID: {self.api_id}")
        print(f"API Hash: {'*' * len(self.api_hash)}")
        print(f"Phone Number: {self.phone_number}")
        print(f"Database: {self.database_name}")
        print(f"Batch Size: {self.batch_size}")
        print(f"Checkpoint Interval: {self.checkpoint_interval}")
        print(f"Request Delay: {self.request_delay:.3f}s")
        print(f"Delete Batch Size: {self.delete_batch_size}")
        print(f"Delete Delay: {self.delete_delay}s")
        print(f"Delete Confirmation: {self.delete_confirmation}")
        print("=" * 30 + "\n")


# Глобальный экземпляр конфигурации
config = Config()