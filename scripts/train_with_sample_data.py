#!/usr/bin/env python3
"""
Train ML models with sample/synthetic data for testing.

This script generates realistic sample data to test the training pipeline
when external data sources (Fangraphs, Savant, Ottoneu) are unavailable.

Usage:
    python scripts/train_with_sample_data.py
"""

import os
import sys
import json
import time
from datetime import datetime

import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from backend.ml.models.player_value import PlayerValueModel


def generate_sample_batter_data(n_samples: int = 200) -> pd.DataFrame:
    """
    Generate realistic sample batter data for training.

    Creates synthetic data based on typical MLB statistical distributions.
    """
    np.random.seed(42)

    # Generate player IDs
    fg_ids = list(range(10000, 10000 + n_samples))

    # Sample player names
    first_names = ['Mike', 'Aaron', 'Mookie', 'Juan', 'Ronald', 'Shohei', 'Corey',
                   'Freddie', 'Manny', 'Trea', 'Bo', 'Marcus', 'Pete', 'Matt', 'Kyle']
    last_names = ['Trout', 'Judge', 'Betts', 'Soto', 'Acuna', 'Ohtani', 'Seager',
                  'Freeman', 'Machado', 'Turner', 'Bichette', 'Semien', 'Alonso', 'Olson', 'Tucker']

    data = []

    for i, fg_id in enumerate(fg_ids):
        # Base WAR (determines overall player quality)
        base_war = np.random.exponential(2.0)
        base_war = np.clip(base_war, 0, 10)

        # Generate correlated stats based on WAR
        pa = int(np.clip(np.random.normal(500 + base_war * 30, 100), 200, 700))
        hr = int(np.clip(np.random.normal(15 + base_war * 3, 8), 0, 60))
        r = int(np.clip(np.random.normal(60 + base_war * 8, 15), 20, 140))
        rbi = int(np.clip(np.random.normal(55 + base_war * 8, 18), 15, 150))
        sb = int(np.clip(np.random.exponential(8 + base_war), 0, 50))

        # Rate stats
        avg = np.clip(np.random.normal(0.260 + base_war * 0.01, 0.025), 0.180, 0.350)
        obp = np.clip(avg + np.random.normal(0.07, 0.02), 0.250, 0.450)
        slg = np.clip(np.random.normal(0.420 + base_war * 0.02, 0.060), 0.280, 0.700)
        woba = np.clip(np.random.normal(0.320 + base_war * 0.015, 0.030), 0.250, 0.450)
        wrc_plus = int(np.clip(np.random.normal(100 + base_war * 10, 20), 50, 180))

        # Statcast metrics (correlated with performance)
        xba = np.clip(avg + np.random.normal(0, 0.015), 0.180, 0.350)
        xslg = np.clip(slg + np.random.normal(0, 0.030), 0.280, 0.700)
        xwoba = np.clip(woba + np.random.normal(0, 0.020), 0.250, 0.450)
        barrel_rate = np.clip(np.random.normal(6 + base_war * 1.5, 3), 0, 25)
        hard_hit_rate = np.clip(np.random.normal(35 + base_war * 2, 7), 20, 60)
        avg_exit_velo = np.clip(np.random.normal(87 + base_war * 1, 3), 80, 98)

        # Projection stats (slight regression to mean)
        proj_war = base_war * 0.8 + np.random.normal(0, 0.5)
        proj_hr = int(hr * 0.9 + np.random.normal(0, 3))
        proj_r = int(r * 0.9 + np.random.normal(0, 8))
        proj_rbi = int(rbi * 0.9 + np.random.normal(0, 10))

        # Target value (Ottoneu dollars) - based on WAR and surplus
        # $1 min, roughly $9/WAR with some noise
        target_value = max(1, base_war * 9 + np.random.normal(0, 3))

        data.append({
            'fg_id': fg_id,
            'name': f"{np.random.choice(first_names)} {np.random.choice(last_names)} {i}",
            'season': np.random.choice([2022, 2023, 2024]),
            'player_type': 'batter',

            # Historical stats
            'hist_pa': pa,
            'hist_hr': hr,
            'hist_r': r,
            'hist_rbi': rbi,
            'hist_sb': sb,
            'hist_avg': round(avg, 3),
            'hist_obp': round(obp, 3),
            'hist_slg': round(slg, 3),
            'hist_woba': round(woba, 3),
            'hist_wrc_plus': wrc_plus,
            'hist_war': round(base_war, 1),

            # Statcast
            'sc_xba': round(xba, 3),
            'sc_xslg': round(xslg, 3),
            'sc_xwoba': round(xwoba, 3),
            'sc_barrel_rate': round(barrel_rate, 1),
            'sc_hard_hit_rate': round(hard_hit_rate, 1),
            'sc_avg_exit_velo': round(avg_exit_velo, 1),

            # Projections
            'proj_war': round(proj_war, 1),
            'proj_hr': proj_hr,
            'proj_r': proj_r,
            'proj_rbi': proj_rbi,

            # Target
            'target_value': round(target_value, 1),
        })

    return pd.DataFrame(data)


