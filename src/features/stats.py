"""
Statistics and Database Maintenance
Handles statistics queries and database optimization.

Architecture: Features Layer (depends on Core)
"""

from typing import Dict, Any

from ..core.database import Database


class StatsManager:
    """
    Manages statistics and database maintenance.

    Responsibilities:
    - Get global statistics
    - Database optimization (VACUUM ANALYZE)
    - Performance metrics

    Dependencies:
    - Database (core layer)
    """

    def __init__(self, database: Database):
        """
        Initialize StatsManager.

        Args:
            database: Database instance
        """
        self.db = database
        self.conn = database.conn

    def get_stats(self, project_name: str = None) -> Dict[str, Any]:
        """
        Get statistics, optionally filtered by project.

        Args:
            project_name: Optional project name to filter by

        Returns:
            Dict with:
            - backend: Database backend ('postgres')
            - projects: Number of projects
            - types: Number of action types
            - actions: Total actions
            - sessions: Total sessions
            - total_tokens: Total tokens used
            - db_size: Database size in bytes

        Uses optimized aggregated queries.
        """
        cursor = self.conn.cursor()

        if project_name:
            # Get project-specific stats
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT a.project_id) as projects,
                    COUNT(DISTINCT a.type_id) as types,
                    COUNT(a.id) as actions,
                    COUNT(DISTINCT a.session_id) as sessions,
                    SUM(a.tokens_used) as total_tokens
                FROM actions a
                JOIN projects p ON a.project_id = p.id
                WHERE p.name = %s
            """, (project_name,))
        else:
            # Get global stats
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT project_id) as projects,
                    COUNT(DISTINCT type_id) as types,
                    COUNT(id) as actions,
                    COUNT(DISTINCT session_id) as sessions,
                    SUM(tokens_used) as total_tokens
                FROM actions
            """)

        stats = dict(cursor.fetchone())

        # Add backend information
        stats['backend'] = 'postgres'

        # PostgreSQL: Use pg_database_size
        cursor.execute("""
            SELECT pg_database_size(current_database()) as size
        """)
        stats['db_size'] = cursor.fetchone()['size']

        return stats

    def vacuum(self) -> None:
        """
        Optimize database with VACUUM ANALYZE.

        Note: VACUUM can take time on large databases.
        Delegates to Database.vacuum() which handles autocommit mode.
        """
        self.db.vacuum()

    def get_db_info(self) -> Dict[str, Any]:
        """
        Get detailed database information.

        Returns:
            Dict with database metadata and settings:
            version, block_size, database_size, shared_buffers, foreign_keys
        """
        cursor = self.conn.cursor()
        info = {}

        cursor.execute("SELECT version()")
        info['version'] = cursor.fetchone()['version']

        cursor.execute("SHOW block_size")
        info['block_size'] = cursor.fetchone()['block_size']

        cursor.execute("SELECT pg_database_size(current_database())")
        info['database_size'] = cursor.fetchone()['pg_database_size']

        cursor.execute("SHOW shared_buffers")
        info['shared_buffers'] = cursor.fetchone()['shared_buffers']

        # Foreign keys always enforced in PostgreSQL
        info['foreign_keys'] = True

        return info

    def get_mcp_tool_stats(self, days: int = 30, export_format: str = None) -> Dict[str, Any]:
        """
        Get MCP tool usage statistics.

        Args:
            days: Number of days to look back (default: 30)
            export_format: Optional export format ('json' or 'csv')

        Returns:
            Dict with tool usage statistics:
            - total_calls: Total number of MCP tool calls
            - unique_tools: Number of unique tools called
            - time_range_days: Time range in days
            - tools: List of tool stats (name, calls, avg_duration_ms, avg_response_kb, success_rate)
            - unused_tools: List of tools that were never called
        """
        import time
        cursor = self.conn.cursor()

        # Calculate timestamp for time range
        now = int(time.time())
        start_timestamp = now - (days * 24 * 60 * 60)

        # Get tool usage stats
        cursor.execute("""
            SELECT
                tool_name,
                COUNT(*) as call_count,
                AVG(duration_ms) as avg_duration_ms,
                AVG(response_size_bytes) / 1024.0 as avg_response_kb,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
            FROM mcp_tool_usage
            WHERE timestamp >= ?
            GROUP BY tool_name
            ORDER BY call_count DESC
        """, [start_timestamp])

        tools_stats = []
        for row in cursor.fetchall():
            tools_stats.append({
                'tool_name': row['tool_name'],
                'calls': row['call_count'],
                'avg_duration_ms': round(row['avg_duration_ms'] or 0, 2),
                'avg_response_kb': round(row['avg_response_kb'] or 0, 2),
                'success_rate': round(row['success_rate'] or 0, 1)
            })

        # Get total call count
        cursor.execute("""
            SELECT COUNT(*) as total
            FROM mcp_tool_usage
            WHERE timestamp >= ?
        """, [start_timestamp])
        total_calls = cursor.fetchone()['total']

        # Get all defined MCP tools (from a hypothetical list)
        # For now, we'll identify unused tools by checking which ones have 0 calls
        used_tools = set(t['tool_name'] for t in tools_stats)

        # Known MCP tools (from mcp_context_server.py) - Updated 2025-11-08 after optimization
        all_tools = [
            'context_save', 'context_search',
            'snippet_search', 'snippet_show',
            'todo_add', 'todo_list', 'todo_start', 'todo_done',
            'session', 'stats', 'projects',
            'ai_prompt',
            'infra_list_hosts', 'infra_show_host', 'infra_list_services'
        ]

        unused_tools = [t for t in all_tools if t not in used_tools]

        result = {
            'total_calls': total_calls,
            'unique_tools': len(used_tools),
            'time_range_days': days,
            'tools': tools_stats,
            'unused_tools': unused_tools
        }

        # Export if requested
        if export_format:
            return self._export_mcp_stats(result, export_format)

        return result

    def _export_mcp_stats(self, stats: Dict[str, Any], format: str) -> str:
        """
        Export MCP stats to JSON or CSV format.

        Args:
            stats: Stats dict from get_mcp_tool_stats()
            format: 'json' or 'csv'

        Returns:
            Formatted string for export
        """
        import json
        import io

        if format == 'json':
            return json.dumps(stats, indent=2)

        elif format == 'csv':
            # CSV export
            output = io.StringIO()
            import csv
            writer = csv.writer(output)

            # Header
            writer.writerow(['Tool Name', 'Calls', 'Avg Duration (ms)', 'Avg Response (KB)', 'Success Rate (%)'])

            # Data rows
            for tool in stats['tools']:
                writer.writerow([
                    tool['tool_name'],
                    tool['calls'],
                    tool['avg_duration_ms'],
                    tool['avg_response_kb'],
                    tool['success_rate']
                ])

            # Add unused tools section
            writer.writerow([])
            writer.writerow(['Unused Tools'])
            for tool in stats['unused_tools']:
                writer.writerow([tool, 0, 0, 0, 0])

            return output.getvalue()

        else:
            raise ValueError(f"Unsupported export format: {format}")