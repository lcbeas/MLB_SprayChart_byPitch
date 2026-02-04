"""
Gameday Feature Generator

Generates features for daily lineup optimization including:
- Matchup data (batter vs pitcher)
- Park factors
- Weather (if available)
- Recent performance trends
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from backend.data_sources.fangraphs import FangraphsClient
from backend.data_sources.savant import SavantClient


class GamedayFeatureGenerator:
    """
    Generates features for daily lineup optimization.
    """

    # Park factors (simplified - would ideally fetch dynamically)
    PARK_FACTORS = {
        'COL': 1.35,  # Coors Field - extreme hitter friendly
        'CIN': 1.10,  # Great American Ball Park
        'TEX': 1.08,  # Globe Life Field
        'BOS': 1.07,  # Fenway Park
        'MIL': 1.05,  # American Family Field
        'PHI': 1.04,  # Citizens Bank Park
        'TOR': 1.03,  # Rogers Centre
        'CHC': 1.02,  # Wrigley Field
        'NYY': 1.01,  # Yankee Stadium
        'BAL': 1.01,  # Camden Yards
        'ATL': 1.00,  # Truist Park
        'CLE': 1.00,  # Progressive Field
        'MIN': 1.00,  # Target Field
        'ARI': 0.99,  # Chase Field
        'DET': 0.99,  # Comerica Park
        'HOU': 0.98,  # Minute Maid Park
        'LAA': 0.98,  # Angel Stadium
        'WSH': 0.98,  # Nationals Park
        'CHW': 0.97,  # Guaranteed Rate Field
        'KC': 0.97,   # Kauffman Stadium
        'STL': 0.97,  # Busch Stadium
        'SD': 0.96,   # Petco Park
        'TB': 0.96,   # Tropicana Field
        'LAD': 0.95,  # Dodger Stadium
        'NYM': 0.95,  # Citi Field
        'PIT': 0.94,  # PNC Park
        'SF': 0.93,   # Oracle Park
        'SEA': 0.92,  # T-Mobile Park
        'OAK': 0.91,  # Oakland Coliseum
        'MIA': 0.90,  # LoanDepot Park
    }

    def __init__(self):
        self.fg_client = FangraphsClient()
        self.savant_client = SavantClient()

    def get_batter_gameday_features(
        self,
        batter_mlbam_id: int,
        pitcher_mlbam_id: int,
        park: str,
        batter_hand: str = 'R',
        pitcher_hand: str = 'R'
    ) -> Dict:
        """
        Generate gameday features for a batter.

        Args:
            batter_mlbam_id: Batter's MLBAM ID
            pitcher_mlbam_id: Opposing pitcher's MLBAM ID
            park: Team abbreviation for park
            batter_hand: 'L' or 'R'
            pitcher_hand: 'L' or 'R'

        Returns:
            Dict with gameday features
        """
        features = {
            'batter_id': batter_mlbam_id,
            'pitcher_id': pitcher_mlbam_id,
            'park': park,
        }

        # Park factor
        features['park_factor'] = self.PARK_FACTORS.get(park.upper(), 1.0)

        # Platoon advantage
        features['platoon_advantage'] = 1 if batter_hand != pitcher_hand else 0

        # Recent batter performance (last 14 days)
        recent_features = self._get_recent_performance(batter_mlbam_id, days=14)
        features.update({f'batter_{k}': v for k, v in recent_features.items()})

        # Pitcher features
        pitcher_features = self._get_pitcher_vulnerability(pitcher_mlbam_id)
        features.update({f'pitcher_{k}': v for k, v in pitcher_features.items()})

        # Calculate matchup score
        features['matchup_score'] = self._calculate_matchup_score(features)

        return features

    def _get_recent_performance(self, mlbam_id: int, days: int = 14) -> Dict:
        """Get recent performance metrics."""
        features = {}

        try:
            current_season = datetime.now().year
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Get recent Statcast data
            df = self.savant_client.get_batter_statcast(mlbam_id, start_date, end_date)

            if df.empty:
                return features

            # Batted ball events
            batted = df[df['type'] == 'X']

            if not batted.empty:
                # Recent exit velocity
                if 'launch_speed' in batted.columns:
                    features['recent_avg_ev'] = batted['launch_speed'].mean()
                    features['recent_hard_hit_pct'] = len(batted[batted['launch_speed'] >= 95]) / len(batted) * 100

                # Recent xwOBA
                if 'estimated_woba_using_speedangle' in batted.columns:
                    features['recent_xwoba'] = batted['estimated_woba_using_speedangle'].mean()

                # Recent barrel rate
                if 'barrel' in batted.columns:
                    features['recent_barrel_pct'] = batted['barrel'].sum() / len(batted) * 100

            # Games played in window
            if 'game_date' in df.columns:
                features['recent_games'] = df['game_date'].nunique()

        except Exception as e:
            print(f"Error getting recent performance: {e}")

        return features

    def _get_pitcher_vulnerability(self, mlbam_id: int) -> Dict:
        """Get pitcher vulnerability metrics."""
        features = {}

        try:
            current_season = datetime.now().year
            expected = self.savant_client.get_pitcher_expected_stats(mlbam_id, current_season)

            if expected:
                features['xwoba_against'] = expected.get('xwOBA_against')
                features['hard_hit_against'] = expected.get('hard_hit_rate_against')
                features['barrel_against'] = expected.get('barrel_rate_against')

            # Get pitch arsenal for vulnerability analysis
            arsenal = self.savant_client.get_pitch_arsenal(mlbam_id, current_season)
            if not arsenal.empty and 'whiff_rate' in arsenal.columns:
                features['avg_whiff_rate'] = arsenal['whiff_rate'].mean()
                features['min_whiff_rate'] = arsenal['whiff_rate'].min()  # Weakest pitch

        except Exception as e:
            print(f"Error getting pitcher vulnerability: {e}")

        return features

    def _calculate_matchup_score(self, features: Dict) -> float:
        """
        Calculate overall matchup score (0-100).
        Higher = better for batter.
        """
        score = 50.0  # Base score

        # Park factor adjustment (-10 to +10)
        park_factor = features.get('park_factor', 1.0)
        score += (park_factor - 1.0) * 30

        # Platoon advantage (+5)
        if features.get('platoon_advantage'):
            score += 5

        # Recent performance adjustment
        recent_xwoba = features.get('batter_recent_xwoba')
        if recent_xwoba:
            score += (recent_xwoba - 0.320) * 50  # .320 is league average

        # Pitcher vulnerability adjustment
        pitcher_xwoba = features.get('pitcher_xwoba_against')
        if pitcher_xwoba:
            score += (pitcher_xwoba - 0.320) * 30

        # Clamp to 0-100
        return max(0, min(100, score))

    def get_pitcher_gameday_features(
        self,
        pitcher_mlbam_id: int,
        opponent_team: str,
        park: str,
        pitcher_hand: str = 'R'
    ) -> Dict:
        """
        Generate gameday features for a starting pitcher.

        Args:
            pitcher_mlbam_id: Pitcher's MLBAM ID
            opponent_team: Opposing team abbreviation
            park: Team abbreviation for park
            pitcher_hand: 'L' or 'R'

        Returns:
            Dict with gameday features
        """
        features = {
            'pitcher_id': pitcher_mlbam_id,
            'opponent': opponent_team,
            'park': park,
        }

        # Park factor (inverse for pitchers)
        features['park_factor'] = 2.0 - self.PARK_FACTORS.get(park.upper(), 1.0)

        # Recent pitcher performance
        recent = self._get_recent_pitcher_performance(pitcher_mlbam_id, days=30)
        features.update(recent)

        return features

    def _get_recent_pitcher_performance(self, mlbam_id: int, days: int = 30) -> Dict:
        """Get recent pitching performance."""
        features = {}

        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            df = self.savant_client.get_pitcher_statcast(mlbam_id, start_date, end_date)

            if df.empty:
                return features

            batted = df[df['type'] == 'X']

            if not batted.empty:
                if 'launch_speed' in batted.columns:
                    features['recent_ev_against'] = batted['launch_speed'].mean()

                if 'estimated_woba_using_speedangle' in batted.columns:
                    features['recent_xwoba_against'] = batted['estimated_woba_using_speedangle'].mean()

            # Strikeout rate
            if 'events' in df.columns:
                strikeouts = len(df[df['events'] == 'strikeout'])
                total_pa = len(df[df['events'].notna()])
                if total_pa > 0:
                    features['recent_k_rate'] = strikeouts / total_pa * 100

            # Games/starts in window
            if 'game_date' in df.columns:
                features['recent_appearances'] = df['game_date'].nunique()

        except Exception as e:
            print(f"Error getting recent pitcher performance: {e}")

        return features

    def generate_lineup_features(
        self,
        lineup: List[Dict],
        opponent_pitcher_id: int,
        park: str
    ) -> pd.DataFrame:
        """
        Generate features for an entire lineup.

        Args:
            lineup: List of dicts with 'mlbam_id', 'position', 'hand'
            opponent_pitcher_id: Opposing starting pitcher MLBAM ID
            park: Park abbreviation

        Returns:
            DataFrame with features for each lineup spot
        """
        rows = []

        # Get pitcher info once
        pitcher_features = self._get_pitcher_vulnerability(opponent_pitcher_id)

        for i, player in enumerate(lineup):
            features = self.get_batter_gameday_features(
                batter_mlbam_id=player['mlbam_id'],
                pitcher_mlbam_id=opponent_pitcher_id,
                park=park,
                batter_hand=player.get('hand', 'R'),
                pitcher_hand=player.get('pitcher_hand', 'R')
            )
            features['lineup_position'] = i + 1
            features['position'] = player.get('position', 'UTIL')
            rows.append(features)

        return pd.DataFrame(rows)
