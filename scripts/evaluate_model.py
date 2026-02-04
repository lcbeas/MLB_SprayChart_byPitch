#!/usr/bin/env python3
"""
Model Evaluation Script

Evaluates trained ML models by:
- Predicting values for players
- Comparing predictions to actual Ottoneu salaries
- Generating buy low / sell high recommendations

Usage:
    python scripts/evaluate_model.py --player "Mike Trout"
    python scripts/evaluate_model.py --roster --team-id 123
    python scripts/evaluate_model.py --report
"""

import os
import sys
import argparse
from datetime import datetime
from typing import Optional

import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from backend.ml.models.player_value import PlayerValueModel
from backend.data_sources.fangraphs import FangraphsClient
from backend.data_sources.ottoneu import OttoneuClient


def evaluate_player(
    player_name: str,
    player_type: str = 'batter'
) -> None:
    """
    Evaluate a single player and show predicted value.

    Args:
        player_name: Player name to search
        player_type: 'batter' or 'pitcher'
    """
    print(f"\nSearching for: {player_name}")

    fg_client = FangraphsClient()
    model = PlayerValueModel()

    # Load models
    if not model.load_models():
        print("Error: Models not trained. Run train_models.py first.")
        return

    # Search for player
    results = fg_client.search_players(player_name, player_type)

    if results.empty:
        print(f"No players found matching '{player_name}'")
        return

    # Show search results
    print("\nMatching players:")
    for i, (_, row) in enumerate(results.iterrows()):
        player_id = row.get('fg_id', row.get('playerid'))
        name = row.get('Name', 'Unknown')
        team = row.get('Team', 'N/A')
        print(f"  {i+1}. {name} ({team}) - ID: {player_id}")

    # Use first match
    first_match = results.iloc[0]
    player_id = first_match.get('fg_id', first_match.get('playerid'))
    name = first_match.get('Name', player_name)

    if pd.isna(player_id):
        print("Could not determine player ID")
        return

    player_id = int(player_id)

    print(f"\nPredicting value for: {name}")
    print("-" * 50)

    try:
        prediction = model.predict_value(player_id, player_type)

        print(f"Predicted WAR: {prediction['predicted_war']}")
        print(f"Predicted Value: ${prediction['predicted_value']:.0f}")
        print(f"Confidence: {prediction['confidence']:.1%}")
        print(f"\nModel predictions:")
        for model_name, value in prediction['model_predictions'].items():
            print(f"  {model_name}: {value:.2f} WAR")

    except Exception as e:
        print(f"Prediction failed: {e}")


def evaluate_roster(
    team_id: int,
    league_id: Optional[str] = None
) -> None:
    """
    Evaluate all players on a team roster.

    Args:
        team_id: Ottoneu team ID
        league_id: Optional league ID override
    """
    print(f"\nEvaluating roster for team {team_id}")

    ottoneu_client = OttoneuClient(league_id=league_id)
    model = PlayerValueModel()

    if not model.load_models():
        print("Error: Models not trained. Run train_models.py first.")
        return

    # Get roster
    roster = ottoneu_client.get_my_roster(team_id)

    if roster.empty:
        print(f"No roster found for team {team_id}")
        return

    print(f"Found {len(roster)} players on roster")
    print("-" * 80)

    results = []

    for _, player in roster.iterrows():
        fg_id = player.get('fg_id')
        name = player.get('name', 'Unknown')
        salary = player.get('salary', 0)
        position = player.get('position', 'N/A')

        if pd.isna(fg_id):
            continue

        # Determine player type from position
        player_type = 'pitcher' if any(p in str(position) for p in ['SP', 'RP', 'P']) else 'batter'

        try:
            prediction = model.predict_value(int(fg_id), player_type)

            results.append({
                'Name': name,
                'Position': position,
                'Salary': salary,
                'Predicted': prediction['predicted_value'],
                'Surplus': prediction['predicted_value'] - salary,
                'Confidence': prediction['confidence'],
            })

        except Exception as e:
            print(f"  Error predicting {name}: {e}")

    if not results:
        print("No predictions generated")
        return

    # Create DataFrame and sort by surplus
    df = pd.DataFrame(results)
    df = df.sort_values('Surplus', ascending=False)

    print("\nRoster Evaluation:")
    print("=" * 80)
    print(f"{'Name':<25} {'Pos':<8} {'Salary':>8} {'Predicted':>10} {'Surplus':>10}")
    print("-" * 80)

    for _, row in df.iterrows():
        surplus_str = f"+${row['Surplus']:.0f}" if row['Surplus'] >= 0 else f"-${abs(row['Surplus']):.0f}"
        print(f"{row['Name']:<25} {row['Position']:<8} ${row['Salary']:>7.0f} ${row['Predicted']:>9.0f} {surplus_str:>10}")

    print("-" * 80)
    print(f"Total Salary: ${df['Salary'].sum():.0f}")
    print(f"Total Predicted Value: ${df['Predicted'].sum():.0f}")
    print(f"Total Surplus: ${df['Surplus'].sum():.0f}")

    # Buy low / Sell high recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    sell_high = df[df['Surplus'] < -5].head(3)
    if not sell_high.empty:
        print("\nConsider trading (Sell High):")
        for _, row in sell_high.iterrows():
            print(f"  - {row['Name']}: salary ${row['Salary']:.0f}, value ${row['Predicted']:.0f}")

    buy_low = df[df['Surplus'] > 10].tail(3)
    if not buy_low.empty:
        print("\nGreat values (Hold/Buy More):")
        for _, row in buy_low.iterrows():
            print(f"  - {row['Name']}: salary ${row['Salary']:.0f}, value ${row['Predicted']:.0f}")


