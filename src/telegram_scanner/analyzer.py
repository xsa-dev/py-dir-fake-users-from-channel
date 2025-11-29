import re
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from .database import DatabaseManager


class DeletionReason(Enum):
    """Причины для удаления пользователя"""
    DELETED_ACCOUNT = "Deleted Account"
    DELETED_USER = "Deleted User"
    DEFAULT_NAME = "Default Name"
    FAKE_PATTERN = "Fake Pattern"
    INACTIVE_LONG = "Inactive Long Time"
    BOT_SUSPICIOUS = "Suspicious Bot"
    EMPTY_PROFILE = "Empty Profile"


@dataclass
class DeletionCandidate:
    """Кандидат на удаление"""
    user_id: int
    access_hash: int
    username: str
    first_name: str
    last_name: str
    reason: DeletionReason
    confidence: float  # Уверенность в правильности решения (0-1)
    details: Dict


class DeletedUserAnalyzer:
    """Анализатор удаленных и подозрительных пользователей"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.deleted_patterns = [
            r'deleted\s+account',
            r'deleted\s+user',
            r'^deleted\s*$',
            r'account\s+deleted',
            r'user\s+deleted'
        ]

        self.fake_patterns = [
            r'^user\d+$',
            r'^\d+$',
            r'^user_\d+$',
            r'^telegram_\d+$',
            r'^anonymous\d*$',
            r'^user$',
            r'^profile$',
            r'^account$'
        ]

        self.suspicious_usernames = [
            r'^user\d+',
            r'^\d{5,}$',
            r'^[a-z]{1,2}\d+$',
            r'^_\w+$',
            r'^\w+_$'
        ]

    async def find_deleted_accounts(
        self,
        channel_id: int = None,
        check_confidence: bool = True
    ) -> List[DeletionCandidate]:
        """
        Найти все удаленные аккаунты

        Args:
            channel_id: ID канала для фильтрации
            check_confidence: Проверять дополнительные признаки

        Returns:
            Список кандидатов на удаление
        """
        candidates = []

        # Получаем всех пользователей из базы
        deleted_users = await self.db.find_deleted_accounts(limit=None, channel_id=channel_id)

        for user in deleted_users:
            candidate = self._analyze_deleted_account(user)
            if candidate:
                candidates.append(candidate)

        return candidates

    def _analyze_deleted_account(self, user: Dict) -> DeletionCandidate:
        """Анализ одного пользователя на предмет удаленного аккаунта"""

        first_name = (user.get('first_name') or '').lower().strip()
        last_name = (user.get('last_name') or '').lower().strip()
        username = (user.get('username') or '').lower().strip()

        # Случай полностью пустого профиля (часто означает удаленный аккаунт)
        if not first_name and not last_name and not username:
            return DeletionCandidate(
                user_id=user['id'],
                access_hash=user['access_hash'],
                username=user['username'],
                first_name=user['first_name'],
                last_name=user['last_name'],
                reason=DeletionReason.DELETED_ACCOUNT,
                confidence=0.85,
                details={
                    'pattern_matched': 'empty_profile_as_deleted',
                    'has_username': False,
                    'bot': user.get('bot', False)
                }
            )

        # Проверяем паттерны удаленных аккаунтов
        for pattern in self.deleted_patterns:
            if re.search(pattern, f"{first_name} {last_name}"):
                reason = DeletionReason.DELETED_ACCOUNT
                confidence = 0.95

                # Дополнительная проверка на отсутствие username
                if not username:
                    confidence = 0.99
                elif username in ['deleted', 'account', 'user', '']:
                    confidence = 0.98

                return DeletionCandidate(
                    user_id=user['id'],
                    access_hash=user['access_hash'],
                    username=user['username'],
                    first_name=user['first_name'],
                    last_name=user['last_name'],
                    reason=reason,
                    confidence=confidence,
                    details={
                        'pattern_matched': pattern,
                        'has_username': bool(user['username']),
                        'bot': user.get('bot', False)
                    }
                )

        return None

    async def find_suspicious_accounts(
        self,
        channel_id: int = None,
        min_confidence: float = 0.7
    ) -> List[DeletionCandidate]:
        """
        Найти подозрительные аккаунты

        Args:
            channel_id: ID канала для фильтрации
            min_confidence: Минимальная уверенность для включения

        Returns:
            Список подозрительных кандидатов
        """
        candidates = []

        # Здесь можно добавить запрос к БД для получения всех пользователей
        # и их анализа на подозрительность

        return candidates

    def _is_suspicious_username(self, username: str) -> Tuple[bool, str, float]:
        """Проверить username на подозрительность"""
        if not username:
            return False, "", 0.0

        username = username.lower()

        for pattern in self.suspicious_usernames:
            if re.search(pattern, username):
                return True, f"Matches pattern: {pattern}", 0.6

        return False, "", 0.0

    def _has_default_profile(self, user: Dict) -> Tuple[bool, str, float]:
        """Проверить на дефолтный профиль"""
        first_name = user.get('first_name', '').strip()
        last_name = user.get('last_name', '').strip()
        username = user.get('username', '').strip()

        issues = []
        confidence = 0.0

        # Нет имени пользователя
        if not first_name and not last_name and not username:
            return True, "Empty profile", 0.9

        # Имена по умолчанию
        default_names = ['user', 'account', 'profile', 'anonymous', 'telegram']
        if first_name.lower() in default_names:
            issues.append(f"Default first name: {first_name}")
            confidence += 0.3

        if last_name and last_name.lower() in default_names:
            issues.append(f"Default last name: {last_name}")
            confidence += 0.2

        if confidence >= min(0.5, 0.5):
            return True, "; ".join(issues), min(confidence, 0.8)

        return False, "", 0.0

    async def analyze_user_batch(self, users: List[Dict]) -> List[DeletionCandidate]:
        """Анализировать пакет пользователей"""
        candidates = []

        for user in users:
            # Проверка на удаленный аккаунт
            deleted = self._analyze_deleted_account(user)
            if deleted:
                candidates.append(deleted)
                continue

            # Проверка на другие признаки
            suspicious = await self._check_suspicious_signs(user)
            if suspicious:
                candidates.extend(suspicious)

        return candidates

    async def _check_suspicious_signs(self, user: Dict) -> List[DeletionCandidate]:
        """Проверить пользователя на другие подозрительные признаки"""
        candidates = []

        # Проверка username
        is_suspicious, reason, confidence = self._is_suspicious_username(user.get('username', ''))
        if is_suspicious and confidence >= 0.6:
            candidates.append(DeletionCandidate(
                user_id=user['id'],
                access_hash=user['access_hash'],
                username=user['username'],
                first_name=user['first_name'],
                last_name=user['last_name'],
                reason=DeletionReason.FAKE_PATTERN,
                confidence=confidence,
                details={'suspicious_username': True, 'reason': reason}
            ))

        # Проверка на пустой профиль
        is_empty, reason, confidence = self._has_default_profile(user)
        if is_empty and confidence >= 0.5:
            candidates.append(DeletionCandidate(
                user_id=user['id'],
                access_hash=user['access_hash'],
                username=user['username'],
                first_name=user['first_name'],
                last_name=user['last_name'],
                reason=DeletionReason.EMPTY_PROFILE,
                confidence=confidence,
                details={'empty_profile': True, 'reason': reason}
            ))

        return candidates

    def filter_by_confidence(self, candidates: List[DeletionCandidate], min_confidence: float = 0.8):
        """Отфильтровать кандидатов по минимальной уверенности"""
        return [c for c in candidates if c.confidence >= min_confidence]

    def group_by_reason(self, candidates: List[DeletionCandidate]) -> Dict[str, List[DeletionCandidate]]:
        """Сгруппировать кандидатов по причине удаления"""
        grouped = {}
        for candidate in candidates:
            reason_str = candidate.reason.value
            if reason_str not in grouped:
                grouped[reason_str] = []
            grouped[reason_str].append(candidate)
        return grouped

    async def get_analysis_report(self, channel_id: int = None) -> Dict:
        """Получить полный отчет анализа"""
        deleted_accounts = await self.find_deleted_accounts(channel_id)
        suspicious_accounts = await self.find_suspicious_accounts(channel_id)

        grouped_deleted = self.group_by_reason(deleted_accounts)
        grouped_suspicious = self.group_by_reason(suspicious_accounts)

        report = {
            'timestamp': datetime.now().isoformat(),
            'channel_id': channel_id,
            'total_candidates': len(deleted_accounts) + len(suspicious_accounts),
            'deleted_accounts': {
                'total': len(deleted_accounts),
                'by_reason': {reason: len(candidates) for reason, candidates in grouped_deleted.items()}
            },
            'suspicious_accounts': {
                'total': len(suspicious_accounts),
                'by_reason': {reason: len(candidates) for reason, candidates in grouped_suspicious.items()}
            },
            'high_confidence_deleted': len([c for c in deleted_accounts if c.confidence >= 0.9]),
            'high_confidence_suspicious': len([c for c in suspicious_accounts if c.confidence >= 0.9])
        }

        return report

    def print_candidates_summary(self, candidates: List[DeletionCandidate], limit: int = 10):
        """Вывести сводку по кандидатам на удаление"""
        if not candidates:
            print("Кандидатов на удаление не найдено")
            return

        grouped = self.group_by_reason(candidates)

        print(f"\nНайдено кандидатов на удаление: {len(candidates)}")
        print("\nПо причинам:")

        for reason, reason_candidates in grouped.items():
            print(f"  {reason}: {len(reason_candidates)}")

        print(f"\nПримеры (первые {min(limit, len(candidates))}):")
        print("-" * 80)

        for i, candidate in enumerate(candidates[:limit]):
            print(f"{i+1}. ID: {candidate.user_id}")
            print(f"   Имя: {candidate.first_name} {candidate.last_name}")
            print(f"   Username: {candidate.username or 'Нет'}")
            print(f"   Причина: {candidate.reason.value}")
            print(f"   Уверенность: {candidate.confidence:.2f}")
            print("-" * 40)
