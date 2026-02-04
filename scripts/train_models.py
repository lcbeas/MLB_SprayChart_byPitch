#!/usr/bin/env python3
"""
ML Model Training Script

Trains player value prediction models using historical data from:
- Fangraphs (stats and projections)
- Baseball Savant (Statcast metrics)
- Ottoneu (actual auction values)

Usage:
    python scripts/train_models.py --seasons 2022 2023 2024
    python scripts/train_models.py --quick  # Fast training with recent data only
    python scripts/train_models.py --full   # Full training with 5 years of data
"""

import os
import sys
import argparse
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from backend.data_sources.fangraphs import FangraphsClient
from backend.data_sources.savant import SavantClient
from backend.data_sources.ottoneu import OttoneuClient
from backend.ml.models.player_value import PlayerValueModel


class TrainingDataGenerator:
    """
    Generates training data for ML models by combining multiple data sources.

    Uses actual Ottoneu salaries as target values when available, with WAR
    as a fallback for players without salary data.
    """

    # WAR to Ottoneu dollars conversion (approximate)
    WAR_TO_DOLLARS = 9.0

    def __init__(self, verbose: bool = True):
        self.fg_client = FangraphsClient()
        self.savant_client = SavantClient()
        self.ottoneu_client = OttoneuClient()
        self.verbose = verbose

        # ID mapping cache
        self._id_map = {}

    def log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def get_current_season(self) -> int:
        """Get current MLB season."""
        now = datetime.now()
        return now.year if now.month >= 4 else now.year - 1

    def build_id_mapping(self) -> Dict:
        """
        Build mapping between Fangraphs IDs and MLBAM IDs.

        Returns:
            Dict mapping fg_id -> mlbam_id
        """
        if self._id_map:
            return self._id_map

        self.log("Building player ID mapping...")

        try:
            # Get Ottoneu average values which often have both IDs
            avg_values = self.ottoneu_client.get_average_values()

            if not avg_values.empty:
                # Look for ID columns
                fg_col = None
                mlbam_col = None

                for col in avg_values.columns:
                    if 'fg' in col.lower() or 'fangraph' in col.lower():
                        fg_col = col
                    if 'mlbam' in col.lower() or 'mlb_id' in col.lower():
                        mlbam_col = col

                if fg_col and mlbam_col:
                    for _, row in avg_values.iterrows():
                        if pd.notna(row[fg_col]) and pd.notna(row[mlbam_col]):
                            self._id_map[int(row[fg_col])] = int(row[mlbam_col])

            self.log(f"Built ID mapping for {len(self._id_map)} players")

        except Exception as e:
            self.log(f"Warning: Could not build ID mapping: {e}")

        return self._id_map

    def get_mlbam_id(self, fg_id: int) -> Optional[int]:
        """Get MLBAM ID from Fangraphs ID."""
        if not self._id_map:
            self.build_id_mapping()
        return self._id_map.get(fg_id)

    def fetch_ottoneu_values(self) -> pd.DataFrame:
        """
        Fetch current Ottoneu average values to use as targets.

        Returns:
            DataFrame with player salaries
        """
        self.log("Fetching Ottoneu average values...")

        try:
            avg_values = self.ottoneu_client.get_average_values()

            if avg_values.empty:
                self.log("Warning: No Ottoneu values found")
                return pd.DataFrame()

            # Standardize column names
            result = avg_values.copy()

            # Identify player ID column
            for col in ['ottoneu_id', 'id', 'fg_majorleagueid']:
                if col in result.columns:
                    result = result.rename(columns={col: 'player_id'})
                    break

            self.log(f"Fetched values for {len(result)} players")
            return result

        except Exception as e:
            self.log(f"Error fetching Ottoneu values: {e}")
            return pd.DataFrame()

    def fetch_batting_stats(
        self,
        season: int,
        min_pa: int = 100
    ) -> pd.DataFrame:
        """
        Fetch batting stats for a season.

        Args:
            season: Year to fetch
            min_pa: Minimum plate appearances

        Returns:
            DataFrame with batting stats
        """
        self.log(f"Fetching {season} batting stats (min {min_pa} PA)...")

        try:
            stats = self.fg_client.get_batting_stats(season, qual=min_pa)

            if stats.empty:
                return pd.DataFrame()

            # Standardize ID column
            if 'playerid' in stats.columns:
                stats = stats.rename(columns={'playerid': 'fg_id'})

            stats['season'] = season
            self.log(f"Found {len(stats)} batters for {season}")

            return stats

        except Exception as e:
            self.log(f"Error fetching batting stats: {e}")
            return pd.DataFrame()

    def fetch_pitching_stats(
        self,
        season: int,
        min_ip: int = 30
    ) -> pd.DataFrame:
        """
        Fetch pitching stats for a season.

        Args:
            season: Year to fetch
            min_ip: Minimum innings pitched

        Returns:
            DataFrame with pitching stats
        """
        self.log(f"Fetching {season} pitching stats (min {min_ip} IP)...")

        try:
            stats = self.fg_client.get_pitching_stats(season, qual=min_ip)

            if stats.empty:
                return pd.DataFrame()

            if 'playerid' in stats.columns:
                stats = stats.rename(columns={'playerid': 'fg_id'})

            stats['season'] = season
            self.log(f"Found {len(stats)} pitchers for {season}")

            return stats

        except Exception as e:
            self.log(f"Error fetching pitching stats: {e}")
            return pd.DataFrame()

    def fetch_statcast_batter_data(
        self,
        season: int,
        min_pa: int = 50
    ) -> pd.DataFrame:
        """
        Fetch Statcast leaderboard data for batters.

        Args:
            season: Year to fetch
            min_pa: Minimum plate appearances

        Returns:
            DataFrame with Statcast metrics
        """
        self.log(f"Fetching {season} batter Statcast data...")

        try:
            # Expected stats
            expected = self.savant_client.get_expected_stats_leaderboard(
                season, player_type='batter', min_pa=min_pa
            )

            # Batted ball data
            batted = self.savant_client.get_statcast_leaderboard(
                season, player_type='batter', min_pa=min_pa
            )

            # Merge if both available
            if not expected.empty and not batted.empty:
                # Find common ID column
                id_col = None
                for col in ['player_id', 'mlbam_id', 'batter']:
                    if col in expected.columns and col in batted.columns:
                        id_col = col
                        break

                if id_col:
                    result = expected.merge(batted, on=id_col, how='outer', suffixes=('', '_bat'))
                    self.log(f"Merged Statcast data for {len(result)} batters")
                    return result

            # Return whichever is available
            if not expected.empty:
                return expected
            if not batted.empty:
                return batted

            return pd.DataFrame()

        except Exception as e:
            self.log(f"Error fetching Statcast data: {e}")
            return pd.DataFrame()

    def fetch_statcast_pitcher_data(
        self,
        season: int,
        min_pa: int = 50
    ) -> pd.DataFrame:
        """
        Fetch Statcast leaderboard data for pitchers.

        Args:
            season: Year to fetch
            min_pa: Minimum batters faced

        Returns:
            DataFrame with Statcast metrics
        """
        self.log(f"Fetching {season} pitcher Statcast data...")

        try:
            expected = self.savant_client.get_expected_stats_leaderboard(
                season, player_type='pitcher', min_pa=min_pa
            )

            if not expected.empty:
                self.log(f"Found Statcast data for {len(expected)} pitchers")

            return expected

        except Exception as e:
            self.log(f"Error fetching pitcher Statcast: {e}")
            return pd.DataFrame()

    def fetch_projections(self, player_type: str = 'bat') -> pd.DataFrame:
        """
        Fetch current projections from multiple systems.

        Args:
            player_type: 'bat' or 'pit'

        Returns:
            DataFrame with consensus projections
        """
        self.log(f"Fetching projections for {player_type}...")

        systems = ['steamer', 'zips', 'atc']
        all_projections = []

        for system in systems:
            try:
                proj = self.fg_client.get_projections(system=system, player_type=player_type)
                if not proj.empty:
                    proj['projection_system'] = system
                    all_projections.append(proj)
            except Exception as e:
                self.log(f"Warning: Could not fetch {system} projections: {e}")

        if not all_projections:
            return pd.DataFrame()

        combined = pd.concat(all_projections, ignore_index=True)
        self.log(f"Fetched {len(combined)} projection records")

        return combined

    def create_consensus_projections(
        self,
        projections: pd.DataFrame,
        player_type: str = 'bat'
    ) -> pd.DataFrame:
        """
        Create consensus projections from multiple systems.

        Args:
            projections: DataFrame with projections from multiple systems
            player_type: 'bat' or 'pit'

        Returns:
            DataFrame with consensus values per player
        """
        if projections.empty:
            return pd.DataFrame()

        # Identify ID column
        id_col = 'fg_id' if 'fg_id' in projections.columns else 'playerid'
        if id_col not in projections.columns:
            return pd.DataFrame()

        # Key stats to average
        if player_type == 'bat':
            stat_cols = ['PA', 'HR', 'R', 'RBI', 'SB', 'AVG', 'OBP', 'SLG', 'wOBA', 'wRC+', 'WAR']
        else:
            stat_cols = ['IP', 'W', 'SV', 'K', 'ERA', 'WHIP', 'FIP', 'xFIP', 'WAR']

        # Get available stat columns
        available_stats = [col for col in stat_cols if col in projections.columns]

        if not available_stats:
            return pd.DataFrame()

        # Group by player and calculate mean
        agg_dict = {col: 'mean' for col in available_stats}

        # Also keep name if available
        if 'Name' in projections.columns:
            agg_dict['Name'] = 'first'
        if 'Team' in projections.columns:
            agg_dict['Team'] = 'first'

        consensus = projections.groupby(id_col).agg(agg_dict).reset_index()

        # Rename columns to indicate they're projections
        rename_dict = {col: f'proj_{col}' for col in available_stats}
        consensus = consensus.rename(columns=rename_dict)

        self.log(f"Created consensus projections for {len(consensus)} players")
        return consensus

    def generate_batter_training_data(
        self,
        seasons: List[int],
        min_pa: int = 150
    ) -> pd.DataFrame:
        """
        Generate training dataset for batters.

        Args:
            seasons: List of seasons to include
            min_pa: Minimum plate appearances

        Returns:
            DataFrame ready for model training
        """
        self.log("=" * 60)
        self.log("GENERATING BATTER TRAINING DATA")
        self.log("=" * 60)

        all_rows = []

        # Fetch Ottoneu values for targets
        ottoneu_values = self.fetch_ottoneu_values()

        # Fetch current projections
        projections = self.fetch_projections('bat')
        consensus_proj = self.create_consensus_projections(projections, 'bat')

        for season in seasons:
            self.log(f"\n--- Processing {season} ---")

            # Fetch historical stats
            stats = self.fetch_batting_stats(season, min_pa)
            if stats.empty:
                continue

            # Fetch Statcast data
            statcast = self.fetch_statcast_batter_data(season, min_pa=min_pa // 2)

            # Process each player
            for _, row in stats.iterrows():
                try:
                    fg_id = row.get('fg_id')
                    if pd.isna(fg_id):
                        continue
                    fg_id = int(fg_id)

                    # Initialize feature dict
                    features = {
                        'fg_id': fg_id,
                        'name': row.get('Name', ''),
                        'season': season,
                        'player_type': 'batter',
                    }

                    # Historical stats features
                    for stat in ['PA', 'HR', 'R', 'RBI', 'SB', 'AVG', 'OBP', 'SLG',
                                 'wOBA', 'wRC+', 'WAR', 'BB%', 'K%']:
                        if stat in row and pd.notna(row[stat]):
                            features[f'hist_{stat.lower().replace("%", "_pct").replace("+", "_plus")}'] = float(row[stat])

                    # Try to add Statcast features
                    if not statcast.empty:
                        mlbam_id = self.get_mlbam_id(fg_id)
                        if mlbam_id:
                            for id_col in ['player_id', 'mlbam_id', 'batter']:
                                if id_col in statcast.columns:
                                    player_sc = statcast[statcast[id_col] == mlbam_id]
                                    if not player_sc.empty:
                                        sc_row = player_sc.iloc[0]
                                        for sc_stat in ['xba', 'xslg', 'xwoba', 'barrel_batted_rate',
                                                        'hard_hit_percent', 'avg_hit_speed']:
                                            if sc_stat in sc_row and pd.notna(sc_row[sc_stat]):
                                                features[f'sc_{sc_stat}'] = float(sc_row[sc_stat])
                                        break

                    # Add projection features if available
                    if not consensus_proj.empty and 'fg_id' in consensus_proj.columns:
                        player_proj = consensus_proj[consensus_proj['fg_id'] == fg_id]
                        if not player_proj.empty:
                            proj_row = player_proj.iloc[0]
                            for col in proj_row.index:
                                if col.startswith('proj_') and pd.notna(proj_row[col]):
                                    features[col] = float(proj_row[col])

                    # Calculate target value
                    target_value = None

                    # Try Ottoneu average salary first
                    if not ottoneu_values.empty:
                        for id_col in ['player_id', 'fg_majorleagueid', 'ottoneu_id']:
                            if id_col in ottoneu_values.columns:
                                player_ott = ottoneu_values[ottoneu_values[id_col] == fg_id]
                                if not player_ott.empty:
                                    if 'avg_salary' in player_ott.columns:
                                        target_value = float(player_ott.iloc[0]['avg_salary'])
                                    break

                    # Fallback to WAR-based value
                    if target_value is None and 'hist_war' in features:
                        target_value = max(1, features['hist_war'] * self.WAR_TO_DOLLARS)

                    if target_value is not None:
                        features['target_value'] = target_value
                        all_rows.append(features)

                except Exception as e:
                    self.log(f"Error processing batter: {e}")
                    continue

        if not all_rows:
            return pd.DataFrame()

        result = pd.DataFrame(all_rows)
        self.log(f"\nGenerated {len(result)} batter training samples")

        return result

    def generate_pitcher_training_data(
        self,
        seasons: List[int],
        min_ip: int = 40
    ) -> pd.DataFrame:
        """
        Generate training dataset for pitchers.

        Args:
            seasons: List of seasons to include
            min_ip: Minimum innings pitched

        Returns:
            DataFrame ready for model training
        """
        self.log("=" * 60)
        self.log("GENERATING PITCHER TRAINING DATA")
        self.log("=" * 60)

        all_rows = []

        # Fetch Ottoneu values
        ottoneu_values = self.fetch_ottoneu_values()

        # Fetch projections
        projections = self.fetch_projections('pit')
        consensus_proj = self.create_consensus_projections(projections, 'pit')

        for season in seasons:
            self.log(f"\n--- Processing {season} ---")

            stats = self.fetch_pitching_stats(season, min_ip)
            if stats.empty:
                continue

            statcast = self.fetch_statcast_pitcher_data(season, min_pa=min_ip * 3)

            for _, row in stats.iterrows():
                try:
                    fg_id = row.get('fg_id')
                    if pd.isna(fg_id):
                        continue
                    fg_id = int(fg_id)

                    features = {
                        'fg_id': fg_id,
                        'name': row.get('Name', ''),
                        'season': season,
                        'player_type': 'pitcher',
                    }

                    # Historical stats
                    for stat in ['IP', 'W', 'SV', 'HLD', 'G', 'GS', 'ERA', 'WHIP',
                                 'FIP', 'xFIP', 'K/9', 'BB/9', 'WAR', 'K%', 'BB%']:
                        if stat in row and pd.notna(row[stat]):
                            features[f'hist_{stat.lower().replace("/", "_").replace("%", "_pct")}'] = float(row[stat])

                    # Role indicator
                    if 'GS' in row and 'G' in row:
                        gs_ratio = row['GS'] / max(row['G'], 1)
                        features['is_starter'] = 1 if gs_ratio > 0.5 else 0

                    # Statcast features
                    if not statcast.empty:
                        mlbam_id = self.get_mlbam_id(fg_id)
                        if mlbam_id:
                            for id_col in ['player_id', 'mlbam_id', 'pitcher']:
                                if id_col in statcast.columns:
                                    player_sc = statcast[statcast[id_col] == mlbam_id]
                                    if not player_sc.empty:
                                        sc_row = player_sc.iloc[0]
                                        for sc_stat in ['xba', 'xslg', 'xwoba', 'barrel_batted_rate',
                                                        'hard_hit_percent']:
                                            if sc_stat in sc_row and pd.notna(sc_row[sc_stat]):
                                                features[f'sc_{sc_stat}_against'] = float(sc_row[sc_stat])
                                        break

                    # Projection features
                    if not consensus_proj.empty and 'fg_id' in consensus_proj.columns:
                        player_proj = consensus_proj[consensus_proj['fg_id'] == fg_id]
                        if not player_proj.empty:
                            proj_row = player_proj.iloc[0]
                            for col in proj_row.index:
                                if col.startswith('proj_') and pd.notna(proj_row[col]):
                                    features[col] = float(proj_row[col])

                    # Target value
                    target_value = None

                    if not ottoneu_values.empty:
                        for id_col in ['player_id', 'fg_majorleagueid', 'ottoneu_id']:
                            if id_col in ottoneu_values.columns:
                                player_ott = ottoneu_values[ottoneu_values[id_col] == fg_id]
                                if not player_ott.empty:
                                    if 'avg_salary' in player_ott.columns:
                                        target_value = float(player_ott.iloc[0]['avg_salary'])
                                    break

                    if target_value is None and 'hist_war' in features:
                        target_value = max(1, features['hist_war'] * self.WAR_TO_DOLLARS)

                    if target_value is not None:
                        features['target_value'] = target_value
                        all_rows.append(features)

                except Exception as e:
                    self.log(f"Error processing pitcher: {e}")
                    continue

        if not all_rows:
            return pd.DataFrame()

        result = pd.DataFrame(all_rows)
        self.log(f"\nGenerated {len(result)} pitcher training samples")

        return result


def train_models(
    seasons: List[int],
    min_pa: int = 150,
    min_ip: int = 40,
    test_size: float = 0.2,
    save_data: bool = True,
    verbose: bool = True
) -> Dict:
    """
    Main training function.

    Args:
        seasons: List of seasons to use for training
        min_pa: Minimum PA for batters
        min_ip: Minimum IP for pitchers
        test_size: Test set fraction
        save_data: Whether to save training data to disk
        verbose: Print progress messages

    Returns:
        Dict with training results
    """
    print("=" * 70)
    print("OTTONEU FANTASY BASEBALL - ML MODEL TRAINING")
    print("=" * 70)
    print(f"Seasons: {seasons}")
    print(f"Min PA: {min_pa}, Min IP: {min_ip}")
    print(f"Test size: {test_size}")
    print()

    start_time = time.time()

    # Generate training data
    generator = TrainingDataGenerator(verbose=verbose)

    print("\n[1/4] Generating batter training data...")
    batter_df = generator.generate_batter_training_data(seasons, min_pa)

    print("\n[2/4] Generating pitcher training data...")
    pitcher_df = generator.generate_pitcher_training_data(seasons, min_ip)

    # Save training data if requested
    if save_data:
        data_dir = os.path.join(Config.DATA_DIR, 'training')
        os.makedirs(data_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if not batter_df.empty:
            batter_path = os.path.join(data_dir, f'batter_training_{timestamp}.csv')
            batter_df.to_csv(batter_path, index=False)
            print(f"Saved batter data to: {batter_path}")

        if not pitcher_df.empty:
            pitcher_path = os.path.join(data_dir, f'pitcher_training_{timestamp}.csv')
            pitcher_df.to_csv(pitcher_path, index=False)
            print(f"Saved pitcher data to: {pitcher_path}")

    # Train models
    print("\n[3/4] Training ML models...")
    model = PlayerValueModel()

    results = model.train(
        batter_df=batter_df,
        pitcher_df=pitcher_df,
        target_col='target_value',
        test_size=test_size
    )

    # Print results
    print("\n[4/4] Training complete!")
    print("\n" + "=" * 70)
    print("TRAINING RESULTS")
    print("=" * 70)

    if 'batter' in results:
        print("\nBatter Model:")
        print(f"  Samples: {results['batter'].get('n_samples', 'N/A')}")
        print(f"  Features: {results['batter'].get('n_features', 'N/A')}")
        print(f"  Ensemble MAE: ${results['batter'].get('ensemble_mae', 'N/A'):.2f}")
        print(f"  Ensemble R2: {results['batter'].get('ensemble_r2', 'N/A'):.3f}")
        print(f"  Weights: {results['batter'].get('ensemble_weights', {})}")

        print("\n  Top 5 Important Features:")
        importance = results['batter'].get('feature_importance', {})
        for i, (feat, imp) in enumerate(list(importance.items())[:5]):
            print(f"    {i+1}. {feat}: {imp:.4f}")

    if 'pitcher' in results:
        print("\nPitcher Model:")
        print(f"  Samples: {results['pitcher'].get('n_samples', 'N/A')}")
        print(f"  Features: {results['pitcher'].get('n_features', 'N/A')}")
        print(f"  Ensemble MAE: ${results['pitcher'].get('ensemble_mae', 'N/A'):.2f}")
        print(f"  Ensemble R2: {results['pitcher'].get('ensemble_r2', 'N/A'):.3f}")
        print(f"  Weights: {results['pitcher'].get('ensemble_weights', {})}")

        print("\n  Top 5 Important Features:")
        importance = results['pitcher'].get('feature_importance', {})
        for i, (feat, imp) in enumerate(list(importance.items())[:5]):
            print(f"    {i+1}. {feat}: {imp:.4f}")

    elapsed = time.time() - start_time
    print(f"\nTotal training time: {elapsed:.1f} seconds")

    # Save results summary
    results_path = os.path.join(Config.DATA_DIR, 'models', 'training_results.json')
    os.makedirs(os.path.dirname(results_path), exist_ok=True)

    # Convert numpy types for JSON serialization
    def convert_numpy(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.int32, np.int64)):
            return int(obj)
        return obj

    results_json = {
        'timestamp': datetime.now().isoformat(),
        'seasons': seasons,
        'min_pa': min_pa,
        'min_ip': min_ip,
        'test_size': test_size,
        'elapsed_seconds': elapsed,
        'batter': {k: convert_numpy(v) for k, v in results.get('batter', {}).items()},
        'pitcher': {k: convert_numpy(v) for k, v in results.get('pitcher', {}).items()},
    }

    with open(results_path, 'w') as f:
        json.dump(results_json, f, indent=2, default=str)
    print(f"\nResults saved to: {results_path}")

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Train ML models for Ottoneu player value prediction'
    )

    parser.add_argument(
        '--seasons', '-s',
        nargs='+',
        type=int,
        help='Seasons to include in training (e.g., 2022 2023 2024)'
    )

    parser.add_argument(
        '--quick', '-q',
        action='store_true',
        help='Quick training with recent 2 seasons only'
    )

    parser.add_argument(
        '--full', '-f',
        action='store_true',
        help='Full training with 5 years of data'
    )

    parser.add_argument(
        '--min-pa',
        type=int,
        default=150,
        help='Minimum plate appearances for batters (default: 150)'
    )

    parser.add_argument(
        '--min-ip',
        type=int,
        default=40,
        help='Minimum innings pitched for pitchers (default: 40)'
    )

    parser.add_argument(
        '--test-size',
        type=float,
        default=0.2,
        help='Test set fraction (default: 0.2)'
    )

    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save training data to disk'
    )

    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Minimal output'
    )

    args = parser.parse_args()

    # Determine seasons
    current_season = datetime.now().year if datetime.now().month >= 4 else datetime.now().year - 1

    if args.seasons:
        seasons = args.seasons
    elif args.quick:
        seasons = [current_season - 1, current_season]
    elif args.full:
        seasons = list(range(current_season - 4, current_season + 1))
    else:
        # Default: 3 years
        seasons = [current_season - 2, current_season - 1, current_season]

    # Run training
    train_models(
        seasons=seasons,
        min_pa=args.min_pa,
        min_ip=args.min_ip,
        test_size=args.test_size,
        save_data=not args.no_save,
        verbose=not args.quiet
    )


if __name__ == '__main__':
    main()
