"""
Algorithm Layer: Features, Risk, Position Sizing (No Trading Decisions)

Philosophy:
- Calculate features (descriptive, not prescriptive)
- Enforce hard risk limits (non-negotiable)
- Provide context (not instructions)
- LET THE LLM DECIDE

KISS Principle:
- Use ta-lib/pandas-ta for indicators
- Simple, clear separation of concerns
- No complex logic - just math and limits
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False


class AlgorithmLayer:
    """
    Deterministic layer: Features, Risk, Context.

    What it DOES:
    - Calculates market features
    - Enforces hard risk limits
    - Detects regime (for context only)
    - Calculates position sizes

    What it DOESN'T DO:
    - Make trading decisions
    - Tell LLM what to do
    - Execute strategies
    """

    def __init__(self, max_leverage: float = 6.0, max_heat: float = 0.25):
        self.logger = logging.getLogger(__name__)
        self.max_leverage = max_leverage
        self.max_heat = max_heat
        self.risk_per_trade = 0.015  # 1.5% of account per trade

    def prepare_context(
        self,
        asset: str,
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_4h: List[Dict],
        candles_1d: List[Dict],
        current_price: float,
        account_equity: float,
        positions: List[Dict],
        active_trades: List[Dict],
        risk_metrics: Dict,
        funding_rate: Optional[float] = None,
        open_interest: Optional[float] = None,
        prev_open_interest: Optional[float] = None
    ) -> Dict:
        """
        Prepare clean context for LLM decision making.

        Returns:
        {
            "allowed_to_trade": bool,
            "reason": str (if not allowed),
            "features": {...},  # 30-40 clean features
            "regime": {...},    # Context, not instructions
            "risk_state": {...},
            "constraints": {...}
        }
        """

        # 1. CHECK HARD RISK LIMITS FIRST
        risk_check = self._check_hard_limits(risk_metrics, account_equity, positions)

        if not risk_check["allowed"]:
            return {
                "allowed_to_trade": False,
                "reason": risk_check["reason"],
                "asset": asset
            }

        # 2. CALCULATE FEATURES (using KISS - ta-lib/pandas-ta)
        features = self._calculate_features(
            candles_5m, candles_1h, candles_4h, candles_1d, current_price
        )

        # 3. DETECT REGIME (context only, not rules)
        regime = self._detect_regime(features)

        # 4. ADD PERPETUAL-SPECIFIC DATA
        if funding_rate is not None:
            features["funding"] = {
                "rate": round(funding_rate, 8),
                "annualized_pct": round(funding_rate * 24 * 365 * 100, 2)
            }

        if open_interest is not None and prev_open_interest is not None:
            features["open_interest"] = {
                "current": open_interest,
                "change_pct": round(((open_interest - prev_open_interest) / prev_open_interest * 100), 2) if prev_open_interest > 0 else 0
            }

        # 5. RETURN CLEAN CONTEXT
        return {
            "allowed_to_trade": True,
            "asset": asset,
            "price": round(current_price, 2),
            "features": features,
            "regime": regime,
            "risk_state": {
                "portfolio_heat": risk_metrics.get("portfolio_heat", 0),
                "current_drawdown_pct": risk_metrics.get("current_drawdown_pct", 0),
                "total_leverage": risk_metrics.get("total_leverage", 0),
                "consecutive_losses": risk_metrics.get("consecutive_losses", 0),
                "available_capacity": "high" if risk_metrics.get("portfolio_heat", 0) < 0.15 else "medium" if risk_metrics.get("portfolio_heat", 0) < 0.20 else "low"
            },
            "constraints": {
                "max_leverage": self.max_leverage,
                "max_heat": self.max_heat,
                "risk_per_trade": self.risk_per_trade
            }
        }

    def _check_hard_limits(self, risk_metrics: Dict, account_equity: float, positions: List[Dict]) -> Dict:
        """
        Enforce hard risk limits (non-negotiable).

        These are NOT suggestions - they are circuit breakers.
        """

        # Drawdown circuit breaker
        if risk_metrics.get("current_drawdown_pct", 0) < -10:
            return {
                "allowed": False,
                "reason": "CIRCUIT_BREAKER: Drawdown exceeded -10%. Trading halted."
            }

        # Portfolio heat limit
        if risk_metrics.get("portfolio_heat", 0) > self.max_heat:
            return {
                "allowed": False,
                "reason": f"RISK_LIMIT: Portfolio heat {risk_metrics['portfolio_heat']:.1%} exceeds {self.max_heat:.1%}"
            }

        # Leverage limit
        if risk_metrics.get("total_leverage", 0) > self.max_leverage:
            return {
                "allowed": False,
                "reason": f"RISK_LIMIT: Total leverage {risk_metrics['total_leverage']:.1f}x exceeds {self.max_leverage}x"
            }

        return {"allowed": True}

    def _calculate_features(
        self,
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_4h: List[Dict],
        candles_1d: List[Dict],
        current_price: float
    ) -> Dict:
        """
        Calculate clean, normalized features using ta-lib/pandas-ta.

        Returns ~30-40 features (KISS - not 50+, that was overkill).
        """

        features = {}

        # Convert to DataFrames
        df_5m = self._to_df(candles_5m)
        df_1h = self._to_df(candles_1h)
        df_4h = self._to_df(candles_4h)
        df_1d = self._to_df(candles_1d)

        # TREND FEATURES (multi-timeframe)
        features["trend"] = {
            "5m": self._calc_trend(df_5m, current_price),
            "1h": self._calc_trend(df_1h, current_price),
            "4h": self._calc_trend(df_4h, current_price),
            "1d": self._calc_trend(df_1d, current_price)
        }

        # MOMENTUM FEATURES
        features["momentum"] = {
            "rsi_5m": self._calc_rsi(df_5m),
            "rsi_1h": self._calc_rsi(df_1h),
            "macd_5m": self._calc_macd(df_5m),
            "stoch_5m": self._calc_stoch(df_5m)
        }

        # VOLATILITY FEATURES
        features["volatility"] = {
            "atr_5m": self._calc_atr(df_5m),
            "atr_4h": self._calc_atr(df_4h),
            "bb_width_5m": self._calc_bb_width(df_5m)
        }

        # VOLUME FEATURES
        features["volume"] = {
            "vwap_distance_pct": self._calc_vwap_distance(df_1h, current_price),
            "volume_ratio_5m": self._calc_volume_ratio(df_5m),
            "obv_trend_5m": self._calc_obv_trend(df_5m)
        }

        # MEAN REVERSION FEATURES
        features["mean_reversion"] = {
            "z_score": self._calc_z_score(df_5m, current_price),
            "bb_position": self._calc_bb_position(df_5m, current_price),
            "ema20_distance_pct": self._calc_ema_distance(df_5m, current_price, 20)
        }

        return features

    def _to_df(self, candles: List[Dict]) -> pd.DataFrame:
        """Convert candle list to DataFrame."""
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles)

        # Handle different column name formats
        rename_map = {'t': 'timestamp', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}
        df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def _calc_trend(self, df: pd.DataFrame, current_price: float) -> Dict:
        """Calculate trend features for a timeframe."""
        if len(df) < 50:
            return {"ema_align": 0, "adx": None}

        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        # EMA alignment (20 vs 50)
        if TALIB_AVAILABLE:
            ema20 = talib.EMA(close, timeperiod=20)[-1]
            ema50 = talib.EMA(close, timeperiod=50)[-1]
            adx = talib.ADX(high, low, close, timeperiod=14)[-1]
        elif PANDAS_TA_AVAILABLE:
            ema20 = ta.ema(df['close'], length=20).iloc[-1]
            ema50 = ta.ema(df['close'], length=50).iloc[-1]
            adx_data = ta.adx(df['high'], df['low'], df['close'], length=14)
            adx = adx_data['ADX_14'].iloc[-1] if 'ADX_14' in adx_data else None
        else:
            ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            adx = None

        # Normalize EMA alignment to -1 to +1
        ema_align = np.clip((ema20 - ema50) / current_price * 50, -1, 1) if current_price else 0

        return {
            "ema_align": round(float(ema_align), 3),
            "adx": round(float(adx), 1) if adx is not None and not np.isnan(adx) else None
        }

    def _calc_rsi(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate RSI."""
        if len(df) < 14:
            return None

        if TALIB_AVAILABLE:
            rsi = talib.RSI(df['close'].values, timeperiod=14)[-1]
        elif PANDAS_TA_AVAILABLE:
            rsi = ta.rsi(df['close'], length=14).iloc[-1]
        else:
            # Simple RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs)).iloc[-1]

        return round(float(rsi), 1) if not np.isnan(rsi) else None

    def _calc_macd(self, df: pd.DataFrame) -> Optional[str]:
        """Calculate MACD direction."""
        if len(df) < 26:
            return None

        if TALIB_AVAILABLE:
            _, _, hist = talib.MACD(df['close'].values)
            if len(hist) >= 2:
                return "bullish" if hist[-1] > hist[-2] else "bearish"
        elif PANDAS_TA_AVAILABLE:
            macd = ta.macd(df['close'])
            if macd is not None and 'MACDh_12_26_9' in macd.columns:
                hist = macd['MACDh_12_26_9']
                if len(hist) >= 2:
                    return "bullish" if hist.iloc[-1] > hist.iloc[-2] else "bearish"

        return None

    def _calc_stoch(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate Stochastic %K."""
        if len(df) < 14:
            return None

        if TALIB_AVAILABLE:
            k, _ = talib.STOCH(df['high'].values, df['low'].values, df['close'].values)
            return round(float(k[-1]), 1) if not np.isnan(k[-1]) else None
        elif PANDAS_TA_AVAILABLE:
            stoch = ta.stoch(df['high'], df['low'], df['close'])
            if stoch is not None and 'STOCHk_14_3_3' in stoch.columns:
                k = stoch['STOCHk_14_3_3'].iloc[-1]
                return round(float(k), 1) if not np.isnan(k) else None

        return None

    def _calc_atr(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate ATR."""
        if len(df) < 14:
            return None

        if TALIB_AVAILABLE:
            atr = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=14)[-1]
        elif PANDAS_TA_AVAILABLE:
            atr = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
        else:
            tr = pd.DataFrame({
                'hl': df['high'] - df['low'],
                'hc': (df['high'] - df['close'].shift()).abs(),
                'lc': (df['low'] - df['close'].shift()).abs()
            }).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]

        return round(float(atr), 2) if not np.isnan(atr) else None

    def _calc_bb_width(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate Bollinger Band width as % of price."""
        if len(df) < 20:
            return None

        if TALIB_AVAILABLE:
            upper, _, lower = talib.BBANDS(df['close'].values, timeperiod=20)
            width = (upper[-1] - lower[-1]) / df['close'].iloc[-1] * 100
        elif PANDAS_TA_AVAILABLE:
            bb = ta.bbands(df['close'], length=20)
            if bb is not None and 'BBU_20_2.0' in bb.columns:
                upper = bb['BBU_20_2.0'].iloc[-1]
                lower = bb['BBL_20_2.0'].iloc[-1]
                width = (upper - lower) / df['close'].iloc[-1] * 100
            else:
                return None
        else:
            return None

        return round(float(width), 2) if not np.isnan(width) else None

    def _calc_vwap_distance(self, df: pd.DataFrame, current_price: float) -> Optional[float]:
        """Calculate distance from VWAP as %."""
        if len(df) < 24:
            return None

        df_24h = df.iloc[-24:].copy()
        vwap = (df_24h['close'] * df_24h['volume']).sum() / df_24h['volume'].sum()

        if vwap > 0:
            distance = ((current_price - vwap) / vwap) * 100
            return round(float(distance), 2)

        return None

    def _calc_volume_ratio(self, df: pd.DataFrame) -> Optional[float]:
        """Calculate current volume vs 20-bar average."""
        if len(df) < 20:
            return None

        current_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].iloc[-20:].mean()

        return round(float(current_vol / avg_vol), 2) if avg_vol > 0 else None

    def _calc_obv_trend(self, df: pd.DataFrame) -> Optional[str]:
        """Calculate OBV trend."""
        if len(df) < 20:
            return None

        if TALIB_AVAILABLE:
            obv = talib.OBV(df['close'].values, df['volume'].values)
            obv_ma = talib.SMA(obv, timeperiod=10)
            if len(obv) >= 10:
                return "bullish" if obv[-1] > obv_ma[-1] else "bearish"

        return None

    def _calc_z_score(self, df: pd.DataFrame, current_price: float) -> Optional[float]:
        """Calculate Z-score (standard deviations from mean)."""
        if len(df) < 20:
            return None

        mean = df['close'].iloc[-20:].mean()
        std = df['close'].iloc[-20:].std()

        if std > 0:
            z = (current_price - mean) / std
            return round(float(z), 2)

        return None

    def _calc_bb_position(self, df: pd.DataFrame, current_price: float) -> Optional[float]:
        """Calculate position within Bollinger Bands (0 to 1)."""
        if len(df) < 20:
            return None

        if TALIB_AVAILABLE:
            upper, _, lower = talib.BBANDS(df['close'].values, timeperiod=20)
            upper_val = upper[-1]
            lower_val = lower[-1]
        elif PANDAS_TA_AVAILABLE:
            bb = ta.bbands(df['close'], length=20)
            if bb is not None and 'BBU_20_2.0' in bb.columns:
                upper_val = bb['BBU_20_2.0'].iloc[-1]
                lower_val = bb['BBL_20_2.0'].iloc[-1]
            else:
                return None
        else:
            return None

        if upper_val > lower_val:
            position = (current_price - lower_val) / (upper_val - lower_val)
            return round(float(np.clip(position, 0, 1)), 2)

        return None

    def _calc_ema_distance(self, df: pd.DataFrame, current_price: float, period: int) -> Optional[float]:
        """Calculate distance from EMA as %."""
        if len(df) < period:
            return None

        if TALIB_AVAILABLE:
            ema = talib.EMA(df['close'].values, timeperiod=period)[-1]
        elif PANDAS_TA_AVAILABLE:
            ema = ta.ema(df['close'], length=period).iloc[-1]
        else:
            ema = df['close'].ewm(span=period, adjust=False).mean().iloc[-1]

        if ema > 0:
            distance = ((current_price - ema) / ema) * 100
            return round(float(distance), 2)

        return None

    def _detect_regime(self, features: Dict) -> Dict:
        """
        Detect market regime (context for LLM, not rules).

        Returns descriptive context, NOT instructions.
        """

        adx_4h = features['trend']['4h'].get('adx')

        if adx_4h is None:
            return {
                "type": "unknown",
                "note": "Insufficient data for regime detection"
            }

        if adx_4h > 25:
            return {
                "type": "trending",
                "strength": min(int((adx_4h / 50) * 100), 100),
                "note": f"ADX at {adx_4h} suggests directional moves are more likely. Markets in this regime often show momentum continuation."
            }
        elif adx_4h < 20:
            return {
                "type": "ranging",
                "strength": int((20 - adx_4h) / 20 * 100),
                "note": f"ADX at {adx_4h} suggests choppy, range-bound conditions. Markets in this regime often mean-revert."
            }
        else:
            return {
                "type": "transitioning",
                "strength": 50,
                "note": f"ADX at {adx_4h} is in neutral zone. Market direction is unclear."
            }

    def calculate_position_size(
        self,
        conviction: int,
        account_equity: float,
        atr: float,
        current_price: float
    ) -> float:
        """
        Calculate position size based on conviction and risk parameters.

        Formula: Kelly-inspired position sizing
        """

        if conviction < 30:
            return 0  # Too low conviction

        # Risk amount based on conviction
        conviction_multiplier = conviction / 100
        risk_amount = account_equity * self.risk_per_trade * conviction_multiplier

        # Position size based on ATR stop
        stop_distance_atr = 1.5
        stop_distance_usd = atr * stop_distance_atr

        if stop_distance_usd > 0:
            size_in_asset = risk_amount / stop_distance_usd
            position_usd = size_in_asset * current_price
            return round(position_usd, 2)

        return 0
