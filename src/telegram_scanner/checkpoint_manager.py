import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class Checkpoint:
    """Класс для хранения информации о чекпоинте"""
    operation_type: str  # 'export', 'analyze', 'delete'
    channel_id: int
    channel_username: str
    processed_items: int
    total_items: int
    last_id: Optional[int] = None
    timestamp: str = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}


class CheckpointManager:
    """Менеджер для сохранения и загрузки чекпоинтов"""

    def __init__(self, checkpoints_dir: str = "checkpoints"):
        self.checkpoints_dir = Path(checkpoints_dir)
        self.checkpoints_dir.mkdir(exist_ok=True)

    def save_checkpoint(self, checkpoint: Checkpoint) -> str:
        """
        Сохранить чекпоинт

        Args:
            checkpoint: Объект чекпоинта

        Returns:
            Имя файла чекпоинта
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{checkpoint.operation_type}_{checkpoint.channel_id}_{timestamp}.json"
        filepath = self.checkpoints_dir / filename

        checkpoint.timestamp = datetime.now().isoformat()

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(checkpoint), f, indent=2, ensure_ascii=False)

        # Также сохраняем последний чекпоинт для данной операции
        latest_filename = f"latest_{checkpoint.operation_type}_{checkpoint.channel_id}.json"
        latest_filepath = self.checkpoints_dir / latest_filename

        with open(latest_filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(checkpoint), f, indent=2, ensure_ascii=False)

        return str(filepath)

    def load_latest_checkpoint(self, operation_type: str, channel_id: int) -> Optional[Checkpoint]:
        """
        Загрузить последний чекпоинт для операции

        Args:
            operation_type: Тип операции
            channel_id: ID канала

        Returns:
            Объект чекпоинта или None
        """
        filename = f"latest_{operation_type}_{channel_id}.json"
        filepath = self.checkpoints_dir / filename

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Checkpoint(**data)
        except Exception as e:
            print(f"Ошибка загрузки чекпоинта: {e}")
            return None

    def load_all_checkpoints(self, operation_type: Optional[str] = None) -> list:
        """
        Загрузить все чекпоинты

        Args:
            operation_type: Фильтр по типу операции

        Returns:
            Список чекпоинтов
        """
        checkpoints = []

        for file_path in self.checkpoints_dir.glob("*.json"):
            if file_path.name.startswith("latest_"):
                continue

            if operation_type and not file_path.name.startswith(f"{operation_type}_"):
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                checkpoints.append(Checkpoint(**data))
            except Exception as e:
                print(f"Ошибка загрузки чекпоинта {file_path}: {e}")

        return sorted(checkpoints, key=lambda x: x.timestamp, reverse=True)

    def delete_checkpoint(self, operation_type: str, channel_id: int, timestamp: str = None):
        """
        Удалить чекпоинт

        Args:
            operation_type: Тип операции
            channel_id: ID канала
            timestamp: Временная метка чекпоинта
        """
        if timestamp:
            filename = f"{operation_type}_{channel_id}_{timestamp}.json"
            filepath = self.checkpoints_dir / filename
            if filepath.exists():
                filepath.unlink()

        # Удаляем latest чекпоинт
        latest_filename = f"latest_{operation_type}_{channel_id}.json"
        latest_filepath = self.checkpoints_dir / latest_filename
        if latest_filepath.exists():
            latest_filepath.unlink()

    def clean_old_checkpoints(self, keep_count: int = 5):
        """
        Очистить старые чекпоинты, оставив только последние

        Args:
            keep_count: Сколько последних чекпоинтов оставить
        """
        checkpoints = self.load_all_checkpoints()

        # Группируем по operation_type и channel_id
        grouped = {}
        for checkpoint in checkpoints:
            key = (checkpoint.operation_type, checkpoint.channel_id)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(checkpoint)

        # Оставляем только последние keep_count для каждой группы
        for (op_type, channel_id), cp_list in grouped.items():
            cp_list.sort(key=lambda x: x.timestamp, reverse=True)
            for checkpoint in cp_list[keep_count:]:
                self.delete_checkpoint(
                    checkpoint.operation_type,
                    checkpoint.channel_id,
                    checkpoint.timestamp.replace(':', '').replace('-', '')
                )

    def get_progress_percentage(self, checkpoint: Checkpoint) -> float:
        """Получить процент выполнения"""
        if checkpoint.total_items == 0:
            return 0.0
        return (checkpoint.processed_items / checkpoint.total_items) * 100

    def print_checkpoint_info(self, checkpoint: Checkpoint):
        """Вывести информацию о чекпоинте"""
        print(f"\nЧекпоинт: {checkpoint.operation_type}")
        print(f"Канал: {checkpoint.channel_username}")
        print(f"Прогресс: {checkpoint.processed_items:,} / {checkpoint.total_items:,} "
              f"({self.get_progress_percentage(checkpoint):.1f}%)")
        print(f"Время: {checkpoint.timestamp}")
        if checkpoint.metadata:
            print("Дополнительная информация:")
            for key, value in checkpoint.metadata.items():
                print(f"  {key}: {value}")

    def save_batch_data(self, data: Any, filename: str) -> str:
        """
        Сохранить пакет данных (pickle для сложных объектов)

        Args:
            data: Данные для сохранения
            filename: Имя файла

        Returns:
            Путь к файлу
        """
        filepath = self.checkpoints_dir / filename
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
        return str(filepath)

    def load_batch_data(self, filename: str) -> Any:
        """
        Загрузить пакет данных

        Args:
            filename: Имя файла

        Returns:
            Загруженные данные
        """
        filepath = self.checkpoints_dir / filename
        with open(filepath, 'rb') as f:
            return pickle.load(f)

    def list_checkpoints(self) -> Dict[str, list]:
        """
        Показать все доступные чекпоинты

        Returns:
            Словарь с чекпоинтами по типам операций
        """
        checkpoints = self.load_all_checkpoints()
        grouped = {}

        for checkpoint in checkpoints:
            if checkpoint.operation_type not in grouped:
                grouped[checkpoint.operation_type] = []
            grouped[checkpoint.operation_type].append(checkpoint)

        return grouped