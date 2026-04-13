"""
Smart Search - Universal Search across all content types
Searches in ai_instructions, snippets, AND actions with ranked results.

Architecture: Features Layer (depends on Domain + Core)
"""

from typing import List, Dict, Optional
from ..core.database import Database
from .ai_instructions import AIInstructionManager
from .snippets import SnippetManager
from ..domain.search import SearchManager


class SmartSearchManager:
    """
    Universal search across all content types with intelligent ranking.

    Searches in:
    1. ai_instructions (rules, standards, configs)
    2. snippets (code, templates, files)
    3. actions (history, events, decisions)

    Ranking Strategy:
    - ai_instructions: Highest priority (persistent knowledge)
    - snippets: Medium priority (reusable code)
    - actions: Lowest priority (historical context)

    Within each type:
    - Relevance score (FTS rank or match quality)
    - Usage count / importance
    - Recency

    Use Cases:
    - "wolf prod ssh" → Finds SSH config in instructions
    - "security sanitizer" → Finds security rules + code snippets
    - "authentication" → Finds implementations + decisions

    Dependencies:
    - AIInstructionManager
    - SnippetManager
    - SearchManager (actions)
    - Database
    """

    def __init__(
        self,
        database: Database,
        ai_instruction_manager: AIInstructionManager = None,
        snippet_manager: SnippetManager = None,
        search_manager: SearchManager = None
    ):
        """
        Initialize SmartSearchManager.

        Args:
            database: Database instance
            ai_instruction_manager: Optional pre-initialized manager
            snippet_manager: Optional pre-initialized manager
            search_manager: Optional pre-initialized manager
        """
        self.db = database
        self.conn = database.conn

        # Initialize managers (or use provided ones)
        self.ai_instructions = ai_instruction_manager or AIInstructionManager(database)
        self.snippets = snippet_manager or SnippetManager(database)
        self.actions = search_manager or SearchManager(database)

    def search(
        self,
        query: str,
        limit_per_type: int = 5,
        total_limit: int = 20,
        include_types: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Universal search across all content types with ranked results.

        Args:
            query: Search query
            limit_per_type: Max results per content type
            total_limit: Max total results (top-ranked)
            include_types: Optional list to filter types
                          ['instructions', 'snippets', 'actions']

        Returns:
            Dict with keys: 'instructions', 'snippets', 'actions', 'ranked_all'
            Each contains list of results with 'content_type' and 'rank' fields

        Ranking Algorithm:
            1. Search each content type independently
            2. Calculate base score per type:
               - instructions: 100 (highest priority)
               - snippets: 70 (medium priority)
               - actions: 40 (lowest priority - historical)
            3. Add relevance boost (FTS rank * 10)
            4. Sort by final score DESC
            5. Return top N results

        Example:
            results = search("wolf prod ssh")
            # Returns:
            # {
            #   'instructions': [{instruction #52 with SSH hosts}],
            #   'snippets': [{ssh-config snippet}],
            #   'actions': [{deployment to wolf_prod}],
            #   'ranked_all': [top 20 results sorted by score]
            # }
        """
        # Determine which types to include
        if include_types is None:
            include_types = ['instructions', 'snippets', 'actions']

        results = {}

        # 1. Search AI Instructions
        if 'instructions' in include_types:
            instructions = self.ai_instructions.search_filtered(
                query=query,
                limit=limit_per_type
            )

            # Add content_type and base score
            for inst in instructions:
                inst['content_type'] = 'instruction'
                inst['base_score'] = 100  # Highest priority
                inst['relevance_boost'] = inst.get('rank', 0.1) * 10 if 'rank' in inst else 5
                inst['final_score'] = inst['base_score'] + inst['relevance_boost']
                inst['result_type'] = 'instruction'  # For display

            results['instructions'] = instructions
        else:
            results['instructions'] = []

        # 2. Search Snippets
        if 'snippets' in include_types:
            snippets = self.snippets.search(
                query=query,
                limit=limit_per_type
            )

            # Add content_type and base score
            for snippet in snippets:
                snippet['content_type'] = 'snippet'
                snippet['base_score'] = 70  # Medium priority
                snippet['relevance_boost'] = 5  # Snippets don't have FTS rank
                snippet['final_score'] = snippet['base_score'] + snippet['relevance_boost']
                snippet['result_type'] = 'snippet'

            results['snippets'] = snippets
        else:
            results['snippets'] = []

        # 3. Search Actions
        if 'actions' in include_types:
            actions = self.actions.search(
                query=query,
                limit=limit_per_type
            )

            # Add content_type and base score
            for action in actions:
                action['content_type'] = 'action'
                action['base_score'] = 40  # Lowest priority (historical)
                # Actions might have rank from FTS
                action['relevance_boost'] = action.get('rank', 0.05) * 10 if 'rank' in action else 3
                action['final_score'] = action['base_score'] + action['relevance_boost']
                action['result_type'] = 'action'

            results['actions'] = actions
        else:
            results['actions'] = []

        # 4. Combine and rank all results
        all_results = []
        all_results.extend(results['instructions'])
        all_results.extend(results['snippets'])
        all_results.extend(results['actions'])

        # Sort by final_score DESC
        all_results.sort(key=lambda x: x['final_score'], reverse=True)

        # Limit total results
        results['ranked_all'] = all_results[:total_limit]

        # Add result counts
        results['counts'] = {
            'instructions': len(results['instructions']),
            'snippets': len(results['snippets']),
            'actions': len(results['actions']),
            'total': len(all_results),
            'ranked_total': len(results['ranked_all'])
        }

        return results

    def search_simple(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        Simplified universal search - returns only ranked results.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of ranked results with content_type field

        This is a convenience method that calls search() and returns
        only the 'ranked_all' results.
        """
        results = self.search(query, total_limit=limit)
        return results['ranked_all']
