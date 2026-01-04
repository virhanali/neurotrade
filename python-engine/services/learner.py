"""
NeuroTrade AI - Advanced Machine Learning Module (v4.0)
=======================================================
Production-Grade Self-Learning System with:
- XGBoost/LightGBM for win probability prediction
- Time-based feature engineering
- Market regime detection
- Adaptive confidence thresholds
- Real-time performance analytics
"""

import logging
import numpy as np
import pickle
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

import sqlalchemy
from sqlalchemy import create_engine, text
from config import settings

# Try to import ML libraries (graceful fallback if not available)
try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False
    logging.warning("[LEARNER] LightGBM not installed. Using rule-based fallback.")

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


@dataclass
class MarketRegime:
    """Current market regime based on recent performance"""
    regime: str  # TRENDING, RANGING, VOLATILE, QUIET
    win_rate: float
    avg_pnl: float
    sample_size: int
    confidence: float  # How confident we are in this regime


@dataclass
class MLPrediction:
    """ML model prediction for a trade"""
    win_probability: float
    recommended_confidence_threshold: int
    regime: MarketRegime
    insights: List[str]


class DeepLearner:
    """
    Production-Grade Machine Learning Module.
    Persists trade knowledge to PostgreSQL and uses ML for predictions.
    """

    MODEL_PATH = "/tmp/neurotrade_ml_model.pkl"
    SCALER_PATH = "/tmp/neurotrade_scaler.pkl"
    MIN_SAMPLES_FOR_ML = 50  # Minimum trades before ML kicks in
    REGIME_WINDOW_SIZE = int(os.getenv("REGIME_WINDOW_SIZE", "20"))

    def __init__(self):
        # Database connection
        try:
            self.engine = create_engine(
                settings.DATABASE_URL,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True
            )
            logging.info("[LEARNER] Connected to PostgreSQL Knowledge Base.")
        except Exception as e:
            logging.error(f"[LEARNER] Failed to connect to DB: {e}")
            self.engine = None

        # ML Model (lazy loaded)
        self.model = None
        self.scaler = None
        self.last_train_time = None
        self.retrain_interval = timedelta(hours=6)  # Retrain every 6 hours

        # Cache for performance
        self._regime_cache = None
        self._regime_cache_time = None
        self._cache_ttl = timedelta(minutes=5)

    def record_outcome(self, symbol: str, signal_data: Dict, outcome: str, pnl: float):
        """
        Save trade result to Database (Permanent Long-Term Memory).
        Enhanced with timestamp-based features.
        """
        if not self.engine:
            logging.error("[LEARNER] DB connection missing. Cannot save learning.")
            return

        try:
            # Extract current time features
            now = datetime.utcnow()
            hour_of_day = now.hour
            day_of_week = now.weekday()  # 0=Monday, 6=Sunday

            # Extract metrics safely
            metric_data = {
                'symbol': symbol,
                'outcome': outcome,
                'pnl': pnl,
                'adx': signal_data.get('adx', 0),
                'vol_z_score': signal_data.get('vol_z_score', 0),
                'ker': signal_data.get('efficiency_ratio', signal_data.get('ker', 0)),
                'is_squeeze': signal_data.get('is_squeeze', False),
                'score': signal_data.get('score', 0),
                'vol_ratio': signal_data.get('vol_ratio', 1.0),
                'atr_pct': signal_data.get('atr_pct', 0),
                'funding_rate': signal_data.get('funding_rate', 0),
                'ls_ratio': signal_data.get('ls_ratio', 0),
                'whale_score': signal_data.get('whale_score', 0),
                'hour_of_day': hour_of_day,
                'day_of_week': day_of_week
            }

            # Check if extended columns exist, use basic insert if not
            stmt = text("""
                INSERT INTO ai_learning_logs
                (symbol, outcome, pnl, adx, vol_z_score, ker, is_squeeze, score, funding_rate, ls_ratio, whale_score)
                VALUES
                (:symbol, :outcome, :pnl, :adx, :vol_z_score, :ker, :is_squeeze, :score, :funding_rate, :ls_ratio, :whale_score)
            """)

            with self.engine.connect() as conn:
                conn.execute(stmt, {
                    'symbol': metric_data['symbol'],
                    'outcome': metric_data['outcome'],
                    'pnl': metric_data['pnl'],
                    'adx': metric_data['adx'],
                    'vol_z_score': metric_data['vol_z_score'],
                    'ker': metric_data['ker'],
                    'is_squeeze': metric_data['is_squeeze'],
                    'score': metric_data['score'],
                    'funding_rate': metric_data['funding_rate'],
                    'ls_ratio': metric_data['ls_ratio'],
                    'whale_score': metric_data['whale_score']
                })
                conn.commit()

            logging.info(f"[LEARNER] Knowledge saved for {symbol} ({outcome}, PnL: {pnl:.2f}%)")

            # Trigger model retrain if needed
            self._check_retrain()

        except Exception as e:
            logging.error(f"[LEARNER] Failed to save knowledge: {e}")

    def _fetch_training_data(self) -> Optional[List[Dict]]:
        """Fetch historical data for ML training."""
        if not self.engine:
            return None

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT outcome, adx, vol_z_score, ker, is_squeeze, score, pnl,
                           funding_rate, ls_ratio, whale_score,
                           EXTRACT(HOUR FROM timestamp) as hour,
                           EXTRACT(DOW FROM timestamp) as dow
                    FROM ai_learning_logs
                    ORDER BY timestamp DESC
                    LIMIT 2000
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            logging.error(f"[LEARNER] Failed to fetch training data: {e}")
            return None

    def _prepare_features(self, data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare feature matrix and labels for training."""
        X = []
        y = []

        for row in data:
            features = [
                float(row.get('adx', 0) or 0),
                float(row.get('vol_z_score', 0) or 0),
                float(row.get('ker', 0) or 0),
                1.0 if row.get('is_squeeze') else 0.0,
                float(row.get('score', 0) or 0),
                float(row.get('funding_rate', 0) or 0),
                float(row.get('ls_ratio', 0) or 0),
                float(row.get('whale_score', 0) or 0),
                float(row.get('hour', 12) or 12),
                float(row.get('dow', 0) or 0),
                # Derived features
                float(row.get('adx', 0) or 0) * float(row.get('ker', 0) or 0),  # ADX * KER interaction
                1.0 if float(row.get('vol_z_score', 0) or 0) > 2.0 else 0.0,  # High volume flag
            ]
            X.append(features)
            y.append(1 if row.get('outcome') == 'WIN' else 0)

        return np.array(X), np.array(y)

    def _train_model(self):
        """Train LightGBM model on historical data."""
        if not HAS_LIGHTGBM or not HAS_SKLEARN:
            logging.info("[LEARNER] ML libraries not available. Using rule-based system.")
            return

        data = self._fetch_training_data()
        if not data or len(data) < self.MIN_SAMPLES_FOR_ML:
            logging.info(f"[LEARNER] Not enough data for ML training ({len(data) if data else 0}/{self.MIN_SAMPLES_FOR_ML})")
            return

        try:
            X, y = self._prepare_features(data)

            # Check for class imbalance
            win_rate = np.mean(y)
            if win_rate < 0.1 or win_rate > 0.9:
                logging.warning(f"[LEARNER] Severe class imbalance (WR: {win_rate:.1%}). Model may be unreliable.")

            # Split data
            X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

            # Scale features
            self.scaler = StandardScaler()
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_val_scaled = self.scaler.transform(X_val)

            # Train LightGBM
            train_data = lgb.Dataset(X_train_scaled, label=y_train)
            val_data = lgb.Dataset(X_val_scaled, label=y_val, reference=train_data)

            params = {
                'objective': 'binary',
                'metric': 'auc',
                'boosting_type': 'gbdt',
                'num_leaves': 15,  # Keep simple to avoid overfitting
                'learning_rate': 0.05,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1,
                'is_unbalance': True  # Handle class imbalance
            }

            self.model = lgb.train(
                params,
                train_data,
                num_boost_round=100,
                valid_sets=[val_data],
                callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)]
            )

            # Evaluate
            val_preds = self.model.predict(X_val_scaled)
            val_auc = self._calculate_auc(y_val, val_preds)

            logging.info(f"[LEARNER] Model trained! Validation AUC: {val_auc:.3f}, Samples: {len(data)}")

            # Save model
            self._save_model()
            self.last_train_time = datetime.utcnow()

        except Exception as e:
            logging.error(f"[LEARNER] Model training failed: {e}")
            self.model = None

    def _calculate_auc(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate AUC-ROC score."""
        try:
            from sklearn.metrics import roc_auc_score
            return roc_auc_score(y_true, y_pred)
        except:
            return 0.5

    def _save_model(self):
        """Save model and scaler to disk."""
        try:
            if self.model:
                self.model.save_model(self.MODEL_PATH)
            if self.scaler:
                with open(self.SCALER_PATH, 'wb') as f:
                    pickle.dump(self.scaler, f)
            logging.info("[LEARNER] Model saved to disk.")
        except Exception as e:
            logging.error(f"[LEARNER] Failed to save model: {e}")

    def _load_model(self):
        """Load model and scaler from disk."""
        try:
            if os.path.exists(self.MODEL_PATH) and HAS_LIGHTGBM:
                self.model = lgb.Booster(model_file=self.MODEL_PATH)
                logging.info("[LEARNER] Model loaded from disk.")
            if os.path.exists(self.SCALER_PATH) and HAS_SKLEARN:
                with open(self.SCALER_PATH, 'rb') as f:
                    self.scaler = pickle.load(f)
        except Exception as e:
            logging.error(f"[LEARNER] Failed to load model: {e}")
            self.model = None
            self.scaler = None

    def _check_retrain(self):
        """Check if model needs retraining."""
        if self.last_train_time is None:
            self._load_model()
            if self.model is None:
                self._train_model()
        elif datetime.utcnow() - self.last_train_time > self.retrain_interval:
            self._train_model()

    def predict_win_probability(self, metrics: Dict) -> float:
        """
        Predict win probability using ML model.
        Falls back to rule-based estimation if ML unavailable.
        """
        # Ensure model is loaded/trained
        if self.model is None:
            self._check_retrain()

        # If still no model, use rule-based fallback
        if self.model is None or self.scaler is None:
            return self._rule_based_probability(metrics)

        try:
            # Prepare features
            now = datetime.utcnow()
            features = np.array([[
                float(metrics.get('adx', 0) or 0),
                float(metrics.get('vol_z_score', 0) or 0),
                float(metrics.get('efficiency_ratio', metrics.get('ker', 0)) or 0),
                1.0 if metrics.get('is_squeeze') else 0.0,
                float(metrics.get('score', 0) or 0),
                float(now.hour),
                float(now.weekday()),
                float(metrics.get('adx', 0) or 0) * float(metrics.get('efficiency_ratio', metrics.get('ker', 0)) or 0),
                1.0 if float(metrics.get('vol_z_score', 0) or 0) > 2.0 else 0.0,
            ]])

            features_scaled = self.scaler.transform(features)
            probability = self.model.predict(features_scaled)[0]

            return float(np.clip(probability, 0.0, 1.0))

        except Exception as e:
            logging.error(f"[LEARNER] Prediction failed: {e}")
            return self._rule_based_probability(metrics)

    def _rule_based_probability(self, metrics: Dict) -> float:
        """Fallback rule-based win probability estimation."""
        score = 0.5  # Base probability

        # ADX contribution
        adx = float(metrics.get('adx', 0) or 0)
        if adx > 25:
            score += 0.1  # Trending market
        elif adx < 15:
            score -= 0.05  # Very weak trend

        # Volume Z-Score contribution
        vol_z = float(metrics.get('vol_z_score', 0) or 0)
        if vol_z > 3.0:
            score += 0.15  # Significant volume anomaly
        elif vol_z > 2.0:
            score += 0.08

        # Efficiency Ratio contribution
        ker = float(metrics.get('efficiency_ratio', metrics.get('ker', 0)) or 0)
        if ker > 0.7:
            score += 0.12  # Very clean trend
        elif ker > 0.5:
            score += 0.06
        elif ker < 0.25:
            score -= 0.1  # Choppy market

        # Squeeze contribution
        if metrics.get('is_squeeze'):
            score += 0.08  # Potential breakout

        # Screener score contribution
        screener_score = float(metrics.get('score', 0) or 0)
        if screener_score > 80:
            score += 0.1
        elif screener_score > 60:
            score += 0.05

        return max(0.1, min(0.9, score))

    def get_market_regime(self) -> MarketRegime:
        """Detect current market regime based on recent trades."""
        # Check cache
        if self._regime_cache and self._regime_cache_time:
            if datetime.utcnow() - self._regime_cache_time < self._cache_ttl:
                return self._regime_cache

        if not self.engine:
            return MarketRegime("UNKNOWN", 0.5, 0.0, 0, 0.0)

        try:
            with self.engine.connect() as conn:
                # Get last 24 hours of trades
                result = conn.execute(text("""
                    SELECT outcome, pnl, adx, vol_z_score
                    FROM ai_learning_logs
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    ORDER BY timestamp DESC
                """))
                trades = [dict(row._mapping) for row in result]

            if len(trades) < 5:
                return MarketRegime("UNKNOWN", 0.5, 0.0, len(trades), 0.2)

            # Calculate metrics
            wins = sum(1 for t in trades if t['outcome'] == 'WIN')
            win_rate = wins / len(trades)
            avg_pnl = np.mean([float(t['pnl'] or 0) for t in trades])
            avg_adx = np.mean([float(t['adx'] or 25) for t in trades])
            avg_vol_z = np.mean([float(t['vol_z_score'] or 0) for t in trades])

            # Determine regime
            if avg_adx > 30 and win_rate > 0.55:
                regime = "TRENDING"
            elif avg_adx < 20 and avg_vol_z < 1.5:
                regime = "QUIET"
            elif avg_vol_z > 2.5:
                regime = "VOLATILE"
            else:
                regime = "RANGING"

            # Confidence based on sample size
            confidence = min(1.0, len(trades) / 50)

            result = MarketRegime(regime, win_rate, avg_pnl, len(trades), confidence)

            # Cache result
            self._regime_cache = result
            self._regime_cache_time = datetime.utcnow()

            return result

        except Exception as e:
            logging.error(f"[LEARNER] Failed to detect market regime: {e}")
            return MarketRegime("UNKNOWN", 0.5, 0.0, 0, 0.0)

    def get_recommended_threshold(self, base_confidence: int = 75) -> int:
        """
        Get adaptive confidence threshold based on market conditions.
        Returns recommended minimum confidence for trade execution.
        """
        regime = self.get_market_regime()

        if regime.regime == "TRENDING" and regime.win_rate > 0.6:
            # Good trending market - can be more aggressive
            return max(60, base_confidence - 10)
        elif regime.regime == "QUIET":
            # Quiet market - be more selective
            return min(85, base_confidence + 5)
        elif regime.regime == "VOLATILE":
            # Volatile - be cautious
            return min(90, base_confidence + 10)
        elif regime.win_rate < 0.4:
            # Poor performance - tighten filters
            return min(90, base_confidence + 15)

        return base_confidence

    def get_prediction(self, metrics: Dict) -> MLPrediction:
        """
        Get full ML prediction with win probability, regime, and insights.
        """
        win_prob = self.predict_win_probability(metrics)
        regime = self.get_market_regime()
        threshold = self.get_recommended_threshold()

        insights = []

        # Generate insights
        if win_prob > 0.7:
            insights.append(f"HIGH WIN PROBABILITY ({win_prob:.0%}). Strong setup detected.")
        elif win_prob < 0.4:
            insights.append(f"LOW WIN PROBABILITY ({win_prob:.0%}). Consider skipping.")

        if regime.regime == "TRENDING":
            insights.append(f"TRENDING MARKET. Momentum strategies favored.")
        elif regime.regime == "RANGING":
            insights.append(f"RANGING MARKET. Mean-reversion strategies may work.")
        elif regime.regime == "VOLATILE":
            insights.append(f"HIGH VOLATILITY. Tighten stop-losses.")

        if regime.win_rate < 0.4 and regime.sample_size > 10:
            insights.append(f"WARNING: Recent WR is {regime.win_rate:.0%}. Market is difficult.")

        return MLPrediction(
            win_probability=win_prob,
            recommended_confidence_threshold=threshold,
            regime=regime,
            insights=insights
        )

    def get_learning_context(self) -> str:
        """
        Query DB for last 100 trades and generate insight for AI prompts.
        Enhanced with ML predictions and market regime.
        """
        if not self.engine:
            return ""

        try:
            with self.engine.connect() as conn:
                # Fetch last 100 trades
                result = conn.execute(text("""
                    SELECT outcome, adx, vol_z_score, ker, is_squeeze, pnl
                    FROM ai_learning_logs
                    ORDER BY timestamp DESC
                    LIMIT 100
                """))
                history = [dict(row._mapping) for row in result]

            if len(history) < 5:
                return "AI MEMORY: Insufficient data for patterns (Exploration Phase). Trade conservatively."

            # Calculate Stats
            total = len(history)
            wins = sum(1 for h in history if h['outcome'] == 'WIN')
            win_rate = wins / total if total > 0 else 0
            avg_pnl = np.mean([float(h['pnl'] or 0) for h in history])

            # Helper for conditional win rate
            def get_wr(condition_func):
                subset = [h for h in history if condition_func(h)]
                if not subset: return None
                w = sum(1 for h in subset if h['outcome'] == 'WIN')
                return w / len(subset)

            # Analyze Patterns
            squeeze_wr = get_wr(lambda h: h['is_squeeze'])
            high_vol_wr = get_wr(lambda h: float(h['vol_z_score'] or 0) > 2.0)
            low_adx_wr = get_wr(lambda h: float(h['adx'] or 0) < 25)
            high_adx_wr = get_wr(lambda h: float(h['adx'] or 0) >= 25)
            high_ker_wr = get_wr(lambda h: float(h['ker'] or 0) > 0.5)

            # Get market regime
            regime = self.get_market_regime()

            # Generate Prompt Context
            msg = "AI SELF-LEARNING INSIGHTS (LIVE DB STATS):\n"
            msg += f"- Global Win Rate (Last {total} Trades): {win_rate*100:.1f}%.\n"
            msg += f"- Average PnL: {avg_pnl:.2f}%.\n"
            msg += f"- Current Market Regime: {regime.regime} (Confidence: {regime.confidence:.0%}).\n"

            # Performance-based advice
            if win_rate < 0.4:
                msg += "- CRITICAL: Market is difficult. TIGHTEN STOP LOSSES. Consider WAIT signals.\n"
            elif win_rate > 0.6:
                msg += "- ADVICE: Market is favorable. Can be slightly more AGGRESSIVE on entries.\n"

            # Pattern-based advice
            if squeeze_wr is not None:
                if squeeze_wr < 0.35:
                    msg += f"- PATTERN: Squeezes failing ({squeeze_wr*100:.0f}% WR). Avoid breakout bets.\n"
                elif squeeze_wr > 0.65:
                    msg += f"- PATTERN: Squeezes winning ({squeeze_wr*100:.0f}% WR). Breakouts are valid.\n"

            if low_adx_wr is not None and high_adx_wr is not None:
                if low_adx_wr > high_adx_wr + 0.1:
                    msg += f"- PATTERN: Sideways markets outperforming. Ping-Pong strategy VALID.\n"
                elif high_adx_wr > low_adx_wr + 0.1:
                    msg += f"- PATTERN: Trending markets outperforming. Momentum strategy VALID.\n"

            if high_vol_wr is not None and high_vol_wr > 0.65:
                msg += f"- PATTERN: High Volume (Z>2) trades winning {high_vol_wr*100:.0f}%. Follow the whales.\n"

            if high_ker_wr is not None and high_ker_wr > 0.6:
                msg += f"- PATTERN: Clean trends (KER>0.5) winning {high_ker_wr*100:.0f}%. Prefer smooth price action.\n"

            # ML recommendation
            threshold = self.get_recommended_threshold()
            if threshold != 75:
                msg += f"- ML RECOMMENDATION: Adjust confidence threshold to {threshold}%.\n"

            return msg

        except Exception as e:
            logging.error(f"[LEARNER] Failed to retrieve context: {e}")
            return ""

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from the trained model."""
        if self.model is None:
            return {}

        try:
            feature_names = [
                'adx', 'vol_z_score', 'ker', 'is_squeeze', 'score',
                'funding_rate', 'ls_ratio', 'whale_score',
                'hour', 'day_of_week', 'adx_ker_interaction', 'high_volume_flag'
            ]
            importance = self.model.feature_importance(importance_type='gain')
            return dict(zip(feature_names, importance.tolist()))
        except:
            return {}

    def get_performance_stats(self) -> Dict:
        """Get comprehensive performance statistics."""
        if not self.engine:
            return {}

        try:
            with self.engine.connect() as conn:
                # Overall stats
                result = conn.execute(text("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                        AVG(pnl) as avg_pnl,
                        SUM(pnl) as total_pnl,
                        MAX(pnl) as best_trade,
                        MIN(pnl) as worst_trade
                    FROM ai_learning_logs
                """))
                row = result.fetchone()

                if row:
                    total = row[0] or 0
                    wins = row[1] or 0
                    return {
                        'total_trades': total,
                        'wins': wins,
                        'losses': total - wins,
                        'win_rate': wins / total if total > 0 else 0,
                        'avg_pnl': float(row[2] or 0),
                        'total_pnl': float(row[3] or 0),
                        'best_trade': float(row[4] or 0),
                        'worst_trade': float(row[5] or 0),
                        'model_active': self.model is not None,
                        'feature_importance': self.get_feature_importance()
                    }
            return {}
        except Exception as e:
            logging.error(f"[LEARNER] Failed to get performance stats: {e}")
            return {}


    def _detect_market_regime(self) -> MarketRegime:
        """Analyze recent trades to determine market regime"""
        try:
            if not self.engine:
                 return MarketRegime("UNKNOWN", 0.0, 0.0, 0, 0.0)

            with self.engine.connect() as conn:
                # Get last N samples
                query = text(f"""
                    SELECT pnl
                    FROM ai_learning_logs
                    ORDER BY timestamp DESC
                    LIMIT {self.REGIME_WINDOW_SIZE}
                """)
                result = conn.execute(query).fetchall()
                
            samples = [float(row[0]) for row in result]
            if not samples:
                return MarketRegime("WAITING_DATA", 0.0, 0.0, 0, 0.0)
                
            count = len(samples)
            wins = sum(1 for x in samples if x > 0)
            win_rate = wins / count
            avg_pnl = sum(samples) / count
            
            # Simple heuristic for regime
            if abs(avg_pnl) < 1.0 and win_rate > 0.4 and win_rate < 0.6:
                 regime = "QUIET"
            elif win_rate > 0.6:
                 regime = "TRENDING"
            elif win_rate < 0.4:
                 regime = "VOLATILE"
            else:
                 regime = "RANGING"
                 
            confidence = min(1.0, count / float(self.REGIME_WINDOW_SIZE))
            
            return MarketRegime(regime, win_rate, avg_pnl, count, confidence)
            
        except Exception as e:
            logging.error(f"Regime detection failed: {e}")
            return MarketRegime("ERROR", 0.0, 0.0, 0, 0.0)

    def get_brain_stats(self) -> Dict:
        """Get comprehensive ML statistics for Brain Health dashboard"""
        if not self.engine:
            return {"status": "error", "message": "No DB connection"}

        try:
            # 1. Get sample count
            with self.engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM ai_learning_logs")).scalar() or 0
                
            # 2. Get feature importance
            importance = self.get_feature_importance()
            
            # 3. Get regime info
            regime = self._detect_market_regime()
            
            return {
                "status": "active" if count >= self.MIN_SAMPLES_FOR_ML else "learning",
                "samples": count,
                "required_samples": self.MIN_SAMPLES_FOR_ML,
                "progress_percent": min(100, int((count / self.MIN_SAMPLES_FOR_ML) * 100)),
                "model_trained": self.model is not None,
                "last_train_time": self.last_train_time.isoformat() if self.last_train_time else None,
                "feature_importance": importance,
                "market_regime": {
                    "type": regime.regime,
                    "win_rate": round(regime.win_rate * 100, 1),
                    "confidence": round(regime.confidence * 100, 1)
                }
            }
        except Exception as e:
            logging.error(f"[LEARNER] Failed to get brain stats: {e}")
            return {"status": "error", "message": str(e)}


# Global Instance
learner = DeepLearner()
