"""
Baseball Savant data fetcher

Fetches Statcast data including expected stats, pitch data, and advanced metrics.
"""

import pandas as pd
from typing import Optional
from pybaseball import statcast_batter, statcast_pitcher, playerid_lookup

from config import Config
from backend.utils.cache import cached_data


class SavantClient:
    """Client for fetching data from Baseball Savant."""

    def __init__(self):
        self.base_url = Config.SAVANT_BASE_URL

    def lookup_player_id(self, last_name: str, first_name: str) -> Optional[int]:
        """
        Look up a player's MLB ID by name.

        Args:
            last_name: Player's last name
            first_name: Player's first name

        Returns:
            MLB player ID or None if not found
        """
        try:
            result = playerid_lookup(last_name, first_name)
            if not result.empty:
                return int(result.iloc[0]['key_mlbam'])
        except Exception as e:
            print(f"Error looking up player: {e}")
        return None

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_batter_statcast(self, player_id: int, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch Statcast data for a batter.

        Args:
            player_id: MLB player ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with pitch-level Statcast data
        """
        try:
            return statcast_batter(start_date, end_date, player_id)
        except Exception as e:
            print(f"Error fetching batter statcast: {e}")
            return pd.DataFrame()

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_pitcher_statcast(self, player_id: int, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch Statcast data for a pitcher.

        Args:
            player_id: MLB player ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with pitch-level Statcast data
        """
        try:
            return statcast_pitcher(start_date, end_date, player_id)
        except Exception as e:
            print(f"Error fetching pitcher statcast: {e}")
            return pd.DataFrame()

    def get_expected_stats(self, player_id: int, season: int) -> dict:
        """
        Get expected stats (xBA, xSLG, xwOBA) for a player.

        Args:
            player_id: MLB player ID
            season: The season year

        Returns:
            Dict with expected statistics
        """
        # TODO: Implement expected stats calculation from Statcast data
        return {
            'xBA': None,
            'xSLG': None,
            'xwOBA': None,
            'xERA': None,  # For pitchers
            'barrel_rate': None,
            'hard_hit_rate': None
        }

    def get_pitch_arsenal(self, player_id: int, season: int) -> pd.DataFrame:
        """
        Get pitch arsenal breakdown for a pitcher.

        Args:
            player_id: MLB player ID
            season: The season year

        Returns:
            DataFrame with pitch types and their usage/effectiveness
        """
        # TODO: Implement pitch arsenal analysis
        return pd.DataFrame()

    def get_sprint_speed(self, player_id: int, season: int) -> Optional[float]:
        """
        Get sprint speed for a player.

        Args:
            player_id: MLB player ID
            season: The season year

        Returns:
            Sprint speed in ft/sec or None
        """
        # TODO: Implement sprint speed fetching
        return None


# Module-level instance for easy importing
client = SavantClient()
