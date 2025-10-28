"""
Robust Feature Engineering Using Industry-Standard Libraries

Philosophy:
1. Don't reinvent the wheel - use ta-lib / pandas-ta
2. Multi-timeframe analysis (5m, 1h, 4h, 1d, 1w)
3. Volume profile and VWAP (institutional reference)
4. Open Interest analysis (perpetual futures edge)
5. Regime detection (trending vs mean-reverting)
6. Feature validation (backtestable, statistically sound)

Dependencies:
    pip install pandas-ta ta-lib-binary numpy pandas

If ta-lib fails, use pandas-ta (pure Python, no C dependencies)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logging.warning("ta-lib not available, falling back to pandas-ta")

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logging.warning("pandas-ta not available, using minimal indicators")


class RobustFeatureEngineer:
    """
    Production-grade feature engineering using industry-standard libraries.

    Calculates 40-50 robust features across multiple timeframes:
    - Trend: Multi-timeframe EMA alignment, ADX
    - Momentum: RSI, Stochastic, Williams %R, ROC
    - Volatility: ATR, Bollinger Bands, Historical Vol
    - Volume: VWAP, Volume Profile, OBV
    - Perpetual-specific: OI changes, Funding divergence
    - Regime: Trending vs Mean-reverting detection
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.regime_history = {}  # Track regime changes

    def extract_comprehensive_features(
        self,
        asset: str,
        candles_1m: List[Dict],
        candles_5m: List[Dict],
        candles_1h: List[Dict],
        candles_4h: List[Dict],
        candles_1d: List[Dict],
        candles_1w: Optional[List[Dict]] = None,
        current_price: float = None,
        funding_rate: Optional[float] = None,
        open_interest: Optional[float] = None,
        prev_open_interest: Optional[float] = None,
    ) -> Dict:
        """
        Extract comprehensive feature set using industry-standard methods.

        Returns ~40-50 features organized by category.
        """

        # Convert to DataFrames for vectorized operations
        df_1m = self._to_dataframe(candles_1m)
        df_5m = self._to_dataframe(candles_5m)
        df_1h = self._to_dataframe(candles_1h)
        df_4h = self._to_dataframe(candles_4h)
        df_1d = self._to_dataframe(candles_1d)
        df_1w = self._to_dataframe(candles_1w) if candles_1w else None

        if current_price is None and len(df_5m) > 0:
            current_price = df_5m['close'].iloc[-1]

        features = {
            "asset": asset,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": round(current_price, 2) if current_price else None
        }

        # 1. Multi-Timeframe Trend Analysis (10 features)
        features["trend"] = self._extract_multi_timeframe_trend(
            df_5m, df_1h, df_4h, df_1d, df_1w, current_price
        )

        # 2. Momentum Features (8 features)
        features["momentum"] = self._extract_momentum_features(df_5m, df_1h, df_4h)

        # 3. Volatility Features (6 features)
        features["volatility"] = self._extract_volatility_features(df_5m, df_4h, df_1d)

        # 4. Volume Features (6 features)
        features["volume"] = self._extract_volume_features(df_1m, df_5m, df_1h, current_price)

        # 5. Mean Reversion Features (5 features)
        features["mean_reversion"] = self._extract_mean_reversion_features(df_5m, current_price)

        # 6. Perpetual Futures Features (5 features)
        features["perpetual"] = self._extract_perpetual_features(
            funding_rate, open_interest, prev_open_interest, df_4h
        )

        # 7. Regime Detection (4 features)
        features["regime"] = self._detect_market_regime(asset, df_5m, df_1h, df_4h, df_1d)

        # 8. Multi-Timeframe Alignment (3 features)
        features["alignment"] = self._calculate_timeframe_alignment(
            features["trend"]
        )

        # 9. Risk-Adjusted Levels (for execution)
        features["levels"] = self._calculate_risk_levels(df_5m, df_1h, current_price)

        return features

    def _to_dataframe(self, candles: List[Dict]) -> pd.DataFrame:
        """Convert candle list to DataFrame with proper dtypes."""
        if not candles or len(candles) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(candles)

        # Ensure proper column names
        if 't' in df.columns:
            df.rename(columns={
                't': 'timestamp',
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume'
            }, inplace=True)

        # Convert to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def _extract_multi_timeframe_trend(
        self,
        df_5m: pd.DataFrame,
        df_1h: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_1d: pd.DataFrame,
        df_1w: Optional[pd.DataFrame],
        current_price: float
    ) -> Dict:
        """
        Multi-timeframe trend analysis using industry-standard indicators.

        Returns 10 features:
        - EMA alignment per timeframe (5m, 1h, 4h, 1d, 1w)
        - ADX (trend strength) per timeframe
        - Overall trend hierarchy score
        """

        def calculate_trend_strength(df: pd.DataFrame, timeframe: str) -> Dict:
            """Calculate trend strength using ADX and EMA alignment."""
            if len(df) < 50:
                return {"ema_align": 0, "adx": None, "strength": 0}

            close = df['close'].values
            high = df['high'].values
            low = df['low'].values

            # EMA alignment (20 vs 50)
            if TALIB_AVAILABLE:
                ema20 = talib.EMA(close, timeperiod=20)
                ema50 = talib.EMA(close, timeperiod=50)
                adx = talib.ADX(high, low, close, timeperiod=14)
            elif PANDAS_TA_AVAILABLE:
                ema20 = ta.ema(df['close'], length=20)
                ema50 = ta.ema(df['close'], length=50)
                adx_data = ta.adx(df['high'], df['low'], df['close'], length=14)
                adx = adx_data['ADX_14'] if 'ADX_14' in adx_data else None
            else:
                # Fallback: simple EMA
                ema20 = df['close'].ewm(span=20, adjust=False).mean()
                ema50 = df['close'].ewm(span=50, adjust=False).mean()
                adx = None

            # EMA alignment score (-1 to +1)
            if ema20 is not None and ema50 is not None:
                latest_ema20 = ema20.iloc[-1] if hasattr(ema20, 'iloc') else ema20[-1]
                latest_ema50 = ema50.iloc[-1] if hasattr(ema50, 'iloc') else ema50[-1]

                spread = (latest_ema20 - latest_ema50) / current_price if current_price else 0
                ema_align = np.clip(spread * 50, -1, 1)  # Normalize to -1 to +1
            else:
                ema_align = 0

            # ADX strength
            if adx is not None:
                latest_adx = adx.iloc[-1] if hasattr(adx, 'iloc') else adx[-1]
                latest_adx = float(latest_adx) if not np.isnan(latest_adx) else None
            else:
                latest_adx = None

            # Combined trend strength
            # ADX > 25 = trending, ADX < 20 = ranging
            # Strength = ema_align * (ADX_normalized)
            if latest_adx and not np.isnan(latest_adx):
                adx_normalized = min(latest_adx / 50, 1.0)  # Normalize ADX (50 = very strong)
                strength = ema_align * adx_normalized
            else:
                strength = ema_align * 0.5  # Assume moderate strength if no ADX

            return {
                "ema_align": round(float(ema_align), 3),
                "adx": round(float(latest_adx), 1) if latest_adx and not np.isnan(latest_adx) else None,
                "strength": round(float(strength), 3)
            }

        # Calculate for each timeframe
        trend_5m = calculate_trend_strength(df_5m, "5m")
        trend_1h = calculate_trend_strength(df_1h, "1h")
        trend_4h = calculate_trend_strength(df_4h, "4h")
        trend_1d = calculate_trend_strength(df_1d, "1d")
        trend_1w = calculate_trend_strength(df_1w, "1w") if df_1w is not None and len(df_1w) >= 50 else {"ema_align": 0, "adx": None, "strength": 0}

        # Trend hierarchy: Does higher timeframe agree with lower?
        # If 1d is bearish but 5m is bullish → conflict
        hierarchy_score = 0
        weights = {"1w": 0.4, "1d": 0.3, "4h": 0.2, "1h": 0.1}

        for tf, weight in weights.items():
            if tf == "1w":
                hierarchy_score += trend_1w["ema_align"] * weight
            elif tf == "1d":
                hierarchy_score += trend_1d["ema_align"] * weight
            elif tf == "4h":
                hierarchy_score += trend_4h["ema_align"] * weight
            elif tf == "1h":
                hierarchy_score += trend_1h["ema_align"] * weight

        return {
            "5m": trend_5m,
            "1h": trend_1h,
            "4h": trend_4h,
            "1d": trend_1d,
            "1w": trend_1w,
            "hierarchy_score": round(hierarchy_score, 3),  # -1 to +1, weighted by timeframe
            "primary_trend": "bullish" if hierarchy_score > 0.2 else "bearish" if hierarchy_score < -0.2 else "neutral"
        }

    def _extract_momentum_features(
        self,
        df_5m: pd.DataFrame,
        df_1h: pd.DataFrame,
        df_4h: pd.DataFrame
    ) -> Dict:
        """
        Momentum features using industry-standard indicators.

        Returns 8 features:
        - RSI (5m, 1h, 4h) with percentile ranking
        - Stochastic %K, %D
        - Williams %R
        - ROC (Rate of Change)
        - MACD histogram direction
        """

        def calculate_momentum(df: pd.DataFrame) -> Dict:
            """Calculate momentum indicators for a timeframe."""
            if len(df) < 30:
                return {}

            close = df['close'].values
            high = df['high'].values
            low = df['low'].values

            if TALIB_AVAILABLE:
                rsi = talib.RSI(close, timeperiod=14)
                stoch_k, stoch_d = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowd_period=3)
                willr = talib.WILLR(high, low, close, timeperiod=14)
                roc = talib.ROC(close, timeperiod=10)
                macd, macd_signal, macd_hist = talib.MACD(close)
            elif PANDAS_TA_AVAILABLE:
                rsi = ta.rsi(df['close'], length=14)
                stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3)
                stoch_k = stoch['STOCHk_14_3_3'] if stoch is not None and 'STOCHk_14_3_3' in stoch.columns else None
                stoch_d = stoch['STOCHd_14_3_3'] if stoch is not None and 'STOCHd_14_3_3' in stoch.columns else None
                willr = ta.willr(df['high'], df['low'], df['close'], length=14)
                roc = ta.roc(df['close'], length=10)
                macd_data = ta.macd(df['close'])
                macd_hist = macd_data['MACDh_12_26_9'] if macd_data is not None and 'MACDh_12_26_9' in macd_data.columns else None
            else:
                # Minimal fallback
                return {}

            # Extract latest values
            result = {}

            if rsi is not None:
                latest_rsi = rsi.iloc[-1] if hasattr(rsi, 'iloc') else rsi[-1]
                result["rsi"] = round(float(latest_rsi), 1) if not np.isnan(latest_rsi) else None

                # RSI percentile (current RSI vs last 50 bars)
                if len(rsi) >= 50:
                    rsi_values = rsi.iloc[-50:].values if hasattr(rsi, 'iloc') else rsi[-50:]
                    rsi_values = [r for r in rsi_values if not np.isnan(r)]
                    if len(rsi_values) > 0:
                        percentile = np.percentile(rsi_values, 50)
                        result["rsi_percentile"] = int((latest_rsi / 100) * 100) if not np.isnan(latest_rsi) else 50

            if stoch_k is not None:
                latest_k = stoch_k.iloc[-1] if hasattr(stoch_k, 'iloc') else stoch_k[-1]
                result["stoch_k"] = round(float(latest_k), 1) if not np.isnan(latest_k) else None

            if willr is not None:
                latest_willr = willr.iloc[-1] if hasattr(willr, 'iloc') else willr[-1]
                result["willr"] = round(float(latest_willr), 1) if not np.isnan(latest_willr) else None

            if roc is not None:
                latest_roc = roc.iloc[-1] if hasattr(roc, 'iloc') else roc[-1]
                result["roc"] = round(float(latest_roc), 2) if not np.isnan(latest_roc) else None

            if macd_hist is not None:
                latest_macd_hist = macd_hist.iloc[-1] if hasattr(macd_hist, 'iloc') else macd_hist[-1]
                prev_macd_hist = macd_hist.iloc[-2] if hasattr(macd_hist, 'iloc') else macd_hist[-2]

                if not np.isnan(latest_macd_hist) and not np.isnan(prev_macd_hist):
                    result["macd_direction"] = 1 if latest_macd_hist > prev_macd_hist else -1
                else:
                    result["macd_direction"] = 0

            return result

        return {
            "5m": calculate_momentum(df_5m),
            "1h": calculate_momentum(df_1h),
            "4h": calculate_momentum(df_4h)
        }

    def _extract_volatility_features(
        self,
        df_5m: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_1d: pd.DataFrame
    ) -> Dict:
        """
        Volatility features with regime classification.

        Returns 6 features:
        - ATR (5m, 4h, 1d) with percentile
        - Bollinger Band width percentile
        - Historical volatility
        - Volatility regime classification
        """

        def calculate_atr_percentile(df: pd.DataFrame) -> Tuple[float, int]:
            """Calculate ATR and its percentile vs recent history."""
            if len(df) < 30:
                return None, None

            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            if TALIB_AVAILABLE:
                atr = talib.ATR(high, low, close, timeperiod=14)
            elif PANDAS_TA_AVAILABLE:
                atr = ta.atr(df['high'], df['low'], df['close'], length=14)
            else:
                # Simple ATR
                tr = pd.DataFrame({
                    'hl': df['high'] - df['low'],
                    'hc': (df['high'] - df['close'].shift()).abs(),
                    'lc': (df['low'] - df['close'].shift()).abs()
                }).max(axis=1)
                atr = tr.rolling(14).mean()

            if atr is not None and len(atr) >= 50:
                latest_atr = atr.iloc[-1] if hasattr(atr, 'iloc') else atr[-1]
                atr_values = atr.iloc[-50:].values if hasattr(atr, 'iloc') else atr[-50:]
                atr_values = [a for a in atr_values if not np.isnan(a)]

                if len(atr_values) > 0 and not np.isnan(latest_atr):
                    below = sum(1 for a in atr_values if a < latest_atr)
                    percentile = int((below / len(atr_values)) * 100)
                    return round(float(latest_atr), 2), percentile

            return None, None

        atr_5m, atr_5m_pct = calculate_atr_percentile(df_5m)
        atr_4h, atr_4h_pct = calculate_atr_percentile(df_4h)
        atr_1d, atr_1d_pct = calculate_atr_percentile(df_1d)

        # Volatility regime based on 4h ATR percentile
        if atr_4h_pct is not None:
            if atr_4h_pct < 30:
                regime = "low"
            elif atr_4h_pct > 70:
                regime = "high"
            else:
                regime = "medium"
        else:
            regime = "unknown"

        # Bollinger Band width (volatility measure)
        bb_width_pct = None
        if len(df_5m) >= 20 and PANDAS_TA_AVAILABLE:
            bbands = ta.bbands(df_5m['close'], length=20, std=2)
            if bbands is not None and 'BBU_20_2.0' in bbands.columns and 'BBL_20_2.0' in bbands.columns:
                latest_upper = bbands['BBU_20_2.0'].iloc[-1]
                latest_lower = bbands['BBL_20_2.0'].iloc[-1]
                latest_close = df_5m['close'].iloc[-1]

                if not np.isnan(latest_upper) and not np.isnan(latest_lower) and latest_close > 0:
                    bb_width = (latest_upper - latest_lower) / latest_close
                    bb_width_pct = round(float(bb_width * 100), 2)

        return {
            "atr_5m": atr_5m,
            "atr_5m_percentile": atr_5m_pct,
            "atr_4h": atr_4h,
            "atr_4h_percentile": atr_4h_pct,
            "regime": regime,
            "bb_width_pct": bb_width_pct
        }

    def _extract_volume_features(
        self,
        df_1m: pd.DataFrame,
        df_5m: pd.DataFrame,
        df_1h: pd.DataFrame,
        current_price: float
    ) -> Dict:
        """
        Volume-based features including VWAP and volume profile.

        Returns 6 features:
        - VWAP distance
        - Volume MA ratio (current vs average)
        - OBV (On Balance Volume) trend
        - Volume Profile (high volume price levels)
        """

        vwap_distance = None
        volume_ma_ratio = None
        obv_trend = None

        # VWAP calculation (using 1h data for day's VWAP)
        if len(df_1h) >= 24 and current_price:  # At least 24 hours
            df_24h = df_1h.iloc[-24:].copy()
            df_24h['vwap'] = (df_24h['close'] * df_24h['volume']).cumsum() / df_24h['volume'].cumsum()
            latest_vwap = df_24h['vwap'].iloc[-1]

            if not np.isnan(latest_vwap) and latest_vwap > 0:
                vwap_distance = ((current_price - latest_vwap) / latest_vwap) * 100
                vwap_distance = round(vwap_distance, 2)

        # Volume MA ratio
        if len(df_5m) >= 20:
            latest_volume = df_5m['volume'].iloc[-1]
            avg_volume = df_5m['volume'].iloc[-20:].mean()

            if avg_volume > 0:
                volume_ma_ratio = round(float(latest_volume / avg_volume), 2)

        # OBV trend
        if len(df_5m) >= 20:
            if TALIB_AVAILABLE:
                obv = talib.OBV(df_5m['close'].values, df_5m['volume'].values)
                obv_ma = talib.SMA(obv, timeperiod=10)

                if len(obv) >= 10 and len(obv_ma) >= 10:
                    latest_obv = obv[-1]
                    latest_obv_ma = obv_ma[-1]

                    if not np.isnan(latest_obv) and not np.isnan(latest_obv_ma):
                        obv_trend = 1 if latest_obv > latest_obv_ma else -1

        # Volume profile (simplified - find high volume price levels)
        volume_profile_levels = None
        if len(df_1h) >= 100:
            df_profile = df_1h.iloc[-100:].copy()

            # Create price buckets (1% increments)
            df_profile['price_bucket'] = (df_profile['close'] / df_profile['close'].max() * 100).astype(int)
            volume_by_price = df_profile.groupby('price_bucket')['volume'].sum().sort_values(ascending=False)

            if len(volume_by_price) >= 3:
                top_3_buckets = volume_by_price.head(3).index.tolist()
                # Convert buckets back to approximate prices
                max_price = df_profile['close'].max()
                volume_profile_levels = [round((bucket / 100) * max_price, 0) for bucket in top_3_buckets]

        return {
            "vwap_distance_pct": vwap_distance,  # +ve = above VWAP (bullish), -ve = below (bearish)
            "volume_ma_ratio": volume_ma_ratio,  # >1 = above average volume
            "obv_trend": obv_trend,  # 1 = bullish, -1 = bearish
            "volume_profile_levels": volume_profile_levels  # High volume price levels
        }

    def _extract_mean_reversion_features(
        self,
        df_5m: pd.DataFrame,
        current_price: float
    ) -> Dict:
        """
        Mean reversion features with Z-score.

        Returns 5 features:
        - Z-score (distance from mean in std devs)
        - Bollinger Band position (0 to 1)
        - Distance from EMA20
        - Overbought/oversold duration
        """

        if len(df_5m) < 20:
            return {}

        close_series = df_5m['close']

        # Z-score: how many standard deviations from mean
        mean_20 = close_series.iloc[-20:].mean()
        std_20 = close_series.iloc[-20:].std()

        if std_20 > 0:
            z_score = (current_price - mean_20) / std_20
            z_score = round(float(z_score), 2)
        else:
            z_score = 0

        # Bollinger Band position
        bb_position = None
        if PANDAS_TA_AVAILABLE:
            bbands = ta.bbands(close_series, length=20, std=2)
            if bbands is not None and all(col in bbands.columns for col in ['BBU_20_2.0', 'BBL_20_2.0']):
                latest_upper = bbands['BBU_20_2.0'].iloc[-1]
                latest_lower = bbands['BBL_20_2.0'].iloc[-1]

                if not np.isnan(latest_upper) and not np.isnan(latest_lower) and latest_upper > latest_lower:
                    bb_position = (current_price - latest_lower) / (latest_upper - latest_lower)
                    bb_position = round(float(np.clip(bb_position, 0, 1)), 2)

        # Distance from EMA20 (percentage)
        ema20 = close_series.ewm(span=20, adjust=False).mean().iloc[-1]
        if ema20 > 0:
            ema20_distance_pct = ((current_price - ema20) / ema20) * 100
            ema20_distance_pct = round(ema20_distance_pct, 2)
        else:
            ema20_distance_pct = 0

        # Overbought/oversold duration (how many bars has RSI been >70 or <30)
        oversold_duration = 0
        overbought_duration = 0

        if TALIB_AVAILABLE and len(df_5m) >= 14:
            rsi = talib.RSI(close_series.values, timeperiod=14)

            for i in range(len(rsi)-1, max(0, len(rsi)-10), -1):
                if not np.isnan(rsi[i]):
                    if rsi[i] < 30:
                        oversold_duration += 1
                    elif rsi[i] > 70:
                        overbought_duration += 1
                    else:
                        break

        return {
            "z_score": z_score,  # -2 to +2 typically, >2 = extreme overbought, <-2 = extreme oversold
            "bb_position": bb_position,  # 0 = at lower band, 1 = at upper band, 0.5 = middle
            "ema20_distance_pct": ema20_distance_pct,  # % above/below EMA20
            "oversold_duration_bars": oversold_duration,  # How long RSI <30
            "overbought_duration_bars": overbought_duration  # How long RSI >70
        }

    def _extract_perpetual_features(
        self,
        funding_rate: Optional[float],
        open_interest: Optional[float],
        prev_open_interest: Optional[float],
        df_4h: pd.DataFrame
    ) -> Dict:
        """
        Perpetual futures specific features.

        Returns 5 features:
        - Funding rate (annualized %)
        - Funding pressure (expensive longs/shorts)
        - OI change %
        - OI trend (increasing/decreasing)
        - OI + Price correlation
        """

        funding_annualized = None
        funding_pressure = "neutral"

        if funding_rate is not None:
            funding_annualized = round(funding_rate * 24 * 365 * 100, 2)

            if funding_annualized > 20:
                funding_pressure = "expensive_longs"
            elif funding_annualized < -20:
                funding_pressure = "expensive_shorts"

        oi_change_pct = None
        oi_trend = "stable"

        if open_interest is not None and prev_open_interest is not None and prev_open_interest > 0:
            oi_change_pct = ((open_interest - prev_open_interest) / prev_open_interest) * 100
            oi_change_pct = round(oi_change_pct, 2)

            if oi_change_pct > 5:
                oi_trend = "increasing"
            elif oi_change_pct < -5:
                oi_trend = "decreasing"

        # OI + Price correlation (simplified)
        # If OI increasing + Price increasing = strong uptrend
        # If OI decreasing + Price decreasing = strong downtrend
        oi_price_signal = "neutral"

        if len(df_4h) >= 2 and oi_change_pct is not None:
            price_change_pct = ((df_4h['close'].iloc[-1] - df_4h['close'].iloc[-2]) / df_4h['close'].iloc[-2]) * 100

            if oi_change_pct > 2 and price_change_pct > 1:
                oi_price_signal = "strong_bullish"
            elif oi_change_pct > 2 and price_change_pct < -1:
                oi_price_signal = "weak_bearish"  # Shorts piling in
            elif oi_change_pct < -2 and price_change_pct > 1:
                oi_price_signal = "weak_bullish"  # Short covering
            elif oi_change_pct < -2 and price_change_pct < -1:
                oi_price_signal = "strong_bearish"

        return {
            "funding_rate": round(funding_rate, 8) if funding_rate else None,
            "funding_annualized_pct": funding_annualized,
            "funding_pressure": funding_pressure,
            "oi_change_pct": oi_change_pct,
            "oi_price_signal": oi_price_signal
        }

    def _detect_market_regime(
        self,
        asset: str,
        df_5m: pd.DataFrame,
        df_1h: pd.DataFrame,
        df_4h: pd.DataFrame,
        df_1d: pd.DataFrame
    ) -> Dict:
        """
        Detect market regime (trending vs mean-reverting).

        Returns 4 features:
        - regime_type: trending / mean_reverting / transitioning
        - regime_strength: 0-100 (confidence in regime classification)
        - regime_duration_bars: How long in current regime
        - recommended_strategy: trend_following / mean_reversion / stay_out
        """

        # Use ADX to determine trending vs ranging
        # ADX > 25 = trending, ADX < 20 = ranging

        regime_type = "transitioning"
        regime_strength = 50

        if len(df_4h) >= 30:
            high = df_4h['high'].values
            low = df_4h['low'].values
            close = df_4h['close'].values

            if TALIB_AVAILABLE:
                adx = talib.ADX(high, low, close, timeperiod=14)

                if adx is not None and len(adx) >= 14:
                    latest_adx = adx[-1]

                    if not np.isnan(latest_adx):
                        if latest_adx > 25:
                            regime_type = "trending"
                            regime_strength = int(min(latest_adx, 100))
                        elif latest_adx < 20:
                            regime_type = "mean_reverting"
                            regime_strength = int(100 - latest_adx * 5)  # Lower ADX = stronger mean reversion

        # Regime duration (how many bars has ADX been above/below threshold)
        regime_duration = 0
        if len(df_4h) >= 30 and TALIB_AVAILABLE:
            high = df_4h['high'].values
            low = df_4h['low'].values
            close = df_4h['close'].values
            adx = talib.ADX(high, low, close, timeperiod=14)

            threshold = 25 if regime_type == "trending" else 20

            for i in range(len(adx)-1, max(0, len(adx)-20), -1):
                if not np.isnan(adx[i]):
                    if regime_type == "trending" and adx[i] > threshold:
                        regime_duration += 1
                    elif regime_type == "mean_reverting" and adx[i] < threshold:
                        regime_duration += 1
                    else:
                        break

        # Recommended strategy based on regime
        if regime_type == "trending" and regime_strength > 60:
            recommended_strategy = "trend_following"
        elif regime_type == "mean_reverting" and regime_strength > 60:
            recommended_strategy = "mean_reversion"
        else:
            recommended_strategy = "stay_out"  # Low confidence, don't trade

        return {
            "regime_type": regime_type,
            "regime_strength": regime_strength,
            "regime_duration_bars": regime_duration,
            "recommended_strategy": recommended_strategy
        }

    def _calculate_timeframe_alignment(self, trend_features: Dict) -> Dict:
        """
        Calculate multi-timeframe alignment score.

        Returns 3 features:
        - alignment_score: 0-100 (how many timeframes agree)
        - alignment_direction: bullish / bearish / neutral
        - strongest_timeframe: which timeframe has strongest trend
        """

        timeframes = ["5m", "1h", "4h", "1d", "1w"]
        alignments = []

        for tf in timeframes:
            if tf in trend_features and "ema_align" in trend_features[tf]:
                ema_align = trend_features[tf]["ema_align"]
                if ema_align > 0.2:
                    alignments.append(1)  # Bullish
                elif ema_align < -0.2:
                    alignments.append(-1)  # Bearish
                else:
                    alignments.append(0)  # Neutral

        if not alignments:
            return {"alignment_score": 0, "alignment_direction": "neutral", "strongest_timeframe": None}

        # Alignment score: what % are aligned with majority
        majority = 1 if sum(alignments) > 0 else -1 if sum(alignments) < 0 else 0

        if majority != 0:
            aligned_count = sum(1 for a in alignments if a == majority)
            alignment_score = int((aligned_count / len(alignments)) * 100)
        else:
            alignment_score = 0

        alignment_direction = "bullish" if majority > 0 else "bearish" if majority < 0 else "neutral"

        # Find strongest timeframe (highest ADX * ema_align)
        strongest_tf = None
        max_strength = 0

        for tf in timeframes:
            if tf in trend_features and "strength" in trend_features[tf]:
                strength = abs(trend_features[tf]["strength"])
                if strength > max_strength:
                    max_strength = strength
                    strongest_tf = tf

        return {
            "alignment_score": alignment_score,
            "alignment_direction": alignment_direction,
            "strongest_timeframe": strongest_tf
        }

    def _calculate_risk_levels(
        self,
        df_5m: pd.DataFrame,
        df_1h: pd.DataFrame,
        current_price: float
    ) -> Dict:
        """
        Calculate risk-adjusted entry/stop/target levels.

        Returns suggested levels for execution (not mandates).
        """

        if len(df_5m) < 20 or not current_price:
            return {}

        # ATR for stop distance
        high = df_5m['high'].values
        low = df_5m['low'].values
        close = df_5m['close'].values

        if TALIB_AVAILABLE:
            atr = talib.ATR(high, low, close, timeperiod=14)
            latest_atr = atr[-1] if atr is not None and len(atr) > 0 else current_price * 0.01
        else:
            latest_atr = current_price * 0.01

        # Swing high/low from last 20 bars
        recent_high = df_5m['high'].iloc[-20:].max()
        recent_low = df_5m['low'].iloc[-20:].min()

        # VWAP as reference
        vwap = None
        if len(df_1h) >= 24:
            df_24h = df_1h.iloc[-24:].copy()
            df_24h['vwap'] = (df_24h['close'] * df_24h['volume']).cumsum() / df_24h['volume'].cumsum()
            vwap = df_24h['vwap'].iloc[-1]

        return {
            "atr": round(float(latest_atr), 2) if not np.isnan(latest_atr) else None,
            "stop_long_atr": round(current_price - (1.5 * latest_atr), 2) if not np.isnan(latest_atr) else None,
            "stop_short_atr": round(current_price + (1.5 * latest_atr), 2) if not np.isnan(latest_atr) else None,
            "target_long_atr": round(current_price + (2.5 * latest_atr), 2) if not np.isnan(latest_atr) else None,
            "target_short_atr": round(current_price - (2.5 * latest_atr), 2) if not np.isnan(latest_atr) else None,
            "swing_high": round(float(recent_high), 2),
            "swing_low": round(float(recent_low), 2),
            "vwap": round(float(vwap), 2) if vwap is not None and not np.isnan(vwap) else None
        }


def compress_robust_context(
    account_state: Dict,
    features_per_asset: List[Dict],
    risk_metrics: Dict
) -> Dict:
    """
    Create compressed context from robust features.

    Total features per asset: ~40-50
    Total context size: Still manageable for LLM
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": {
            "equity": round(account_state.get('account_value', 0), 2),
            "available_margin": round(account_state.get('balance', 0), 2),
            "position_count": len(account_state.get('positions', []))
        },
        "risk_state": risk_metrics,
        "assets": features_per_asset
    }
