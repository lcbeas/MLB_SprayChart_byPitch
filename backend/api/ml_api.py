"""
ML API endpoints

Exposes lineup optimization, player value prediction, and model training functionality.
"""

import math
from flask import Blueprint, jsonify, request
from backend.ml.models.lineup_optimizer import LineupOptimizer
from backend.ml.models.player_value import PlayerValueModel
from config import Config
import pandas as pd

bp = Blueprint('ml', __name__)


def sanitize_for_json(obj):
    """
    Recursively sanitize an object for JSON serialization.
    Converts NaN, Inf to None/safe values.
    """
    if obj is None:
        return None
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (int, str, bool)):
        return obj
    else:
        # Try to convert numpy types
        try:
            if hasattr(obj, 'item'):  # numpy scalar
                val = obj.item()
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    return None
                return val
        except (ValueError, TypeError):
            pass
        return obj

# Singleton instances (to avoid reloading models on each request)
_lineup_optimizer = None
_value_model = None


def get_lineup_optimizer():
    """Get or create LineupOptimizer instance."""
    global _lineup_optimizer
    if _lineup_optimizer is None:
        _lineup_optimizer = LineupOptimizer()
    return _lineup_optimizer


def get_value_model():
    """Get or create PlayerValueModel instance."""
    global _value_model
    if _value_model is None:
        _value_model = PlayerValueModel()
        _value_model.load_models()
    return _value_model


# -----------------------------------------------------------------------------
# Lineup Optimizer Endpoints
# -----------------------------------------------------------------------------

@bp.route('/lineup/optimize', methods=['POST'])
def optimize_lineup():
    """
    Optimize daily lineup for maximum expected points.

    POST body:
        {
            "roster": [
                {
                    "player_id": 123,
                    "mlbam_id": 456,
                    "name": "Player Name",
                    "positions": ["SS", "2B"],
                    "salary": 10,
                    "projected_points": 7.5
                },
                ...
            ],
            "matchups": {
                "123": {
                    "opponent_pitcher_id": 789,
                    "opponent_team": "NYY",
                    "park": "NYY",
                    "pitcher_hand": "R"
                },
                ...
            },
            "inning_limits": {
                "456": 50.5
            },
            "date": "2024-06-15"
        }

    Returns:
        Optimized lineup with expected points
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'roster' not in data or not data['roster']:
        return jsonify({'error': 'roster is required and cannot be empty'}), 400

    try:
        optimizer = get_lineup_optimizer()
        result = optimizer.optimize_lineup(
            roster=data['roster'],
            matchups=data.get('matchups', {}),
            inning_limits=data.get('inning_limits'),
            date=data.get('date')
        )

        return jsonify(sanitize_for_json(result))
    except Exception as e:
        return jsonify({'error': f'Lineup optimization failed: {str(e)}'}), 500


@bp.route('/lineup/suggest-changes', methods=['POST'])
def suggest_lineup_changes():
    """
    Suggest changes to improve current lineup.

    POST body:
        {
            "current_lineup": {
                "batting_lineup": {...},
                "pitching_lineup": {...}
            },
            "roster": [...],
            "matchups": {...}
        }

    Returns:
        List of suggested swaps with expected point gain
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    required_fields = ['current_lineup', 'roster', 'matchups']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    try:
        optimizer = get_lineup_optimizer()
        suggestions = optimizer.suggest_lineup_changes(
            current_lineup=data['current_lineup'],
            roster=data['roster'],
            matchups=data['matchups']
        )

        return jsonify(sanitize_for_json({
            'suggestions': suggestions,
            'count': len(suggestions)
        }))
    except Exception as e:
        return jsonify({'error': f'Failed to generate suggestions: {str(e)}'}), 500


