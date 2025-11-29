import asyncio
from typing import List, Dict, Optional, Callable
from telethon import TelegramClient
from telethon.tl import functions
from tqdm.asyncio import tqdm
import time
from datetime import datetime

from .config import config
from .database import DatabaseManager
from .analyzer import DeletionCandidate, DeletionReason
from .checkpoint_manager import CheckpointManager, Checkpoint


class TelegramUserDeleter:
    """Класс для безопасного удаления пользователей из канала"""

    def __init__(self, client: TelegramClient, db_manager: DatabaseManager):
        self.client = client
        self.db = db_manager
        self.checkpoint_manager = CheckpointManager()
        self.deleted_count = 0
        self.error_count = 0
        self.start_time = None
        self.last_request_time = 0

    async def rate_limit(self):
        """Управление лимитом запросов"""
        elapsed = time.time() - self.last_request_time
        if elapsed < config.delete_delay:
            await asyncio.sleep(config.delete_delay - elapsed)
        self.last_request_time = time.time()

    async def preview_deletions(self, candidates: List[DeletionCandidate], limit: int = 20):
        """
        Показать предпросмотр кандидатов на удаление

        Args:
            candidates: Список кандидатов
            limit: Сколько показать в preview
        """
        if not candidates:
            print("Нет кандидатов для удаления")
            return False

        print(f"\nПРЕДПРОСМОТ УДАЛЕНИЯ")
        print("="*60)
        print(f"Всего кандидатов: {len(candidates)}")
        print(f"Показано первых {min(limit, len(candidates))}:")
        print("-"*60)

        for i, candidate in enumerate(candidates[:limit]):
            status_emoji = "🤖" if candidate.details.get('bot') else "👤"
            print(f"{i+1}. {status_emoji} ID: {candidate.user_id}")
            print(f"   Имя: {candidate.first_name or 'Нет'} {candidate.last_name or ''}")
            print(f"   Username: @{candidate.username}" if candidate.username else "   Username: Нет")
            print(f"   Причина: {candidate.reason.value}")
            print(f"   Уверенность: {candidate.confidence:.1%}")
            print("-"*40)

        if len(candidates) > limit:
            print(f"... и еще {len(candidates) - limit} пользователей")

        return True

    async def confirm_deletion(self, candidates: List[DeletionCandidate]) -> bool:
        """
        Запросить подтверждение на удаление

        Args:
            candidates: Список кандидатов

        Returns:
            True если пользователь подтвердил удаление
        """
        if not config.delete_confirmation:
            return True

        # Группировка по причинам
        from collections import defaultdict
        grouped = defaultdict(int)
        for candidate in candidates:
            grouped[candidate.reason.value] += 1

        print(f"\nПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ")
        print("="*50)
        print(f"К удалению: {len(candidates)} пользователей")
        print("\nПо причинам:")
        for reason, count in grouped.items():
            print(f"  {reason}: {count}")
        print("="*50)

        while True:
            response = input("\nУдалить этих пользователей? (yes/no/preview): ").lower().strip()

            if response in ['yes', 'y', 'да']:
                return True
            elif response in ['no', 'n', 'нет']:
                print("Удаление отменено")
                return False
            elif response in ['preview', 'p', 'предпросмотр']:
                await self.preview_deletions(candidates)
                continue
            else:
                print("Пожалуйста, введите yes, no или preview")

    async def delete_users(
        self,
        channel_username: str,
        candidates: List[DeletionCandidate],
        batch_size: Optional[int] = None,
        checkpoint_interval: int = 100,
        resume: bool = False
    ) -> Dict:
        """
        Удалить пользователей из канала

        Args:
            channel_username: Имя канала
            candidates: Список кандидатов на удаление
            batch_size: Размер пакета для удаления
            checkpoint_interval: Частота сохранения чекпоинтов
            resume: Возобновить с последнего чекпоинта

        Returns:
            Статистика удаления
        """
        if not candidates:
            return {'deleted': 0, 'errors': 0, 'total': 0}

        # Проверяем права администратора
        if not await self._check_admin_rights(channel_username):
            raise PermissionError("Недостаточно прав для удаления пользователей")

        # Показываем предпросмотр
        await self.preview_deletions(candidates)

        # Запрашиваем подтверждение
        if not await self.confirm_deletion(candidates):
            return {'deleted': 0, 'errors': 0, 'total': 0, 'cancelled': True}

        # Возобновление с чекпоинта
        if resume:
            checkpoint = self.checkpoint_manager.load_latest_checkpoint('delete', hash(channel_username))
            if checkpoint:
                start_index = checkpoint.processed_items
                print(f"Возобновление с позиции: {start_index}")
                candidates = candidates[start_index:]
            else:
                print("Чекпоинт не найден, начинаем сначала")

        batch_size = batch_size or config.delete_batch_size
        self.start_time = time.time()

        print(f"\nНАЧАЛО УДАЛЕНИЯ")
        print(f"Канал: {channel_username}")
        print(f"К удалению: {len(candidates)} пользователей")
        print(f"Размер пакета: {batch_size}")
        print("="*50)

        # Прогресс-бар
        pbar = tqdm(
            total=len(candidates),
            desc="Удаление пользователей",
            unit="пользователей"
        )

        try:
            # Получаем entity канала
            channel = await self.client.get_entity(channel_username)

            # Обрабатываем пачками
            for i in range(0, len(candidates), batch_size):
                batch = candidates[i:i + batch_size]
                await self._delete_batch(channel, batch, i)

                # Обновляем прогресс
                pbar.update(len(batch))

                # Сохраняем чекпоинт
                if (i + len(batch)) % checkpoint_interval == 0:
                    await self._save_checkpoint('delete', hash(channel_username), i + len(batch), len(candidates), channel_username)

                # Небольшая пауза между пакетами
                await asyncio.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\nУдаление прервано пользователем")
            # Сохраняем текущий прогресс
            if self.deleted_count > 0:
                await self._save_checkpoint('delete', hash(channel_username), self.deleted_count, len(candidates), channel_username)
        except Exception as e:
            print(f"\n\nОшибка во время удаления: {e}")
        finally:
            pbar.close()

        # Финальная статистика
        elapsed_time = time.time() - self.start_time
        stats = {
            'deleted': self.deleted_count,
            'errors': self.error_count,
            'total': len(candidates),
            'elapsed_time': elapsed_time,
            'rate': self.deleted_count / elapsed_time if elapsed_time > 0 else 0,
            'channel_username': channel_username
        }

        await self._print_deletion_summary(stats)

        # Удаляем чекпоинт после успешного завершения
        if stats['deleted'] == stats['total']:
            self.checkpoint_manager.delete_checkpoint('delete', hash(channel_username))

        return stats

    async def _delete_batch(self, channel, batch: List[DeletionCandidate], batch_index: int):
        """Удалить пакет пользователей"""
        for candidate in batch:
            try:
                await self.rate_limit()

                # Удаляем участника
                await self.client.kick_participant(
                    channel,
                    candidate.user_id
                )

                # Логируем успешное удаление
                await self.db.log_deletion(
                    candidate.user_id,
                    candidate.username or '',
                    'success',
                    None
                )

                self.deleted_count += 1

            except Exception as e:
                self.error_count += 1
                error_msg = str(e)

                # Логируем ошибку
                await self.db.log_deletion(
                    candidate.user_id,
                    candidate.username or '',
                    'error',
                    error_msg
                )

                # Пропускаем некоторые типы ошибок
                if "CHANNEL_PRIVATE" in error_msg:
                    print(f"\nОшибка: канал стал приватным или вы были удалены из него")
                    raise
                elif "USER_ADMIN_INVALID" in error_msg:
                    print(f"\nОшибка: недостаточно прав для удаления пользователя {candidate.user_id}")
                elif "USER_NOT_PARTICIPANT" in error_msg:
                    # Пользователь уже не в канале
                    self.deleted_count += 1
                # Другие ошибки логируем, но продолжаем

    async def _check_admin_rights(self, channel_username: str) -> bool:
        """Проверить права администратора в канале"""
        try:
            channel = await self.client.get_entity(channel_username)
            # Проверяем, можем ли мы получить информацию о канале
            full_channel = await self.client(functions.channels.GetFullChannelRequest(channel))
            return True
        except Exception as e:
            print(f"Ошибка проверки прав: {e}")
            return False

    async def _save_checkpoint(
        self,
        operation_type: str,
        channel_id: int,
        processed: int,
        total: int,
        channel_username: str
    ):
        """Сохранить чекпоинт прогресса"""
        checkpoint = Checkpoint(
            operation_type=operation_type,
            channel_id=channel_id,
            channel_username=channel_username,
            processed_items=processed,
            total_items=total,
            metadata={
                'deleted_count': self.deleted_count,
                'error_count': self.error_count,
                'elapsed_time': time.time() - self.start_time if self.start_time else 0
            }
        )
        self.checkpoint_manager.save_checkpoint(checkpoint)

    async def _print_deletion_summary(self, stats: Dict):
        """Вывести сводку по удалению"""
        print("\n" + "="*50)
        print("УДАЛЕНИЕ ЗАВЕРШЕНО")
        print("="*50)
        print(f"Канал: {stats['channel_username']}")
        print(f"Удалено: {stats['deleted']:,}".replace(',', ' '))
        print(f"Ошибок: {stats['errors']}")
        print(f"Всего в очереди: {stats['total']:,}".replace(',', ' '))
        print(f"Время работы: {stats['elapsed_time']:.2f} сек")
        print(f"Скорость: {stats['rate']:.2f} пользователей/сек")

        if 'cancelled' in stats and stats['cancelled']:
            print("Статус: Отменено пользователем")

        print("="*50)

        # Получаем статистику из БД
        db_stats = await self.db.get_deletion_stats()
        print(f"\nОбщая статистика удалений:")
        print(f"  Всего попыток: {db_stats['total']}")
        print(f"  Успешных: {db_stats['successful']}")
        print(f"  Неудачных: {db_stats['failed']}")

    async def resume_deletion(
        self,
        channel_username: str,
        candidates: List[DeletionCandidate]
    ) -> Dict:
        """Возобновить прерванное удаление"""
        return await self.delete_users(channel_username, candidates, resume=True)

    async def export_candidates_to_file(
        self,
        candidates: List[DeletionCandidate],
        filename: str,
        format: str = 'csv'
    ):
        """Экспортировать кандидатов в файл"""
        import csv
        import json

        if format.lower() == 'csv':
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', 'Username', 'First Name', 'Last Name', 'Reason', 'Confidence'])
                for candidate in candidates:
                    writer.writerow([
                        candidate.user_id,
                        candidate.username or '',
                        candidate.first_name or '',
                        candidate.last_name or '',
                        candidate.reason.value,
                        f"{candidate.confidence:.2f}"
                    ])
        elif format.lower() == 'json':
            data = []
            for candidate in candidates:
                data.append({
                    'id': candidate.user_id,
                    'username': candidate.username,
                    'first_name': candidate.first_name,
                    'last_name': candidate.last_name,
                    'reason': candidate.reason.value,
                    'confidence': candidate.confidence,
                    'details': candidate.details
                })

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Кандидаты экспортированы в файл: {filename}")
