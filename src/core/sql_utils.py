"""
SQL Utility Functions for PostgreSQL
"""


def format_timestamp_sql(timestamp_column: str, format: str = 'localtime') -> str:
    """
    Format a Unix timestamp column to datetime string.

    Args:
        timestamp_column: Name of the timestamp column (e.g., 'a.timestamp')
        format: 'localtime' or 'utc'

    Returns:
        SQL expression for formatted datetime

    Example:
        PostgreSQL: to_char(to_timestamp(a.timestamp), 'YYYY-MM-DD HH24:MI:SS')
    """
    if format == 'utc':
        return f"to_char(to_timestamp({timestamp_column}), 'YYYY-MM-DD HH24:MI:SS')"
    else:
        return f"to_char(to_timestamp({timestamp_column}) AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"
