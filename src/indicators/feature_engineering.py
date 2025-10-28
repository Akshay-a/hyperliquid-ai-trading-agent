"""
Feature Engineering for AI Trading Agent

Philosophy (Jim Simons style):
1. Features, not raw data - compress information into actionable signals
2. Statistical rigor - all features should be backtestable
3. Fast computation - <500ms for all features
4. Interpretable - each feature has clear trading meaning
5. Regime-aware - features adapt to market conditions

This module replaces the verbose context with compressed, high-quality features.
"""

from typing import Dict, List, Optional
import statistics
import math
from datetime import datetime, timezone


class FeatureEngineer:
    """
    Compresses raw market data into 15-20 high-quality features for LLM decision-making.

    Replaces 500+ data points with statistically significant, interpretable features.
    """

    def __init__(self):
        self.feature_history = {}  # For percentile calculations

    def extract_features(
        self,
        asset: str,
        current_price: float,
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_4h: List[Dict],
        orderbook: Optional[Dict] = None,
        funding_rate: Optional[float] = None,
        open_interest: Optional[float] = None
    ) -> Dict:
        """
        Extract compressed feature set from raw market data.

        Returns 15-20 features instead of 500+ raw data points.

        Args:
            asset: Symbol
            current_price: Latest mid price
            candles_5m: Last 50 5-minute candles
            candles_1h: Last 50 1-hour candles
            candles_4h: Last 50 4-hour candles
            orderbook: Optional L2 snapshot
            funding_rate: Optional perpetual funding rate
            open_interest: Optional open interest

        Returns:
            Dictionary of compressed features ready for LLM consumption
        """
        features = {
            "symbol": asset,
            "price": round(current_price, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Trend features (4 features)
        features["trend"] = self._extract_trend_features(
            candles_5m, candles_1h, candles_4h, current_price
        )

        # Momentum features (3 features)
        features["momentum"] = self._extract_momentum_features(candles_5m, candles_1h)

        # Volatility features (3 features)
        features["volatility"] = self._extract_volatility_features(
            asset, candles_5m, candles_4h
        )

        # Mean reversion features (3 features)
        features["mean_reversion"] = self._extract_mean_reversion_features(
            current_price, candles_5m
        )

        # Microstructure features (3 features)
        features["microstructure"] = self._extract_microstructure_features(
            candles_5m, orderbook
        )

        # Position guidance (computed levels)
        features["levels"] = self._compute_actionable_levels(
            current_price, candles_5m, candles_4h, orderbook
        )

        # Perpetual-specific (if applicable)
        if funding_rate is not None:
            features["funding"] = {
                "rate": round(funding_rate, 8),
                "annualized_pct": round(funding_rate * 24 * 365 * 100, 2),
                "pressure": self._interpret_funding(funding_rate)
            }

        return features

    def _extract_trend_features(
        self,
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_4h: List[Dict],
        current_price: float
    ) -> Dict:
        """
        Trend features (4 total):
        - strength_5m, strength_1h, strength_4h: -1 to +1 (based on EMA alignment)
        - consistency: 0 to 1 (what % of recent bars aligned with trend)
        """

        def calculate_trend_strength(candles: List[Dict], current: float) -> float:
            """Calculate trend strength from EMA relationship."""
            if len(candles) < 50:
                return 0.0

            closes = [c['close'] for c in candles]

            # EMA calculation
            ema_20 = self._ema(closes, 20)
            ema_50 = self._ema(closes, 50)

            if ema_20 is None or ema_50 is None:
                return 0.0

            # Normalize to -1 to +1
            spread = (ema_20 - ema_50) / current
            # Clamp to reasonable range (±2%)
            strength = max(-1.0, min(1.0, spread * 50))

            return round(strength, 3)

        def calculate_consistency(candles: List[Dict]) -> float:
            """Calculate what % of recent bars are aligned with trend."""
            if len(candles) < 20:
                return 0.5

            recent = candles[-20:]
            bullish_bars = sum(1 for c in recent if c['close'] > c['open'])

            return round(bullish_bars / len(recent), 3)

        return {
            "strength_5m": calculate_trend_strength(candles_5m, current_price),
            "strength_1h": calculate_trend_strength(candles_1h, current_price),
            "strength_4h": calculate_trend_strength(candles_4h, current_price),
            "consistency": calculate_consistency(candles_5m)
        }

    def _extract_momentum_features(
        self,
        candles_5m: List[Dict],
        candles_1h: List[Dict]
    ) -> Dict:
        """
        Momentum features (3 total):
        - rsi_percentile: 0-100 (where is current RSI vs recent RSI range)
        - macd_regime: -1/0/1 (bearish/neutral/bullish)
        - acceleration: -1 to +1 (is momentum increasing or decreasing)
        """

        def calculate_rsi_percentile(candles: List[Dict]) -> Optional[int]:
            """RSI percentile vs last 50 bars (more robust than absolute RSI)."""
            if len(candles) < 30:
                return None

            closes = [c['close'] for c in candles]

            # Calculate RSI
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas]
            losses = [-d if d < 0 else 0 for d in deltas]

            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14

            if avg_loss == 0:
                current_rsi = 100
            else:
                rs = avg_gain / avg_loss
                current_rsi = 100 - (100 / (1 + rs))

            # Get historical RSI values
            historical_rsi = []
            for i in range(14, len(closes)):
                period_gains = [gains[j] for j in range(i-14, i)]
                period_losses = [losses[j] for j in range(i-14, i)]
                ag = sum(period_gains) / 14
                al = sum(period_losses) / 14
                if al == 0:
                    historical_rsi.append(100)
                else:
                    rs_hist = ag / al
                    historical_rsi.append(100 - (100 / (1 + rs_hist)))

            # Percentile
            below = sum(1 for rsi in historical_rsi if rsi < current_rsi)
            percentile = int((below / len(historical_rsi)) * 100) if historical_rsi else 50

            return percentile

        def calculate_macd_regime(candles: List[Dict]) -> int:
            """MACD histogram state: -1 (bearish), 0 (neutral), 1 (bullish)."""
            if len(candles) < 26:
                return 0

            closes = [c['close'] for c in candles]
            ema_12 = self._ema(closes, 12)
            ema_26 = self._ema(closes, 26)

            if ema_12 is None or ema_26 is None:
                return 0

            macd_line = ema_12 - ema_26

            # Simple regime classification
            if macd_line > 0.002 * closes[-1]:  # >0.2% of price
                return 1
            elif macd_line < -0.002 * closes[-1]:
                return -1
            else:
                return 0

        def calculate_acceleration(candles: List[Dict]) -> float:
            """Is momentum accelerating or decelerating?"""
            if len(candles) < 10:
                return 0.0

            closes = [c['close'] for c in candles[-10:]]

            # Compare recent rate of change
            roc_recent = (closes[-1] - closes[-3]) / closes[-3]
            roc_older = (closes[-4] - closes[-6]) / closes[-6]

            if abs(roc_older) < 0.0001:  # Avoid division by zero
                return 0.0

            acceleration = (roc_recent - roc_older) / abs(roc_older)

            # Clamp to -1 to +1
            return round(max(-1.0, min(1.0, acceleration)), 3)

        return {
            "rsi_percentile": calculate_rsi_percentile(candles_5m),
            "macd_regime": calculate_macd_regime(candles_5m),
            "acceleration": calculate_acceleration(candles_5m)
        }

    def _extract_volatility_features(
        self,
        asset: str,
        candles_5m: List[Dict],
        candles_4h: List[Dict]
    ) -> Dict:
        """
        Volatility features (3 total):
        - atr_percentile: 0-100 (current ATR vs historical)
        - regime: low/medium/high
        - realized_vol: actual price movement (standard deviation)
        """

        def calculate_atr_percentile(candles: List[Dict]) -> Optional[int]:
            """ATR percentile vs last 50 bars."""
            if len(candles) < 20:
                return None

            atrs = []
            for i in range(1, len(candles)):
                high_low = candles[i]['high'] - candles[i]['low']
                high_close = abs(candles[i]['high'] - candles[i-1]['close'])
                low_close = abs(candles[i]['low'] - candles[i-1]['close'])
                true_range = max(high_low, high_close, low_close)
                atrs.append(true_range)

            if len(atrs) < 14:
                return None

            # Rolling ATR (14-period average)
            atr_values = []
            for i in range(13, len(atrs)):
                atr_values.append(sum(atrs[i-13:i+1]) / 14)

            current_atr = atr_values[-1]

            # Percentile
            below = sum(1 for atr in atr_values if atr < current_atr)
            percentile = int((below / len(atr_values)) * 100) if atr_values else 50

            # Store for history
            key = f"{asset}_atr"
            if key not in self.feature_history:
                self.feature_history[key] = []
            self.feature_history[key].append(current_atr)
            if len(self.feature_history[key]) > 100:
                self.feature_history[key].pop(0)

            return percentile

        def classify_regime(percentile: Optional[int]) -> str:
            """Classify volatility regime."""
            if percentile is None:
                return "medium"
            if percentile < 30:
                return "low"
            elif percentile > 70:
                return "high"
            else:
                return "medium"

        def calculate_realized_vol(candles: List[Dict]) -> float:
            """Standard deviation of returns."""
            if len(candles) < 10:
                return 0.0

            closes = [c['close'] for c in candles[-10:]]
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

            if not returns:
                return 0.0

            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance)

            return round(std_dev, 6)

        atr_perc = calculate_atr_percentile(candles_5m)

        return {
            "atr_percentile": atr_perc,
            "regime": classify_regime(atr_perc),
            "realized_vol": calculate_realized_vol(candles_5m)
        }

    def _extract_mean_reversion_features(
        self,
        current_price: float,
        candles_5m: List[Dict]
    ) -> Dict:
        """
        Mean reversion features (3 total):
        - distance_from_ema20: -1 to +1 (how far from EMA20)
        - bb_position: 0 to 1 (position within Bollinger Bands)
        - recent_extreme: boolean (was price at extreme in last N bars)
        """

        if len(candles_5m) < 30:
            return {
                "distance_from_ema20": 0.0,
                "bb_position": 0.5,
                "recent_extreme": False
            }

        closes = [c['close'] for c in candles_5m]

        # EMA20
        ema_20 = self._ema(closes, 20)
        if ema_20:
            distance = (current_price - ema_20) / ema_20
            # Normalize to -1 to +1 (±2% is considered extreme)
            distance_norm = max(-1.0, min(1.0, distance * 50))
        else:
            distance_norm = 0.0

        # Bollinger Bands position
        sma_20 = sum(closes[-20:]) / 20
        std_dev = math.sqrt(sum((c - sma_20) ** 2 for c in closes[-20:]) / 20)
        bb_upper = sma_20 + (2 * std_dev)
        bb_lower = sma_20 - (2 * std_dev)

        if bb_upper > bb_lower:
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
            bb_position = max(0.0, min(1.0, bb_position))
        else:
            bb_position = 0.5

        # Recent extreme (price touched upper/lower BB in last 5 bars)
        recent_highs = [c['high'] for c in candles_5m[-5:]]
        recent_lows = [c['low'] for c in candles_5m[-5:]]

        touched_upper = any(h >= bb_upper * 0.995 for h in recent_highs)
        touched_lower = any(l <= bb_lower * 1.005 for l in recent_lows)
        recent_extreme = touched_upper or touched_lower

        return {
            "distance_from_ema20": round(distance_norm, 3),
            "bb_position": round(bb_position, 3),
            "recent_extreme": recent_extreme
        }

    def _extract_microstructure_features(
        self,
        candles_5m: List[Dict],
        orderbook: Optional[Dict]
    ) -> Dict:
        """
        Microstructure features (3 total):
        - spread_regime: tight/normal/wide (for execution quality)
        - volume_surprise: -1 to +1 (current volume vs average)
        - pressure: -1 to +1 (simplified orderbook pressure if available)

        Note: Orderbook pressure is for EXECUTION timing, not directional prediction.
        """

        # Volume surprise
        if len(candles_5m) >= 20:
            recent_vols = [c['volume'] for c in candles_5m[-20:]]
            avg_vol = sum(recent_vols) / len(recent_vols)
            current_vol = candles_5m[-1]['volume']

            if avg_vol > 0:
                surprise = (current_vol - avg_vol) / avg_vol
                volume_surprise = max(-1.0, min(1.0, surprise))
            else:
                volume_surprise = 0.0
        else:
            volume_surprise = 0.0

        # Spread regime (from orderbook if available)
        if orderbook and 'spread_bps' in orderbook:
            spread_bps = orderbook['spread_bps']
            if spread_bps < 3:
                spread_regime = "tight"
            elif spread_bps < 10:
                spread_regime = "normal"
            else:
                spread_regime = "wide"
        else:
            spread_regime = "unknown"

        # Orderbook pressure (simplified - for execution, not direction)
        if orderbook and 'imbalance_ratio' in orderbook:
            imbalance = orderbook['imbalance_ratio']
            # Normalize to -1 to +1
            # imbalance > 2 = strong buy pressure
            # imbalance < 0.5 = strong sell pressure
            if imbalance > 1:
                pressure = min(1.0, (imbalance - 1) / 2)
            else:
                pressure = max(-1.0, (imbalance - 1) * 2)
        else:
            pressure = 0.0

        return {
            "spread_regime": spread_regime,
            "volume_surprise": round(volume_surprise, 3),
            "pressure": round(pressure, 3)  # Use for entry timing, not direction
        }

    def _compute_actionable_levels(
        self,
        current_price: float,
        candles_5m: List[Dict],
        candles_4h: List[Dict],
        orderbook: Optional[Dict]
    ) -> Dict:
        """
        Compute suggested stop-loss and take-profit levels based on:
        - ATR-based stops
        - Recent swing highs/lows
        - Bollinger Bands

        These are SUGGESTIONS, not mandates. LLM can override.
        """

        if len(candles_5m) < 20:
            return {
                "stop_suggestion": None,
                "target_suggestion": None,
                "risk_reward": None
            }

        # Calculate ATR for stop placement
        atr_values = []
        for i in range(1, min(15, len(candles_5m))):
            c = candles_5m[-i]
            prev = candles_5m[-i-1]
            high_low = c['high'] - c['low']
            high_close = abs(c['high'] - prev['close'])
            low_close = abs(c['low'] - prev['close'])
            atr_values.append(max(high_low, high_close, low_close))

        atr = sum(atr_values) / len(atr_values) if atr_values else current_price * 0.01

        # Stop: 1.5 ATR below current (for long)
        stop_long = current_price - (1.5 * atr)
        stop_short = current_price + (1.5 * atr)

        # Target: 2.5 ATR above current (for long)
        target_long = current_price + (2.5 * atr)
        target_short = current_price - (2.5 * atr)

        # Recent swing high/low (for reference)
        recent_high = max(c['high'] for c in candles_5m[-20:])
        recent_low = min(c['low'] for c in candles_5m[-20:])

        return {
            "support_swing": round(recent_low, 2),
            "resistance_swing": round(recent_high, 2),
            "stop_long_suggestion": round(stop_long, 2),
            "stop_short_suggestion": round(stop_short, 2),
            "target_long_suggestion": round(target_long, 2),
            "target_short_suggestion": round(target_short, 2),
            "atr": round(atr, 2)
        }

    def _interpret_funding(self, funding_rate: float) -> str:
        """Interpret funding rate pressure."""
        annualized = funding_rate * 24 * 365 * 100

        if annualized > 20:
            return "expensive_longs"  # Longs paying shorts
        elif annualized < -20:
            return "expensive_shorts"
        else:
            return "neutral"

    def _ema(self, values: List[float], period: int) -> Optional[float]:
        """Calculate exponential moving average."""
        if len(values) < period:
            return None

        multiplier = 2 / (period + 1)

        # Start with SMA
        ema = sum(values[:period]) / period

        # Calculate EMA for remaining values
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema

        return ema


def compress_context_for_llm(
    account_state: Dict,
    features_per_asset: List[Dict],
    risk_metrics: Dict,
    market_regime: Dict
) -> Dict:
    """
    Create final compressed context for LLM (Jim Simons approved).

    Total size: ~100 numbers instead of 500+
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "account": {
            "equity": round(account_state.get('account_value', 0), 2),
            "available_margin": round(account_state.get('balance', 0), 2),
            "daily_pnl": round(account_state.get('daily_pnl', 0), 2),
            "position_count": len(account_state.get('positions', []))
        },

        "risk_state": risk_metrics,

        "assets": features_per_asset,

        "market_regime": market_regime
    }
