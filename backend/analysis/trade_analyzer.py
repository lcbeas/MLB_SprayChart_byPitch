"""
Trade Analyzer

Evaluates trades and finds optimal trade opportunities in Ottoneu leagues.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from itertools import combinations, product

from backend.data_sources.ottoneu import OttoneuClient
from backend.ml.models.player_value import PlayerValueModel
from backend.analysis.roster_analyzer import RosterAnalyzer


class TradeAnalyzer:
    """
    Analyzes trades and finds trade opportunities.

    Features:
    - Evaluate proposed trades for fairness
    - Find optimal trades to improve roster
    - Identify teams that might accept specific trades
    """

    def __init__(self, league_id: Optional[str] = None):
        self.ottoneu_client = OttoneuClient(league_id=league_id)
        self.value_model = PlayerValueModel()
        self.value_model.load_models()
        self.roster_analyzer = RosterAnalyzer(league_id=league_id)

    def evaluate_trade(
        self,
        my_team_id: int,
        my_players: List[Dict],
        their_team_id: int,
        their_players: List[Dict]
    ) -> Dict:
        """
        Evaluate a proposed trade.

        Args:
            my_team_id: Your team ID
            my_players: List of your players being traded (with player_id, name, salary)
            their_team_id: Other team's ID
            their_players: List of their players being traded

        Returns:
            Dict with trade evaluation
        """
        # Calculate values for players being traded
        my_value = self._calculate_package_value(my_players)
        their_value = self._calculate_package_value(their_players)

        # Calculate salary implications
        my_salary_out = sum(p.get('salary', 0) for p in my_players)
        their_salary_out = sum(p.get('salary', 0) for p in their_players)
        salary_change = their_salary_out - my_salary_out

        # Fairness analysis
        value_diff = their_value['total_value'] - my_value['total_value']
        value_diff_pct = (value_diff / max(my_value['total_value'], 1)) * 100

        # Determine fairness
        if abs(value_diff_pct) < 10:
            fairness = 'fair'
            fairness_description = 'Trade is roughly fair'
        elif value_diff_pct > 10:
            fairness = 'favorable'
            fairness_description = f'You gain ~${abs(value_diff):.0f} in value'
        else:
            fairness = 'unfavorable'
            fairness_description = f'You lose ~${abs(value_diff):.0f} in value'

        # Positional impact
        positional_impact = self._analyze_positional_impact(
            my_team_id, my_players, their_players
        )

        return {
            'timestamp': datetime.now().isoformat(),
            'my_team_id': my_team_id,
            'their_team_id': their_team_id,
            'my_package': {
                'players': my_players,
                **my_value,
            },
            'their_package': {
                'players': their_players,
                **their_value,
            },
            'value_difference': round(value_diff, 1),
            'value_difference_pct': round(value_diff_pct, 1),
            'salary_change': round(salary_change, 1),
            'fairness': fairness,
            'fairness_description': fairness_description,
            'positional_impact': positional_impact,
            'recommendation': self._generate_trade_recommendation(
                value_diff_pct, positional_impact, salary_change
            ),
        }

    def _calculate_package_value(self, players: List[Dict]) -> Dict:
        """Calculate total value for a package of players."""
        total_value = 0
        total_salary = 0
        player_values = []

        for player in players:
            player_id = player.get('player_id') or player.get('fg_id')
            player_type = player.get('player_type', 'batter')
            mlbam_id = player.get('mlbam_id')

            try:
                if self.value_model.is_trained(player_type):
                    pred = self.value_model.predict_value(player_id, player_type, mlbam_id)
                    value = pred['predicted_value']
                else:
                    # Fallback to salary as proxy
                    value = player.get('salary', 5) * 1.2
            except Exception:
                value = player.get('salary', 5) * 1.2

            salary = player.get('salary', 0)
            surplus = value - salary

            player_values.append({
                'name': player.get('name', str(player_id)),
                'predicted_value': round(value, 1),
                'salary': salary,
                'surplus': round(surplus, 1),
            })

            total_value += value
            total_salary += salary

        return {
            'player_values': player_values,
            'total_value': round(total_value, 1),
            'total_salary': round(total_salary, 1),
            'total_surplus': round(total_value - total_salary, 1),
        }

    def _analyze_positional_impact(
        self,
        my_team_id: int,
        my_players: List[Dict],
        their_players: List[Dict]
    ) -> Dict:
        """Analyze how trade affects positional depth."""
        impact = {}

        # Group outgoing players by position
        out_positions = {}
        for p in my_players:
            pos = p.get('position', 'UTIL').split('/')[0]
            out_positions[pos] = out_positions.get(pos, 0) + 1

        # Group incoming players by position
        in_positions = {}
        for p in their_players:
            pos = p.get('position', 'UTIL').split('/')[0]
            in_positions[pos] = in_positions.get(pos, 0) + 1

        # All affected positions
        all_positions = set(out_positions.keys()) | set(in_positions.keys())

        for pos in all_positions:
            out_count = out_positions.get(pos, 0)
            in_count = in_positions.get(pos, 0)
            net_change = in_count - out_count

            impact[pos] = {
                'outgoing': out_count,
                'incoming': in_count,
                'net_change': net_change,
                'assessment': 'neutral' if net_change == 0 else (
                    'gain' if net_change > 0 else 'loss'
                ),
            }

        return impact

    def _generate_trade_recommendation(
        self,
        value_diff_pct: float,
        positional_impact: Dict,
        salary_change: float
    ) -> Dict:
        """Generate trade recommendation."""
        # Count positional gains/losses
        gains = sum(1 for p in positional_impact.values() if p['assessment'] == 'gain')
        losses = sum(1 for p in positional_impact.values() if p['assessment'] == 'loss')

        # Score the trade
        score = 50 + value_diff_pct * 2  # Value impact

        # Positional impact
        if gains > losses:
            score += 10
            positional_note = "Improves positional depth"
        elif losses > gains:
            score -= 10
            positional_note = "Reduces positional depth"
        else:
            positional_note = "Neutral positional impact"

        # Salary impact (cap flexibility)
        if salary_change < -10:
            score += 5
            salary_note = "Frees up cap space"
        elif salary_change > 20:
            score -= 5
            salary_note = "Increases salary commitment"
        else:
            salary_note = "Minimal salary impact"

        # Clamp score
        score = max(0, min(100, score))

        # Generate recommendation
        if score >= 70:
            action = 'accept'
            reasoning = 'Trade is favorable - accept'
        elif score >= 50:
            action = 'consider'
            reasoning = 'Trade is fair - consider based on roster needs'
        else:
            action = 'decline'
            reasoning = 'Trade is unfavorable - decline or counter'

        return {
            'action': action,
            'score': round(score, 0),
            'reasoning': reasoning,
            'notes': [positional_note, salary_note],
        }

    def find_trade_targets(
        self,
        my_team_id: int,
        target_position: Optional[str] = None,
        max_salary: Optional[float] = None
    ) -> List[Dict]:
        """
        Find players on other teams that would be good trade targets.

        Args:
            my_team_id: Your team ID
            target_position: Specific position to target (optional)
            max_salary: Maximum salary to consider

        Returns:
            List of potential trade targets with value analysis
        """
        all_rosters = self.ottoneu_client.get_league_rosters()

        if all_rosters.empty:
            return []

        # Filter to other teams
        other_teams = all_rosters[all_rosters['owner_id'] != my_team_id]

        if target_position:
            position_pattern = target_position
            other_teams = other_teams[
                other_teams['position'].str.contains(position_pattern, case=False, na=False)
            ]

        if max_salary:
            other_teams = other_teams[other_teams['salary'] <= max_salary]

        # Calculate surplus value for each player
        targets = []
        avg_values = self.ottoneu_client.get_average_values()

        for _, player in other_teams.iterrows():
            player_data = {
                'player_id': player.get('fg_id', player.get('ottoneu_id')),
                'name': player.get('name', ''),
                'position': player.get('position', ''),
                'team': player.get('mlb_team', ''),
                'salary': player.get('salary', 0),
                'owner_id': player.get('owner_id'),
                'owner_name': player.get('owner_name', ''),
            }

            # Get average value if available
            if not avg_values.empty and 'ottoneu_id' in player:
                avg_row = avg_values[avg_values['ottoneu_id'] == player['ottoneu_id']]
                if not avg_row.empty:
                    player_data['avg_value'] = avg_row.iloc[0].get('avg_salary', 0)
                    player_data['surplus'] = player_data['avg_value'] - player_data['salary']

            targets.append(player_data)

        # Sort by surplus value
        targets = sorted(targets, key=lambda x: x.get('surplus', 0), reverse=True)

        return targets[:50]  # Top 50 targets

    def find_fair_trades(
        self,
        my_team_id: int,
        target_player_id: int,
        max_players_to_give: int = 2
    ) -> List[Dict]:
        """
        Find fair trade packages to acquire a specific player.

        Args:
            my_team_id: Your team ID
            target_player_id: Player you want to acquire
            max_players_to_give: Max players you're willing to trade

        Returns:
            List of fair trade proposals
        """
        # Get rosters
        my_roster = self.ottoneu_client.get_my_roster(team_id=my_team_id)
        all_rosters = self.ottoneu_client.get_league_rosters()

        if my_roster.empty or all_rosters.empty:
            return []

        # Find target player
        target_player = all_rosters[
            (all_rosters.get('fg_id', all_rosters.get('ottoneu_id')) == target_player_id) |
            (all_rosters.get('ottoneu_id') == target_player_id)
        ]

        if target_player.empty:
            return []

        target = target_player.iloc[0]
        target_value = self._estimate_player_value(target)
        target_owner = target.get('owner_id')

        # Find combinations of my players that match value
        fair_trades = []

        for n in range(1, max_players_to_give + 1):
            for players in combinations(my_roster.iterrows(), n):
                package = [row for _, row in players]
                package_value = sum(self._estimate_player_value(p) for p in package)
                package_salary = sum(p.get('salary', 0) for p in package)

                # Check if roughly fair (within 15%)
                value_ratio = package_value / max(target_value, 1)

                if 0.85 <= value_ratio <= 1.15:
                    fair_trades.append({
                        'my_players': [
                            {
                                'name': p.get('name'),
                                'position': p.get('position'),
                                'salary': p.get('salary'),
                                'value': round(self._estimate_player_value(p), 1),
                            }
                            for p in package
                        ],
                        'target_player': {
                            'name': target.get('name'),
                            'position': target.get('position'),
                            'salary': target.get('salary'),
                            'value': round(target_value, 1),
                            'owner_id': target_owner,
                        },
                        'my_total_value': round(package_value, 1),
                        'target_value': round(target_value, 1),
                        'value_ratio': round(value_ratio, 2),
                        'salary_change': round(target.get('salary', 0) - package_salary, 1),
                    })

        # Sort by closeness to 1:1 value
        fair_trades.sort(key=lambda x: abs(x['value_ratio'] - 1))

        return fair_trades[:10]  # Top 10 proposals

    def suggest_trades(
        self,
        my_team_id: int,
        improve_position: Optional[str] = None
    ) -> List[Dict]:
        """
        Suggest trades to improve roster.

        Args:
            my_team_id: Your team ID
            improve_position: Specific position to improve (optional)

        Returns:
            List of suggested trades with reasoning
        """
        # Get roster analysis
        analysis = self.roster_analyzer.analyze_roster(my_team_id)

        # Identify positions to improve
        positions_to_improve = []

        if improve_position:
            positions_to_improve = [improve_position]
        else:
            for weakness in analysis.get('weaknesses', [])[:3]:
                if weakness.get('position'):
                    positions_to_improve.append(weakness['position'])

        # Identify players to trade away (sell high candidates)
        sell_high = analysis.get('value_opportunities', {}).get('sell_high', [])

        suggestions = []

        for position in positions_to_improve:
            # Find targets at this position
            targets = self.find_trade_targets(my_team_id, target_position=position)[:5]

            for target in targets:
                if not sell_high:
                    continue

                # Try to find a fair trade
                trades = self.find_fair_trades(
                    my_team_id,
                    target.get('player_id'),
                    max_players_to_give=2
                )

                if trades:
                    best_trade = trades[0]
                    suggestions.append({
                        'type': 'upgrade',
                        'position': position,
                        'acquire': target.get('name'),
                        'from_team': target.get('owner_name'),
                        'give_up': [p['name'] for p in best_trade['my_players']],
                        'value_assessment': 'fair' if 0.9 <= best_trade['value_ratio'] <= 1.1 else 'slight overpay',
                        'reasoning': f"Upgrade {position} by acquiring {target.get('name')}",
                    })

        return suggestions[:5]

    def _estimate_player_value(self, player: pd.Series) -> float:
        """Estimate player value using model or fallback."""
        player_id = player.get('fg_id', player.get('ottoneu_id'))
        player_type = 'pitcher' if any(p in str(player.get('position', ''))
                                       for p in ['SP', 'RP']) else 'batter'

        try:
            if self.value_model.is_trained(player_type) and player_id:
                pred = self.value_model.predict_value(int(player_id), player_type)
                return pred['predicted_value']
        except Exception:
            pass

        # Fallback to salary * 1.2 as rough estimate
        return player.get('salary', 5) * 1.2

    def analyze_league_trade_market(self, my_team_id: int) -> Dict:
        """
        Analyze the overall trade market in the league.

        Returns insights about which teams might be buyers/sellers
        and general trade opportunities.
        """
        all_rosters = self.ottoneu_client.get_league_rosters()
        standings = self.ottoneu_client.get_league_standings()

        if all_rosters.empty:
            return {}

        # Analyze each team
        teams = all_rosters['owner_id'].unique()
        team_analysis = []

        for team in teams:
            if team == my_team_id:
                continue

            team_roster = all_rosters[all_rosters['owner_id'] == team]
            team_data = {
                'team_id': team,
                'team_name': team_roster.iloc[0].get('owner_name', f'Team {team}') if not team_roster.empty else f'Team {team}',
                'total_salary': team_roster['salary'].sum() if 'salary' in team_roster.columns else 0,
                'player_count': len(team_roster),
                'cap_space': 400 - (team_roster['salary'].sum() if 'salary' in team_roster.columns else 0),
            }

            # Determine if buyer or seller
            if team_data['cap_space'] > 50:
                team_data['market_position'] = 'buyer'
                team_data['trade_interest'] = 'Looking to acquire talent'
            elif team_data['cap_space'] < 10:
                team_data['market_position'] = 'seller'
                team_data['trade_interest'] = 'May need to shed salary'
            else:
                team_data['market_position'] = 'neutral'
                team_data['trade_interest'] = 'Open to fair trades'

            team_analysis.append(team_data)

        # Find best trade partners
        buyers = [t for t in team_analysis if t['market_position'] == 'buyer']
        sellers = [t for t in team_analysis if t['market_position'] == 'seller']

        return {
            'team_analysis': sorted(team_analysis, key=lambda x: x['cap_space'], reverse=True),
            'potential_buyers': buyers[:5],
            'potential_sellers': sellers[:5],
            'summary': {
                'total_teams': len(teams) - 1,
                'buyers': len(buyers),
                'sellers': len(sellers),
                'neutral': len(team_analysis) - len(buyers) - len(sellers),
            },
        }
