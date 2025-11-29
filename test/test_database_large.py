import os
import tempfile
import unittest
from pathlib import Path

from telegram_scanner.analyzer import DeletedUserAnalyzer
from telegram_scanner.database import DatabaseManager, User


def build_user(user_id: int, deleted: bool, channel_id: int, channel_username: str) -> User:
    """Создать тестового пользователя."""
    first_name = "Deleted" if deleted else f"User{user_id}"
    last_name = "Account" if deleted else f"LN{user_id}"
    username = None if deleted else f"user{user_id}"
    photo_id = user_id * 100 if not deleted else None

    return User(
        id=user_id,
        access_hash=user_id * 10 + 1,
        username=username,
        first_name=first_name,
        last_name=last_name,
        photo_id=photo_id,
        bot=False,
        verified=False,
        restricted=False,
        premium=False,
    )


class TestDatabaseLargeVolumes(unittest.IsolatedAsyncioTestCase):
    """Проверка сохранения и анализа больших объемов пользователей."""

    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.db = DatabaseManager(str(self.db_path))
        await self.db.init_database()
        self.analyzer = DeletedUserAnalyzer(self.db)
        self.channel_id = 123
        self.channel_username = "@test"

    async def asyncTearDown(self):
        await self.db.close() if hasattr(self.db, "close") else None
        self.tmpdir.cleanup()

    async def _insert_users(self, total_users: int, deleted_ids: set[int], batch_size: int):
        """Записать пользователей пачками, не держа все в памяти."""
        for start in range(1, total_users + 1, batch_size):
            end = min(start + batch_size, total_users + 1)
            users = [
                build_user(uid, deleted=uid in deleted_ids, channel_id=self.channel_id, channel_username=self.channel_username)
                for uid in range(start, end)
            ]
            await self.db.insert_users_batch(users, self.channel_id, self.channel_username)

    async def _assert_deleted_found(self, expected_deleted_ids: set[int]):
        candidates = await self.analyzer.find_deleted_accounts(channel_id=self.channel_id)
        found_ids = {c.user_id for c in candidates}
        self.assertTrue(expected_deleted_ids.issubset(found_ids))

    async def test_save_and_parse_10k_users(self):
        total = 10_000
        deleted_ids = {1, 2, 3, 4, 5, 9999, 10_000}
        await self._insert_users(total_users=total, deleted_ids=deleted_ids, batch_size=2_000)

        count = await self.db.get_total_users_count(channel_id=self.channel_id)
        self.assertEqual(count, total)
        await self._assert_deleted_found(deleted_ids)

    @unittest.skipUnless(os.getenv("RUN_HEAVY_TESTS") == "1", "Установите RUN_HEAVY_TESTS=1 для запуска теста на 2М записей")
    async def test_save_and_parse_2m_users(self):
        total = 2_000_000
        deleted_ids = {1, 2, 3, 4, 5}
        await self._insert_users(total_users=total, deleted_ids=deleted_ids, batch_size=50_000)

        count = await self.db.get_total_users_count(channel_id=self.channel_id)
        self.assertEqual(count, total)
        await self._assert_deleted_found(deleted_ids)
