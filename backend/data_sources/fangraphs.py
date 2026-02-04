"""
Fangraphs data fetcher

Fetches player projections, statistics, and valuations from Fangraphs.
"""

import pandas as pd
from typing import Optional, Dict, List
from pybaseball import batting_stats, pitching_stats, fg_batting_data, fg_pitching_data

from config import Config
from backend.utils.cache import cached_data


class FangraphsClient:
    """Client for fetching data from Fangraphs."""

    def __init__(self):
        self.base_url = Config.FANGRAPHS_BASE_URL

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_batting_stats(self, season: int, qual: int = 1) -> pd.DataFrame:
        """
        Fetch batting statistics for a given season.

        Args:
            season: The MLB season year
            qual: Minimum plate appearances (default 1 for all players)

        Returns:
            DataFrame with batting statistics
        """
        try:
            return batting_stats(season, qual=qual)
        except Exception as e:
            print(f"Error fetching batting stats: {e}")
            return pd.DataFrame()

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_pitching_stats(self, season: int, qual: int = 1) -> pd.DataFrame:
        """
        Fetch pitching statistics for a given season.

        Args:
            season: The MLB season year
            qual: Minimum innings pitched (default 1 for all players)

        Returns:
            DataFrame with pitching statistics
        """
        try:
            return pitching_stats(season, qual=qual)
        except Exception as e:
            print(f"Error fetching pitching stats: {e}")
            return pd.DataFrame()

    def get_projections(self, system: str = 'steamer') -> Dict[str, pd.DataFrame]:
        """
        Fetch player projections from a specific projection system.

        Args:
            system: Projection system ('steamer', 'zips', 'atc', 'thebat')

        Returns:
            Dict with 'batting' and 'pitching' DataFrames
        """
        # TODO: Implement projection fetching
        # This will require scraping Fangraphs projection pages
        return {
            'batting': pd.DataFrame(),
            'pitching': pd.DataFrame()
        }

    def get_auction_values(self, league_type: str = 'ottoneu') -> pd.DataFrame:
        """
        Fetch auction values for Ottoneu leagues.

        Args:
            league_type: Type of league for value calculations

        Returns:
            DataFrame with player auction values
        """
        # TODO: Implement Ottoneu value fetching from Fangraphs
        return pd.DataFrame()


# Module-level instance for easy importing
client = FangraphsClient()
