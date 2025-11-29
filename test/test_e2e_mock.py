import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from telethon.tl import functions

from telegram_scanner.config import config
from telegram_scanner.database import DatabaseManager, User
from telegram_scanner.exporter import TelegramExporter
from telegram_scanner.analyzer import DeletedUserAnalyzer
from telegram_scanner.deleter import TelegramUserDeleter
from telegram_scanner.checkpoint_manager import CheckpointManager


class FakeUser:
    """Минимальная заглушка пользователя Telethon."""

    def __init__(self, *, user_id: int, access_hash: int, username, first_name, last_name, deleted: bool = False):
        self.id = user_id
        self.access_hash = access_hash
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.bot = False
        self.verified = False
        self.restricted = False
        self.premium = False
        self.status = None
        self.photo = None
        if deleted:
            # Имитируем удаленный аккаунт (нет username/имени)
            self.username = None
            self.first_name = "Deleted"
            self.last_name = "Account"


class FakeClient:
    """Заглушка TelegramClient для e2e теста без сети."""

    def __init__(self, users, channel_id=1234, channel_username="@test"):
        self.users = list(users)
        self.channel_id = channel_id
        self.channel_username = channel_username
        self.kicked = []

    async def connect(self):
        return True

    async def disconnect(self):
        return True

    async def is_user_authorized(self):
        return True

    async def get_entity(self, username):
        return SimpleNamespace(id=self.channel_id, title=username, username=username)

    async def __call__(self, request):
        # Количество участников
        if isinstance(request, functions.channels.GetFullChannelRequest):
            return SimpleNamespace(full_chat=SimpleNamespace(participants_count=len(self.users)))

        # Пагинация по участникам
        if isinstance(request, functions.channels.GetParticipantsRequest):
            offset = getattr(request, "offset", 0)
            limit = getattr(request, "limit", 0) or len(self.users)
            slice_users = self.users[offset : offset + limit]
            return SimpleNamespace(users=slice_users)

        raise NotImplementedError(f"Unexpected request: {request}")

    async def kick_participant(self, channel, user_id):
        self.kicked.append(user_id)
        return True


class TestE2EMock(unittest.IsolatedAsyncioTestCase):
    """End-to-end тест без сети на экспорт → анализ → удаление."""

    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "e2e.db"
        self.checkpoints_dir = Path(self.tmpdir.name) / "checkpoints"
        self.checkpoints_dir.mkdir(exist_ok=True)

        # Подготавливаем фейковые данные
        self.channel_username = "@test_channel"
        self.channel_id = 999
        base_users = [
            FakeUser(user_id=1, access_hash=11, username="active1", first_name="Active", last_name="User"),
            FakeUser(user_id=2, access_hash=22, username="active2", first_name="Active", last_name="User"),
            FakeUser(user_id=3, access_hash=33, username=None, first_name="Deleted", last_name="Account", deleted=True),
            FakeUser(user_id=4, access_hash=44, username=None, first_name="Deleted", last_name="Account", deleted=True),
            FakeUser(user_id=5, access_hash=55, username="maybe", first_name="Maybe", last_name="User"),
        ]
        self.fake_client = FakeClient(base_users, channel_id=self.channel_id, channel_username=self.channel_username)

        # DB и менеджеры
        self.db = DatabaseManager(str(self.db_path))
        await self.db.init_database()
        self.exporter = TelegramExporter(self.fake_client, self.db)
        self.analyzer = DeletedUserAnalyzer(self.db)
        self.deleter = TelegramUserDeleter(self.fake_client, self.db)
        # Изолируем чекпоинты
        self.deleter.checkpoint_manager = CheckpointManager(str(self.checkpoints_dir))

        # Убираем подтверждение удаления
        self._old_delete_confirmation = config.delete_confirmation
        config.delete_confirmation = False

    async def asyncTearDown(self):
        config.delete_confirmation = self._old_delete_confirmation
        await self.db.close() if hasattr(self.db, "close") else None
        self.tmpdir.cleanup()

    async def test_export_analyze_delete_flow(self):
        # Экспорт
        stats = await self.exporter.export_channel_participants(self.channel_username)
        self.assertEqual(stats["exported"], len(self.fake_client.users))
        self.assertEqual(stats["channel_id"], self.channel_id)

        # Анализ
        candidates = await self.analyzer.find_deleted_accounts(channel_id=self.channel_id)
        deleted_ids = {c.user_id for c in candidates}
        self.assertSetEqual(deleted_ids, {3, 4})

        # Удаление (без подтверждений)
        delete_stats = await self.deleter.delete_users(self.channel_username, candidates)
        self.assertFalse(delete_stats.get("cancelled"))
        # Перенос в deleted_users
        await self.db.mark_users_as_deleted([c.user_id for c in candidates])

        total_left = await self.db.get_total_users_count(channel_id=self.channel_id)
        self.assertEqual(total_left, len(self.fake_client.users) - len(deleted_ids))

        # Проверяем что записи перенесены
        import aiosqlite

        async with aiosqlite.connect(self.db.db_name) as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM deleted_users WHERE id IN (3,4)")
            count_deleted = (await cur.fetchone())[0]
        self.assertEqual(count_deleted, len(deleted_ids))


if __name__ == "__main__":
    asyncio.run(unittest.main())
