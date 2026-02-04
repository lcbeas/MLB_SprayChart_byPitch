"""
Player Feature Generator

Generates features for player value prediction by combining data from
Fangraphs, Baseball Savant, and Ottoneu.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
from datetime import datetime

from backend.data_sources.fangraphs import FangraphsClient
from backend.data_sources.savant import SavantClient
from backend.data_sources.ottoneu import OttoneuClient


class PlayerFeatureGenerator:
    """
    Generates ML features for player value prediction.

    Combines:
    - Historical performance (Fangraphs)
    - Projections (multiple systems)
    - Statcast metrics (Baseball Savant)
    - Market data (Ottoneu average values)
    """

    # Key batting features for value prediction
    BATTER_STAT_FEATURES = [
        'PA', 'HR', 'R', 'RBI', 'SB', 'AVG', 'OBP', 'SLG', 'wOBA', 'wRC+', 'WAR'
    ]

    # Key pitching features
    PITCHER_STAT_FEATURES = [
        'IP', 'W', 'SV', 'HLD', 'K', 'ERA', 'WHIP', 'FIP', 'xFIP', 'K/9', 'BB/9', 'WAR'
    ]

    # Statcast features for batters
    BATTER_STATCAST_FEATURES = [
        'xBA', 'xSLG', 'xwOBA', 'barrel_rate', 'hard_hit_rate',
        'avg_exit_velo', 'sweet_spot_rate'
    ]

    # Statcast features for pitchers
    PITCHER_STATCAST_FEATURES = [
        'xBA_against', 'xSLG_against', 'xwOBA_against',
        'barrel_rate_against', 'hard_hit_rate_against', 'avg_exit_velo_against'
    ]

    def __init__(self):
        self.fg_client = FangraphsClient()
        self.savant_client = SavantClient()
        self.ottoneu_client = OttoneuClient()

    def get_current_season(self) -> int:
        """Get current MLB season."""
        now = datetime.now()
        return now.year if now.month >= 4 else now.year - 1

    def generate_batter_features(
        self,
        player_id: int,
        mlbam_id: Optional[int] = None,
        seasons: int = 3
    ) -> Dict:
        """
        Generate comprehensive features for a batter.

        Args:
            player_id: Fangraphs player ID
            mlbam_id: MLB AM player ID (for Statcast)
            seasons: Number of historical seasons to include

        Returns:
            Dict with all features
        """
        current_season = self.get_current_season()
        features = {
            'fg_id': player_id,
            'mlbam_id': mlbam_id,
            'player_type': 'batter',
            'timestamp': datetime.now().isoformat(),
        }

        # Historical stats (weighted average with recency bias)
        historical_features = self._get_historical_batter_features(
            player_id, current_season, seasons
        )
        features.update(historical_features)

        # Projection features (consensus of multiple systems)
        projection_features = self._get_projection_features(player_id, 'bat')
        features.update(projection_features)

        # Statcast features
        if mlbam_id:
            statcast_features = self._get_batter_statcast_features(mlbam_id, current_season)
            features.update(statcast_features)

        # Age-related features
        age_features = self._get_age_features(player_id)
        features.update(age_features)

        # Market features
        market_features = self._get_market_features(player_id)
        features.update(market_features)

        return features

    def generate_pitcher_features(
        self,
        player_id: int,
        mlbam_id: Optional[int] = None,
        seasons: int = 3
    ) -> Dict:
        """
        Generate comprehensive features for a pitcher.

        Args:
            player_id: Fangraphs player ID
            mlbam_id: MLB AM player ID (for Statcast)
            seasons: Number of historical seasons to include

        Returns:
            Dict with all features
        """
        current_season = self.get_current_season()
        features = {
            'fg_id': player_id,
            'mlbam_id': mlbam_id,
            'player_type': 'pitcher',
            'timestamp': datetime.now().isoformat(),
        }

        # Historical stats
        historical_features = self._get_historical_pitcher_features(
            player_id, current_season, seasons
        )
        features.update(historical_features)

        # Projection features
        projection_features = self._get_projection_features(player_id, 'pit')
        features.update(projection_features)

        # Statcast features
        if mlbam_id:
            statcast_features = self._get_pitcher_statcast_features(mlbam_id, current_season)
            features.update(statcast_features)

        # Age features
        age_features = self._get_age_features(player_id)
        features.update(age_features)

        # Market features
        market_features = self._get_market_features(player_id)
        features.update(market_features)

        return features

    def _get_historical_batter_features(
        self,
        player_id: int,
        current_season: int,
        seasons: int
    ) -> Dict:
        """Get weighted historical batting stats."""
        features = {}

        # Weights for recency (most recent = highest weight)
        weights = [0.5, 0.3, 0.2][:seasons]
        weights = [w / sum(weights) for w in weights]  # Normalize

        weighted_stats = {stat: 0.0 for stat in self.BATTER_STAT_FEATURES}
        total_pa = 0

        for i, season in enumerate(range(current_season, current_season - seasons, -1)):
            stats = self.fg_client.get_batting_stats(season, qual=1)
            if stats.empty:
                continue

            player_stats = stats[stats.get('fg_id', stats.get('playerid', pd.Series())) == player_id]
            if player_stats.empty:
                continue

            row = player_stats.iloc[0]
            weight = weights[i] if i < len(weights) else weights[-1]

            for stat in self.BATTER_STAT_FEATURES:
                if stat in row:
                    weighted_stats[stat] += float(row[stat]) * weight

            if 'PA' in row:
                total_pa += int(row['PA'])

        # Add to features with prefix
        for stat, value in weighted_stats.items():
            features[f'hist_{stat.lower()}'] = value

        features['hist_total_pa'] = total_pa

        # Calculate trend (comparing recent to past)
        features.update(self._calculate_trend_features(player_id, current_season, 'bat'))

        return features

    def _get_historical_pitcher_features(
        self,
        player_id: int,
        current_season: int,
        seasons: int
    ) -> Dict:
        """Get weighted historical pitching stats."""
        features = {}

        weights = [0.5, 0.3, 0.2][:seasons]
        weights = [w / sum(weights) for w in weights]

        weighted_stats = {stat: 0.0 for stat in self.PITCHER_STAT_FEATURES}
        total_ip = 0

        for i, season in enumerate(range(current_season, current_season - seasons, -1)):
            stats = self.fg_client.get_pitching_stats(season, qual=1)
            if stats.empty:
                continue

            player_stats = stats[stats.get('fg_id', stats.get('playerid', pd.Series())) == player_id]
            if player_stats.empty:
                continue

            row = player_stats.iloc[0]
            weight = weights[i] if i < len(weights) else weights[-1]

            for stat in self.PITCHER_STAT_FEATURES:
                if stat in row:
                    weighted_stats[stat] += float(row[stat]) * weight

            if 'IP' in row:
                total_ip += float(row['IP'])

        for stat, value in weighted_stats.items():
            features[f'hist_{stat.lower().replace("/", "_")}'] = value

        features['hist_total_ip'] = total_ip

        # Role indicator (SP vs RP)
        if total_ip > 0:
            gs_ratio = weighted_stats.get('GS', 0) / max(weighted_stats.get('G', 1), 1)
            features['is_starter'] = 1 if gs_ratio > 0.5 else 0
        else:
            features['is_starter'] = 0

        features.update(self._calculate_trend_features(player_id, current_season, 'pit'))

        return features

    def _get_projection_features(self, player_id: int, player_type: str) -> Dict:
        """Get consensus projection features from multiple systems."""
        features = {}

        systems = ['steamer', 'zips', 'atc']
        projections = []

        for system in systems:
            try:
                proj = self.fg_client.get_projections(system=system, player_type=player_type)
                if not proj.empty:
                    player_proj = proj[proj.get('fg_id', proj.get('playerid', pd.Series())) == player_id]
                    if not player_proj.empty:
                        projections.append(player_proj.iloc[0].to_dict())
            except Exception:
                continue

        if not projections:
            return features

        # Calculate consensus (average) projections
        stat_cols = self.BATTER_STAT_FEATURES if player_type == 'bat' else self.PITCHER_STAT_FEATURES

        for stat in stat_cols:
            values = [p.get(stat) for p in projections if p.get(stat) is not None]
            if values:
                try:
                    features[f'proj_{stat.lower().replace("/", "_")}'] = np.mean([float(v) for v in values])
                    features[f'proj_{stat.lower().replace("/", "_")}_std'] = np.std([float(v) for v in values])
                except (ValueError, TypeError):
                    pass

        # Projection agreement score (lower std = more agreement)
        stds = [v for k, v in features.items() if k.endswith('_std') and v is not None]
        if stds:
            features['proj_agreement'] = 1 / (1 + np.mean(stds))

        return features

    def _get_batter_statcast_features(self, mlbam_id: int, season: int) -> Dict:
        """Get Statcast features for a batter."""
        features = {}

        try:
            expected = self.savant_client.get_expected_stats(mlbam_id, season)
            for key in self.BATTER_STATCAST_FEATURES:
                if key in expected:
                    features[f'sc_{key.lower()}'] = expected[key]

            # Batted ball profile
            profile = self.savant_client.get_batted_ball_profile(mlbam_id, season)
            for key in ['gb_pct', 'ld_pct', 'fb_pct', 'pull_pct', 'center_pct', 'oppo_pct']:
                if key in profile:
                    features[f'sc_{key}'] = profile[key]

            # Plate discipline
            discipline = self.savant_client.get_plate_discipline(mlbam_id, season)
            for key in ['zone_pct', 'swing_pct', 'o_swing_pct', 'contact_pct', 'whiff_pct']:
                if key in discipline:
                    features[f'sc_{key}'] = discipline[key]

            # Sprint speed
            speed = self.savant_client.get_player_sprint_speed(mlbam_id, season)
            if speed and speed.get('sprint_speed'):
                features['sc_sprint_speed'] = speed['sprint_speed']

        except Exception as e:
            print(f"Error getting Statcast features: {e}")

        return features

    def _get_pitcher_statcast_features(self, mlbam_id: int, season: int) -> Dict:
        """Get Statcast features for a pitcher."""
        features = {}

        try:
            expected = self.savant_client.get_pitcher_expected_stats(mlbam_id, season)
            for key in self.PITCHER_STATCAST_FEATURES:
                if key in expected:
                    features[f'sc_{key.lower()}'] = expected[key]

            # Pitch arsenal summary
            arsenal = self.savant_client.get_pitch_arsenal(mlbam_id, season)
            if not arsenal.empty:
                # Primary pitch velocity
                if 'avg_velocity' in arsenal.columns:
                    features['sc_primary_velo'] = arsenal.iloc[0]['avg_velocity']
                    features['sc_max_velo'] = arsenal['avg_velocity'].max()

                # Number of pitches with > 10% usage
                features['sc_pitch_count'] = len(arsenal[arsenal['usage_pct'] >= 10])

                # Average whiff rate across pitches
                if 'whiff_rate' in arsenal.columns:
                    features['sc_avg_whiff'] = arsenal['whiff_rate'].mean()

        except Exception as e:
            print(f"Error getting pitcher Statcast features: {e}")

        return features

    def _get_age_features(self, player_id: int) -> Dict:
        """Get age-related features."""
        features = {}

        try:
            player_info = self.fg_client.get_player_page(player_id)
            if player_info.get('age'):
                age = player_info['age']
                features['age'] = age
                features['age_squared'] = age ** 2  # Non-linear aging curve

                # Peak age indicators
                features['pre_peak'] = 1 if age < 27 else 0
                features['peak'] = 1 if 27 <= age <= 31 else 0
                features['post_peak'] = 1 if age > 31 else 0

        except Exception:
            pass

        return features

    def _get_market_features(self, player_id: int) -> Dict:
        """Get market value features from Ottoneu."""
        features = {}

        try:
            avg_values = self.ottoneu_client.get_average_values()
            if not avg_values.empty:
                # Try to find player by various ID columns
                player_row = None
                for id_col in ['ottoneu_id', 'fg_id', 'playerid']:
                    if id_col in avg_values.columns:
                        match = avg_values[avg_values[id_col] == player_id]
                        if not match.empty:
                            player_row = match.iloc[0]
                            break

                if player_row is not None:
                    if 'avg_salary' in player_row:
                        features['market_avg_salary'] = player_row['avg_salary']
                    if 'roster_pct' in player_row:
                        features['market_roster_pct'] = player_row['roster_pct']

        except Exception as e:
            print(f"Error getting market features: {e}")

        return features

    def _calculate_trend_features(
        self,
        player_id: int,
        current_season: int,
        player_type: str
    ) -> Dict:
        """Calculate performance trend features."""
        features = {}

        try:
            # Compare last season to 2 seasons ago
            if player_type == 'bat':
                recent = self.fg_client.get_batting_stats(current_season - 1, qual=1)
                older = self.fg_client.get_batting_stats(current_season - 2, qual=1)
                key_stat = 'wRC+'
            else:
                recent = self.fg_client.get_pitching_stats(current_season - 1, qual=1)
                older = self.fg_client.get_pitching_stats(current_season - 2, qual=1)
                key_stat = 'FIP'

            if recent.empty or older.empty:
                return features

            id_col = 'fg_id' if 'fg_id' in recent.columns else 'playerid'

            recent_player = recent[recent[id_col] == player_id]
            older_player = older[older[id_col] == player_id]

            if not recent_player.empty and not older_player.empty:
                if key_stat in recent_player.columns and key_stat in older_player.columns:
                    recent_val = float(recent_player.iloc[0][key_stat])
                    older_val = float(older_player.iloc[0][key_stat])

                    if player_type == 'bat':
                        # Higher wRC+ is better
                        features['trend_direction'] = 1 if recent_val > older_val else -1
                        features['trend_magnitude'] = recent_val - older_val
                    else:
                        # Lower FIP is better
                        features['trend_direction'] = 1 if recent_val < older_val else -1
                        features['trend_magnitude'] = older_val - recent_val

        except Exception as e:
            print(f"Error calculating trends: {e}")

        return features

    def generate_training_dataset(
        self,
        seasons: List[int],
        min_pa: int = 200,
        min_ip: int = 50
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Generate training datasets for batters and pitchers.

        Args:
            seasons: List of seasons to include
            min_pa: Minimum PA for batters
            min_ip: Minimum IP for pitchers

        Returns:
            Tuple of (batter_df, pitcher_df)
        """
        batter_rows = []
        pitcher_rows = []

        for season in seasons:
            print(f"Processing season {season}...")

            # Get batting stats
            batters = self.fg_client.get_batting_stats(season, qual=min_pa)
            if not batters.empty:
                for _, row in batters.iterrows():
                    player_id = row.get('fg_id', row.get('playerid'))
                    if player_id:
                        try:
                            features = self.generate_batter_features(int(player_id))
                            features['season'] = season
                            # Target: next season's value or current value
                            features['target_value'] = row.get('WAR', 0)
                            batter_rows.append(features)
                        except Exception as e:
                            print(f"Error processing batter {player_id}: {e}")

            # Get pitching stats
            pitchers = self.fg_client.get_pitching_stats(season, qual=min_ip)
            if not pitchers.empty:
                for _, row in pitchers.iterrows():
                    player_id = row.get('fg_id', row.get('playerid'))
                    if player_id:
                        try:
                            features = self.generate_pitcher_features(int(player_id))
                            features['season'] = season
                            features['target_value'] = row.get('WAR', 0)
                            pitcher_rows.append(features)
                        except Exception as e:
                            print(f"Error processing pitcher {player_id}: {e}")

        batter_df = pd.DataFrame(batter_rows) if batter_rows else pd.DataFrame()
        pitcher_df = pd.DataFrame(pitcher_rows) if pitcher_rows else pd.DataFrame()

        return batter_df, pitcher_df
