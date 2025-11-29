import sqlite3
import aiosqlite
from datetime import datetime
from typing import List, Dict, Optional, AsyncGenerator
from dataclasses import dataclass, asdict


@dataclass
class User:
    id: int
    access_hash: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    photo_id: Optional[int] = None
    bot: bool = False
    verified: bool = False
    restricted: bool = False
    status: Optional[str] = None
    last_online: Optional[datetime] = None
    premium: bool = False
    added_date: Optional[datetime] = None

    def to_tuple(self) -> tuple:
        return (
            self.id,
            self.access_hash,
            self.username,
            self.first_name,
            self.last_name,
            self.photo_id,
            self.bot,
            self.verified,
            self.restricted,
            self.status,
            self.last_online.isoformat() if self.last_online else None,
            self.premium,
            datetime.now().isoformat()
        )


class DatabaseManager:
    def __init__(self, db_name: str = "channel_users.db"):
        self.db_name = db_name
        self.connection = None
        self._schema_upgraded = False

    async def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    access_hash INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    photo_id INTEGER,
                    bot BOOLEAN DEFAULT FALSE,
                    verified BOOLEAN DEFAULT FALSE,
                    restricted BOOLEAN DEFAULT FALSE,
                    status TEXT,
                    last_online TEXT,
                    premium BOOLEAN DEFAULT FALSE,
                    added_date TEXT,
                    channel_id INTEGER,
                    channel_username TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_last_name ON users(last_name)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_bot ON users(bot)")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS deleted_users (
                    id INTEGER PRIMARY KEY,
                    access_hash INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    photo_id INTEGER,
                    bot BOOLEAN DEFAULT FALSE,
                    status TEXT,
                    last_online TEXT,
                    channel_id INTEGER,
                    channel_username TEXT,
                    deletion_reason TEXT,
                    found_at TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_deleted_users_first_name ON deleted_users(first_name)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_deleted_users_last_name ON deleted_users(last_name)")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS export_progress (
                    channel_id INTEGER PRIMARY KEY,
                    channel_username TEXT,
                    total_members INTEGER,
                    processed_members INTEGER DEFAULT 0,
                    last_user_id INTEGER,
                    last_date TEXT,
                    status TEXT DEFAULT 'in_progress',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS deletion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    deletion_time TEXT,
                    status TEXT,
                    error_message TEXT
                )
            """)

            await db.commit()

        # Попытка добавить недостающие столбцы для существующих БД
        if not self._schema_upgraded:
            await self._upgrade_schema()
            self._schema_upgraded = True

    async def _upgrade_schema(self):
        """Добавить новые столбцы, если они отсутствуют."""
        async with aiosqlite.connect(self.db_name) as db:
            for table in ("users", "deleted_users"):
                try:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN photo_id INTEGER")
                except Exception:
                    pass
            await db.commit()

    async def insert_users_batch(self, users: List[User], channel_id: int, channel_username: str) -> int:
        """Пакетная вставка пользователей"""
        if not users:
            return 0

        async with aiosqlite.connect(self.db_name) as db:
            values = [
                (*user.to_tuple(), channel_id, channel_username)
                for user in users
            ]

            await db.executemany("""
                INSERT OR REPLACE INTO users (
                    id, access_hash, username, first_name, last_name,
                    photo_id, bot, verified, restricted, status, last_online,
                    premium, added_date, channel_id, channel_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values)

            await db.commit()
            return len(users)

    async def get_total_users_count(self, channel_id: Optional[int] = None) -> int:
        """Получить общее количество пользователей"""
        async with aiosqlite.connect(self.db_name) as db:
            if channel_id:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM users WHERE channel_id = ?",
                    (channel_id,)
                )
            else:
                cursor = await db.execute("SELECT COUNT(*) FROM users")

            result = await cursor.fetchone()
            return result[0] if result else 0

    async def find_deleted_accounts(
        self,
        limit: Optional[int] = None,
        channel_id: Optional[int] = None
    ) -> List[Dict]:
        """Найти удаленные аккаунты"""
        async with aiosqlite.connect(self.db_name) as db:
            conditions = [
                "(first_name LIKE 'Deleted%' OR first_name IS NULL)",
                "(last_name LIKE 'Account%' OR last_name LIKE 'User%' OR last_name IS NULL)"
            ]

            params = []
            if channel_id:
                conditions.append("channel_id = ?")
                params.append(channel_id)

            query = f"""
                SELECT id, access_hash, username, first_name, last_name,
                       bot, status, last_online, channel_id, channel_username
                FROM users
                WHERE {' AND '.join(conditions)}
                ORDER BY id
            """

            if limit:
                query += f" LIMIT {limit}"

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def get_users_by_ids(self, user_ids: List[int]) -> List[Dict]:
        """Получить пользователей по их ID"""
        if not user_ids:
            return []

        async with aiosqlite.connect(self.db_name) as db:
            placeholders = ','.join(['?' for _ in user_ids])
            cursor = await db.execute(f"""
                SELECT id, access_hash, username, first_name, last_name
                FROM users
                WHERE id IN ({placeholders})
            """, user_ids)

            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def update_progress(
        self,
        channel_id: int,
        channel_username: str,
        processed: int,
        total: int,
        last_user_id: Optional[int] = None,
        status: str = "in_progress"
    ):
        """Обновить прогресс выгрузки"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT OR REPLACE INTO export_progress
                (channel_id, channel_username, total_members,
                 processed_members, last_user_id, status,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT created_at FROM export_progress WHERE channel_id = ?), ?),
                        ?)
            """, (channel_id, channel_username, total, processed,
                  last_user_id, status, channel_id, datetime.now().isoformat(),
                  datetime.now().isoformat()))

            await db.commit()

    async def get_progress(self, channel_id: int) -> Optional[Dict]:
        """Получить прогресс выгрузки"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT * FROM export_progress WHERE channel_id = ?
            """, (channel_id,))

            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

    async def mark_users_as_deleted(self, user_ids: List[int], reason: str = "Deleted Account"):
        """Пометить пользователей как удаленные"""
        if not user_ids:
            return

        async with aiosqlite.connect(self.db_name) as db:
            # Сначала перемещаем в таблицу deleted_users
            placeholders = ','.join(['?' for _ in user_ids])
            await db.execute(f"""
                INSERT OR IGNORE INTO deleted_users
                (id, access_hash, username, first_name, last_name,
                 photo_id, bot, status, last_online, channel_id, channel_username,
                 deletion_reason, found_at)
                SELECT id, access_hash, username, first_name, last_name,
                       photo_id, bot, status, last_online, channel_id, channel_username,
                       ?, ?
                FROM users
                WHERE id IN ({placeholders})
            """, (reason, datetime.now().isoformat(), *user_ids))

            # Затем удаляем из основной таблицы
            await db.execute(f"""
                DELETE FROM users WHERE id IN ({placeholders})
            """, user_ids)

            await db.commit()

    async def log_deletion(self, user_id: int, username: str, status: str, error: str = None):
        """Залогировать операцию удаления"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO deletion_log
                (user_id, username, deletion_time, status, error_message)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, datetime.now().isoformat(), status, error))

            await db.commit()

    async def get_deletion_stats(self) -> Dict:
        """Получить статистику удалений"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'success' THEN 1 END) as successful,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) as failed,
                    COUNT(CASE WHEN error_message IS NOT NULL THEN 1 END) as with_errors
                FROM deletion_log
            """)

            result = await cursor.fetchone()
            if result:
                return {
                    'total': result[0],
                    'successful': result[1],
                    'failed': result[2],
                    'with_errors': result[3]
                }
            return {'total': 0, 'successful': 0, 'failed': 0, 'with_errors': 0}

    async def close(self):
        """Закрыть соединение с базой данных"""
        if self.connection:
            await self.connection.close()