@bp.route('/lineup/inning-limits', methods=['POST'])
def calculate_inning_limits():
    """
    Calculate remaining innings for each pitcher based on pace.

    POST body:
        {
            "roster": [
                {"player_id": 123, "positions": ["SP"], "projected_ip_ros": 100},
                ...
            ],
            "league_limit": 1500,
            "games_remaining": 100,
            "current_ip": {
                "123": 50.1
            }
        }

    Returns:
        Dict of player_id -> remaining IP allowed
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'roster' not in data:
        return jsonify({'error': 'roster is required'}), 400

    try:
        optimizer = get_lineup_optimizer()
        limits = optimizer.calculate_inning_limits(
            roster=data['roster'],
            league_limit=data.get('league_limit', 1500),
            games_remaining=data.get('games_remaining', 162),
            current_ip=data.get('current_ip')
        )

        return jsonify({
            'inning_limits': limits,
            'league_limit': data.get('league_limit', 1500),
            'games_remaining': data.get('games_remaining', 162)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to calculate inning limits: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Player Value Endpoints
# -----------------------------------------------------------------------------

@bp.route('/value/predict', methods=['GET'])
def predict_player_value():
    """
    Predict Ottoneu dollar value for a player.

    Query params:
        player_id: Fangraphs player ID (required)
        player_type: 'batter' or 'pitcher' (default: 'batter')
        mlbam_id: Optional MLBAM ID for Statcast features

    Returns:
        Predicted value with confidence score
    """
    player_id = request.args.get('player_id', type=int)
    if not player_id:
        return jsonify({'error': 'player_id is required'}), 400

    player_type = request.args.get('player_type', 'batter')
    mlbam_id = request.args.get('mlbam_id', type=int)

    try:
        model = get_value_model()

        if not model.is_trained(player_type):
            return jsonify({
                'error': f'Model for {player_type} is not trained. Call /ml/train first.',
                'is_trained': False
            }), 400

        prediction = model.predict_value(player_id, player_type, mlbam_id)
        return jsonify(prediction)
    except Exception as e:
        return jsonify({'error': f'Prediction failed: {str(e)}'}), 500


@bp.route('/value/predict-batch', methods=['POST'])
def predict_batch_values():
    """
    Predict values for multiple players.

    POST body:
        {
            "players": [
                {"player_id": 123, "name": "Player A", "mlbam_id": 456},
                ...
            ],
            "player_type": "batter"
        }

    Returns:
        List of predictions for all players
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'players' not in data or not data['players']:
        return jsonify({'error': 'players is required and cannot be empty'}), 400

    player_type = data.get('player_type', 'batter')

    try:
        model = get_value_model()

        if not model.is_trained(player_type):
            return jsonify({
                'error': f'Model for {player_type} is not trained. Call /ml/train first.',
                'is_trained': False
            }), 400

        predictions_df = model.predict_batch(data['players'], player_type)

        return jsonify({
            'predictions': predictions_df.to_dict('records'),
            'count': len(predictions_df)
        })
    except Exception as e:
        return jsonify({'error': f'Batch prediction failed: {str(e)}'}), 500


