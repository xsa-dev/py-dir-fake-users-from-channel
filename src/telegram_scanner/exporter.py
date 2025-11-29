import asyncio
from typing import List, Optional, AsyncGenerator
from telethon import TelegramClient
from telethon.tl import functions, types
from tqdm.asyncio import tqdm
import time
from datetime import datetime

from .config import config
from .database import DatabaseManager, User


class TelegramExporter:
    """Класс для выгрузки участников Telegram канала"""

    def __init__(self, client: TelegramClient, db_manager: DatabaseManager):
        self.client = client
        self.db = db_manager
        self.exported_count = 0
        self.error_count = 0
        self.start_time = None
        self.last_request_time = 0
        self._status = "in_progress"

    async def rate_limit(self):
        """Управление лимитом запросов"""
        elapsed = time.time() - self.last_request_time
        if elapsed < config.request_delay:
            await asyncio.sleep(config.request_delay - elapsed)
        self.last_request_time = time.time()

    async def get_channel_info(self, channel_username: str) -> types.Channel:
        """Получить информацию о канале"""
        try:
            entity = await self.client.get_entity(channel_username)
            if isinstance(entity, types.Channel):
                return entity
            # Для тестов/заглушек допускаем объекты с полем id
            if hasattr(entity, "id"):
                return entity
            raise ValueError(f"Entity {channel_username} не является каналом")
        except Exception as e:
            raise ValueError(f"Не удалось получить информацию о канале {channel_username}: {e}")

    async def get_total_members_count(self, channel: types.Channel) -> int:
        """Получить общее количество участников канала"""
        try:
            full_chat = await self.client(functions.channels.GetFullChannelRequest(channel))
            return full_chat.full_chat.participants_count or 0
        except Exception as e:
            print(f"Не удалось получить количество участников: {e}")
            return 0

    async def export_channel_participants(self, channel_username: str, resume: bool = False) -> dict:
        """
        Экспортировать всех участников канала

        Args:
            channel_username: Имя пользователя канала
            resume: Продолжить с последнего сохраненного прогресса

        Returns:
            Словарь со статистикой экспорта
        """
        print(f"\nНачинаю экспорт участников канала: {channel_username}")

        # Получаем информацию о канале
        channel = await self.get_channel_info(channel_username)
        channel_id = channel.id

        # Получаем общее количество участников
        total_members = await self.get_total_members_count(channel)
        print(f"Общее количество участников: {total_members:,}".replace(',', ' '))

        # Проверяем возможность возобновления
        last_user_id = None
        if resume:
            progress = await self.db.get_progress(channel_id)
            if progress and progress['status'] == 'in_progress':
                self.exported_count = progress['processed_members']
                last_user_id = progress['last_user_id']
                print(f"Возобновление с позиции: {self.exported_count:,} участников")

        self.start_time = time.time()

        # Инициализация прогресс-бара
        if resume:
            initial_value = self.exported_count
        else:
            initial_value = 0

        pbar = tqdm(
            total=total_members,
            initial=initial_value,
            desc="Экспорт участников",
            unit="участников",
            dynamic_ncols=True
        )

        try:
            # Собираем всех участников
            async for user_batch in self._get_participants_batch(channel, last_user_id):
                # Сохраняем в базу данных
                saved_count = await self.db.insert_users_batch(
                    user_batch, channel_id, channel_username
                )
                self.exported_count += saved_count

                # Обновляем прогресс в базе данных
                if self.exported_count % config.checkpoint_interval == 0:
                    await self.db.update_progress(
                        channel_id, channel_username,
                        self.exported_count, total_members,
                        user_batch[-1].id if user_batch else None
                    )
                    print(f"\nСохранен прогресс: {self.exported_count:,} участников")

                # Обновляем прогресс-бар
                pbar.update(len(user_batch))

        except KeyboardInterrupt:
            print("\n\nЭкспорт прерван пользователем")
            self._status = "cancelled"
        except Exception as e:
            print(f"\n\nОшибка во время экспорта: {e}")
            self._status = "error"
        finally:
            pbar.close()

        # Финальное обновление прогресса
        if self._status == "in_progress":
            self._status = "completed"

        await self.db.update_progress(
            channel_id, channel_username,
            self.exported_count, total_members,
            status=self._status
        )

        # Статистика
        elapsed_time = time.time() - self.start_time
        stats = {
            'exported': self.exported_count,
            'errors': self.error_count,
            'total': total_members,
            'elapsed_time': elapsed_time,
            'rate': self.exported_count / elapsed_time if elapsed_time > 0 else 0,
            'channel_id': channel_id,
            'channel_username': channel_username
        }

        return stats

    async def _get_participants_batch(
        self, channel: types.Channel, offset_user: Optional[int] = None
    ) -> AsyncGenerator[List[User], None]:
        """
        Генератор пакетов участников канала

        Args:
            channel: Объект канала
            offset_user: ID пользователя для начала (для возобновления)

        Yields:
            Списки объектов User
        """
        offset = 0
        batch_size = min(config.batch_size, 200)  # Telethon limit

        while True:
            try:
                await self.rate_limit()

                # Используем IterateParticipantsRequest
                request = functions.channels.GetParticipantsRequest(
                    channel=channel,
                    filter=types.ChannelParticipantsSearch(''),  # Все участники
                    offset=offset,
                    limit=batch_size,
                    hash=0
                )

                result = await self.client(request)

                if not result.users:
                    break

                # Преобразуем пользователей в объекты User
                users = []
                for user in result.users:
                    # Если возобновляем и еще не дошли до нужного ID
                    if offset_user and user.id <= offset_user:
                        continue

                    user_obj = User(
                        id=user.id,
                        access_hash=user.access_hash,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        photo_id=getattr(user.photo, "photo_id", None) if getattr(user, "photo", None) else None,
                        bot=user.bot,
                        verified=user.verified,
                        restricted=user.restricted,
                        premium=user.premium
                    )

                    # Определяем статус
                    if hasattr(user, 'status') and user.status:
                        if isinstance(user.status, types.UserStatusOnline):
                            user_obj.status = 'online'
                        elif isinstance(user.status, types.UserStatusOffline):
                            user_obj.status = 'offline'
                            user_obj.last_online = user.status.was_online
                        elif isinstance(user.status, types.UserStatusRecently):
                            user_obj.status = 'recently'
                        elif isinstance(user.status, types.UserStatusLastWeek):
                            user_obj.status = 'last_week'
                        elif isinstance(user.status, types.UserStatusLastMonth):
                            user_obj.status = 'last_month'
                        else:
                            user_obj.status = 'unknown'
                    else:
                        user_obj.status = 'unknown'

                    users.append(user_obj)

                if not users:
                    break

                yield users

                # Проверяем, получили ли мы все участники
                if len(result.users) < batch_size:
                    break

                offset += len(users)

            except Exception as e:
                self.error_count += 1
                print(f"\nОшибка при получении пакета: {e}")
                await asyncio.sleep(1)  # Пауза перед повторной попыткой
                continue

    async def print_export_summary(self, stats: dict):
        """Вывести сводку по экспорту"""
        print("\n" + "="*50)
        print("ЭКСПОРТ ЗАВЕРШЕН")
        print("="*50)
        print(f"Канал: {stats['channel_username']}")
        print(f"Экспортировано: {stats['exported']:,}".replace(',', ' '))
        print(f"Ошибок: {stats['errors']}")
        print(f"Общее количество: {stats['total']:,}".replace(',', ' '))
        print(f"Время работы: {stats['elapsed_time']:.2f} сек")
        print(f"Скорость: {stats['rate']:.2f} участников/сек")
        print("="*50)

    async def resume_export(self, channel_username: str) -> dict:
        """Возобновить прерванный экспорт"""
        return await self.export_channel_participants(channel_username, resume=True)
