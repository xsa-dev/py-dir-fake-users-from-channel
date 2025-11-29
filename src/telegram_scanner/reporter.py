import json
import csv
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import pandas as pd
from tabulate import tabulate

from .database import DatabaseManager
from .analyzer import DeletionCandidate


class ReportGenerator:
    """Генератор отчетов по результатам сканирования и удаления"""

    def __init__(self, db_manager: DatabaseManager, output_dir: str = "reports"):
        self.db = db_manager
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    async def generate_full_report(
        self,
        channel_id: int = None,
        channel_username: str = None,
        include_deleted: bool = True,
        include_suspicious: bool = False,
        export_format: str = "both"
    ) -> Dict:
        """
        Сгенерировать полный отчет

        Args:
            channel_id: ID канала
            channel_username: Имя канала
            include_deleted: Включить удаленные аккаунты
            include_suspicious: Включить подозрительные аккаунты
            export_format: Формат экспорта (csv, json, both)

        Returns:
            Словарь с путями к созданным файлам
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"report_{channel_username or channel_id}_{timestamp}"
        generated_files = {}

        # Получаем статистику
        total_users = await self.db.get_total_users_count(channel_id)
        deletion_stats = await self.db.get_deletion_stats()

        # Получаем удаленных пользователей
        deleted_users = []
        if include_deleted:
            deleted_users = await self.db.find_deleted_accounts(channel_id=channel_id)

        # Формируем отчет
        report_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'channel_id': channel_id,
                'channel_username': channel_username,
                'total_users_scanned': total_users,
                'deleted_accounts_found': len(deleted_users),
                'deletion_stats': deletion_stats
            },
            'deleted_accounts': deleted_users
        }

        # Экспорт в JSON
        if export_format in ['json', 'both']:
            json_path = await self._export_json(report_data, f"{base_filename}.json")
            generated_files['json'] = str(json_path)

        # Экспорт в CSV
        if export_format in ['csv', 'both']:
            csv_paths = await self._export_csv(report_data, base_filename)
            generated_files['csv'] = csv_paths

        # Создаем текстовый отчет
        txt_path = await self._export_text_report(report_data, f"{base_filename}.txt")
        generated_files['txt'] = str(txt_path)

        return generated_files

    async def _export_json(self, data: Dict, filename: str) -> Path:
        """Экспорт в JSON формат"""
        filepath = self.output_dir / filename

        # Конвертируем datetime объекты в строки
        def datetime_converter(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=datetime_converter)

        return filepath

    async def _export_csv(self, data: Dict, base_filename: str) -> Dict[str, Path]:
        """Экспорт в CSV формат"""
        files = {}

        # CSV для удаленных аккаунтов
        if data.get('deleted_accounts'):
            deleted_filename = f"{base_filename}_deleted_accounts.csv"
            deleted_filepath = self.output_dir / deleted_filename

            with open(deleted_filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Заголовок
                writer.writerow([
                    'ID', 'Access Hash', 'Username', 'First Name', 'Last Name',
                    'Bot', 'Status', 'Last Online', 'Channel ID', 'Channel Username'
                ])

                # Данные
                for user in data['deleted_accounts']:
                    writer.writerow([
                        user.get('id', ''),
                        user.get('access_hash', ''),
                        user.get('username', ''),
                        user.get('first_name', ''),
                        user.get('last_name', ''),
                        user.get('bot', False),
                        user.get('status', ''),
                        user.get('last_online', ''),
                        user.get('channel_id', ''),
                        user.get('channel_username', '')
                    ])

            files['deleted_accounts'] = deleted_filepath

        # CSV для статистики удалений
        if data['metadata']['deletion_stats']:
            stats_filename = f"{base_filename}_deletion_stats.csv"
            stats_filepath = self.output_dir / stats_filename

            stats = data['metadata']['deletion_stats']
            with open(stats_filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Total Attempts', stats['total']])
                writer.writerow(['Successful', stats['successful']])
                writer.writerow(['Failed', stats['failed']])
                writer.writerow(['With Errors', stats['with_errors']])

            files['deletion_stats'] = stats_filepath

        return files

    async def _export_text_report(self, data: Dict, filename: str) -> Path:
        """Создать текстовый отчет"""
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("ОТЧЕТ ПО АНАЛИЗУ КАНАЛА\n")
            f.write("="*50 + "\n\n")

            # Метаданные
            metadata = data['metadata']
            f.write("Информация:\n")
            f.write(f"  Канал: {metadata.get('channel_username', 'N/A')} (ID: {metadata.get('channel_id', 'N/A')})\n")
            f.write(f"  Дата генерации: {metadata['generated_at']}\n")
            f.write(f"  Всего пользователей просканировано: {metadata['total_users_scanned']:,}\n".replace(',', ' '))
            f.write(f"  Найдено удаленных аккаунтов: {metadata['deleted_accounts_found']:,}\n".replace(',', ' '))
            f.write("\n")

            # Статистика удалений
            stats = metadata['deletion_stats']
            if stats['total'] > 0:
                f.write("Статистика удалений:\n")
                f.write(f"  Всего попыток: {stats['total']}\n")
                f.write(f"  Успешных удалений: {stats['successful']}\n")
                f.write(f"  Неудачных попыток: {stats['failed']}\n")
                f.write(f"  С ошибками: {stats['with_errors']}\n")
                f.write("\n")

            # Топ-20 удаленных аккаунтов
            deleted = data.get('deleted_accounts', [])
            if deleted:
                f.write("Первые 20 удаленных аккаунтов:\n")
                f.write("-"*60 + "\n")
                for i, user in enumerate(deleted[:20], 1):
                    f.write(f"{i:2d}. ID: {user['id']}\n")
                    f.write(f"     Имя: {user.get('first_name', '')} {user.get('last_name', '')}\n")
                    if user.get('username'):
                        f.write(f"     Username: @{user['username']}\n")
                    f.write(f"     Бот: {'Да' if user.get('bot') else 'Нет'}\n")
                    f.write("\n")

                if len(deleted) > 20:
                    f.write(f"... и еще {len(deleted) - 20} удаленных аккаунтов\n")

        return filepath

    async def generate_candidates_report(
        self,
        candidates: List[DeletionCandidate],
        channel_username: str,
        filename: Optional[str] = None
    ) -> Dict:
        """
        Сгенерировать отчет по кандидатам на удаление

        Args:
            candidates: Список кандидатов
            channel_username: Имя канала
            filename: Опциональное имя файла

        Returns:
            Словарь с путями к файлам
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"deletion_candidates_{channel_username}_{timestamp}"

        generated_files = {}

        # Конвертируем кандидатов в словари
        candidates_data = []
        for candidate in candidates:
            candidates_data.append({
                'id': candidate.user_id,
                'access_hash': candidate.access_hash,
                'username': candidate.username,
                'first_name': candidate.first_name,
                'last_name': candidate.last_name,
                'reason': candidate.reason.value,
                'confidence': candidate.confidence,
                'is_bot': candidate.details.get('bot', False)
            })

        # Экспорт в CSV
        csv_filename = f"{filename}.csv"
        csv_filepath = self.output_dir / csv_filename

        with open(csv_filepath, 'w', newline='', encoding='utf-8') as f:
            if candidates_data:
                writer = csv.DictWriter(f, fieldnames=candidates_data[0].keys())
                writer.writeheader()
                writer.writerows(candidates_data)

        generated_files['csv'] = str(csv_filepath)

        # Экспорт в JSON
        json_filename = f"{filename}.json"
        json_filepath = self.output_dir / json_filename

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'channel_username': channel_username,
                    'total_candidates': len(candidates)
                },
                'candidates': candidates_data
            }, f, indent=2, ensure_ascii=False)

        generated_files['json'] = str(json_filepath)

        return generated_files

    async def print_summary_report(self, channel_id: int = None, channel_username: str = None):
        """Вывести краткий отчет в консоль"""
        print("\n" + "="*60)
        print("СВОДНЫЙ ОТЧЕТ")
        print("="*60)

        # Общая статистика
        total_users = await self.db.get_total_users_count(channel_id)
        deleted_users = await self.db.find_deleted_accounts(channel_id=channel_id)
        deletion_stats = await self.db.get_deletion_stats()

        print(f"Канал: {channel_username or 'ID: ' + str(channel_id)}")
        print(f"Всего пользователей в БД: {total_users:,}".replace(',', ' '))
        print(f"Найдено удаленных аккаунтов: {len(deleted_users):,}".replace(',', ' '))

        if deletion_stats['total'] > 0:
            print(f"\nСтатистика удалений:")
            print(f"  Всего попыток: {deletion_stats['total']}")
            print(f"  Успешно: {deletion_stats['successful']}")
            print(f"  Ошибок: {deletion_stats['failed']}")

        # Таблица по причинам
        from collections import defaultdict
        reason_stats = defaultdict(int)
        for user in deleted_users:
            first_name = (user.get('first_name') or '').lower()
            if first_name.startswith('deleted'):
                reason_stats['Deleted Account'] += 1
            else:
                reason_stats['Other'] += 1

        if reason_stats:
            print(f"\nРаспределение по причинам:")
            table_data = [[reason, count] for reason, count in reason_stats.items()]
            print(tabulate(table_data, headers=['Причина', 'Количество'], tablefmt='grid'))

        print("="*60)

    async def export_to_excel(
        self,
        channel_username: str,
        include_deleted: bool = True,
        include_deletion_log: bool = True
    ) -> Path:
        """
        Экспортировать все данные в Excel файл

        Args:
            channel_username: Имя канала
            include_deleted: Включить удаленные аккаунты
            include_deletion_log: Включить лог удалений

        Returns:
            Путь к Excel файлу
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"full_report_{channel_username}_{timestamp}.xlsx"
        filepath = self.output_dir / filename

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Лист с общей статистикой
            stats = await self.db.get_deletion_stats()
            total_users = await self.db.get_total_users_count()
            deleted_users = await self.db.find_deleted_accounts() if include_deleted else []

            stats_df = pd.DataFrame([
                ['Всего пользователей', total_users],
                ['Найдено удаленных аккаунтов', len(deleted_users)],
                ['Всего попыток удаления', stats['total']],
                ['Успешных удалений', stats['successful']],
                ['Неудачных попыток', stats['failed']],
                ['С ошибками', stats['with_errors']]
            ], columns=['Метрика', 'Значение'])

            stats_df.to_excel(writer, sheet_name='Общая статистика', index=False)

            # Лист с удаленными аккаунтами
            if include_deleted and deleted_users:
                deleted_df = pd.DataFrame(deleted_users)
                deleted_df.to_excel(writer, sheet_name='Удаленные аккаунты', index=False)

        return filepath
