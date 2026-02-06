"""
Ottoneu data fetcher

Fetches league-specific data including rosters, salaries, and player ownership.
"""

import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from io import StringIO
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from config import Config
from backend.utils.cache import cached_data


class OttoneuClient:
    """Client for fetching data from Ottoneu."""

    # Ottoneu scoring format mappings
    SCORING_FORMATS = {
        1: 'FanGraphs Points',
        2: 'SABR Points',
        3: '4x4 Classic',
        4: '5x5 Classic',
        5: 'H2H FanGraphs Points',
        6: 'H2H SABR Points',
    }

    def __init__(self, league_id: Optional[str] = None):
        self.base_url = Config.OTTONEU_BASE_URL
        self.league_id = league_id or Config.OTTONEU_LEAGUE_ID
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; OttoneuRosterTool/1.0)'
        })

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request with error handling."""
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _get_soup(self, url: str) -> BeautifulSoup:
        """Fetch a page and return BeautifulSoup object."""
        response = self._get(url)
        return BeautifulSoup(response.content, 'lxml')

    def _get_csv(self, url: str) -> pd.DataFrame:
        """Fetch a CSV endpoint and return DataFrame."""
        response = self._get(url)
        return pd.read_csv(StringIO(response.text))

    def _validate_league_id(self):
        """Ensure league ID is configured."""
        if not self.league_id:
            raise ValueError(
                "League ID not configured. Set OTTONEU_LEAGUE_ID in config.py "
                "or pass league_id to OttoneuClient()"
            )

    @cached_data(hours=1)
    def get_league_rosters(self) -> pd.DataFrame:
        """
        Fetch all rosters in the league via CSV export.

        Returns:
            DataFrame with columns:
            - ottoneu_id: Ottoneu player ID
            - fg_id: FanGraphs player ID
            - name: Player name
            - team: MLB team
            - position: Eligible positions
            - salary: Current salary
            - owner_id: Ottoneu team ID
            - owner_name: Fantasy team name
        """
        self._validate_league_id()

        url = f"{self.base_url}/{self.league_id}/rosterexport"

        try:
            df = self._get_csv(url)

            # Standardize column names - lowercase and replace spaces
            df.columns = df.columns.str.lower().str.replace(' ', '_').str.strip()

            # Debug: print actual columns
            print(f"Roster columns: {list(df.columns)}")

            # Comprehensive column mapping for various Ottoneu export formats
            column_mapping = {
                # Ottoneu ID variations
                'ottoneu_id': 'ottoneu_id',
                'otto_id': 'ottoneu_id',
                'player_id': 'ottoneu_id',
                # FanGraphs ID variations
                'fg_majorleagueid': 'fg_id',
                'fg_id': 'fg_id',
                'fangraphs_id': 'fg_id',
                'fg_minorleagueid': 'fg_minor_id',
                # MLBAM ID
                'mlbam_id': 'mlbam_id',
                'mlb_id': 'mlbam_id',
                # Name variations
                'name': 'name',
                'player_name': 'name',
                'player': 'name',
                # Team variations
                'team': 'mlb_team',
                'mlb_team': 'mlb_team',
                'org': 'mlb_team',
                # Position variations
                'pos': 'position',
                'position': 'position',
                'positions': 'position',
                # Salary variations
                'salary': 'salary',
                'sal': 'salary',
                '$': 'salary',
                # Owner ID variations
                'team_id': 'owner_id',
                'teamid': 'owner_id',
                'owner_id': 'owner_id',
                'fantasy_team_id': 'owner_id',
                # Owner name variations
                'team_name': 'owner_name',
                'teamname': 'owner_name',
                'owner_name': 'owner_name',
                'owner': 'owner_name',
                'fantasy_team': 'owner_name',
            }

            # Only rename columns that exist
            rename_cols = {k: v for k, v in column_mapping.items() if k in df.columns}
            df = df.rename(columns=rename_cols)

            # Clean salary column (remove $ and convert to float)
            if 'salary' in df.columns:
                df['salary'] = df['salary'].replace(r'[\$,]', '', regex=True).astype(float)

            return df

        except Exception as e:
            print(f"Error fetching roster export: {e}")
            return pd.DataFrame()

    def get_teams(self) -> list:
        """
        Get all teams in the league with their IDs and names.
        Extracts from roster data which is more reliable than standings.

        Returns:
            List of dicts with team_id, team_name, player_count, total_salary
        """
        rosters = self.get_league_rosters()

        if rosters.empty:
            return []

        teams = []

        # Find owner columns
        owner_id_col = None
        owner_name_col = None

        for col in rosters.columns:
            if col in ['owner_id', 'team_id', 'teamid']:
                owner_id_col = col
            if col in ['owner_name', 'team_name', 'teamname', 'owner']:
                owner_name_col = col

        if not owner_id_col:
            print(f"Could not find owner_id column. Available: {list(rosters.columns)}")
            return []

        # Group by owner
        for owner_id in rosters[owner_id_col].unique():
            if pd.isna(owner_id):
                continue

            team_players = rosters[rosters[owner_id_col] == owner_id]

            team = {
                'team_id': int(owner_id) if pd.notna(owner_id) else None,
                'team_name': team_players[owner_name_col].iloc[0] if owner_name_col and not team_players.empty else f'Team {owner_id}',
                'player_count': len(team_players),
                'total_salary': team_players['salary'].sum() if 'salary' in team_players.columns else 0
            }
            teams.append(team)

        # Sort by team name
        teams.sort(key=lambda x: x.get('team_name', ''))

        return teams

    def get_my_roster(self, team_id: Optional[int] = None) -> pd.DataFrame:
        """
        Get roster for a specific team (or first team if not specified).

        Args:
            team_id: Ottoneu team ID (optional)

        Returns:
            DataFrame with team's roster
        """
        all_rosters = self.get_league_rosters()

        if all_rosters.empty:
            return pd.DataFrame()

        if team_id:
            return all_rosters[all_rosters['owner_id'] == team_id]

        # Return first team's roster if no team_id specified
        first_owner = all_rosters['owner_id'].iloc[0]
        return all_rosters[all_rosters['owner_id'] == first_owner]

    @cached_data(hours=1)
    def get_free_agents(self, position: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch available free agents by comparing league rosters to average values.
        Free agents are players in the average values list not owned in this league.

        Args:
            position: Filter by position (e.g., 'SP', '1B', 'OF')

        Returns:
            DataFrame with free agent players and their average values
        """
        self._validate_league_id()

        # Get all rostered players in league
        rosters = self.get_league_rosters()
        if rosters.empty:
            return pd.DataFrame()

        # Get average values (all available players)
        avg_values = self.get_average_values()
        if avg_values.empty:
            print("Warning: Could not fetch average values for free agent lookup")
            return pd.DataFrame()

        # Find rostered player IDs - check for various column names
        rostered_ids = set()
        for id_col in ['ottoneu_id', 'otto_id', 'player_id']:
            if id_col in rosters.columns:
                rostered_ids = set(rosters[id_col].dropna().astype(int))
                break

        if not rostered_ids:
            print(f"Warning: Could not find ID column in rosters. Columns: {list(rosters.columns)}")
            return avg_values.copy()  # Return all as potential free agents

        # Find matching ID column in avg_values
        avg_id_col = None
        for id_col in ['ottoneu_id', 'otto_id', 'player_id', 'id']:
            if id_col in avg_values.columns:
                avg_id_col = id_col
                break

        if avg_id_col:
            free_agents = avg_values[~avg_values[avg_id_col].isin(rostered_ids)].copy()
        else:
            print(f"Warning: Could not find ID column in avg_values. Columns: {list(avg_values.columns)}")
            return pd.DataFrame()

        # Filter by position if specified
        if position and 'position' in free_agents.columns:
            # Handle multi-position eligibility (e.g., "1B/OF")
            free_agents = free_agents[
                free_agents['position'].str.contains(position, case=False, na=False)
            ]

        # Sort by average value descending
        if 'avg_salary' in free_agents.columns:
            free_agents = free_agents.sort_values('avg_salary', ascending=False)

        return free_agents

    @cached_data(hours=6)
    def get_average_values(self, scoring_format: Optional[int] = None) -> pd.DataFrame:
        """
        Fetch average auction values across all Ottoneu leagues.

        Args:
            scoring_format: Ottoneu format ID (1=FGPts, 2=SABR, 3=4x4, 4=5x5, etc.)
                          If None, tries to detect from league or defaults to FGPts.

        Returns:
            DataFrame with columns:
            - ottoneu_id: Ottoneu player ID
            - name: Player name
            - position: Eligible positions
            - mlb_team: MLB team
            - avg_salary: Average salary across leagues
            - roster_pct: Percentage of leagues rostered
        """
        # Build URL with optional format filter
        url = f"{self.base_url}/averageValues?export=csv"
        if scoring_format:
            url += f"&format={scoring_format}"

        try:
            df = self._get_csv(url)

            # Standardize column names
            df.columns = df.columns.str.lower().str.replace(' ', '_')

            # Common column mappings
            column_mapping = {
                'ottoneu_id': 'ottoneu_id',
                'id': 'ottoneu_id',
                'name': 'name',
                'positions': 'position',
                'pos': 'position',
                'team': 'mlb_team',
                'avg_value': 'avg_salary',
                'average_value': 'avg_salary',
                'avg_salary': 'avg_salary',
                'roster_%': 'roster_pct',
                'roster_pct': 'roster_pct',
                'rostered': 'roster_pct',
            }

            rename_cols = {k: v for k, v in column_mapping.items() if k in df.columns}
            df = df.rename(columns=rename_cols)

            # Clean numeric columns
            if 'avg_salary' in df.columns:
                df['avg_salary'] = pd.to_numeric(
                    df['avg_salary'].replace(r'[\$,]', '', regex=True),
                    errors='coerce'
                )

            if 'roster_pct' in df.columns:
                df['roster_pct'] = pd.to_numeric(
                    df['roster_pct'].replace(r'[%]', '', regex=True),
                    errors='coerce'
                )

            return df

        except Exception as e:
            print(f"Error fetching average values: {e}")
            return pd.DataFrame()

    @cached_data(hours=1)
    def get_player_info(self, player_id: int) -> Dict:
        """
        Fetch detailed info for a specific player from their Ottoneu page.

        Args:
            player_id: The Ottoneu player ID

        Returns:
            Dict with player information including salary history
        """
        self._validate_league_id()

        url = f"{self.base_url}/{self.league_id}/playercard?id={player_id}"

        try:
            soup = self._get_soup(url)

            player_info = {
                'ottoneu_id': player_id,
                'name': None,
                'position': None,
                'mlb_team': None,
                'salary': None,
                'owner': None,
                'salary_history': [],
            }

            # Parse player name from header
            header = soup.find('h1')
            if header:
                player_info['name'] = header.get_text(strip=True)

            # Parse player details table
            details_table = soup.find('table', class_='player-details')
            if details_table:
                rows = details_table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)

                        if 'position' in label:
                            player_info['position'] = value
                        elif 'team' in label:
                            player_info['mlb_team'] = value
                        elif 'salary' in label:
                            player_info['salary'] = float(value.replace('$', '').replace(',', ''))
                        elif 'owner' in label:
                            player_info['owner'] = value

            # Parse salary history if available
            history_table = soup.find('table', class_='salary-history')
            if history_table:
                rows = history_table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        player_info['salary_history'].append({
                            'date': cells[0].get_text(strip=True),
                            'action': cells[1].get_text(strip=True),
                            'salary': cells[2].get_text(strip=True),
                        })

            return player_info

        except Exception as e:
            print(f"Error fetching player info: {e}")
            return {'ottoneu_id': player_id, 'error': str(e)}

    def get_player_salary_history(self, player_id: int) -> pd.DataFrame:
        """
        Fetch salary history for a specific player.

        Args:
            player_id: The Ottoneu player ID

        Returns:
            DataFrame with salary history
        """
        player_info = self.get_player_info(player_id)
        history = player_info.get('salary_history', [])

        if not history:
            return pd.DataFrame()

        return pd.DataFrame(history)

    @cached_data(hours=1)
    def get_league_standings(self) -> pd.DataFrame:
        """
        Fetch current league standings.

        Returns:
            DataFrame with team standings including:
            - team_id, team_name, owner
            - points/wins/categories depending on format
            - rank
        """
        self._validate_league_id()

        url = f"{self.base_url}/{self.league_id}/standings"

        try:
            soup = self._get_soup(url)

            # Find standings table
            standings_table = soup.find('table', {'id': 'standings'})
            if not standings_table:
                # Try alternate selectors
                standings_table = soup.find('table', class_='standings')

            if not standings_table:
                # Parse from page tables
                tables = pd.read_html(StringIO(str(soup)))
                if tables:
                    df = tables[0]
                    df.columns = df.columns.str.lower().str.replace(' ', '_')
                    return df
                return pd.DataFrame()

            # Parse table with pandas
            df = pd.read_html(StringIO(str(standings_table)))[0]
            df.columns = df.columns.str.lower().str.replace(' ', '_')

            return df

        except Exception as e:
            print(f"Error fetching standings: {e}")
            return pd.DataFrame()

    @cached_data(hours=0.5)  # 30 minute cache for transactions
    def get_recent_transactions(self, days: int = 7) -> pd.DataFrame:
        """
        Fetch recent league transactions.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            DataFrame with transaction details:
            - date, type (add/drop/trade), player, team, salary
        """
        self._validate_league_id()

        url = f"{self.base_url}/{self.league_id}/transactions"

        try:
            soup = self._get_soup(url)

            transactions = []

            # Find transaction entries
            tx_list = soup.find_all('div', class_='transaction')
            if not tx_list:
                # Try alternate: look for transaction table
                tx_table = soup.find('table', class_='transactions')
                if tx_table:
                    df = pd.read_html(StringIO(str(tx_table)))[0]
                    df.columns = df.columns.str.lower().str.replace(' ', '_')
                    return df

            for tx in tx_list:
                tx_data = {
                    'date': None,
                    'type': None,
                    'player': None,
                    'team': None,
                    'salary': None,
                }

                # Parse transaction date
                date_el = tx.find(class_='transaction-date')
                if date_el:
                    tx_data['date'] = date_el.get_text(strip=True)

                # Parse transaction type (add, drop, trade)
                type_el = tx.find(class_='transaction-type')
                if type_el:
                    tx_data['type'] = type_el.get_text(strip=True).lower()

                # Parse player name
                player_el = tx.find('a', class_='player-link')
                if player_el:
                    tx_data['player'] = player_el.get_text(strip=True)

                # Parse team
                team_el = tx.find(class_='team-name')
                if team_el:
                    tx_data['team'] = team_el.get_text(strip=True)

                # Parse salary
                salary_el = tx.find(class_='salary')
                if salary_el:
                    salary_text = salary_el.get_text(strip=True)
                    tx_data['salary'] = float(salary_text.replace('$', '').replace(',', ''))

                transactions.append(tx_data)

            df = pd.DataFrame(transactions)

            # Filter by date if we have date info
            if not df.empty and 'date' in df.columns and df['date'].notna().any():
                try:
                    df['date'] = pd.to_datetime(df['date'])
                    cutoff = datetime.now() - timedelta(days=days)
                    df = df[df['date'] >= cutoff]
                except Exception:
                    pass  # Keep all if date parsing fails

            return df

        except Exception as e:
            print(f"Error fetching transactions: {e}")
            return pd.DataFrame()

    def get_league_info(self) -> Dict:
        """
        Fetch basic league information.

        Returns:
            Dict with league name, format, number of teams, etc.
        """
        self._validate_league_id()

        url = f"{self.base_url}/{self.league_id}"

        try:
            soup = self._get_soup(url)

            info = {
                'league_id': self.league_id,
                'name': None,
                'format': None,
                'num_teams': None,
            }

            # Parse league name
            title = soup.find('title')
            if title:
                info['name'] = title.get_text(strip=True).split('|')[0].strip()

            # Look for format info
            format_el = soup.find(string=re.compile(r'(FanGraphs Points|SABR Points|4x4|5x5)'))
            if format_el:
                info['format'] = format_el.strip()

            return info

        except Exception as e:
            print(f"Error fetching league info: {e}")
            return {'league_id': self.league_id, 'error': str(e)}

    def search_players(self, query: str) -> pd.DataFrame:
        """
        Search for players by name in average values.

        Args:
            query: Player name search string

        Returns:
            DataFrame with matching players
        """
        avg_values = self.get_average_values()

        if avg_values.empty or 'name' not in avg_values.columns:
            return pd.DataFrame()

        # Case-insensitive search
        mask = avg_values['name'].str.contains(query, case=False, na=False)
        return avg_values[mask].copy()

    def get_roster_by_position(self, position: str) -> pd.DataFrame:
        """
        Get all rostered players at a specific position across the league.

        Args:
            position: Position to filter (e.g., 'SP', '1B', 'OF')

        Returns:
            DataFrame with players at that position
        """
        rosters = self.get_league_rosters()

        if rosters.empty or 'position' not in rosters.columns:
            return pd.DataFrame()

        mask = rosters['position'].str.contains(position, case=False, na=False)
        return rosters[mask].sort_values('salary', ascending=False)

    def calculate_surplus_values(self) -> pd.DataFrame:
        """
        Calculate surplus value for all rostered players.
        Surplus = Average Value - Current Salary

        Returns:
            DataFrame with salary, avg_value, and surplus columns
        """
        rosters = self.get_league_rosters()
        avg_values = self.get_average_values()

        if rosters.empty or avg_values.empty:
            return pd.DataFrame()

        # Merge on ottoneu_id
        merged = rosters.merge(
            avg_values[['ottoneu_id', 'avg_salary']],
            on='ottoneu_id',
            how='left'
        )

        # Calculate surplus
        merged['surplus'] = merged['avg_salary'] - merged['salary']

        return merged.sort_values('surplus', ascending=False)


# Module-level instance for easy importing
client = OttoneuClient()
