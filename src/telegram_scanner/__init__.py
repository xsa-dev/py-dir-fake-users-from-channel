"""
Telegram Channel Users Scanner and Cleaner

Инструмент для сканирования и удаления удаленных аккаунтов из Telegram каналов.
Оптимизирован для работы с каналами с миллионами подписчиков.
"""

__version__ = "0.1.0"
__author__ = "Telegram Scanner Team"

from .main import TelegramScannerApp
from .config import config
from .database import DatabaseManager, User
from .exporter import TelegramExporter
from .analyzer import DeletedUserAnalyzer, DeletionCandidate, DeletionReason
from .deleter import TelegramUserDeleter
from .reporter import ReportGenerator
from .checkpoint_manager import CheckpointManager, Checkpoint

__all__ = [
    "TelegramScannerApp",
    "config",
    "DatabaseManager",
    "User",
    "TelegramExporter",
    "DeletedUserAnalyzer",
    "DeletionCandidate",
    "DeletionReason",
    "TelegramUserDeleter",
    "ReportGenerator",
    "CheckpointManager",
    "Checkpoint",
]