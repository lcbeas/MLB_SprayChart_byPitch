"""
Player Value Prediction Model

Predicts player value (in Ottoneu dollars) using:
- Historical performance
- Projections from multiple systems
- Statcast metrics
- Age curves
- Market data

Used for:
- Free agent bidding recommendations
- Trade value calculations
- Buy low / Sell high identification
"""

import os
import json
import pickle
import numpy as np
import pandas as pd
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from config import Config
from backend.ml.features.player_features import PlayerFeatureGenerator


class PlayerValueModel:
    """
    Ensemble model for predicting player value in Ottoneu dollars.

    Uses a stacked ensemble of:
    - Gradient Boosting (captures non-linear relationships)
    - Random Forest (robust to outliers)
    - Ridge Regression (stable baseline)
    """

    # Features to use for prediction (must match feature generator output)
    BATTER_FEATURES = [
        # Historical stats
        'hist_pa', 'hist_hr', 'hist_r', 'hist_rbi', 'hist_sb',
        'hist_avg', 'hist_obp', 'hist_slg', 'hist_woba', 'hist_wrc+', 'hist_war',
        # Projections
        'proj_pa', 'proj_hr', 'proj_r', 'proj_rbi', 'proj_sb',
        'proj_avg', 'proj_obp', 'proj_slg', 'proj_woba', 'proj_wrc+', 'proj_war',
        'proj_agreement',
        # Statcast
        'sc_xba', 'sc_xslg', 'sc_xwoba', 'sc_barrel_rate', 'sc_hard_hit_rate',
        'sc_avg_exit_velo', 'sc_sweet_spot_rate', 'sc_sprint_speed',
        'sc_gb_pct', 'sc_fb_pct', 'sc_pull_pct',
        # Age
        'age', 'age_squared', 'pre_peak', 'peak', 'post_peak',
        # Market
        'market_avg_salary', 'market_roster_pct',
        # Trends
        'trend_direction', 'trend_magnitude',
    ]

    PITCHER_FEATURES = [
        # Historical stats
        'hist_ip', 'hist_w', 'hist_sv', 'hist_hld', 'hist_k',
        'hist_era', 'hist_whip', 'hist_fip', 'hist_xfip', 'hist_k_9', 'hist_bb_9', 'hist_war',
        'is_starter',
        # Projections
        'proj_ip', 'proj_w', 'proj_sv', 'proj_k',
        'proj_era', 'proj_whip', 'proj_fip', 'proj_war',
        'proj_agreement',
        # Statcast
        'sc_xba_against', 'sc_xslg_against', 'sc_xwoba_against',
        'sc_barrel_rate_against', 'sc_hard_hit_rate_against',
        'sc_primary_velo', 'sc_pitch_count', 'sc_avg_whiff',
        # Age
        'age', 'age_squared', 'pre_peak', 'peak', 'post_peak',
        # Market
        'market_avg_salary', 'market_roster_pct',
        # Trends
        'trend_direction', 'trend_magnitude',
    ]

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir or os.path.join(Config.DATA_DIR, 'models')
        os.makedirs(self.model_dir, exist_ok=True)

        self.feature_generator = PlayerFeatureGenerator()

        # Models for batters
        self.batter_models = {
            'gbm': GradientBoostingRegressor(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                min_samples_leaf=10,
                random_state=42
            ),
            'rf': RandomForestRegressor(
                n_estimators=200,
                max_depth=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1
            ),
            'ridge': Ridge(alpha=1.0),
        }

        # Models for pitchers
        self.pitcher_models = {
            'gbm': GradientBoostingRegressor(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                min_samples_leaf=10,
                random_state=42
            ),
            'rf': RandomForestRegressor(
                n_estimators=200,
                max_depth=10,
                min_samples_leaf=5,
                random_state=42,
                n_jobs=-1
            ),
            'ridge': Ridge(alpha=1.0),
        }

        # Scalers
        self.batter_scaler = StandardScaler()
        self.pitcher_scaler = StandardScaler()

        # Meta-model weights (learned during training)
        self.batter_weights = {'gbm': 0.4, 'rf': 0.4, 'ridge': 0.2}
        self.pitcher_weights = {'gbm': 0.4, 'rf': 0.4, 'ridge': 0.2}

        # Training metadata
        self.training_info = {
            'batter': {'trained': False, 'metrics': {}},
            'pitcher': {'trained': False, 'metrics': {}}
        }

    def _prepare_features(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        is_training: bool = True
    ) -> Tuple[np.ndarray, List[str]]:
        """Prepare feature matrix from DataFrame."""
        # Get available features
        available_features = [f for f in feature_cols if f in df.columns]

        if not available_features:
            raise ValueError("No valid features found in data")

        X = df[available_features].copy()

        # Fill missing values with median (for training) or 0 (for prediction)
        if is_training:
            X = X.fillna(X.median())
        else:
            X = X.fillna(0)

        # Replace infinities
        X = X.replace([np.inf, -np.inf], 0)

        return X.values, available_features

    def train(
        self,
        batter_df: pd.DataFrame,
        pitcher_df: pd.DataFrame,
        target_col: str = 'target_value',
        test_size: float = 0.2
    ) -> Dict:
        """
        Train the value prediction models.

        Args:
            batter_df: DataFrame with batter features and target
            pitcher_df: DataFrame with pitcher features and target
            target_col: Column name for target variable
            test_size: Fraction for test split

        Returns:
            Dict with training metrics
        """
        results = {}

        # Train batter model
        if not batter_df.empty and target_col in batter_df.columns:
            print("Training batter model...")
            batter_results = self._train_player_type(
                batter_df, target_col, 'batter', test_size
            )
            results['batter'] = batter_results

        # Train pitcher model
        if not pitcher_df.empty and target_col in pitcher_df.columns:
            print("Training pitcher model...")
            pitcher_results = self._train_player_type(
                pitcher_df, target_col, 'pitcher', test_size
            )
            results['pitcher'] = pitcher_results

        # Save models
        self.save_models()

        return results

    def _train_player_type(
        self,
        df: pd.DataFrame,
        target_col: str,
        player_type: str,
        test_size: float
    ) -> Dict:
        """Train models for a specific player type."""
        features = self.BATTER_FEATURES if player_type == 'batter' else self.PITCHER_FEATURES
        models = self.batter_models if player_type == 'batter' else self.pitcher_models
        scaler = self.batter_scaler if player_type == 'batter' else self.pitcher_scaler

        # Prepare data
        X, used_features = self._prepare_features(df, features, is_training=True)
        y = df[target_col].values

        # Store used features
        if player_type == 'batter':
            self._batter_features_used = used_features
        else:
            self._pitcher_features_used = used_features

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        # Scale features
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train each model
        model_results = {}
        predictions = {}

        for name, model in models.items():
            print(f"  Training {name}...")
            model.fit(X_train_scaled, y_train)

            # Evaluate
            train_pred = model.predict(X_train_scaled)
            test_pred = model.predict(X_test_scaled)
            predictions[name] = test_pred

            model_results[name] = {
                'train_mae': mean_absolute_error(y_train, train_pred),
                'test_mae': mean_absolute_error(y_test, test_pred),
                'train_r2': r2_score(y_train, train_pred),
                'test_r2': r2_score(y_test, test_pred),
            }

        # Optimize ensemble weights using test set performance
        weights = self._optimize_weights(predictions, y_test)
        if player_type == 'batter':
            self.batter_weights = weights
        else:
            self.pitcher_weights = weights

        # Calculate ensemble performance
        ensemble_pred = sum(
            predictions[name] * weights[name] for name in predictions
        )

        results = {
            'individual_models': model_results,
            'ensemble_weights': weights,
            'ensemble_mae': mean_absolute_error(y_test, ensemble_pred),
            'ensemble_r2': r2_score(y_test, ensemble_pred),
            'n_samples': len(df),
            'n_features': len(used_features),
            'features_used': used_features,
        }

        # Feature importance (from GBM)
        gbm = models['gbm']
        importance = dict(zip(used_features, gbm.feature_importances_))
        results['feature_importance'] = dict(
            sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]
        )

        # Update training info
        self.training_info[player_type] = {
            'trained': True,
            'metrics': results,
            'timestamp': datetime.now().isoformat()
        }

        return results

    def _optimize_weights(
        self,
        predictions: Dict[str, np.ndarray],
        y_true: np.ndarray
    ) -> Dict[str, float]:
        """Optimize ensemble weights to minimize MAE."""
        from scipy.optimize import minimize

        model_names = list(predictions.keys())
        pred_matrix = np.column_stack([predictions[name] for name in model_names])

        def objective(weights):
            weights = np.array(weights)
            weights = weights / weights.sum()  # Normalize
            ensemble = pred_matrix @ weights
            return mean_absolute_error(y_true, ensemble)

        # Initial weights
        x0 = np.ones(len(model_names)) / len(model_names)

        # Constraints: weights sum to 1, all positive
        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        bounds = [(0.05, 0.9) for _ in model_names]

        result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)

        optimized = result.x / result.x.sum()
        return dict(zip(model_names, optimized))

    def predict_value(
        self,
        player_id: int,
        player_type: str = 'batter',
        mlbam_id: Optional[int] = None
    ) -> Dict:
        """
        Predict Ottoneu dollar value for a player.

        Args:
            player_id: Fangraphs player ID
            player_type: 'batter' or 'pitcher'
            mlbam_id: Optional MLBAM ID for Statcast features

        Returns:
            Dict with predicted value and confidence
        """
        # Generate features
        if player_type == 'batter':
            features = self.feature_generator.generate_batter_features(player_id, mlbam_id)
            models = self.batter_models
            scaler = self.batter_scaler
            weights = self.batter_weights
            feature_cols = getattr(self, '_batter_features_used', self.BATTER_FEATURES)
        else:
            features = self.feature_generator.generate_pitcher_features(player_id, mlbam_id)
            models = self.pitcher_models
            scaler = self.pitcher_scaler
            weights = self.pitcher_weights
            feature_cols = getattr(self, '_pitcher_features_used', self.PITCHER_FEATURES)

        # Convert to DataFrame for processing
        df = pd.DataFrame([features])
        X, _ = self._prepare_features(df, feature_cols, is_training=False)

        # Scale
        X_scaled = scaler.transform(X)

        # Get predictions from each model
        predictions = {}
        for name, model in models.items():
            predictions[name] = model.predict(X_scaled)[0]

        # Ensemble prediction
        ensemble_value = sum(predictions[name] * weights[name] for name in predictions)

        # Convert WAR to dollars (rough conversion: 1 WAR ≈ $8-10 in Ottoneu)
        # This conversion factor should be calibrated with actual Ottoneu data
        war_to_dollars = 9.0
        dollar_value = ensemble_value * war_to_dollars

        # Confidence based on model agreement
        pred_values = list(predictions.values())
        pred_std = np.std(pred_values)
        confidence = max(0, 1 - (pred_std / max(abs(ensemble_value), 0.1)))

        return {
            'player_id': player_id,
            'player_type': player_type,
            'predicted_war': round(ensemble_value, 2),
            'predicted_value': round(max(1, dollar_value), 0),  # Min $1
            'confidence': round(confidence, 2),
            'model_predictions': {k: round(v, 2) for k, v in predictions.items()},
            'features_used': len(feature_cols),
        }

    def predict_batch(
        self,
        players: List[Dict],
        player_type: str = 'batter'
    ) -> pd.DataFrame:
        """
        Predict values for multiple players.

        Args:
            players: List of dicts with 'player_id' and optional 'mlbam_id'
            player_type: 'batter' or 'pitcher'

        Returns:
            DataFrame with predictions
        """
        results = []
        for player in players:
            try:
                pred = self.predict_value(
                    player['player_id'],
                    player_type,
                    player.get('mlbam_id')
                )
                pred['name'] = player.get('name', '')
                results.append(pred)
            except Exception as e:
                print(f"Error predicting for player {player.get('player_id')}: {e}")

        return pd.DataFrame(results)

    def identify_buy_low_sell_high(
        self,
        roster_df: pd.DataFrame,
        threshold: float = 0.2
    ) -> Dict[str, pd.DataFrame]:
        """
        Identify players who are undervalued (buy low) or overvalued (sell high).

        Args:
            roster_df: DataFrame with 'player_id', 'salary', 'player_type', 'mlbam_id'
            threshold: Minimum difference ratio to flag (0.2 = 20%)

        Returns:
            Dict with 'buy_low' and 'sell_high' DataFrames
        """
        results = []

        for _, row in roster_df.iterrows():
            try:
                pred = self.predict_value(
                    row['player_id'],
                    row.get('player_type', 'batter'),
                    row.get('mlbam_id')
                )

                current_salary = row.get('salary', 0)
                predicted_value = pred['predicted_value']

                # Calculate value difference
                if current_salary > 0:
                    diff_ratio = (predicted_value - current_salary) / current_salary
                else:
                    diff_ratio = 1.0 if predicted_value > 5 else 0.0

                results.append({
                    'player_id': row['player_id'],
                    'name': row.get('name', ''),
                    'position': row.get('position', ''),
                    'current_salary': current_salary,
                    'predicted_value': predicted_value,
                    'value_difference': predicted_value - current_salary,
                    'diff_ratio': diff_ratio,
                    'confidence': pred['confidence'],
                    'recommendation': 'buy_low' if diff_ratio > threshold else (
                        'sell_high' if diff_ratio < -threshold else 'hold'
                    )
                })
            except Exception as e:
                print(f"Error analyzing player {row.get('player_id')}: {e}")

        df = pd.DataFrame(results)

        if df.empty:
            return {'buy_low': pd.DataFrame(), 'sell_high': pd.DataFrame(), 'hold': pd.DataFrame()}

        return {
            'buy_low': df[df['recommendation'] == 'buy_low'].sort_values('diff_ratio', ascending=False),
            'sell_high': df[df['recommendation'] == 'sell_high'].sort_values('diff_ratio'),
            'hold': df[df['recommendation'] == 'hold'].sort_values('predicted_value', ascending=False),
        }

    def save_models(self):
        """Save trained models to disk."""
        for player_type in ['batter', 'pitcher']:
            models = self.batter_models if player_type == 'batter' else self.pitcher_models
            scaler = self.batter_scaler if player_type == 'batter' else self.pitcher_scaler
            weights = self.batter_weights if player_type == 'batter' else self.pitcher_weights

            # Save models
            for name, model in models.items():
                path = os.path.join(self.model_dir, f'{player_type}_{name}.pkl')
                with open(path, 'wb') as f:
                    pickle.dump(model, f)

            # Save scaler
            scaler_path = os.path.join(self.model_dir, f'{player_type}_scaler.pkl')
            with open(scaler_path, 'wb') as f:
                pickle.dump(scaler, f)

            # Save weights
            weights_path = os.path.join(self.model_dir, f'{player_type}_weights.json')
            with open(weights_path, 'w') as f:
                json.dump(weights, f)

        # Save training info
        info_path = os.path.join(self.model_dir, 'training_info.json')
        with open(info_path, 'w') as f:
            json.dump(self.training_info, f, indent=2, default=str)

        # Save feature lists
        features_path = os.path.join(self.model_dir, 'features.json')
        features_info = {
            'batter': getattr(self, '_batter_features_used', self.BATTER_FEATURES),
            'pitcher': getattr(self, '_pitcher_features_used', self.PITCHER_FEATURES),
        }
        with open(features_path, 'w') as f:
            json.dump(features_info, f)

        print(f"Models saved to {self.model_dir}")

    def load_models(self) -> bool:
        """Load trained models from disk."""
        try:
            for player_type in ['batter', 'pitcher']:
                models = self.batter_models if player_type == 'batter' else self.pitcher_models

                # Load models
                for name in models.keys():
                    path = os.path.join(self.model_dir, f'{player_type}_{name}.pkl')
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            models[name] = pickle.load(f)

                # Load scaler
                scaler_path = os.path.join(self.model_dir, f'{player_type}_scaler.pkl')
                if os.path.exists(scaler_path):
                    with open(scaler_path, 'rb') as f:
                        if player_type == 'batter':
                            self.batter_scaler = pickle.load(f)
                        else:
                            self.pitcher_scaler = pickle.load(f)

                # Load weights
                weights_path = os.path.join(self.model_dir, f'{player_type}_weights.json')
                if os.path.exists(weights_path):
                    with open(weights_path, 'r') as f:
                        weights = json.load(f)
                        if player_type == 'batter':
                            self.batter_weights = weights
                        else:
                            self.pitcher_weights = weights

            # Load training info
            info_path = os.path.join(self.model_dir, 'training_info.json')
            if os.path.exists(info_path):
                with open(info_path, 'r') as f:
                    self.training_info = json.load(f)

            # Load feature lists
            features_path = os.path.join(self.model_dir, 'features.json')
            if os.path.exists(features_path):
                with open(features_path, 'r') as f:
                    features_info = json.load(f)
                    self._batter_features_used = features_info.get('batter', self.BATTER_FEATURES)
                    self._pitcher_features_used = features_info.get('pitcher', self.PITCHER_FEATURES)

            print(f"Models loaded from {self.model_dir}")
            return True

        except Exception as e:
            print(f"Error loading models: {e}")
            return False

    def is_trained(self, player_type: str = 'batter') -> bool:
        """Check if model is trained."""
        return self.training_info.get(player_type, {}).get('trained', False)
