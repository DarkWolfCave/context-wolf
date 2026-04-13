"""
Core infrastructure layer
Database, configuration, and shared utilities.
"""

from .database import Database
from .config import Config

__all__ = ['Database', 'Config']
