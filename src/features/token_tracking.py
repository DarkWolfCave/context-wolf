#!/usr/bin/env python3
"""
Token Tracking Extension for Context Manager V2
Tracks token usage for monitoring Context Window consumption
"""

import json
import time
from pathlib import Path
from typing import Dict, Tuple

class TokenTracker:
    """Track token usage to monitor Context Window consumption"""

    # Token estimation constants (Claude specific)
    CHARS_PER_TOKEN = 4
    WORDS_PER_TOKEN = 0.75
    SESSION_TIMEOUT_HOURS = 1  # Consider session stale after 1 hour

    def __init__(self, stats_file: Path = None):
        if not stats_file:
            stats_file = Path.home() / '.context' / 'token_stats.json'

        self.stats_file = stats_file
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        self.stats = self._load_stats()
        self._init_session()

    def _init_session(self):
        """Initializes or resumes a session."""
        now = time.time()
        current_session = self.stats.get('current_session', {})
        
        if current_session and (now - current_session.get('last_update', 0)) < self.SESSION_TIMEOUT_HOURS * 3600:
            # Resume existing session
            self.session_start = current_session.get('start_time', now)
            self.session_tokens = current_session.get('tokens', 0)
        else:
            # Archive old session and start a new one
            if current_session:
                self._archive_session(current_session)
            self.session_start = now
            self.session_tokens = 0
        
        # Ensure current_session object exists for saving
        self.stats['current_session'] = {
            'start_time': self.session_start,
            'tokens': self.session_tokens,
            'last_update': now
        }
        self._save_stats()

    def _load_stats(self) -> Dict:
        """Load existing stats or create new"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass  # Will return default stats
        return {
            'total_tokens': 0,
            'total_searches': 0,
            'total_saves': 0,
            'sessions': [],
            'daily_stats': {},
            'current_session': {}
        }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        if not text:
            return 0

        # Use both methods and take the higher estimate
        char_estimate = len(text) / self.CHARS_PER_TOKEN
        word_estimate = len(text.split()) / self.WORDS_PER_TOKEN

        return int(max(char_estimate, word_estimate))

    def track_operation(self, operation: str, input_text: str, output_text: str = "") -> Tuple[int, int]:
        """Track tokens for an operation"""
        input_tokens = self.estimate_tokens(input_text)
        output_tokens = self.estimate_tokens(output_text)
        total_tokens = input_tokens + output_tokens

        # Update session
        self.session_tokens += total_tokens

        # Update daily stats
        today = time.strftime('%Y-%m-%d')
        if today not in self.stats['daily_stats']:
            self.stats['daily_stats'][today] = {
                'tokens': 0,
                'operations': 0,
                'searches': 0,
                'saves': 0
            }

        self.stats['daily_stats'][today]['tokens'] += total_tokens
        self.stats['daily_stats'][today]['operations'] += 1

        if operation == 'search':
            self.stats['total_searches'] += 1
            self.stats['daily_stats'][today]['searches'] += 1
        elif operation == 'save':
            self.stats['total_saves'] += 1
            self.stats['daily_stats'][today]['saves'] += 1

        self.stats['total_tokens'] += total_tokens

        # Update current session in stats object before saving
        self.stats['current_session'] = {
            'start_time': self.session_start,
            'tokens': self.session_tokens,
            'last_update': time.time()
        }

        # Save stats
        self._save_stats()

        return input_tokens, output_tokens

    def _save_stats(self):
        """Save stats to file"""
        with open(self.stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)

    def get_session_summary(self) -> Dict:
        """Get current session summary"""
        duration = time.time() - self.session_start
        return {
            'session_tokens': self.session_tokens,
            'session_duration': duration,
            'tokens_per_minute': self.session_tokens / (duration / 60) if duration > 60 else self.session_tokens,
            'context_usage_percent': (self.session_tokens / 200000) * 100
        }

    def get_daily_summary(self, date: str = None) -> Dict:
        """Get daily summary"""
        if not date:
            date = time.strftime('%Y-%m-%d')

        return self.stats['daily_stats'].get(date, {
            'tokens': 0,
            'operations': 0,
            'searches': 0,
            'saves': 0
        })

    def get_projection(self) -> Dict:
        """Project when context window would be full"""
        # Get last 7 days average
        last_week_tokens = 0
        days_with_data = 0

        for day in sorted(self.stats['daily_stats'].keys())[-7:]:
            last_week_tokens += self.stats['daily_stats'][day]['tokens']
            days_with_data += 1

        if days_with_data == 0:
            avg_tokens_per_day = self.get_daily_summary()['tokens'] # Use today if no history
            if avg_tokens_per_day == 0:
                return {'message': 'No token usage'}
        else:
            avg_tokens_per_day = last_week_tokens / days_with_data

        if avg_tokens_per_day == 0:
            return {'message': 'No token usage'}

        days_until_full = 200000 / avg_tokens_per_day

        return {
            'avg_tokens_per_day': int(avg_tokens_per_day),
            'days_until_full': round(days_until_full, 1),
            'searches_remaining': int((200000 - self.session_tokens) / 2500),
            'current_usage_percent': round((self.session_tokens / 200000) * 100, 2)
        }

    def _archive_session(self, session_data: Dict):
        """Archives a session to the history."""
        if session_data and session_data.get('tokens', 0) > 0:
            duration = session_data.get('last_update', time.time()) - session_data.get('start_time', time.time())
            self.stats['sessions'].append({
                'timestamp': session_data.get('start_time'),
                'duration': duration,
                'tokens': session_data.get('tokens')
            })

    def reset_session(self):
        """Reset session counters"""
        # Archive the current session
        self._archive_session(self.stats.get('current_session'))
        
        # Reset in-memory and on-disk session
        self.session_tokens = 0
        self.session_start = time.time()
        self.stats['current_session'] = {
            'start_time': self.session_start,
            'tokens': self.session_tokens,
            'last_update': self.session_start
        }
        self._save_stats()

    def print_summary(self):
        """Print a nice summary"""
        session = self.get_session_summary()
        daily = self.get_daily_summary()
        projection = self.get_projection()

        print("\n📊 Token Usage Summary")
        print("=" * 50)

        print(f"\n📍 Current Session:")
        print(f"  Tokens used: {session['session_tokens']:,}")
        print(f"  Context usage: {session['context_usage_percent']:.2f}%")
        print(f"  Rate: {session['tokens_per_minute']:.0f} tokens/min")

        print(f"\n📅 Today ({time.strftime('%Y-%m-%d')}):")
        print(f"  Total tokens: {daily['tokens']:,}")
        print(f"  Operations: {daily['operations']}")
        print(f"  Searches: {daily['searches']}")
        print(f"  Saves: {daily['saves']}")

        if 'days_until_full' in projection:
            print(f"\n🔮 Projection:")
            print(f"  Avg tokens/day: {projection['avg_tokens_per_day']:,}")
            print(f"  Days until full: {projection['days_until_full']}")
            print(f"  Searches remaining: {projection['searches_remaining']}")

        print(f"\n💾 All-time:")
        print(f"  Total tokens: {self.stats['total_tokens']:,}")
        print(f"  Total searches: {self.stats['total_searches']}")
        print(f"  Total saves: {self.stats['total_saves']}")


if __name__ == "__main__":
    # Test/Demo
    tracker = TokenTracker()

    # Simulate some operations
    tracker.track_operation("search", "find docker configs", "Here are 20 results..." * 100)
    tracker.track_operation("save", "Implemented new feature with lots of code" * 10)

    tracker.print_summary()