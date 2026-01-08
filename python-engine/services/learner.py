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
import json
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

    def cache_analysis(self, analysis: Dict):
        """
        Save AI analysis results to cache table BEFORE trade decision.
        This ensures we don't waste API credits and can learn from non-traded signals.
        """
        if not self.engine:
            logging.error("[LEARNER] DB connection missing. Cannot cache analysis.")
            return

        try:
            now = datetime.utcnow()

            stmt = text("""
                INSERT INTO ai_analysis_cache
                (symbol, logic_signal, logic_confidence, logic_reasoning,
                 vision_signal, vision_confidence, vision_reasoning,
                 ml_win_probability, ml_threshold, ml_is_trained, ml_insights,
                 final_signal, final_confidence, recommendation,
                 adx, vol_z_score, ker, is_squeeze, screener_score,
                 whale_signal, whale_confidence,
                 hour_of_day, day_of_week,
                 btc_trend)
                VALUES
                (:symbol, :logic_signal, :logic_confidence, :logic_reasoning,
                 :vision_signal, :vision_confidence, :vision_reasoning,
                 :ml_win_prob, :ml_threshold, :ml_is_trained, :ml_insights,
                 :final_signal, :final_confidence, :recommendation,
                 :adx, :vol_z_score, :ker, :is_squeeze, :score,
                 :whale_signal, :whale_confidence,
                 :hour, :dow, :btc_trend)
                ON CONFLICT (symbol, created_at) DO NOTHING
            """)

            with self.engine.connect() as conn:
                conn.execute(stmt, {
                    'symbol': analysis.get('symbol'),
                    'logic_signal': analysis.get('logic_signal'),
                    'logic_confidence': analysis.get('logic_confidence'),
                    'logic_reasoning': analysis.get('logic_reasoning'),
                    'vision_signal': analysis.get('vision_signal'),
                    'vision_confidence': analysis.get('vision_confidence'),
                    'vision_reasoning': analysis.get('vision_reasoning'),
                    'ml_win_prob': analysis.get('ml_win_probability'),
                    'ml_threshold': analysis.get('ml_threshold'),
                    'ml_is_trained': analysis.get('ml_is_trained', False),
                    'ml_insights': json.dumps(analysis.get('ml_insights', [])),
                    'final_signal': analysis.get('final_signal'),
                    'final_confidence': analysis.get('final_confidence'),
                    'recommendation': analysis.get('recommendation'),
                    'adx': analysis.get('adx'),
                    'vol_z_score': analysis.get('vol_z_score'),
                    'ker': analysis.get('ker'),
                    'is_squeeze': analysis.get('is_squeeze'),
                    'score': analysis.get('screener_score'),
                    'whale_signal': analysis.get('whale_signal'),
                    'whale_confidence': analysis.get('whale_confidence'),
                    'hour': now.hour,
                    'dow': now.weekday(),
                    'btc_trend': analysis.get('btc_trend', 'UNKNOWN')
                })
                conn.commit()

            logging.info(f"[CACHE] Analysis cached for {analysis.get('symbol')} (Signal: {analysis.get('final_signal')}, Conf: {analysis.get('final_confidence')}%)")

        except Exception as e:
            logging.error(f"[LEARNER] Failed to cache analysis: {e}")

    def record_outcome(self, symbol: str, signal_data: Dict, outcome: str, pnl: float):
        """
        Save trade result to Database (Permanent Long-Term Memory).
        Also update ai_analysis_cache with outcome.
        """
        if not self.engine:
            logging.error("[LEARNER] DB connection missing. Cannot save learning.")
            return

        try:
            now = datetime.utcnow()
            hour_of_day = now.hour
            day_of_week = now.weekday()

            # 1. Save to ai_learning_logs (legacy, for ML training)
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

            # 2. Update ai_analysis_cache with outcome (link analysis to result)
            # Find most recent analysis for this symbol and update outcome
            # PostgreSQL doesn't support ORDER BY + LIMIT in UPDATE, use subquery
            stmt_update = text("""
                UPDATE ai_analysis_cache
                SET outcome = :outcome, pnl = :pnl
                WHERE id = (
                    SELECT id FROM ai_analysis_cache
                    WHERE symbol = :symbol AND outcome IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                )
            """)

            with self.engine.connect() as conn:
                result = conn.execute(stmt_update, {
                    'symbol': symbol,
                    'outcome': outcome,
                    'pnl': pnl
                })
                conn.commit()

                if result.rowcount > 0:
                    logging.info(f"[LEARNER] Cached analysis updated for {symbol} with outcome {outcome}")

            # Trigger model retrain if needed
            self._check_retrain()

        except Exception as e:
            logging.error(f"[LEARNER] Failed to save knowledge: {e}")

    def _fetch_training_data(self) -> Optional[List[Dict]]:
        """
        Fetch historical data for ML training.
        Uses ai_learning_logs as primary source (most compatible).
        """
        if not self.engine:
            return None

        try:
            with self.engine.connect() as conn:
                # Use EXTRACT from timestamp for hour/day - always works
                result = conn.execute(text("""
                    SELECT outcome, 
                           COALESCE(adx, 0) as adx, 
                           COALESCE(vol_z_score, 0) as vol_z_score, 
                           COALESCE(ker, 0) as ker, 
                           COALESCE(is_squeeze, false) as is_squeeze, 
                           COALESCE(score, 0) as score,
                           COALESCE(pnl, 0) as pnl,
                           EXTRACT(HOUR FROM timestamp)::int as hour_of_day,
                           EXTRACT(DOW FROM timestamp)::int as day_of_week
                    FROM ai_learning_logs
                    WHERE outcome IN ('WIN', 'LOSS')
                    ORDER BY timestamp DESC
                    LIMIT 1000
                """))

                data = []
                for row in result:
                    data.append({
                        'outcome': row[0],
                        'adx': float(row[1] or 0),
                        'vol_z_score': float(row[2] or 0),
                        'ker': float(row[3] or 0),
                        'is_squeeze': bool(row[4]),
                        'score': float(row[5] or 0),
                        'pnl': float(row[6] or 0),
                        'hour': float(row[7] or 12),
                        'dow': float(row[8] or 0),
                        # Default values for optional columns
                        'funding_rate': 0.0,
                        'ls_ratio': 1.0,
                        'whale_score': 50.0,
                    })

                logging.info(f"[LEARNER] Fetched {len(data)} training samples from ai_learning_logs")
                return data

        except Exception as e:
            logging.error(f"[LEARNER] Failed to fetch training data: {e}")
            return None

    def _fetch_enhanced_training_data(self) -> Optional[List[Dict]]:
        """
        Fetch training data from ai_analysis_cache (enhanced features).
        Falls back to ai_learning_logs if cache doesn't have enough data.
        """
        if not self.engine:
            return None

        try:
            with self.engine.connect() as conn:
                # Try ai_analysis_cache first (more features)
                result = conn.execute(text("""
                    SELECT 
                        outcome,
                        COALESCE(adx, 0) as adx,
                        COALESCE(vol_z_score, 0) as vol_z_score,
                        COALESCE(ker, 0) as ker,
                        COALESCE(is_squeeze, false) as is_squeeze,
                        COALESCE(screener_score, 0) as score,
                        COALESCE(pnl, 0) as pnl,
                        -- Enhanced AI features
                        COALESCE(logic_confidence, 0) as logic_confidence,
                        COALESCE(vision_confidence, 0) as vision_confidence,
                        COALESCE(final_confidence, 0) as final_confidence,
                        COALESCE(ml_win_probability, 0.5) as ml_prob,
                        CASE WHEN logic_signal = vision_signal THEN 1 ELSE 0 END as ai_agreement,
                        -- Whale features
                        COALESCE(whale_confidence, 0) as whale_confidence,
                        CASE WHEN whale_signal IN ('PUMP_IMMINENT', 'DUMP_IMMINENT') THEN 1 ELSE 0 END as whale_active,
                        -- Time features
                        COALESCE(hour_of_day, 12) as hour,
                        COALESCE(day_of_week, 0) as dow
                    FROM ai_analysis_cache
                    WHERE outcome IN ('WIN', 'LOSS')
                    ORDER BY created_at DESC
                    LIMIT 1000
                """))

                data = []
                for row in result:
                    data.append({
                        'outcome': row[0],
                        'adx': float(row[1] or 0),
                        'vol_z_score': float(row[2] or 0),
                        'ker': float(row[3] or 0),
                        'is_squeeze': bool(row[4]),
                        'score': float(row[5] or 0),
                        'pnl': float(row[6] or 0),
                        # Enhanced features
                        'logic_confidence': float(row[7] or 0),
                        'vision_confidence': float(row[8] or 0),
                        'final_confidence': float(row[9] or 0),
                        'ml_prob': float(row[10] or 0.5),
                        'ai_agreement': int(row[11] or 0),
                        'whale_confidence': float(row[12] or 0),
                        'whale_active': int(row[13] or 0),
                        'hour': float(row[14] or 12),
                        'dow': float(row[15] or 0),
                    })

                if len(data) >= self.MIN_SAMPLES_FOR_ML:
                    logging.info(f"[LEARNER] Fetched {len(data)} enhanced samples from ai_analysis_cache")
                    return data
                else:
                    logging.info(f"[LEARNER] Cache has {len(data)} samples, falling back to ai_learning_logs")
                    return self._fetch_training_data()

        except Exception as e:
            logging.warning(f"[LEARNER] Enhanced fetch failed, using fallback: {e}")
            return self._fetch_training_data()

    def _prepare_features(self, data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare feature matrix and labels for training (enhanced version)."""
        X = []
        y = []

        for row in data:
            # Base features (from screener)
            adx = float(row.get('adx', 0) or 0)
            vol_z = float(row.get('vol_z_score', 0) or 0)
            ker = float(row.get('ker', 0) or 0)
            score = float(row.get('score', 0) or 0)
            
            # AI confidence features (from cache)
            logic_conf = float(row.get('logic_confidence', 0) or 0)
            vision_conf = float(row.get('vision_confidence', 0) or 0)
            final_conf = float(row.get('final_confidence', 0) or 0)
            ai_agreement = float(row.get('ai_agreement', 0) or 0)
            
            # Whale features
            whale_conf = float(row.get('whale_confidence', 0) or 0)
            whale_active = float(row.get('whale_active', 0) or 0)
            
            features = [
                # Core screener metrics
                adx,
                vol_z,
                ker,
                1.0 if row.get('is_squeeze') else 0.0,
                score,
                # AI confidence metrics
                logic_conf,
                vision_conf,
                final_conf,
                ai_agreement,
                # Whale metrics
                whale_conf,
                whale_active,
                # Time features
                float(row.get('hour', 12) or 12),
                float(row.get('dow', 0) or 0),
                # Derived features
                adx * ker,  # ADX * KER interaction
                1.0 if vol_z > 2.0 else 0.0,  # High volume flag
                logic_conf * vision_conf / 10000.0,  # AI agreement strength
                1.0 if final_conf >= 80 else 0.0,  # High confidence flag
                whale_active * whale_conf / 100.0,  # Whale signal strength
            ]
            X.append(features)
            y.append(1 if row.get('outcome') == 'WIN' else 0)

        return np.array(X), np.array(y)

    def _train_model(self):
        """Train LightGBM model on historical data (enhanced version)."""
        if not HAS_LIGHTGBM or not HAS_SKLEARN:
            logging.info("[LEARNER] ML libraries not available. Using rule-based system.")
            return

        # Try enhanced data first, fallback to basic
        data = self._fetch_enhanced_training_data()
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
                return ""  # No message = AI not restricted

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

            # ENHANCED: Get insights from ai_analysis_cache
            try:
                with self.engine.connect() as conn:
                    # AI Agreement win rate
                    agreement_result = conn.execute(text("""
                        SELECT 
                            COUNT(*) as total,
                            SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                        FROM ai_analysis_cache
                        WHERE outcome IS NOT NULL
                        AND logic_signal = vision_signal
                    """)).fetchone()
                    
                    if agreement_result and agreement_result[0] > 10:
                        agreement_wr = agreement_result[1] / agreement_result[0]
                        if agreement_wr > 0.6:
                            msg += f"- AI INSIGHT: When Logic+Vision AGREE, WR is {agreement_wr*100:.0f}%. Trust agreement.\n"
                        elif agreement_wr < 0.4:
                            msg += f"- AI INSIGHT: Agreement signals underperforming ({agreement_wr*100:.0f}% WR). Be cautious.\n"
                    
                    # High confidence win rate
                    high_conf_result = conn.execute(text("""
                        SELECT 
                            COUNT(*) as total,
                            SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                        FROM ai_analysis_cache
                        WHERE outcome IS NOT NULL
                        AND final_confidence >= 80
                    """)).fetchone()
                    
                    if high_conf_result and high_conf_result[0] > 5:
                        high_conf_wr = high_conf_result[1] / high_conf_result[0]
                        if high_conf_wr > 0.65:
                            msg += f"- AI INSIGHT: High confidence (80%+) signals winning {high_conf_wr*100:.0f}%. Confidence is calibrated.\n"
                        elif high_conf_wr < 0.5:
                            msg += f"- AI INSIGHT: High confidence signals failing ({high_conf_wr*100:.0f}% WR). AI overconfident.\n"
                    
                    # Whale signal effectiveness
                    whale_result = conn.execute(text("""
                        SELECT 
                            COUNT(*) as total,
                            SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                        FROM ai_analysis_cache
                        WHERE outcome IS NOT NULL
                        AND whale_signal IN ('PUMP_IMMINENT', 'DUMP_IMMINENT')
                    """)).fetchone()
                    
                    if whale_result and whale_result[0] > 5:
                        whale_wr = whale_result[1] / whale_result[0]
                        if whale_wr > 0.6:
                            msg += f"- WHALE INSIGHT: PUMP/DUMP signals winning {whale_wr*100:.0f}%. Whale detection is effective.\n"
                        elif whale_wr < 0.45:
                            msg += f"- WHALE INSIGHT: Whale signals underperforming ({whale_wr*100:.0f}% WR). May need recalibration.\n"
                            
            except Exception as e:
                logging.debug(f"[LEARNER] Enhanced insights failed: {e}")

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
                # Core metrics
                'adx', 'vol_z_score', 'ker', 'is_squeeze', 'score',
                # AI confidence metrics
                'logic_confidence', 'vision_confidence', 'final_confidence', 'ai_agreement',
                # Whale metrics
                'whale_confidence', 'whale_active',
                # Time features
                'hour', 'day_of_week',
                # Derived features
                'adx_ker_interaction', 'high_volume_flag', 
                'ai_agreement_strength', 'high_confidence_flag', 'whale_signal_strength'
            ]
            importance = self.model.feature_importance(importance_type='gain')
            # Handle mismatch between features and importance
            if len(importance) != len(feature_names):
                return {f"feature_{i}": float(v) for i, v in enumerate(importance)}
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