def generate_sample_pitcher_data(n_samples: int = 150) -> pd.DataFrame:
    """
    Generate realistic sample pitcher data for training.
    """
    np.random.seed(43)

    fg_ids = list(range(20000, 20000 + n_samples))

    first_names = ['Gerrit', 'Max', 'Jacob', 'Corbin', 'Zack', 'Spencer', 'Dylan',
                   'Shane', 'Logan', 'Tyler', 'Shohei', 'Kevin', 'Tarik', 'Pablo', 'Kyle']
    last_names = ['Cole', 'Scherzer', 'deGrom', 'Burnes', 'Wheeler', 'Strider', 'Cease',
                  'McClanahan', 'Gilbert', 'Glasnow', 'Ohtani', 'Gausman', 'Skubal', 'Lopez', 'Bradish']

    data = []

    for i, fg_id in enumerate(fg_ids):
        # Starter vs reliever
        is_starter = np.random.random() < 0.6

        # Base WAR
        if is_starter:
            base_war = np.random.exponential(2.5)
            base_war = np.clip(base_war, 0, 8)
            ip = int(np.clip(np.random.normal(160 + base_war * 10, 30), 60, 220))
            gs = int(ip / 6)
            g = gs + np.random.randint(0, 3)
            sv = 0
            hld = 0
        else:
            base_war = np.random.exponential(1.0)
            base_war = np.clip(base_war, 0, 4)
            ip = int(np.clip(np.random.normal(55 + base_war * 10, 15), 30, 90))
            gs = 0
            g = int(ip / 1.2)
            # Some relievers are closers
            if np.random.random() < 0.2:
                sv = int(np.clip(np.random.normal(25 + base_war * 5, 8), 0, 50))
                hld = 0
            else:
                sv = 0
                hld = int(np.clip(np.random.normal(10 + base_war * 5, 5), 0, 35))

        # Performance stats (inversely related to ERA/FIP for pitchers)
        era = np.clip(np.random.normal(4.0 - base_war * 0.3, 0.6), 1.5, 6.0)
        fip = np.clip(era + np.random.normal(0, 0.3), 1.5, 6.0)
        xfip = np.clip(fip + np.random.normal(0, 0.2), 1.5, 6.0)
        whip = np.clip(np.random.normal(1.25 - base_war * 0.05, 0.12), 0.8, 1.6)
        k_9 = np.clip(np.random.normal(8.5 + base_war * 0.5, 1.5), 5, 14)
        bb_9 = np.clip(np.random.normal(3.0 - base_war * 0.2, 0.6), 1, 5)

        k = int(k_9 * ip / 9)
        w = int(np.clip(np.random.normal(8 + base_war * 1.5, 3), 0, 20)) if is_starter else 0

        # Statcast
        xba_against = np.clip(np.random.normal(0.250 - base_war * 0.01, 0.020), 0.180, 0.300)
        xwoba_against = np.clip(np.random.normal(0.320 - base_war * 0.015, 0.025), 0.230, 0.380)
        barrel_rate_against = np.clip(np.random.normal(8 - base_war * 0.5, 2), 3, 15)

        # Target value
        target_value = max(1, base_war * 9 + np.random.normal(0, 2.5))

        data.append({
            'fg_id': fg_id,
            'name': f"{np.random.choice(first_names)} {np.random.choice(last_names)} {i}",
            'season': np.random.choice([2022, 2023, 2024]),
            'player_type': 'pitcher',

            # Historical stats
            'hist_ip': ip,
            'hist_g': g,
            'hist_gs': gs,
            'hist_w': w,
            'hist_sv': sv,
            'hist_hld': hld,
            'hist_k': k,
            'hist_era': round(era, 2),
            'hist_whip': round(whip, 2),
            'hist_fip': round(fip, 2),
            'hist_xfip': round(xfip, 2),
            'hist_k_9': round(k_9, 1),
            'hist_bb_9': round(bb_9, 1),
            'hist_war': round(base_war, 1),
            'is_starter': 1 if is_starter else 0,

            # Statcast
            'sc_xba_against': round(xba_against, 3),
            'sc_xwoba_against': round(xwoba_against, 3),
            'sc_barrel_rate_against': round(barrel_rate_against, 1),

            # Projections
            'proj_war': round(base_war * 0.8 + np.random.normal(0, 0.4), 1),
            'proj_ip': int(ip * 0.9),
            'proj_era': round(era * 1.05 + np.random.normal(0, 0.2), 2),

            # Target
            'target_value': round(target_value, 1),
        })

    return pd.DataFrame(data)


