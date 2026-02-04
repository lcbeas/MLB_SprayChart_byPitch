"""
Fangraphs data fetcher

Fetches player projections, statistics, and valuations from Fangraphs.
Uses pybaseball library where possible, with direct scraping as fallback.
"""

import re
import requests
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from typing import Optional, Dict, List, Union
from datetime import datetime

from config import Config
from backend.utils.cache import cached_data


class FangraphsClient:
    """Client for fetching data from Fangraphs."""

    # Projection system identifiers for Fangraphs URLs
    PROJECTION_SYSTEMS = {
        'steamer': 'steamer',
        'steamer600': 'steamer600',
        'zips': 'zips',
        'zipsdc': 'zipsdc',
        'atc': 'atc',
        'thebat': 'thebat',
        'thebatx': 'thebatx',
        'depthcharts': 'fangraphsdc',
    }

    # Ottoneu scoring format mappings for auction calculator
    OTTONEU_FORMATS = {
        'fangraphs_points': 1,
        'sabr_points': 2,
        '4x4': 3,
        '5x5': 4,
        'h2h_fgpts': 5,
        'h2h_sabr': 6,
    }

    # Standard stat columns to include
    BATTING_STATS = [
        'Name', 'Team', 'G', 'PA', 'AB', 'H', '1B', '2B', '3B', 'HR', 'R', 'RBI',
        'BB', 'SO', 'HBP', 'SF', 'SH', 'GDP', 'SB', 'CS', 'AVG', 'OBP', 'SLG',
        'OPS', 'wOBA', 'wRC+', 'WAR', 'playerid'
    ]

    PITCHING_STATS = [
        'Name', 'Team', 'W', 'L', 'SV', 'HLD', 'G', 'GS', 'IP', 'H', 'R', 'ER',
        'HR', 'BB', 'SO', 'K/9', 'BB/9', 'K/BB', 'HR/9', 'BABIP', 'ERA', 'FIP',
        'xFIP', 'WAR', 'playerid'
    ]

    def __init__(self):
        self.base_url = Config.FANGRAPHS_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; OttoneuRosterTool/1.0)'
        })

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request with error handling."""
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _get_csv(self, url: str) -> pd.DataFrame:
        """Fetch a CSV endpoint and return DataFrame."""
        response = self._get(url)
        return pd.read_csv(StringIO(response.text))

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names across different data sources."""
        if df.empty:
            return df

        # Create a copy to avoid modifying original
        df = df.copy()

        # Common column renames
        column_mapping = {
            'playerid': 'fg_id',
            'PlayerId': 'fg_id',
            'IDfg': 'fg_id',
            'mlbamid': 'mlbam_id',
            'MLBAMID': 'mlbam_id',
            'xMLBAMID': 'mlbam_id',
        }

        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})

        return df

    # -------------------------------------------------------------------------
    # Historical Stats
    # -------------------------------------------------------------------------

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_batting_stats(
        self,
        season: int,
        qual: Union[int, str] = 1,
        split: str = '',
        stat_type: str = 'bat'
    ) -> pd.DataFrame:
        """
        Fetch batting statistics for a given season.

        Args:
            season: The MLB season year
            qual: Minimum plate appearances (default 1 for all players, 'y' for qualified)
            split: Split type ('' for full season, 'L' for vs LHP, 'R' for vs RHP)
            stat_type: 'bat' for standard, 'bat-adv' for advanced

        Returns:
            DataFrame with batting statistics
        """
        try:
            # Use pybaseball if available
            from pybaseball import batting_stats
            df = batting_stats(season, qual=qual)
            return self._standardize_columns(df)
        except ImportError:
            pass
        except Exception as e:
            print(f"pybaseball error, falling back to scraping: {e}")

        # Fallback to direct Fangraphs export
        try:
            url = (
                f"{self.base_url}/leaders.aspx?pos=all&stats={stat_type}&lg=all"
                f"&qual={qual}&type=8&season={season}&month=0&season1={season}"
                f"&ind=0&team=0&rost=0&age=0&filter=&players=0"
            )
            # Add export parameter
            url += "&page=1_100000"  # Get all players

            response = self._get(url)
            tables = pd.read_html(StringIO(response.text))
            if tables:
                df = tables[0]
                return self._standardize_columns(df)

        except Exception as e:
            print(f"Error fetching batting stats: {e}")

        return pd.DataFrame()

    @cached_data(hours=Config.CACHE_EXPIRY_HOURS)
    def get_pitching_stats(
        self,
        season: int,
        qual: Union[int, str] = 1,
        split: str = '',
        stat_type: str = 'pit'
    ) -> pd.DataFrame:
        """
        Fetch pitching statistics for a given season.

        Args:
            season: The MLB season year
            qual: Minimum innings pitched (default 1 for all players, 'y' for qualified)
            split: Split type ('' for full season)
            stat_type: 'pit' for standard, 'pit-adv' for advanced

        Returns:
            DataFrame with pitching statistics
        """
        try:
            from pybaseball import pitching_stats
            df = pitching_stats(season, qual=qual)
            return self._standardize_columns(df)
        except ImportError:
            pass
        except Exception as e:
            print(f"pybaseball error, falling back to scraping: {e}")

        # Fallback to direct export
        try:
            url = (
                f"{self.base_url}/leaders.aspx?pos=all&stats={stat_type}&lg=all"
                f"&qual={qual}&type=8&season={season}&month=0&season1={season}"
                f"&ind=0&team=0&rost=0&age=0&filter=&players=0"
            )

            response = self._get(url)
            tables = pd.read_html(StringIO(response.text))
            if tables:
                df = tables[0]
                return self._standardize_columns(df)

        except Exception as e:
            print(f"Error fetching pitching stats: {e}")

        return pd.DataFrame()

    def get_player_stats(
        self,
        player_id: int,
        start_season: int,
        end_season: Optional[int] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical stats for a specific player.

        Args:
            player_id: Fangraphs player ID
            start_season: First season to include
            end_season: Last season (defaults to current year)

        Returns:
            Dict with 'batting' and 'pitching' DataFrames
        """
        if end_season is None:
            end_season = datetime.now().year

        results = {'batting': pd.DataFrame(), 'pitching': pd.DataFrame()}

        try:
            url = f"{self.base_url}/statss.aspx?playerid={player_id}"
            response = self._get(url)
            tables = pd.read_html(StringIO(response.text))

            for table in tables:
                if 'PA' in table.columns or 'AB' in table.columns:
                    results['batting'] = self._standardize_columns(table)
                elif 'IP' in table.columns or 'ERA' in table.columns:
                    results['pitching'] = self._standardize_columns(table)

        except Exception as e:
            print(f"Error fetching player stats: {e}")

        return results

    def get_multi_season_stats(
        self,
        start_season: int,
        end_season: int,
        player_type: str = 'bat'
    ) -> pd.DataFrame:
        """
        Fetch stats aggregated across multiple seasons.

        Args:
            start_season: First season
            end_season: Last season
            player_type: 'bat' for batters, 'pit' for pitchers

        Returns:
            DataFrame with aggregated stats
        """
        all_stats = []

        for season in range(start_season, end_season + 1):
            if player_type == 'bat':
                df = self.get_batting_stats(season)
            else:
                df = self.get_pitching_stats(season)

            if not df.empty:
                df['Season'] = season
                all_stats.append(df)

        if all_stats:
            return pd.concat(all_stats, ignore_index=True)
        return pd.DataFrame()

    # -------------------------------------------------------------------------
    # Projections
    # -------------------------------------------------------------------------

    @cached_data(hours=12)
    def get_projections(
        self,
        system: str = 'steamer',
        player_type: str = 'bat',
        team: str = ''
    ) -> pd.DataFrame:
        """
        Fetch player projections from a specific projection system.

        Args:
            system: Projection system ('steamer', 'zips', 'atc', 'thebat', 'depthcharts')
            player_type: 'bat' for batters, 'pit' for pitchers
            team: Filter by team (empty for all)

        Returns:
            DataFrame with projections
        """
        system_key = self.PROJECTION_SYSTEMS.get(system.lower(), system)

        try:
            # Try pybaseball first
            from pybaseball import fg_batting_data, fg_pitching_data

            if player_type == 'bat':
                df = fg_batting_data(2024, projection=system_key)
            else:
                df = fg_pitching_data(2024, projection=system_key)

            if not df.empty:
                df = self._standardize_columns(df)
                df['projection_system'] = system

                if team:
                    df = df[df['Team'].str.contains(team, case=False, na=False)]

                return df

        except Exception as e:
            print(f"pybaseball projection error: {e}")

        # Fallback: scrape Fangraphs projections page
        try:
            stats_type = 'bat' if player_type == 'bat' else 'pit'
            url = (
                f"{self.base_url}/projections.aspx?pos=all&stats={stats_type}"
                f"&type={system_key}&team={team}&lg=all&players=0"
            )

            response = self._get(url)
            tables = pd.read_html(StringIO(response.text))

            if tables:
                df = tables[0]
                df = self._standardize_columns(df)
                df['projection_system'] = system
                return df

        except Exception as e:
            print(f"Error fetching projections: {e}")

        return pd.DataFrame()

    def get_all_projections(
        self,
        systems: List[str] = None,
        player_type: str = 'bat'
    ) -> pd.DataFrame:
        """
        Fetch projections from multiple systems and combine them.

        Args:
            systems: List of projection systems (defaults to main ones)
            player_type: 'bat' for batters, 'pit' for pitchers

        Returns:
            DataFrame with all projections, system indicated in column
        """
        if systems is None:
            systems = ['steamer', 'zips', 'atc', 'thebatx']

        all_projections = []

        for system in systems:
            df = self.get_projections(system=system, player_type=player_type)
            if not df.empty:
                all_projections.append(df)

        if all_projections:
            return pd.concat(all_projections, ignore_index=True)
        return pd.DataFrame()

    def get_ros_projections(self, player_type: str = 'bat') -> pd.DataFrame:
        """
        Fetch rest-of-season projections (typically Steamer ROS).

        Args:
            player_type: 'bat' for batters, 'pit' for pitchers

        Returns:
            DataFrame with ROS projections
        """
        return self.get_projections(system='steamer', player_type=player_type)

    def get_depth_charts(self, player_type: str = 'bat') -> pd.DataFrame:
        """
        Fetch Fangraphs Depth Charts projections (playing time weighted).

        Args:
            player_type: 'bat' for batters, 'pit' for pitchers

        Returns:
            DataFrame with depth chart projections
        """
        return self.get_projections(system='depthcharts', player_type=player_type)

    # -------------------------------------------------------------------------
    # Ottoneu Auction Calculator
    # -------------------------------------------------------------------------

    @cached_data(hours=6)
    def get_auction_calculator(
        self,
        scoring_format: str = 'fangraphs_points',
        teams: int = 12,
        budget: int = 400,
        projection: str = 'steamer'
    ) -> pd.DataFrame:
        """
        Fetch Ottoneu auction calculator values.

        Args:
            scoring_format: 'fangraphs_points', 'sabr_points', '4x4', '5x5'
            teams: Number of teams in league
            budget: Auction budget per team
            projection: Projection system to use

        Returns:
            DataFrame with player values
        """
        format_id = self.OTTONEU_FORMATS.get(scoring_format.lower(), 1)

        try:
            # Fangraphs auction calculator URL
            url = (
                f"{self.base_url}/auctiontool.aspx?type={format_id}"
                f"&teams={teams}&budget={budget}&projection={projection}"
                f"&lg=MLB&mp=20&msp=5&mrp=5"
            )

            response = self._get(url)
            tables = pd.read_html(StringIO(response.text))

            if tables:
                # Usually the main table with values
                for table in tables:
                    if 'Value' in table.columns or '$' in str(table.columns):
                        df = self._standardize_columns(table)
                        df['scoring_format'] = scoring_format
                        return df

        except Exception as e:
            print(f"Error fetching auction calculator: {e}")

        return pd.DataFrame()

    @cached_data(hours=6)
    def get_ottoneu_values(
        self,
        scoring_format: str = 'fangraphs_points'
    ) -> pd.DataFrame:
        """
        Fetch pre-calculated Ottoneu values from Fangraphs.

        Args:
            scoring_format: Ottoneu scoring format

        Returns:
            DataFrame with Ottoneu dollar values
        """
        # Map format to the Fangraphs Ottoneu values page
        format_map = {
            'fangraphs_points': 'pfg',
            'sabr_points': 'psabr',
            '4x4': 'p4x4',
            '5x5': 'p5x5',
        }

        format_key = format_map.get(scoring_format.lower(), 'pfg')

        try:
            url = f"{self.base_url}/projections.aspx?pos=all&stats=bat&type={format_key}"
            response = self._get(url)
            tables = pd.read_html(StringIO(response.text))

            if tables:
                df = self._standardize_columns(tables[0])
                return df

        except Exception as e:
            print(f"Error fetching Ottoneu values: {e}")

        return pd.DataFrame()

    # -------------------------------------------------------------------------
    # Player Search & Lookup
    # -------------------------------------------------------------------------

    def search_players(self, query: str, player_type: str = 'all') -> pd.DataFrame:
        """
        Search for players by name.

        Args:
            query: Search string
            player_type: 'bat', 'pit', or 'all'

        Returns:
            DataFrame with matching players
        """
        results = []

        # Search in current projections (has most complete player list)
        if player_type in ['bat', 'all']:
            batters = self.get_projections('steamer', 'bat')
            if not batters.empty and 'Name' in batters.columns:
                matches = batters[batters['Name'].str.contains(query, case=False, na=False)]
                if not matches.empty:
                    matches = matches.copy()
                    matches['player_type'] = 'batter'
                    results.append(matches)

        if player_type in ['pit', 'all']:
            pitchers = self.get_projections('steamer', 'pit')
            if not pitchers.empty and 'Name' in pitchers.columns:
                matches = pitchers[pitchers['Name'].str.contains(query, case=False, na=False)]
                if not matches.empty:
                    matches = matches.copy()
                    matches['player_type'] = 'pitcher'
                    results.append(matches)

        if results:
            return pd.concat(results, ignore_index=True)
        return pd.DataFrame()

    def get_player_page(self, player_id: int) -> Dict:
        """
        Scrape player page for comprehensive info.

        Args:
            player_id: Fangraphs player ID

        Returns:
            Dict with player info
        """
        try:
            url = f"{self.base_url}/statss.aspx?playerid={player_id}"
            response = self._get(url)
            soup = BeautifulSoup(response.content, 'lxml')

            player_info = {
                'fg_id': player_id,
                'name': None,
                'team': None,
                'position': None,
                'age': None,
            }

            # Parse player name
            name_el = soup.find('h1', class_='player-name')
            if name_el:
                player_info['name'] = name_el.get_text(strip=True)

            # Parse player info section
            info_section = soup.find('div', class_='player-info')
            if info_section:
                text = info_section.get_text()

                # Extract team
                team_match = re.search(r'Team:\s*(\w+)', text)
                if team_match:
                    player_info['team'] = team_match.group(1)

                # Extract position
                pos_match = re.search(r'Position:\s*(\w+)', text)
                if pos_match:
                    player_info['position'] = pos_match.group(1)

                # Extract age
                age_match = re.search(r'Age:\s*(\d+)', text)
                if age_match:
                    player_info['age'] = int(age_match.group(1))

            return player_info

        except Exception as e:
            print(f"Error fetching player page: {e}")
            return {'fg_id': player_id, 'error': str(e)}

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def get_current_season(self) -> int:
        """Get the current MLB season year."""
        now = datetime.now()
        # If before April, consider it previous season for stats purposes
        if now.month < 4:
            return now.year - 1
        return now.year

    def get_previous_seasons(self, num_seasons: int = 3) -> List[int]:
        """Get list of previous season years."""
        current = self.get_current_season()
        return list(range(current - num_seasons, current))

    def compare_to_projections(
        self,
        player_id: int,
        season: int,
        player_type: str = 'bat'
    ) -> Dict:
        """
        Compare a player's actual stats to their projections.

        Args:
            player_id: Fangraphs player ID
            season: Season year
            player_type: 'bat' or 'pit'

        Returns:
            Dict with actual stats, projections, and differences
        """
        # Get actual stats
        if player_type == 'bat':
            actual = self.get_batting_stats(season)
        else:
            actual = self.get_pitching_stats(season)

        # Get projections
        projected = self.get_projections('steamer', player_type)

        result = {
            'player_id': player_id,
            'season': season,
            'actual': {},
            'projected': {},
            'difference': {}
        }

        if not actual.empty and 'fg_id' in actual.columns:
            player_actual = actual[actual['fg_id'] == player_id]
            if not player_actual.empty:
                result['actual'] = player_actual.iloc[0].to_dict()

        if not projected.empty and 'fg_id' in projected.columns:
            player_proj = projected[projected['fg_id'] == player_id]
            if not player_proj.empty:
                result['projected'] = player_proj.iloc[0].to_dict()

        # Calculate differences for numeric columns
        for key in result['actual']:
            if key in result['projected']:
                try:
                    actual_val = float(result['actual'][key])
                    proj_val = float(result['projected'][key])
                    result['difference'][key] = actual_val - proj_val
                except (ValueError, TypeError):
                    pass

        return result


# Module-level instance for easy importing
client = FangraphsClient()
