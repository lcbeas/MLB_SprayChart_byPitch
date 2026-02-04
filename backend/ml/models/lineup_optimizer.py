"""
Daily Lineup Optimizer

Optimizes starting lineups for Ottoneu fantasy baseball using:
- Matchup analysis (batter vs pitcher)
- Park factors
- Recent performance trends
- Ottoneu scoring rules and inning limits
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from itertools import combinations

from backend.ml.features.gameday_features import GamedayFeatureGenerator
from backend.ml.models.player_value import PlayerValueModel


class LineupOptimizer:
    """
    Optimizes daily lineups for Ottoneu leagues.

    Considers:
    - Position eligibility
    - Ottoneu scoring format
    - Inning limits (for pitchers)
    - Matchup advantages
    - Recent performance
    """

    # Ottoneu lineup positions
    LINEUP_POSITIONS = {
        'batting': ['C', '1B', '2B', 'SS', '3B', 'OF', 'OF', 'OF', 'UTIL', 'UTIL'],
        'pitching': ['SP', 'SP', 'RP', 'RP', 'P', 'P'],
    }

    # Position eligibility mapping
    POSITION_ELIGIBLE = {
        'C': ['C'],
        '1B': ['1B'],
        '2B': ['2B'],
        'SS': ['SS'],
        '3B': ['3B'],
        'OF': ['LF', 'CF', 'RF', 'OF'],
        'UTIL': ['C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'OF', 'DH'],
        'SP': ['SP'],
        'RP': ['RP'],
        'P': ['SP', 'RP'],
    }

    # Ottoneu FanGraphs Points scoring (per stat)
    FANGRAPHS_POINTS = {
        # Batting
        'AB': -1.0,
        'H': 5.6,
        '2B': 2.9,
        '3B': 5.7,
        'HR': 9.4,
        'BB': 3.0,
        'HBP': 3.0,
        'SB': 1.9,
        'CS': -2.8,
        # Pitching
        'IP': 7.4,
        'K': 2.0,
        'HA': -2.6,  # Hits allowed
        'BBA': -3.0,  # BB allowed
        'HRA': -12.3,  # HR allowed
        'SV': 5.0,
        'HLD': 4.0,
    }

    def __init__(self, scoring_format: str = 'fangraphs_points'):
        self.scoring_format = scoring_format
        self.gameday_features = GamedayFeatureGenerator()
        self.value_model = PlayerValueModel()

        # Try to load trained value model
        self.value_model.load_models()

    def optimize_lineup(
        self,
        roster: List[Dict],
        matchups: Dict[str, Dict],
        inning_limits: Optional[Dict[str, float]] = None,
        date: Optional[str] = None
    ) -> Dict:
        """
        Optimize the starting lineup for a given day.

        Args:
            roster: List of player dicts with keys:
                - player_id, mlbam_id, name, positions, salary
                - For pitchers: projected_ip, current_ip
            matchups: Dict mapping player_id to matchup info:
                - opponent_pitcher_id (for batters)
                - opponent_team (for pitchers)
                - park
            inning_limits: Dict of player_id -> remaining innings allowed
            date: Date string (YYYY-MM-DD)

        Returns:
            Dict with optimized batting and pitching lineups
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # Separate batters and pitchers
        batters = [p for p in roster if not self._is_pitcher(p)]
        pitchers = [p for p in roster if self._is_pitcher(p)]

        # Score each player for today
        batter_scores = self._score_batters(batters, matchups)
        pitcher_scores = self._score_pitchers(pitchers, matchups, inning_limits)

        # Optimize batting lineup
        batting_lineup = self._optimize_batting_lineup(batter_scores)

        # Optimize pitching lineup
        pitching_lineup = self._optimize_pitching_lineup(pitcher_scores, inning_limits)

        # Calculate expected points
        expected_batting = sum(p['expected_points'] for p in batting_lineup.values())
        expected_pitching = sum(p['expected_points'] for p in pitching_lineup.values())

        return {
            'date': date,
            'batting_lineup': batting_lineup,
            'pitching_lineup': pitching_lineup,
            'bench': self._get_bench(roster, batting_lineup, pitching_lineup),
            'expected_batting_points': round(expected_batting, 1),
            'expected_pitching_points': round(expected_pitching, 1),
            'expected_total_points': round(expected_batting + expected_pitching, 1),
            'warnings': self._generate_warnings(batting_lineup, pitching_lineup, inning_limits),
        }

    def _is_pitcher(self, player: Dict) -> bool:
        """Check if player is a pitcher."""
        positions = player.get('positions', player.get('position', ''))
        if isinstance(positions, str):
            positions = [positions]
        return any(p in ['SP', 'RP', 'P'] for p in positions)

    def _score_batters(
        self,
        batters: List[Dict],
        matchups: Dict
    ) -> List[Dict]:
        """Score each batter for today's matchup."""
        scored = []

        for batter in batters:
            player_id = batter.get('player_id') or batter.get('mlbam_id')
            matchup = matchups.get(str(player_id), {})

            # Base score from projected value
            base_score = batter.get('projected_points', 5.0)

            # Get matchup features if available
            matchup_multiplier = 1.0
            if matchup.get('opponent_pitcher_id') and batter.get('mlbam_id'):
                try:
                    features = self.gameday_features.get_batter_gameday_features(
                        batter['mlbam_id'],
                        matchup['opponent_pitcher_id'],
                        matchup.get('park', 'NYY'),
                        batter.get('hand', 'R'),
                        matchup.get('pitcher_hand', 'R')
                    )
                    # Use matchup score to adjust
                    matchup_score = features.get('matchup_score', 50)
                    matchup_multiplier = 0.8 + (matchup_score / 250)  # 0.8 to 1.2
                except Exception:
                    pass

            # Apply park factor
            park = matchup.get('park', 'NYY')
            park_factor = self.gameday_features.PARK_FACTORS.get(park, 1.0)

            # Calculate expected points
            expected_points = base_score * matchup_multiplier * park_factor

            scored.append({
                **batter,
                'matchup_multiplier': round(matchup_multiplier, 2),
                'park_factor': park_factor,
                'expected_points': round(expected_points, 1),
                'score': expected_points,  # For sorting
            })

        return sorted(scored, key=lambda x: x['score'], reverse=True)

    def _score_pitchers(
        self,
        pitchers: List[Dict],
        matchups: Dict,
        inning_limits: Optional[Dict[str, float]] = None
    ) -> List[Dict]:
        """Score each pitcher for today."""
        scored = []

        for pitcher in pitchers:
            player_id = str(pitcher.get('player_id') or pitcher.get('mlbam_id'))
            matchup = matchups.get(player_id, {})

            # Check inning limit
            remaining_ip = None
            if inning_limits and player_id in inning_limits:
                remaining_ip = inning_limits[player_id]
                if remaining_ip <= 0:
                    continue  # Skip if out of innings

            # Base score
            is_starter = 'SP' in pitcher.get('positions', [])
            base_score = pitcher.get('projected_points', 15.0 if is_starter else 5.0)

            # Projected innings
            proj_ip = pitcher.get('projected_ip', 6.0 if is_starter else 1.0)

            # Adjust for remaining innings
            if remaining_ip is not None and proj_ip > remaining_ip:
                ip_ratio = remaining_ip / proj_ip
                base_score *= ip_ratio
                proj_ip = remaining_ip

            # Park factor (inverted for pitchers)
            park = matchup.get('park', 'NYY')
            park_factor = 2.0 - self.gameday_features.PARK_FACTORS.get(park, 1.0)

            expected_points = base_score * park_factor

            scored.append({
                **pitcher,
                'projected_ip': proj_ip,
                'remaining_ip': remaining_ip,
                'park_factor': round(park_factor, 2),
                'expected_points': round(expected_points, 1),
                'score': expected_points,
            })

        return sorted(scored, key=lambda x: x['score'], reverse=True)

    def _optimize_batting_lineup(self, scored_batters: List[Dict]) -> Dict[str, Dict]:
        """
        Optimize batting lineup positions using greedy assignment.
        """
        lineup = {}
        used_players = set()

        # Position slots to fill
        slots = ['C', '1B', '2B', 'SS', '3B', 'OF', 'OF', 'OF', 'UTIL', 'UTIL']

        for slot in slots:
            eligible_positions = self.POSITION_ELIGIBLE.get(slot, [slot])

            # Find best available player for this slot
            best_player = None
            for player in scored_batters:
                player_id = player.get('player_id') or player.get('mlbam_id')
                if player_id in used_players:
                    continue

                # Check position eligibility
                player_positions = player.get('positions', player.get('position', ''))
                if isinstance(player_positions, str):
                    player_positions = [player_positions]

                if any(pos in eligible_positions for pos in player_positions):
                    best_player = player
                    break

            if best_player:
                player_id = best_player.get('player_id') or best_player.get('mlbam_id')
                used_players.add(player_id)

                # Handle duplicate slot names (OF, UTIL)
                slot_key = slot
                counter = 1
                while slot_key in lineup:
                    counter += 1
                    slot_key = f"{slot}{counter}"

                lineup[slot_key] = best_player

        return lineup

    def _optimize_pitching_lineup(
        self,
        scored_pitchers: List[Dict],
        inning_limits: Optional[Dict[str, float]] = None
    ) -> Dict[str, Dict]:
        """
        Optimize pitching lineup.
        """
        lineup = {}
        used_players = set()

        # Separate starters and relievers
        starters = [p for p in scored_pitchers if 'SP' in p.get('positions', [])]
        relievers = [p for p in scored_pitchers if 'RP' in p.get('positions', []) and 'SP' not in p.get('positions', [])]

        # Fill SP slots
        for i, slot in enumerate(['SP', 'SP2']):
            if i < len(starters):
                player = starters[i]
                player_id = player.get('player_id') or player.get('mlbam_id')
                if player_id not in used_players:
                    lineup[slot] = player
                    used_players.add(player_id)

        # Fill RP slots
        for i, slot in enumerate(['RP', 'RP2']):
            if i < len(relievers):
                player = relievers[i]
                player_id = player.get('player_id') or player.get('mlbam_id')
                if player_id not in used_players:
                    lineup[slot] = player
                    used_players.add(player_id)

        # Fill P slots (any pitcher)
        remaining = [p for p in scored_pitchers
                     if (p.get('player_id') or p.get('mlbam_id')) not in used_players]

        for i, slot in enumerate(['P', 'P2']):
            if i < len(remaining):
                player = remaining[i]
                player_id = player.get('player_id') or player.get('mlbam_id')
                lineup[slot] = player
                used_players.add(player_id)

        return lineup

    def _get_bench(
        self,
        roster: List[Dict],
        batting_lineup: Dict,
        pitching_lineup: Dict
    ) -> List[Dict]:
        """Get bench players not in lineup."""
        lineup_ids = set()

        for player in batting_lineup.values():
            lineup_ids.add(player.get('player_id') or player.get('mlbam_id'))

        for player in pitching_lineup.values():
            lineup_ids.add(player.get('player_id') or player.get('mlbam_id'))

        return [p for p in roster
                if (p.get('player_id') or p.get('mlbam_id')) not in lineup_ids]

    def _generate_warnings(
        self,
        batting_lineup: Dict,
        pitching_lineup: Dict,
        inning_limits: Optional[Dict[str, float]] = None
    ) -> List[str]:
        """Generate warnings about the lineup."""
        warnings = []

        # Check for empty slots
        if len(batting_lineup) < 10:
            warnings.append(f"Only {len(batting_lineup)} batting slots filled")
        if len(pitching_lineup) < 6:
            warnings.append(f"Only {len(pitching_lineup)} pitching slots filled")

        # Check inning limits
        if inning_limits:
            for slot, player in pitching_lineup.items():
                player_id = str(player.get('player_id') or player.get('mlbam_id'))
                if player_id in inning_limits:
                    remaining = inning_limits[player_id]
                    if remaining < 10:
                        warnings.append(f"{player.get('name', player_id)} has only {remaining:.1f} IP remaining")

        # Check for low-scoring matchups
        low_scorers = [p for p in batting_lineup.values() if p.get('expected_points', 0) < 3]
        if len(low_scorers) > 3:
            warnings.append(f"{len(low_scorers)} batters with poor matchups today")

        return warnings

    def suggest_lineup_changes(
        self,
        current_lineup: Dict,
        roster: List[Dict],
        matchups: Dict
    ) -> List[Dict]:
        """
        Suggest changes to improve the current lineup.

        Returns list of suggested swaps with expected point gain.
        """
        suggestions = []

        # Score all players
        batters = [p for p in roster if not self._is_pitcher(p)]
        scored = self._score_batters(batters, matchups)

        # Find bench players with higher scores than starters
        lineup_ids = {p.get('player_id') or p.get('mlbam_id')
                      for p in current_lineup.get('batting_lineup', {}).values()}

        bench_players = [p for p in scored
                        if (p.get('player_id') or p.get('mlbam_id')) not in lineup_ids]

        for bench_player in bench_players:
            bench_score = bench_player.get('expected_points', 0)

            # Find starters this bench player could replace
            for slot, starter in current_lineup.get('batting_lineup', {}).items():
                starter_score = starter.get('expected_points', 0)

                # Check position eligibility
                bench_positions = bench_player.get('positions', [])
                if isinstance(bench_positions, str):
                    bench_positions = [bench_positions]

                slot_base = slot.rstrip('0123456789')
                eligible = self.POSITION_ELIGIBLE.get(slot_base, [slot_base])

                if any(pos in eligible for pos in bench_positions):
                    if bench_score > starter_score + 1:  # Require meaningful improvement
                        suggestions.append({
                            'type': 'swap',
                            'slot': slot,
                            'bench_out': starter.get('name', str(starter.get('player_id'))),
                            'bench_in': bench_player.get('name', str(bench_player.get('player_id'))),
                            'current_points': starter_score,
                            'new_points': bench_score,
                            'gain': round(bench_score - starter_score, 1),
                        })

        # Sort by gain
        suggestions.sort(key=lambda x: x['gain'], reverse=True)

        return suggestions[:5]  # Top 5 suggestions

    def calculate_inning_limits(
        self,
        roster: List[Dict],
        league_limit: float = 1500,
        games_remaining: int = 162,
        current_ip: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Calculate remaining innings for each pitcher based on pace.

        Args:
            roster: List of pitcher dicts
            league_limit: Season inning limit (Ottoneu default: 1500)
            games_remaining: Games left in season
            current_ip: Dict of player_id -> IP used so far

        Returns:
            Dict of player_id -> remaining IP allowed
        """
        if current_ip is None:
            current_ip = {}

        total_ip_used = sum(current_ip.values())
        ip_remaining = league_limit - total_ip_used
        games_per_week = 7
        weeks_remaining = games_remaining / games_per_week

        # Calculate pace needed
        ip_per_week = ip_remaining / max(weeks_remaining, 1)

        limits = {}
        pitchers = [p for p in roster if self._is_pitcher(p)]

        for pitcher in pitchers:
            player_id = str(pitcher.get('player_id') or pitcher.get('mlbam_id'))

            # Individual pace based on their projected workload
            proj_ip = pitcher.get('projected_ip_ros', pitcher.get('projected_ip', 100))

            # Their share of remaining innings
            total_proj = sum(p.get('projected_ip_ros', p.get('projected_ip', 100))
                           for p in pitchers)

            if total_proj > 0:
                share = proj_ip / total_proj
                limits[player_id] = ip_remaining * share
            else:
                limits[player_id] = ip_remaining / len(pitchers)

        return limits