@bp.route('/value/buy-low-sell-high', methods=['POST'])
def identify_buy_low_sell_high():
    """
    Identify undervalued (buy low) and overvalued (sell high) players.

    POST body:
        {
            "roster": [
                {
                    "player_id": 123,
                    "name": "Player A",
                    "salary": 15,
                    "player_type": "batter",
                    "mlbam_id": 456,
                    "position": "SS"
                },
                ...
            ],
            "threshold": 0.2
        }

    Returns:
        Categorized players (buy_low, sell_high, hold)
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'roster' not in data or not data['roster']:
        return jsonify({'error': 'roster is required and cannot be empty'}), 400

    threshold = data.get('threshold', 0.2)

    try:
        model = get_value_model()
        roster_df = pd.DataFrame(data['roster'])

        results = model.identify_buy_low_sell_high(roster_df, threshold)

        return jsonify({
            'buy_low': results['buy_low'].to_dict('records') if not results['buy_low'].empty else [],
            'sell_high': results['sell_high'].to_dict('records') if not results['sell_high'].empty else [],
            'hold': results['hold'].to_dict('records') if not results['hold'].empty else [],
            'threshold': threshold
        })
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@bp.route('/value/bid-recommendation', methods=['GET'])
def get_bid_recommendation():
    """
    Get bid recommendation for a free agent.

    Query params:
        player_id: Fangraphs player ID (required)
        player_type: 'batter' or 'pitcher' (default: 'batter')
        mlbam_id: Optional MLBAM ID
        current_bid: Current highest bid (optional)
        budget_remaining: Your remaining budget (optional)

    Returns:
        Recommended bid with reasoning
    """
    player_id = request.args.get('player_id', type=int)
    if not player_id:
        return jsonify({'error': 'player_id is required'}), 400

    player_type = request.args.get('player_type', 'batter')
    mlbam_id = request.args.get('mlbam_id', type=int)
    current_bid = request.args.get('current_bid', 0, type=float)
    budget_remaining = request.args.get('budget_remaining', 400, type=float)

    try:
        model = get_value_model()

        if not model.is_trained(player_type):
            return jsonify({
                'error': f'Model for {player_type} is not trained.',
                'is_trained': False
            }), 400

        prediction = model.predict_value(player_id, player_type, mlbam_id)
        predicted_value = prediction['predicted_value']
        confidence = prediction['confidence']

        # Calculate recommendation
        # Adjust for confidence
        adjusted_value = predicted_value * (0.7 + 0.3 * confidence)

        # Don't recommend bidding more than 25% of remaining budget on one player
        max_recommended = min(adjusted_value, budget_remaining * 0.25)

        # Should we bid?
        should_bid = current_bid < adjusted_value * 0.9  # 10% margin

        recommendation = {
            'player_id': player_id,
            'predicted_value': predicted_value,
            'adjusted_value': round(adjusted_value, 0),
            'confidence': confidence,
            'current_bid': current_bid,
            'max_recommended_bid': round(max_recommended, 0),
            'should_bid': should_bid,
            'reasoning': []
        }

        # Add reasoning
        if should_bid:
            if current_bid == 0:
                recommendation['reasoning'].append(
                    f"Opening bid opportunity - player valued at ${predicted_value:.0f}"
                )
            elif current_bid < predicted_value * 0.7:
                recommendation['reasoning'].append(
                    f"Strong value - current bid ${current_bid:.0f} is well below value of ${predicted_value:.0f}"
                )
            else:
                recommendation['reasoning'].append(
                    f"Moderate value - consider bidding up to ${max_recommended:.0f}"
                )
        else:
            recommendation['reasoning'].append(
                f"Current bid ${current_bid:.0f} exceeds recommended value of ${adjusted_value:.0f}"
            )

        if confidence < 0.5:
            recommendation['reasoning'].append(
                "Low confidence prediction - proceed with caution"
            )

        return jsonify(recommendation)
    except Exception as e:
        return jsonify({'error': f'Recommendation failed: {str(e)}'}), 500


# -----------------------------------------------------------------------------
# Model Training Endpoints
# -----------------------------------------------------------------------------

@bp.route('/train', methods=['POST'])
def train_models():
    """
    Train the player value prediction models.

    POST body:
        {
            "batter_data": [...],  # Optional: training data for batters
            "pitcher_data": [...], # Optional: training data for pitchers
            "use_historical": true # If true, fetch historical data for training
        }

    Note: Training can take several minutes. Consider running asynchronously.

    Returns:
        Training results with metrics
    """
    data = request.get_json() or {}

    try:
        model = get_value_model()

        # If data provided, use it; otherwise generate from historical
        if data.get('batter_data') or data.get('pitcher_data'):
            batter_df = pd.DataFrame(data.get('batter_data', []))
            pitcher_df = pd.DataFrame(data.get('pitcher_data', []))
        elif data.get('use_historical', True):
            # Generate training data from historical performance
            # This would typically fetch data from your data sources
            return jsonify({
                'error': 'Historical data generation not yet implemented. Please provide training data.',
                'expected_format': {
                    'batter_data': [
                        {'player_id': 123, 'target_value': 3.5, 'hist_pa': 500, '...': '...'}
                    ],
                    'pitcher_data': [
                        {'player_id': 456, 'target_value': 2.1, 'hist_ip': 150, '...': '...'}
                    ]
                }
            }), 400
        else:
            return jsonify({'error': 'No training data provided'}), 400

        # Train models
        results = model.train(batter_df, pitcher_df)

        return jsonify({
            'status': 'success',
            'results': results
        })
    except Exception as e:
        return jsonify({'error': f'Training failed: {str(e)}'}), 500


@bp.route('/model-status', methods=['GET'])
def get_model_status():
    """
    Get current model training status and metrics.

    Returns:
        Model status including whether trained, metrics, and timestamps
    """
    try:
        model = get_value_model()

        return jsonify({
            'batter_model': {
                'is_trained': model.is_trained('batter'),
                'metrics': model.training_info.get('batter', {}).get('metrics', {}),
                'timestamp': model.training_info.get('batter', {}).get('timestamp')
            },
            'pitcher_model': {
                'is_trained': model.is_trained('pitcher'),
                'metrics': model.training_info.get('pitcher', {}).get('metrics', {}),
                'timestamp': model.training_info.get('pitcher', {}).get('timestamp')
            },
            'model_weights': {
                'batter': model.batter_weights,
                'pitcher': model.pitcher_weights
            }
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get model status: {str(e)}'}), 500


@bp.route('/feature-importance', methods=['GET'])
def get_feature_importance():
    """
    Get feature importance from trained models.

    Query params:
        player_type: 'batter' or 'pitcher' (default: 'batter')

    Returns:
        Feature importance rankings
    """
    player_type = request.args.get('player_type', 'batter')

    try:
        model = get_value_model()

        if not model.is_trained(player_type):
            return jsonify({
                'error': f'Model for {player_type} is not trained.',
                'is_trained': False
            }), 400

        metrics = model.training_info.get(player_type, {}).get('metrics', {})
        importance = metrics.get('feature_importance', {})

        return jsonify({
            'player_type': player_type,
            'feature_importance': importance,
            'features_used': metrics.get('features_used', [])
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get feature importance: {str(e)}'}), 500