def main():
    """Generate sample data and train models."""
    print("=" * 70)
    print("TRAINING ML MODELS WITH SAMPLE DATA")
    print("=" * 70)
    print()

    start_time = time.time()

    # Generate sample data
    print("[1/4] Generating sample batter data...")
    batter_df = generate_sample_batter_data(200)
    print(f"      Generated {len(batter_df)} batter samples")

    print("\n[2/4] Generating sample pitcher data...")
    pitcher_df = generate_sample_pitcher_data(150)
    print(f"      Generated {len(pitcher_df)} pitcher samples")

    # Save sample data
    data_dir = os.path.join(Config.DATA_DIR, 'training')
    os.makedirs(data_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    batter_path = os.path.join(data_dir, f'sample_batter_training_{timestamp}.csv')
    pitcher_path = os.path.join(data_dir, f'sample_pitcher_training_{timestamp}.csv')

    batter_df.to_csv(batter_path, index=False)
    pitcher_df.to_csv(pitcher_path, index=False)
    print(f"\n      Saved training data to {data_dir}")

    # Train models
    print("\n[3/4] Training ML models...")
    model = PlayerValueModel()

    results = model.train(
        batter_df=batter_df,
        pitcher_df=pitcher_df,
        target_col='target_value',
        test_size=0.2
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
        print(f"  Ensemble MAE: ${results['batter'].get('ensemble_mae', 0):.2f}")
        print(f"  Ensemble R2: {results['batter'].get('ensemble_r2', 0):.3f}")

        weights = results['batter'].get('ensemble_weights', {})
        print(f"  Ensemble weights: ", end="")
        for name, w in weights.items():
            print(f"{name}={w:.2f} ", end="")
        print()

        print("\n  Top 5 Important Features:")
        importance = results['batter'].get('feature_importance', {})
        for i, (feat, imp) in enumerate(list(importance.items())[:5]):
            print(f"    {i+1}. {feat}: {imp:.4f}")

    if 'pitcher' in results:
        print("\nPitcher Model:")
        print(f"  Samples: {results['pitcher'].get('n_samples', 'N/A')}")
        print(f"  Features: {results['pitcher'].get('n_features', 'N/A')}")
        print(f"  Ensemble MAE: ${results['pitcher'].get('ensemble_mae', 0):.2f}")
        print(f"  Ensemble R2: {results['pitcher'].get('ensemble_r2', 0):.3f}")

        weights = results['pitcher'].get('ensemble_weights', {})
        print(f"  Ensemble weights: ", end="")
        for name, w in weights.items():
            print(f"{name}={w:.2f} ", end="")
        print()

        print("\n  Top 5 Important Features:")
        importance = results['pitcher'].get('feature_importance', {})
        for i, (feat, imp) in enumerate(list(importance.items())[:5]):
            print(f"    {i+1}. {feat}: {imp:.4f}")

    elapsed = time.time() - start_time
    print(f"\nTotal training time: {elapsed:.1f} seconds")

    # Save results
    results_path = os.path.join(Config.DATA_DIR, 'models', 'training_results.json')

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
        'data_type': 'sample',
        'batter_samples': len(batter_df),
        'pitcher_samples': len(pitcher_df),
        'elapsed_seconds': elapsed,
        'batter': {k: convert_numpy(v) for k, v in results.get('batter', {}).items()},
        'pitcher': {k: convert_numpy(v) for k, v in results.get('pitcher', {}).items()},
    }

    with open(results_path, 'w') as f:
        json.dump(results_json, f, indent=2, default=str)

    print(f"\nResults saved to: {results_path}")
    print(f"Models saved to: {Config.DATA_DIR}/models/")

    # Verify models saved
    print("\n" + "=" * 70)
    print("SAVED MODEL FILES")
    print("=" * 70)
    model_dir = os.path.join(Config.DATA_DIR, 'models')
    for f in sorted(os.listdir(model_dir)):
        filepath = os.path.join(model_dir, f)
        size = os.path.getsize(filepath)
        print(f"  {f}: {size:,} bytes")


if __name__ == '__main__':
    main()
