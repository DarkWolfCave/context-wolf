"""
Duplicate Detection Manager

Domain Layer: Duplicate detection and similarity matching.
Uses difflib for text similarity analysis.

Architecture: Domain Layer (Business Logic)
Dependencies: Only Core Layer (Database via conn parameter)
"""

import difflib
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import json


class DuplicateDetectionManager:
    """
    Manages duplicate detection and entry similarity matching.

    Responsibilities:
    - Calculate text similarity using difflib
    - Detect duplicate entries with configurable thresholds
    - Create entry relations based on similarity
    - Provide related entry suggestions

    Architecture: Domain Layer
    """

    # Konfigurierbare Schwellenwerte
    THRESHOLDS = {
        "exact_duplicate": {
            "min_similarity": 0.95,
            "same_project": True,
            "time_window_hours": 1,
            "action": "warn_strong"
        },
        "likely_duplicate": {
            "min_similarity": 0.85,
            "same_project": True,
            "time_window_hours": 24,
            "action": "warn_mild"
        },
        "related_content": {
            "min_similarity": 0.70,
            "same_project": True,
            "time_window_hours": 168,  # 7 Tage
            "action": "link"
        },
        "cross_reference": {
            "min_similarity": 0.75,
            "same_project": False,
            "time_window_hours": None,  # Zeitunabhängig
            "action": "note"
        }
    }

    def __init__(self, conn):
        """
        Initialize duplicate detection manager.

        Args:
            conn: Database connection (with row_factory for dict-like access)
        """
        self.conn = conn
        self.similarity_cache = {}  # Cache für Performance

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Berechne Ähnlichkeit zwischen zwei Texten"""
        # Cache-Key für Performance
        cache_key = hash(text1) ^ hash(text2)
        if cache_key in self.similarity_cache:
            return self.similarity_cache[cache_key]

        # Normalisierung für besseren Vergleich
        # Handle None values
        if not text1 or not text2:
            return 0.0

        text1 = text1.lower().strip()
        text2 = text2.lower().strip()

        # difflib SequenceMatcher für Ähnlichkeit
        similarity = difflib.SequenceMatcher(None, text1, text2).ratio()

        # Cache für 100 letzte Vergleiche
        if len(self.similarity_cache) > 100:
            self.similarity_cache.clear()
        self.similarity_cache[cache_key] = similarity

        return similarity

    def find_similar_entries(self, content: str, project: str = None,
                            limit: int = 10) -> List[Dict]:
        """Finde ähnliche Einträge in der Datenbank"""
        cursor = self.conn.cursor()

        # Query für letzte Einträge (mit oder ohne Projekt-Filter)
        if project:
            query = """
                SELECT
                    a.id,
                    a.timestamp,
                    ac.content,
                    a.summary,
                    p.name as project,
                    at.name as type
                FROM actions a
                JOIN action_content ac ON a.id = ac.action_id
                JOIN projects p ON a.project_id = p.id
                JOIN action_types at ON a.type_id = at.id
                WHERE p.name = ?
                ORDER BY a.timestamp DESC
                LIMIT 100
            """
            cursor.execute(query, (project,))
        else:
            query = """
                SELECT
                    a.id,
                    a.timestamp,
                    ac.content,
                    a.summary,
                    p.name as project,
                    at.name as type
                FROM actions a
                JOIN action_content ac ON a.id = ac.action_id
                JOIN projects p ON a.project_id = p.id
                JOIN action_types at ON a.type_id = at.id
                ORDER BY a.timestamp DESC
                LIMIT 100
            """
            cursor.execute(query)

        similar_entries = []
        current_time = datetime.now()

        for row in cursor.fetchall():
            # Ähnlichkeit berechnen
            similarity = self.calculate_similarity(content, row['content'])

            if similarity < 0.5:  # Unter 50% ignorieren
                continue

            # Zeit-Differenz berechnen
            entry_time = datetime.fromtimestamp(row['timestamp'])
            time_diff = current_time - entry_time

            # Kategorie bestimmen
            category = self._categorize_similarity(
                similarity,
                row['project'] == project,
                time_diff.total_seconds() / 3600  # In Stunden
            )

            similar_entries.append({
                'id': row['id'],
                'similarity': similarity,
                'category': category,
                'content': row['summary'][:100],  # Kurze Preview
                'project': row['project'],
                'type': row['type'],
                'timestamp': entry_time.strftime("%Y-%m-%d %H:%M"),
                'time_ago': self._format_time_ago(time_diff)
            })

        # Sortiere nach Ähnlichkeit
        similar_entries.sort(key=lambda x: x['similarity'], reverse=True)

        return similar_entries[:limit]

    def _categorize_similarity(self, similarity: float, same_project: bool,
                               hours_diff: float) -> str:
        """Kategorisiere die Art der Ähnlichkeit"""
        for category, rules in self.THRESHOLDS.items():
            if similarity >= rules['min_similarity']:
                # Projekt-Check
                if rules['same_project'] is not None:
                    if rules['same_project'] != same_project:
                        continue

                # Zeit-Check
                if rules['time_window_hours'] is not None:
                    if hours_diff > rules['time_window_hours']:
                        continue

                return category

        return "possibly_related"

    def _format_time_ago(self, time_diff: timedelta) -> str:
        """Formatiere Zeit-Differenz lesbar"""
        total_seconds = int(time_diff.total_seconds())

        if total_seconds < 60:
            return "gerade eben"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"vor {minutes} Minute{'n' if minutes != 1 else ''}"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"vor {hours} Stunde{'n' if hours != 1 else ''}"
        else:
            days = total_seconds // 86400
            return f"vor {days} Tag{'en' if days != 1 else ''}"

    def check_for_duplicates(self, content: str, project: str = None) -> Dict:
        """Hauptfunktion: Prüfe auf Duplikate und gebe Empfehlung"""
        similar = self.find_similar_entries(content, project, limit=5)

        result = {
            'has_duplicates': False,
            'should_warn': False,
            'exact_match': None,
            'similar_entries': similar,
            'recommendation': None
        }

        if not similar:
            return result

        # Prüfe auf exakte Duplikate
        for entry in similar:
            if entry['category'] == 'exact_duplicate':
                result['has_duplicates'] = True
                result['should_warn'] = True
                result['exact_match'] = entry
                result['recommendation'] = f"⚠️ Fast identischer Eintrag gefunden (#{entry['id']} - {entry['time_ago']})"
                break
            elif entry['category'] == 'likely_duplicate':
                result['should_warn'] = True
                result['recommendation'] = f"📎 Sehr ähnlicher Eintrag: #{entry['id']} ({entry['similarity']:.0%} Match - {entry['time_ago']})"
                break

        return result

    def create_relations_table(self):
        """Erstelle Tabelle für Beziehungen zwischen Einträgen"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entry_relations (
                id SERIAL PRIMARY KEY,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                similarity_score REAL NOT NULL,
                relation_type TEXT NOT NULL,
                created_at INTEGER DEFAULT (EXTRACT(epoch FROM now())::bigint),
                FOREIGN KEY (source_id) REFERENCES actions(id),
                FOREIGN KEY (target_id) REFERENCES actions(id),
                UNIQUE(source_id, target_id)
            )
        """)

        # Index für Performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relations_source
            ON entry_relations(source_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relations_target
            ON entry_relations(target_id)
        """)

        self.conn.commit()

    def save_relation(self, source_id: int, target_id: int,
                     similarity: float, relation_type: str):
        """Speichere Beziehung zwischen zwei Einträgen"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO entry_relations
            (source_id, target_id, similarity_score, relation_type)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (source_id, target_id) DO UPDATE
            SET similarity_score = EXCLUDED.similarity_score,
                relation_type = EXCLUDED.relation_type
        """, (source_id, target_id, similarity, relation_type))
        self.conn.commit()

    def get_related_entries(self, entry_id: int) -> List[Dict]:
        """Hole alle verwandten Einträge"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                er.*,
                a.summary,
                p.name as project,
                at.name as type
            FROM entry_relations er
            JOIN actions a ON (er.target_id = a.id OR er.source_id = a.id)
            JOIN projects p ON a.project_id = p.id
            JOIN action_types at ON a.type_id = at.id
            WHERE (er.source_id = ? OR er.target_id = ?)
                AND a.id != ?
            ORDER BY er.similarity_score DESC
        """, (entry_id, entry_id, entry_id))

        return [dict(row) for row in cursor.fetchall()]