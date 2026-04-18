"""
Test Reporting Feature for ContextWolf
Provides statistics, summaries, and reports for test executions

Features:
- Test execution statistics
- Success/failure rates
- Performance metrics
- Trend analysis
- Test coverage reporting
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from src.core.database import Database
from src.core.helpers import format_timestamp


class TestReporter:
    """
    Provides reporting and statistics for test executions.

    Responsibilities:
    - Generate execution summaries
    - Calculate success rates
    - Track performance trends
    - Coverage analysis
    """

    def __init__(self, db: Database):
        """Initialize with database connection"""
        self.db = db

    def get_suite_summary(self, suite_id: int) -> Dict[str, Any]:
        """
        Get summary statistics for a test suite.

        Args:
            suite_id: Test suite ID

        Returns:
            Dictionary with suite statistics
        """
        cursor = self.db.conn.cursor()

        # Get suite info
        cursor.execute("""
            SELECT
                ts.*,
                p.name as project_name
            FROM test_suites ts
            JOIN projects p ON ts.project_id = p.id
            WHERE ts.id = ?
        """, (suite_id,))

        suite = cursor.fetchone()
        if not suite:
            return None

        suite_dict = dict(suite)

        # Get test case counts
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN priority = 'critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high
            FROM test_cases
            WHERE suite_id = ?
        """, (suite_id,))

        counts = dict(cursor.fetchone())

        # Get latest execution stats
        cursor.execute("""
            SELECT
                COUNT(*) as total_executions,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error,
                MAX(executed_at) as last_execution
            FROM test_executions te
            JOIN test_cases tc ON te.test_case_id = tc.id
            WHERE tc.suite_id = ?
        """, (suite_id,))

        exec_stats = dict(cursor.fetchone())

        # Calculate success rate
        total_exec = exec_stats['total_executions'] or 0
        if total_exec > 0:
            success_rate = (exec_stats['passed'] or 0) / total_exec * 100
        else:
            success_rate = 0

        return {
            'suite': suite_dict,
            'test_counts': counts,
            'execution_stats': exec_stats,
            'success_rate': round(success_rate, 2)
        }

    def get_test_case_stats(self, test_case_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Get statistics for a specific test case.

        Args:
            test_case_id: Test case ID
            days: Number of days to analyze (default 30)

        Returns:
            Dictionary with test case statistics
        """
        cursor = self.db.conn.cursor()

        # Get test case info
        cursor.execute("""
            SELECT
                tc.*,
                ts.name as suite_name
            FROM test_cases tc
            JOIN test_suites ts ON tc.suite_id = ts.id
            WHERE tc.id = ?
        """, (test_case_id,))

        test_case = cursor.fetchone()
        if not test_case:
            return None

        test_case_dict = dict(test_case)

        # Get execution history
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        cursor.execute("""
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(duration_ms) as avg_duration,
                MIN(duration_ms) as min_duration,
                MAX(duration_ms) as max_duration,
                MAX(executed_at) as last_run
            FROM test_executions
            WHERE test_case_id = ? AND executed_at >= ?
        """, (test_case_id, since))

        stats = dict(cursor.fetchone())

        # Calculate metrics
        total_runs = stats['total_runs'] or 0
        if total_runs > 0:
            success_rate = (stats['passed'] or 0) / total_runs * 100
        else:
            success_rate = 0

        return {
            'test_case': test_case_dict,
            'period_days': days,
            'statistics': stats,
            'success_rate': round(success_rate, 2)
        }

    def get_recent_failures(
        self,
        project_name: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent test failures.

        Args:
            project_name: Filter by project (None = all)
            limit: Maximum number of failures to return

        Returns:
            List of recent failures with details
        """
        cursor = self.db.conn.cursor()

        query = """
            SELECT
                te.id as execution_id,
                te.status,
                te.exit_code,
                te.duration_ms,
                te.executed_at,
                te.stderr_preview,
                tc.name as test_name,
                tc.command,
                ts.name as suite_name,
                p.name as project_name
            FROM test_executions te
            JOIN test_cases tc ON te.test_case_id = tc.id
            JOIN test_suites ts ON tc.suite_id = ts.id
            JOIN projects p ON ts.project_id = p.id
            WHERE te.status IN ('failed', 'timeout', 'error')
        """
        params = []

        if project_name:
            query += " AND p.name = ?"
            params.append(project_name)

        query += " ORDER BY te.executed_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_flaky_tests(
        self,
        project_name: str = None,
        min_runs: int = 5,
        min_failure_rate: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Identify flaky tests (inconsistent pass/fail).

        A test is considered flaky if:
        - It has been run at least min_runs times
        - It has a failure rate between min_failure_rate and (1 - min_failure_rate)

        Args:
            project_name: Filter by project
            min_runs: Minimum number of runs to consider
            min_failure_rate: Minimum failure rate to be considered flaky

        Returns:
            List of potentially flaky tests
        """
        cursor = self.db.conn.cursor()

        query = """
            SELECT
                tc.id as test_case_id,
                tc.name as test_name,
                ts.name as suite_name,
                p.name as project_name,
                COUNT(*) as total_runs,
                SUM(CASE WHEN te.status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) as failed,
                CAST(SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as failure_rate
            FROM test_cases tc
            JOIN test_suites ts ON tc.suite_id = ts.id
            JOIN projects p ON ts.project_id = p.id
            JOIN test_executions te ON tc.id = te.test_case_id
            WHERE tc.active = 1
        """
        params = []

        if project_name:
            query += " AND p.name = ?"
            params.append(project_name)

        query += """
            GROUP BY tc.id, tc.name, ts.name, p.name
            HAVING COUNT(*) >= ?
            AND CAST(SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) >= ?
            AND CAST(SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) <= ?
            ORDER BY CAST(SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) DESC
        """
        params.extend([min_runs, min_failure_rate, 1 - min_failure_rate])

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_performance_trends(
        self,
        test_case_id: int,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get performance trend for a test case.

        Args:
            test_case_id: Test case ID
            limit: Number of recent executions to analyze

        Returns:
            Dictionary with performance metrics and trend data
        """
        cursor = self.db.conn.cursor()

        # Get recent execution durations
        cursor.execute("""
            SELECT
                id,
                duration_ms,
                executed_at,
                status
            FROM test_executions
            WHERE test_case_id = ?
            ORDER BY executed_at DESC
            LIMIT ?
        """, (test_case_id, limit))

        executions = [dict(row) for row in cursor.fetchall()]

        if not executions:
            return None

        # Calculate metrics
        durations = [e['duration_ms'] for e in executions if e['status'] == 'passed']

        if not durations:
            return None

        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)

        # Simple trend: compare first half vs second half
        if len(durations) >= 4:
            midpoint = len(durations) // 2
            recent_avg = sum(durations[:midpoint]) / midpoint
            older_avg = sum(durations[midpoint:]) / (len(durations) - midpoint)
            trend_pct = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0

            if trend_pct > 10:
                trend = 'slower'
            elif trend_pct < -10:
                trend = 'faster'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'
            trend_pct = 0

        return {
            'test_case_id': test_case_id,
            'sample_size': len(durations),
            'avg_duration_ms': round(avg_duration, 2),
            'min_duration_ms': min_duration,
            'max_duration_ms': max_duration,
            'trend': trend,
            'trend_percentage': round(trend_pct, 2),
            'executions': executions
        }

    def get_project_coverage(self, project_name: str) -> Dict[str, Any]:
        """
        Get test coverage overview for a project.

        Args:
            project_name: Project name

        Returns:
            Dictionary with coverage statistics
        """
        cursor = self.db.conn.cursor()

        # Get project ID
        project_id = self.db.get_or_create_project(project_name)

        # Get test suite counts
        cursor.execute("""
            SELECT
                COUNT(*) as total_suites,
                SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) as active_suites
            FROM test_suites
            WHERE project_id = ?
        """, (project_id,))

        suite_counts = dict(cursor.fetchone())

        # Get test case counts
        cursor.execute("""
            SELECT
                COUNT(*) as total_tests,
                SUM(CASE WHEN tc.active = 1 THEN 1 ELSE 0 END) as active_tests,
                SUM(CASE WHEN tc.priority = 'critical' THEN 1 ELSE 0 END) as critical_tests
            FROM test_cases tc
            JOIN test_suites ts ON tc.suite_id = ts.id
            WHERE ts.project_id = ?
        """, (project_id,))

        test_counts = dict(cursor.fetchone())

        # Get execution summary (last 7 days)
        since = int((datetime.now() - timedelta(days=7)).timestamp())
        cursor.execute("""
            SELECT
                COUNT(*) as total_executions,
                SUM(CASE WHEN te.status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM test_executions te
            JOIN test_cases tc ON te.test_case_id = tc.id
            JOIN test_suites ts ON tc.suite_id = ts.id
            WHERE ts.project_id = ? AND te.executed_at >= ?
        """, (project_id, since))

        exec_stats = dict(cursor.fetchone())

        # Calculate success rate
        total_exec = exec_stats['total_executions'] or 0
        if total_exec > 0:
            success_rate = (exec_stats['passed'] or 0) / total_exec * 100
        else:
            success_rate = 0

        # Get coverage records
        cursor.execute("""
            SELECT
                component_name,
                test_count,
                coverage_percentage,
                last_tested
            FROM test_coverage
            WHERE project_id = ?
            ORDER BY coverage_percentage ASC
        """, (project_id,))

        coverage_records = [dict(row) for row in cursor.fetchall()]

        return {
            'project': project_name,
            'suites': suite_counts,
            'tests': test_counts,
            'executions_last_7_days': exec_stats,
            'success_rate_7_days': round(success_rate, 2),
            'coverage_by_component': coverage_records
        }

    def get_execution_timeline(
        self,
        project_name: str = None,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get timeline of test executions.

        Args:
            project_name: Filter by project (None = all)
            days: Number of days to include

        Returns:
            List of execution records by date
        """
        cursor = self.db.conn.cursor()

        since = int((datetime.now() - timedelta(days=days)).timestamp())

        query = """
            SELECT
                DATE(to_timestamp(te.executed_at)) as date,
                COUNT(*) as total_runs,
                SUM(CASE WHEN te.status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN te.status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN te.status = 'timeout' THEN 1 ELSE 0 END) as timeout,
                SUM(CASE WHEN te.status = 'error' THEN 1 ELSE 0 END) as error,
                AVG(te.duration_ms) as avg_duration
            FROM test_executions te
            JOIN test_cases tc ON te.test_case_id = tc.id
            JOIN test_suites ts ON tc.suite_id = ts.id
            JOIN projects p ON ts.project_id = p.id
            WHERE te.executed_at >= ?
        """
        params = [since]

        if project_name:
            query += " AND p.name = ?"
            params.append(project_name)

        query += " GROUP BY date ORDER BY date DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
