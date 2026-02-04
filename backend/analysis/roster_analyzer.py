"""
Roster Analyzer

Analyzes roster composition and compares to league and championship-caliber teams.
Identifies positional strengths/weaknesses and improvement opportunities.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from datetime import datetime

from backend.data_sources.ottoneu import OttoneuClient
from backend.data_sources.fangraphs import FangraphsClient
from backend.ml.models.player_value import PlayerValueModel


class RosterAnalyzer:
    """
    Analyzes roster composition and identifies improvement opportunities.

    Compares:
    - Your roster vs league average
    - Your roster vs top teams in league
    - Your roster vs championship teams across Ottoneu
    """

    # Position groupings for analysis
    POSITION_GROUPS = {
        'C': ['C'],
        '1B': ['1B'],
        '2B': ['2B'],
        'SS': ['SS'],
        '3B': ['3B'],
        'OF': ['LF', 'CF', 'RF', 'OF'],
        'UTIL': ['DH', 'UTIL'],
        'SP': ['SP'],
        'RP': ['RP'],
    }

    def __init__(self, league_id: Optional[str] = None):
        self.ottoneu_client = OttoneuClient(league_id=league_id)
        self.fg_client = FangraphsClient()
        self.value_model = PlayerValueModel()
        self.value_model.load_models()

    def analyze_roster(
        self,
        team_id: int,
        compare_to: str = 'league'
    ) -> Dict:
        """
        Comprehensive roster analysis.

        Args:
            team_id: Your Ottoneu team ID
            compare_to: 'league' or 'top_teams'

        Returns:
            Dict with analysis results
        """
        # Get your roster
        my_roster = self.ottoneu_client.get_my_roster(team_id=team_id)
        if my_roster.empty:
            return {'error': 'Could not load roster'}

        # Get league context
        all_rosters = self.ottoneu_client.get_league_rosters()
        standings = self.ottoneu_client.get_league_standings()

        # Analyze by position
        positional_analysis = self._analyze_positions(my_roster, all_rosters)

        # Compare to league
        league_comparison = self._compare_to_league(my_roster, all_rosters)

        # Compare to top teams
        top_team_comparison = self._compare_to_top_teams(my_roster, all_rosters, standings)

        # Identify weaknesses and improvements
        weaknesses = self._identify_weaknesses(positional_analysis, league_comparison)

        # Get buy low / sell high recommendations
        value_analysis = self._analyze_value_opportunities(my_roster)

        # Calculate overall roster strength
        roster_score = self._calculate_roster_score(
            positional_analysis, league_comparison, top_team_comparison
        )

        return {
            'team_id': team_id,
            'timestamp': datetime.now().isoformat(),
            'roster_score': roster_score,
            'positional_analysis': positional_analysis,
            'league_comparison': league_comparison,
            'top_team_comparison': top_team_comparison,
            'weaknesses': weaknesses,
            'value_opportunities': value_analysis,
            'recommendations': self._generate_recommendations(
                weaknesses, value_analysis, positional_analysis
            ),
        }

    def _analyze_positions(
        self,
        my_roster: pd.DataFrame,
        all_rosters: pd.DataFrame
    ) -> Dict:
        """Analyze roster by position group."""
        analysis = {}

        for position, eligible in self.POSITION_GROUPS.items():
            # My players at this position
            my_players = my_roster[
                my_roster['position'].str.contains('|'.join(eligible), case=False, na=False)
            ].copy()

            if my_players.empty:
                analysis[position] = {
                    'players': [],
                    'total_salary': 0,
                    'avg_salary': 0,
                    'count': 0,
                    'projected_war': 0,
                }
                continue

            # League players at this position
            league_players = all_rosters[
                all_rosters['position'].str.contains('|'.join(eligible), case=False, na=False)
            ]

            # Calculate metrics
            my_salary = my_players['salary'].sum() if 'salary' in my_players.columns else 0
            league_avg_salary = league_players['salary'].mean() if 'salary' in league_players.columns else 0

            analysis[position] = {
                'players': my_players[['name', 'salary', 'position']].to_dict('records') if 'name' in my_players.columns else [],
                'total_salary': round(my_salary, 1),
                'avg_salary': round(my_players['salary'].mean(), 1) if 'salary' in my_players.columns else 0,
                'count': len(my_players),
                'league_avg_salary': round(league_avg_salary, 1),
                'salary_vs_league': round(my_salary / max(league_avg_salary, 1) - 1, 2) * 100 if league_avg_salary else 0,
                'top_player_salary': my_players['salary'].max() if 'salary' in my_players.columns else 0,
            }

        return analysis

    def _compare_to_league(
        self,
        my_roster: pd.DataFrame,
        all_rosters: pd.DataFrame
    ) -> Dict:
        """Compare roster to league average."""
        comparison = {}

        # Get unique teams
        if 'owner_id' not in all_rosters.columns:
            return comparison

        teams = all_rosters['owner_id'].unique()
        team_stats = []

        for team in teams:
            team_roster = all_rosters[all_rosters['owner_id'] == team]
            team_stats.append({
                'team_id': team,
                'total_salary': team_roster['salary'].sum() if 'salary' in team_roster.columns else 0,
                'player_count': len(team_roster),
                'avg_salary': team_roster['salary'].mean() if 'salary' in team_roster.columns else 0,
            })

        league_df = pd.DataFrame(team_stats)

        # My stats
        my_salary = my_roster['salary'].sum() if 'salary' in my_roster.columns else 0
        my_count = len(my_roster)

        comparison = {
            'my_total_salary': round(my_salary, 1),
            'league_avg_salary': round(league_df['total_salary'].mean(), 1),
            'league_median_salary': round(league_df['total_salary'].median(), 1),
            'salary_rank': int((league_df['total_salary'] < my_salary).sum()) + 1,
            'total_teams': len(teams),
            'my_player_count': my_count,
            'league_avg_player_count': round(league_df['player_count'].mean(), 1),
            'cap_space': 400 - my_salary,  # Ottoneu cap
        }

        return comparison

    def _compare_to_top_teams(
        self,
        my_roster: pd.DataFrame,
        all_rosters: pd.DataFrame,
        standings: pd.DataFrame
    ) -> Dict:
        """Compare roster to top performing teams."""
        comparison = {}

        if standings.empty or 'owner_id' not in all_rosters.columns:
            return comparison

        # Get top 3 teams from standings
        top_teams = standings.head(3)

        # Analyze positional differences
        for position, eligible in self.POSITION_GROUPS.items():
            my_players = my_roster[
                my_roster['position'].str.contains('|'.join(eligible), case=False, na=False)
            ]
            my_salary = my_players['salary'].sum() if 'salary' in my_players.columns else 0

            # Top teams' average at this position
            top_salaries = []
            for _, team_row in top_teams.iterrows():
                team_id = team_row.get('team_id', team_row.get('owner_id'))
                if team_id:
                    team_players = all_rosters[
                        (all_rosters['owner_id'] == team_id) &
                        (all_rosters['position'].str.contains('|'.join(eligible), case=False, na=False))
                    ]
                    top_salaries.append(team_players['salary'].sum() if 'salary' in team_players.columns else 0)

            avg_top = np.mean(top_salaries) if top_salaries else 0

            comparison[position] = {
                'my_salary': round(my_salary, 1),
                'top_teams_avg': round(avg_top, 1),
                'difference': round(my_salary - avg_top, 1),
                'gap_pct': round((my_salary / max(avg_top, 1) - 1) * 100, 1) if avg_top else 0,
            }

        return comparison

    def _identify_weaknesses(
        self,
        positional_analysis: Dict,
        league_comparison: Dict
    ) -> List[Dict]:
        """Identify roster weaknesses."""
        weaknesses = []

        for position, stats in positional_analysis.items():
            # Check if position is understaffed
            if stats['count'] == 0:
                weaknesses.append({
                    'position': position,
                    'type': 'no_players',
                    'severity': 'critical',
                    'message': f'No players at {position}',
                })
            elif stats['count'] == 1 and position not in ['C', 'UTIL']:
                weaknesses.append({
                    'position': position,
                    'type': 'low_depth',
                    'severity': 'moderate',
                    'message': f'Only 1 player at {position} - no depth',
                })

            # Check if spending is below league average
            if stats.get('salary_vs_league', 0) < -30:
                weaknesses.append({
                    'position': position,
                    'type': 'underinvested',
                    'severity': 'moderate',
                    'message': f'{position} salary {abs(stats["salary_vs_league"]):.0f}% below league average',
                })

        # Sort by severity
        severity_order = {'critical': 0, 'moderate': 1, 'minor': 2}
        weaknesses.sort(key=lambda x: severity_order.get(x['severity'], 3))

        return weaknesses

    def _analyze_value_opportunities(self, my_roster: pd.DataFrame) -> Dict:
        """Identify buy low / sell high opportunities using ML model."""
        if not self.value_model.is_trained('batter'):
            return {
                'buy_low': [],
                'sell_high': [],
                'message': 'Value model not trained - run training first'
            }

        # Prepare roster for analysis
        roster_data = []
        for _, row in my_roster.iterrows():
            roster_data.append({
                'player_id': row.get('fg_id', row.get('ottoneu_id')),
                'name': row.get('name', ''),
                'position': row.get('position', ''),
                'salary': row.get('salary', 0),
                'player_type': 'pitcher' if any(p in str(row.get('position', ''))
                                                for p in ['SP', 'RP']) else 'batter',
                'mlbam_id': row.get('mlbam_id'),
            })

        roster_df = pd.DataFrame(roster_data)

        if roster_df.empty:
            return {'buy_low': [], 'sell_high': []}

        # Get value analysis
        analysis = self.value_model.identify_buy_low_sell_high(roster_df)

        return {
            'buy_low': analysis['buy_low'].head(5).to_dict('records') if not analysis['buy_low'].empty else [],
            'sell_high': analysis['sell_high'].head(5).to_dict('records') if not analysis['sell_high'].empty else [],
        }

    def _calculate_roster_score(
        self,
        positional: Dict,
        league_comp: Dict,
        top_comp: Dict
    ) -> Dict:
        """Calculate overall roster strength score (0-100)."""
        scores = []

        # Positional coverage score
        positions_filled = sum(1 for p in positional.values() if p['count'] > 0)
        coverage_score = (positions_filled / len(positional)) * 100
        scores.append(coverage_score)

        # Salary deployment score
        if league_comp.get('my_total_salary') and league_comp.get('league_avg_salary'):
            salary_ratio = league_comp['my_total_salary'] / league_comp['league_avg_salary']
            salary_score = min(100, salary_ratio * 100)
            scores.append(salary_score)

        # Comparison to top teams
        if top_comp:
            gaps = [v.get('gap_pct', 0) for v in top_comp.values() if isinstance(v, dict)]
            avg_gap = np.mean(gaps) if gaps else 0
            top_score = max(0, min(100, 50 + avg_gap))
            scores.append(top_score)

        overall = np.mean(scores) if scores else 50

        return {
            'overall': round(overall, 0),
            'coverage': round(coverage_score, 0),
            'salary_deployment': round(scores[1] if len(scores) > 1 else 50, 0),
            'vs_top_teams': round(scores[2] if len(scores) > 2 else 50, 0),
            'grade': self._score_to_grade(overall),
        }

    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

    def _generate_recommendations(
        self,
        weaknesses: List[Dict],
        value_analysis: Dict,
        positional: Dict
    ) -> List[Dict]:
        """Generate actionable recommendations."""
        recommendations = []

        # Address critical weaknesses first
        for weakness in weaknesses[:3]:
            if weakness['severity'] == 'critical':
                recommendations.append({
                    'priority': 'high',
                    'action': 'fill_position',
                    'position': weakness['position'],
                    'message': f"Priority: Address {weakness['position']} - {weakness['message']}",
                })
            elif weakness['severity'] == 'moderate':
                recommendations.append({
                    'priority': 'medium',
                    'action': 'improve_position',
                    'position': weakness['position'],
                    'message': f"Consider improving {weakness['position']}: {weakness['message']}",
                })

        # Sell high recommendations
        for player in value_analysis.get('sell_high', [])[:2]:
            recommendations.append({
                'priority': 'medium',
                'action': 'sell_high',
                'player': player.get('name'),
                'message': f"Sell high on {player.get('name')} - valued at ${player.get('predicted_value')}, "
                          f"salary ${player.get('current_salary')}",
            })

        # Buy low recommendations (for FA)
        if value_analysis.get('buy_low'):
            recommendations.append({
                'priority': 'low',
                'action': 'target_fa',
                'message': "Check free agent market for undervalued players",
            })

        return recommendations[:5]

    def get_positional_rankings(self, position: str) -> pd.DataFrame:
        """
        Get league-wide rankings for a specific position.

        Returns DataFrame with all players at position ranked by value.
        """
        all_rosters = self.ottoneu_client.get_league_rosters()

        if all_rosters.empty:
            return pd.DataFrame()

        eligible = self.POSITION_GROUPS.get(position, [position])

        position_players = all_rosters[
            all_rosters['position'].str.contains('|'.join(eligible), case=False, na=False)
        ].copy()

        if position_players.empty:
            return pd.DataFrame()

        # Add surplus value if we have avg values
        avg_values = self.ottoneu_client.get_average_values()
        if not avg_values.empty and 'ottoneu_id' in position_players.columns:
            position_players = position_players.merge(
                avg_values[['ottoneu_id', 'avg_salary']],
                on='ottoneu_id',
                how='left'
            )
            position_players['surplus'] = position_players['avg_salary'] - position_players['salary']

        # Sort by salary or surplus
        sort_col = 'surplus' if 'surplus' in position_players.columns else 'salary'
        position_players = position_players.sort_values(sort_col, ascending=False)

        return position_players