def generate_report() -> None:
    """Generate a model performance report."""
    print("\nModel Performance Report")
    print("=" * 70)

    model = PlayerValueModel()

    if not model.load_models():
        print("Error: Models not trained. Run train_models.py first.")
        return

    # Load training info
    info = model.training_info

    for player_type in ['batter', 'pitcher']:
        type_info = info.get(player_type, {})

        if not type_info.get('trained'):
            print(f"\n{player_type.title()} Model: NOT TRAINED")
            continue

        print(f"\n{player_type.title()} Model:")
        print("-" * 50)

        metrics = type_info.get('metrics', {})
        print(f"  Training samples: {metrics.get('n_samples', 'N/A')}")
        print(f"  Features used: {metrics.get('n_features', 'N/A')}")
        print(f"  Ensemble MAE: ${metrics.get('ensemble_mae', 0):.2f}")
        print(f"  Ensemble R2: {metrics.get('ensemble_r2', 0):.3f}")

        weights = metrics.get('ensemble_weights', {})
        if weights:
            print(f"  Ensemble weights:")
            for model_name, weight in weights.items():
                print(f"    - {model_name}: {weight:.2%}")

        # Individual model performance
        individual = metrics.get('individual_models', {})
        if individual:
            print(f"  Individual model R2:")
            for model_name, model_metrics in individual.items():
                print(f"    - {model_name}: {model_metrics.get('test_r2', 0):.3f}")

        # Feature importance
        importance = metrics.get('feature_importance', {})
        if importance:
            print(f"  Top 10 features:")
            for i, (feat, imp) in enumerate(list(importance.items())[:10]):
                print(f"    {i+1:2}. {feat}: {imp:.4f}")

        timestamp = type_info.get('timestamp')
        if timestamp:
            print(f"  Trained: {timestamp}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Evaluate trained ML models for player value prediction'
    )

    parser.add_argument(
        '--player', '-p',
        type=str,
        help='Player name to evaluate'
    )

    parser.add_argument(
        '--type', '-t',
        choices=['batter', 'pitcher'],
        default='batter',
        help='Player type (default: batter)'
    )

    parser.add_argument(
        '--roster', '-r',
        action='store_true',
        help='Evaluate entire team roster'
    )

    parser.add_argument(
        '--team-id',
        type=int,
        help='Ottoneu team ID for roster evaluation'
    )

    parser.add_argument(
        '--league-id',
        type=str,
        help='Ottoneu league ID (default: from config)'
    )

    parser.add_argument(
        '--report',
        action='store_true',
        help='Generate model performance report'
    )

    args = parser.parse_args()

    if args.player:
        evaluate_player(args.player, args.type)
    elif args.roster:
        if not args.team_id:
            print("Error: --team-id required for roster evaluation")
            return
        evaluate_roster(args.team_id, args.league_id)
    elif args.report:
        generate_report()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
