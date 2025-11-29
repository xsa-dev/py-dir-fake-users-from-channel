import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, ApiIdInvalidError

from .config import config
from .database import DatabaseManager
from .exporter import TelegramExporter
from .analyzer import DeletedUserAnalyzer
from .deleter import TelegramUserDeleter
from .reporter import ReportGenerator
from .checkpoint_manager import CheckpointManager


class TelegramScannerApp:
    """Основное приложение для сканирования и удаления пользователей"""

    def __init__(self):
        self.client = None
        self.db_manager = None
        self.exporter = None
        self.analyzer = None
        self.deleter = None
        self.reporter = None
        self.checkpoint_manager = None

    @staticmethod
    def _safe_input(prompt: str) -> str | None:
        """Безопасный ввод с обработкой отсутствия stdin"""
        try:
            return input(prompt)
        except EOFError:
            print("Ввод недоступен. Запустите скрипт в интерактивном терминале и попробуйте снова.")
            return None

    async def initialize(self):
        """Инициализация компонентов"""
        print("Инициализация приложения...")

        # Проверка конфигурации
        if not config.validate():
            print("Ошибка в конфигурации. Проверьте .env файл.")
            return False

        # Показываем конфигурацию
        config.print_config()

        # Инициализация клиента Telegram
        self.client = TelegramClient(
            config.session_name,
            config.api_id,
            config.api_hash
        )

        # Инициализация менеджера базы данных
        self.db_manager = DatabaseManager(config.database_name)
        await self.db_manager.init_database()

        # Инициализация остальных компонентов
        self.exporter = TelegramExporter(self.client, self.db_manager)
        self.analyzer = DeletedUserAnalyzer(self.db_manager)
        self.deleter = TelegramUserDeleter(self.client, self.db_manager)
        self.reporter = ReportGenerator(self.db_manager)
        self.checkpoint_manager = CheckpointManager()

        print("Инициализация завершена.")
        return True

    async def authenticate(self):
        """Аутентификация в Telegram"""
        print("\nАутентификация в Telegram...")
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                print("Отправка кода запроса...")
                phone_code = await self.client.send_code_request(config.phone_number)
                code = self._safe_input("Введите код из Telegram: ")
                if not code:
                    return False
                try:
                    await self.client.sign_in(config.phone_number, code)
                except SessionPasswordNeededError:
                    password = self._safe_input("Двухфакторная аутентификация. Введите пароль: ")
                    if not password:
                        return False
                    await self.client.sign_in(password=password)
            print("Аутентификация успешна!")
            return True
        except ApiIdInvalidError:
            print("Ошибка: неверный API ID или API Hash")
            return False
        except Exception as e:
            print(f"Ошибка аутентификации: {e}")
            return False

    async def show_main_menu(self):
        """Главное меню приложения"""
        while True:
            print("\n" + "="*50)
            print("ТЕЛЕГРАМ СКАНЕР")
            print("="*50)
            print("1. Экспортировать участников канала")
            print("2. Анализировать удаленные аккаунты")
            print("3. Показать статистику")
            print("4. Удалить пользователей")
            print("5. Сгенерировать отчет")
            print("6. Управление чекпоинтами")
            print("7. Настройки")
            print("0. Выход")
            print("-"*50)

            choice = input("Выберите действие: ").strip()

            if choice == "1":
                await self.export_channel_menu()
            elif choice == "2":
                await self.analyze_menu()
            elif choice == "3":
                await self.show_statistics()
            elif choice == "4":
                await self.delete_users_menu()
            elif choice == "5":
                await self.generate_report_menu()
            elif choice == "6":
                await self.checkpoints_menu()
            elif choice == "7":
                await self.settings_menu()
            elif choice == "0":
                print("Выход...")
                break
            else:
                print("Неверный выбор. Попробуйте снова.")

    async def export_channel_menu(self):
        """Меню экспорта участников"""
        channel_username = input("Введите имя канала (например, @channel_name): ").strip()

        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username

        # Проверяем наличие чекпоинтов
        checkpoint = self.checkpoint_manager.load_latest_checkpoint('export', hash(channel_username))
        if checkpoint:
            resume = input(f"Найден незавершенный экспорт ({checkpoint.processed_items:,} / {checkpoint.total_items:,}). Возобновить? (y/n): ").lower()
            if resume == 'y':
                await self.export_channel(channel_username, resume=True)
                return

        await self.export_channel(channel_username)

    async def export_channel(self, channel_username: str, resume: bool = False):
        """Экспорт участников канала"""
        try:
            stats = await self.exporter.export_channel_participants(channel_username, resume)
            await self.exporter.print_export_summary(stats)

            # Автоматически запускаем анализ после экспорта
            analyze = input("\nЗапустить анализ удаленных аккаунтов? (y/n): ").lower()
            if analyze == 'y':
                await self.analyze_deleted_users(stats['channel_id'], channel_username)

        except Exception as e:
            print(f"Ошибка при экспорте: {e}")

    async def analyze_menu(self):
        """Меню анализа"""
        channel_username = input("Введите имя канала (или Enter для анализа всех): ").strip()

        channel_id = None
        if channel_username:
            if not channel_username.startswith('@'):
                channel_username = '@' + channel_username
            # Здесь можно получить ID канала через client.get_entity
        else:
            # Показываем список каналов в БД
            # Для простоты анализируем все
            pass

        await self.analyze_deleted_users(channel_id, channel_username)

    async def analyze_deleted_users(self, channel_id: int = None, channel_username: str = None):
        """Анализ удаленных пользователей"""
        print("\nАнализ удаленных аккаунтов...")
        candidates = await self.analyzer.find_deleted_accounts(channel_id)

        if candidates:
            self.analyzer.print_candidates_summary(candidates)

            # Сохраняем кандидатов
            save = input("\nСохранить список кандидатов? (y/n): ").lower()
            if save == 'y':
                files = await self.reporter.generate_candidates_report(
                    candidates,
                    channel_username or "unknown"
                )
                print(f"Сохранено в: {', '.join(files.values())}")

            # Предлагаем удалить
            delete = input("\nУдалить найденные аккаунты? (y/n): ").lower()
            if delete == 'y':
                # Получаем entity канала
                channel_entity = await self.client.get_entity(channel_username)
                channel_id = channel_entity.id

                stats = await self.deleter.delete_users(channel_username, candidates)
                if not stats.get('cancelled'):
                    await self.db_manager.mark_users_as_deleted(
                        [c.user_id for c in candidates],
                        reason=candidates[0].reason.value if candidates else "Deleted Account"
                    )
        else:
            print("Удаленные аккаунты не найдены")

    async def show_statistics(self):
        """Показать статистику"""
        await self.reporter.print_summary_report()

    async def delete_users_menu(self):
        """Меню удаления пользователей"""
        channel_username = input("Введите имя канала: ").strip()
        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username

        # Сначала анализируем
        candidates = await self.analyzer.find_deleted_accounts()

        if not candidates:
            print("Нет кандидатов для удаления")
            return

        # Показываем предпросмотр
        await self.deleter.preview_deletions(candidates)

        # Удаляем
        stats = await self.deleter.delete_users(channel_username, candidates)
        if not stats.get('cancelled'):
            await self.db_manager.mark_users_as_deleted(
                [c.user_id for c in candidates],
                reason=candidates[0].reason.value if candidates else "Deleted Account"
            )

    async def generate_report_menu(self):
        """Меню генерации отчетов"""
        channel_username = input("Введите имя канала (или Enter для всех): ").strip()

        channel_id = None
        if channel_username:
            if not channel_username.startswith('@'):
                channel_username = '@' + channel_username

        print("\nВыберите формат отчета:")
        print("1. CSV")
        print("2. JSON")
        print("3. Текстовый")
        print("4. Все форматы")

        format_choice = input("Ваш выбор: ").strip()
        format_map = {
            '1': 'csv',
            '2': 'json',
            '3': 'txt',
            '4': 'both'
        }

        export_format = format_map.get(format_choice, 'both')

        print("\nГенерация отчета...")
        files = await self.reporter.generate_full_report(
            channel_id=channel_id,
            channel_username=channel_username,
            export_format=export_format
        )

        print("\nОтчеты сохранены:")
        for fmt, path in files.items():
            if isinstance(path, dict):
                for sub_fmt, sub_path in path.items():
                    print(f"  {fmt}/{sub_fmt}: {sub_path}")
            else:
                print(f"  {fmt}: {path}")

    async def checkpoints_menu(self):
        """Меню управления чекпоинтами"""
        checkpoints = self.checkpoint_manager.list_checkpoints()

        if not checkpoints:
            print("Нет сохраненных чекпоинтов")
            return

        print("\nСохраненные чекпоинты:")
        for op_type, cp_list in checkpoints.items():
            print(f"\n{op_type.upper()}:")
            for cp in cp_list[:5]:  # Показываем последние 5
                print(f"  {cp.channel_username}: {cp.processed_items}/{cp.total_items} "
                      f"({cp.timestamp[:19]})")

        action = input("\nОчистить старые чекпоинты? (y/n): ").lower()
        if action == 'y':
            self.checkpoint_manager.clean_old_checkpoints()
            print("Старые чекпоинты удалены")

    async def settings_menu(self):
        """Меню настроек"""
        print("\nТекущие настройки:")
        config.print_config()

        if input("\nИзменить настройки? (y/n): ").lower() == 'y':
            print("Для изменения настроек отредактируйте файл .env и перезапустите приложение")

    async def cleanup(self):
        """Очистка ресурсов"""
        if self.client:
            await self.client.disconnect()
        if self.db_manager:
            await self.db_manager.close()

    async def run(self):
        """Запуск приложения"""
        try:
            # Инициализация
            if not await self.initialize():
                return

            # Аутентификация
            if not await self.authenticate():
                return

            # Главное меню
            await self.show_main_menu()

        except KeyboardInterrupt:
            print("\nПрерывание работы...")
        except Exception as e:
            print(f"\nОшибка: {e}")
        finally:
            await self.cleanup()


async def main():
    """Главная функция"""
    app = TelegramScannerApp()
    await app.run()


if __name__ == "__main__":
    # Проверяем версию Python
    if sys.version_info < (3, 12):
        print("Требуется Python 3.12 или выше")
        sys.exit(1)

    # Запускаем приложение
    asyncio.run(main())
