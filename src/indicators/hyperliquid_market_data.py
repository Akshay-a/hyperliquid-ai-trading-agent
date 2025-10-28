"""
Real-time market microstructure data from Hyperliquid SDK.
Provides orderbook analysis, candlestick data, and volume delta calculations.

This module replaces TAAPI dependency with native Hyperliquid data for:
- Zero latency (vs 1-3s from third-party API)
- Zero basis risk (same exchange data)
- Free access (no subscription costs)
- Full market microstructure visibility
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import asyncio
import logging
import statistics

try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logging.warning("pandas not available, using simplified indicator calculations")


class HyperliquidMarketData:
    """
    Market microstructure data provider using Hyperliquid SDK.

    Provides real-time orderbook snapshots, candlestick data, and derived
    microstructure metrics like liquidity imbalances and volume delta.
    """

    def __init__(self, info):
        """
        Initialize with Hyperliquid Info instance.

        Args:
            info: hyperliquid.info.Info instance from HyperliquidAPI
        """
        self.info = info
        self._logger = logging.getLogger(__name__)

    async def get_orderbook_snapshot(self, asset: str, depth: int = 20) -> Dict:
        """
        Fetch L2 orderbook and derive microstructure metrics.

        Args:
            asset: Trading pair symbol (e.g., "BTC", "ETH")
            depth: Number of price levels to fetch per side

        Returns:
            Dictionary containing:
            - bids/asks: Top price levels
            - spread: bid-ask spread in absolute and basis points
            - imbalance_ratio: bid_depth / ask_depth (>1 = bullish)
            - bid/ask_depth_0.5pct: Liquidity within 0.5% of mid
            - liquidity_levels: Significant support/resistance from large orders
        """
        try:
            snapshot = await asyncio.to_thread(self.info.l2_snapshot, asset)

            # Extract bid and ask levels
            levels = snapshot.get("levels", [[], []])
            if len(levels) < 2:
                return {"error": "Invalid orderbook structure"}

            bids = levels[0][:depth] if levels[0] else []
            asks = levels[1][:depth] if levels[1] else []

            if not bids or not asks:
                return {"error": "Empty orderbook"}

            # Parse prices and sizes
            best_bid_px = float(bids[0]["px"])
            best_bid_sz = float(bids[0]["sz"])
            best_ask_px = float(asks[0]["px"])
            best_ask_sz = float(asks[0]["sz"])

            mid = (best_bid_px + best_ask_px) / 2
            spread = best_ask_px - best_bid_px
            spread_bps = (spread / mid) * 10000

            # Calculate depth within 0.5% of mid
            threshold_bid = mid * 0.995
            threshold_ask = mid * 1.005

            bid_depth_usd = sum(
                float(level["px"]) * float(level["sz"])
                for level in bids
                if float(level["px"]) >= threshold_bid
            )

            ask_depth_usd = sum(
                float(level["px"]) * float(level["sz"])
                for level in asks
                if float(level["px"]) <= threshold_ask
            )

            imbalance = bid_depth_usd / ask_depth_usd if ask_depth_usd > 0 else 999

            # Identify significant liquidity levels
            liquidity_levels = self._identify_liquidity_levels(bids, asks, mid)

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mid_price": round(mid, 2),
                "best_bid": round(best_bid_px, 2),
                "best_ask": round(best_ask_px, 2),
                "best_bid_size": round(best_bid_sz, 6),
                "best_ask_size": round(best_ask_sz, 6),
                "spread": round(spread, 2),
                "spread_bps": round(spread_bps, 2),
                "imbalance_ratio": round(imbalance, 2),
                "bid_depth_0.5pct": round(bid_depth_usd, 0),
                "ask_depth_0.5pct": round(ask_depth_usd, 0),
                "top_bids": [
                    {"px": round(float(b["px"]), 2), "sz": round(float(b["sz"]), 6)}
                    for b in bids[:5]
                ],
                "top_asks": [
                    {"px": round(float(a["px"]), 2), "sz": round(float(a["sz"]), 6)}
                    for a in asks[:5]
                ],
                "liquidity_levels": liquidity_levels,
                "signal": self._interpret_orderbook_signal(imbalance, spread_bps)
            }

        except Exception as e:
            self._logger.error(f"Orderbook fetch error for {asset}: {e}")
            return {"error": str(e)}

    def _identify_liquidity_levels(self, bids: List, asks: List, mid: float) -> List[Dict]:
        """
        Find significant liquidity concentrations (large orders).

        Large orders often act as support (bids) or resistance (asks).

        Args:
            bids: List of bid levels with px and sz
            asks: List of ask levels with px and sz
            mid: Current mid price

        Returns:
            List of liquidity levels with price, size, type, and strength
        """
        levels = []

        # Calculate size distribution
        all_sizes = [float(b["sz"]) for b in bids] + [float(a["sz"]) for a in asks]
        if not all_sizes:
            return []

        median_size = statistics.median(all_sizes)
        threshold_strong = median_size * 5
        threshold_medium = median_size * 3

        # Check bids for support levels
        for level in bids:
            sz = float(level["sz"])
            px = float(level["px"])

            if sz > threshold_medium:
                strength = "very_strong" if sz > threshold_strong else "strong" if sz > threshold_medium * 1.5 else "medium"
                levels.append({
                    "price": round(px, 2),
                    "size": round(sz, 6),
                    "type": "support",
                    "strength": strength,
                    "distance_bps": round(((px - mid) / mid) * 10000, 2)
                })

        # Check asks for resistance levels
        for level in asks:
            sz = float(level["sz"])
            px = float(level["px"])

            if sz > threshold_medium:
                strength = "very_strong" if sz > threshold_strong else "strong" if sz > threshold_medium * 1.5 else "medium"
                levels.append({
                    "price": round(px, 2),
                    "size": round(sz, 6),
                    "type": "resistance",
                    "strength": strength,
                    "distance_bps": round(((px - mid) / mid) * 10000, 2)
                })

        # Sort by distance from mid price
        return sorted(levels, key=lambda x: abs(x["distance_bps"]))[:10]

    def _interpret_orderbook_signal(self, imbalance: float, spread_bps: float) -> str:
        """
        Interpret orderbook state into trading signal.

        Args:
            imbalance: bid_depth / ask_depth ratio
            spread_bps: Spread in basis points

        Returns:
            Signal interpretation: "strong_bullish", "bullish", "neutral", etc.
        """
        if spread_bps > 20:
            return "illiquid"  # Wide spread = avoid trading

        if imbalance > 2.5:
            return "strong_bullish"
        elif imbalance > 1.5:
            return "bullish"
        elif imbalance > 0.8:
            return "neutral"
        elif imbalance > 0.4:
            return "bearish"
        else:
            return "strong_bearish"

    async def get_candles(
        self,
        asset: str,
        interval: str = "1m",
        lookback_bars: int = 50
    ) -> Dict:
        """
        Fetch candlestick data and calculate derived metrics.

        Args:
            asset: Trading pair symbol
            interval: Candle interval ("1m", "5m", "15m", "1h", "4h", "1d")
            lookback_bars: Number of historical bars to fetch

        Returns:
            Dictionary containing:
            - candles: Recent OHLCV data
            - indicators: Technical indicators (EMA, RSI, MACD, ATR, etc.)
            - volume_analysis: Volume patterns and delta
            - price_action: Recent price movement summary
        """
        try:
            # Map interval to seconds
            interval_map = {
                "1m": 60, "5m": 300, "15m": 900,
                "1h": 3600, "4h": 14400, "1d": 86400
            }
            seconds_per_bar = interval_map.get(interval, 60)

            # Calculate time range
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)  # milliseconds
            start_time = end_time - (lookback_bars * seconds_per_bar * 1000)

            # Fetch candles from Hyperliquid
            candles_raw = await asyncio.to_thread(
                self.info.candles_snapshot,
                asset,
                interval,
                start_time,
                end_time
            )

            if not candles_raw or len(candles_raw) == 0:
                return {"error": "No candles data available"}

            # Parse candles
            candles = []
            for c in candles_raw:
                candles.append({
                    "timestamp": c["t"],
                    "open": float(c["o"]),
                    "high": float(c["h"]),
                    "low": float(c["l"]),
                    "close": float(c["c"]),
                    "volume": float(c["v"])
                })

            if len(candles) < 10:
                return {"error": "Insufficient candle data"}

            # Calculate indicators
            if PANDAS_AVAILABLE:
                indicators = self._calculate_indicators_pandas(candles)
            else:
                indicators = self._calculate_indicators_simple(candles)

            # Volume analysis
            volume_analysis = self._analyze_volume(candles)

            # Price action summary
            price_action = self._summarize_price_action(candles, interval)

            return {
                "interval": interval,
                "bar_count": len(candles),
                "candles": candles[-5:],  # Last 5 for context
                "indicators": indicators,
                "volume_analysis": volume_analysis,
                "price_action": price_action
            }

        except Exception as e:
            self._logger.error(f"Candles fetch error for {asset} {interval}: {e}")
            return {"error": str(e)}

    def _calculate_indicators_pandas(self, candles: List[Dict]) -> Dict:
        """Calculate technical indicators using pandas (if available)."""
        df = pd.DataFrame(candles)

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])

        # Trend indicators: EMA
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

        # Momentum: RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))

        delta_7 = df['close'].diff()
        gain_7 = (delta_7.where(delta_7 > 0, 0)).rolling(window=7).mean()
        loss_7 = (-delta_7.where(delta_7 < 0, 0)).rolling(window=7).mean()
        rs_7 = gain_7 / loss_7
        df['rsi_7'] = 100 - (100 / (1 + rs_7))

        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Volatility: ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr_14'] = true_range.rolling(14).mean()

        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

        # Extract latest values
        latest = df.iloc[-1]

        return {
            "ema_20": round(float(latest['ema_20']), 2) if pd.notna(latest['ema_20']) else None,
            "ema_50": round(float(latest['ema_50']), 2) if pd.notna(latest['ema_50']) else None,
            "rsi_14": round(float(latest['rsi_14']), 2) if pd.notna(latest['rsi_14']) else None,
            "rsi_7": round(float(latest['rsi_7']), 2) if pd.notna(latest['rsi_7']) else None,
            "macd": round(float(latest['macd']), 2) if pd.notna(latest['macd']) else None,
            "macd_signal": round(float(latest['macd_signal']), 2) if pd.notna(latest['macd_signal']) else None,
            "macd_hist": round(float(latest['macd_hist']), 2) if pd.notna(latest['macd_hist']) else None,
            "atr_14": round(float(latest['atr_14']), 2) if pd.notna(latest['atr_14']) else None,
            "bb_upper": round(float(latest['bb_upper']), 2) if pd.notna(latest['bb_upper']) else None,
            "bb_middle": round(float(latest['bb_middle']), 2) if pd.notna(latest['bb_middle']) else None,
            "bb_lower": round(float(latest['bb_lower']), 2) if pd.notna(latest['bb_lower']) else None,
        }

    def _calculate_indicators_simple(self, candles: List[Dict]) -> Dict:
        """Simplified indicator calculation without pandas."""
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]

        # Simple moving average (SMA) helper
        def sma(values, period):
            if len(values) < period:
                return None
            return sum(values[-period:]) / period

        # Exponential moving average (EMA) helper
        def ema(values, period):
            if len(values) < period:
                return None
            multiplier = 2 / (period + 1)
            ema_val = sma(values[:period], period)
            for price in values[period:]:
                ema_val = (price - ema_val) * multiplier + ema_val
            return ema_val

        # Simple RSI
        def rsi(values, period):
            if len(values) < period + 1:
                return None
            deltas = [values[i] - values[i-1] for i in range(1, len(values))]
            gains = [d if d > 0 else 0 for d in deltas[-period:]]
            losses = [-d if d < 0 else 0 for d in deltas[-period:]]
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                return 100
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        return {
            "ema_20": round(ema(closes, 20), 2) if ema(closes, 20) else None,
            "ema_50": round(ema(closes, 50), 2) if ema(closes, 50) else None,
            "rsi_14": round(rsi(closes, 14), 2) if rsi(closes, 14) else None,
            "rsi_7": round(rsi(closes, 7), 2) if rsi(closes, 7) else None,
            "sma_20": round(sma(closes, 20), 2) if sma(closes, 20) else None,
            "atr_14": round(sma([h - l for h, l in zip(highs[-14:], lows[-14:])], 14), 2) if len(highs) >= 14 else None,
        }

    def _analyze_volume(self, candles: List[Dict]) -> Dict:
        """
        Analyze volume patterns and estimate delta.

        Volume delta = buy volume - sell volume
        Positive delta = accumulation (bullish)
        Negative delta = distribution (bearish)
        """
        if len(candles) < 20:
            return {"error": "Insufficient data for volume analysis"}

        volumes = [c['volume'] for c in candles]
        avg_volume = sum(volumes[-20:]) / 20
        latest_volume = volumes[-1]
        volume_spike = latest_volume / avg_volume if avg_volume > 0 else 1.0

        # Estimate buy/sell volume from price movement
        # If close > open → more buying pressure
        # If close < open → more selling pressure
        buy_volume_estimate = sum(
            c['volume'] if c['close'] > c['open'] else 0
            for c in candles[-10:]
        )
        sell_volume_estimate = sum(
            c['volume'] if c['close'] < c['open'] else 0
            for c in candles[-10:]
        )

        delta = buy_volume_estimate - sell_volume_estimate
        total = buy_volume_estimate + sell_volume_estimate
        delta_pct = (delta / total * 100) if total > 0 else 0

        # Cumulative delta over longer period
        cumulative_delta = sum(
            c['volume'] * (1 if c['close'] > c['open'] else -1)
            for c in candles[-20:]
        )

        signal = "accumulation" if cumulative_delta > 0 else "distribution"

        return {
            "current_volume": round(latest_volume, 2),
            "avg_volume": round(avg_volume, 2),
            "volume_spike": round(volume_spike, 2),
            "buy_volume_estimate": round(buy_volume_estimate, 2),
            "sell_volume_estimate": round(sell_volume_estimate, 2),
            "delta_estimate": round(delta, 2),
            "delta_pct": round(delta_pct, 2),
            "cumulative_delta": round(cumulative_delta, 2),
            "trend": signal,
            "signal": "bullish" if delta > 0 else "bearish"
        }

    def _summarize_price_action(self, candles: List[Dict], interval: str) -> Dict:
        """Summarize recent price action patterns."""
        if len(candles) < 5:
            return {}

        latest = candles[-1]
        prev_1 = candles[-2] if len(candles) >= 2 else candles[-1]
        prev_5 = candles[-6] if len(candles) >= 6 else candles[0]

        # Price changes
        change_1bar = latest['close'] - prev_1['close']
        change_5bars = latest['close'] - prev_5['close']

        # Range calculation
        recent_high = max(c['high'] for c in candles[-20:])
        recent_low = min(c['low'] for c in candles[-20:])
        range_pct = ((recent_high - recent_low) / latest['close']) * 100

        # Candle pattern detection
        body = latest['close'] - latest['open']
        upper_wick = latest['high'] - max(latest['open'], latest['close'])
        lower_wick = min(latest['open'], latest['close']) - latest['low']
        total_range = latest['high'] - latest['low']

        pattern = "neutral"
        if total_range > 0:
            if abs(body / total_range) > 0.7:
                pattern = "strong_trend"
            elif upper_wick > abs(body) * 2:
                pattern = "rejection_high"  # Bearish
            elif lower_wick > abs(body) * 2:
                pattern = "rejection_low"  # Bullish
            elif abs(body / total_range) < 0.3:
                pattern = "consolidation"

        return {
            "last_close": round(latest['close'], 2),
            "last_open": round(latest['open'], 2),
            "last_high": round(latest['high'], 2),
            "last_low": round(latest['low'], 2),
            "change_1bar": round(change_1bar, 2),
            "change_5bars": round(change_5bars, 2),
            "high_20bars": round(recent_high, 2),
            "low_20bars": round(recent_low, 2),
            "range_pct": round(range_pct, 2),
            "candle_pattern": pattern,
            "body_size": round(body, 2),
            "upper_wick": round(upper_wick, 2),
            "lower_wick": round(lower_wick, 2)
        }

    async def get_comprehensive_market_data(self, asset: str) -> Dict:
        """
        Fetch all market data for an asset in parallel.

        Combines orderbook, multiple timeframe candles, and perpetual data
        into a single comprehensive snapshot.

        Args:
            asset: Trading pair symbol

        Returns:
            Complete market microstructure snapshot
        """
        try:
            # Fetch all data sources in parallel
            orderbook_task = self.get_orderbook_snapshot(asset)
            candles_1m_task = self.get_candles(asset, "1m", 50)
            candles_5m_task = self.get_candles(asset, "5m", 50)
            candles_4h_task = self.get_candles(asset, "4h", 50)

            orderbook, candles_1m, candles_5m, candles_4h = await asyncio.gather(
                orderbook_task,
                candles_1m_task,
                candles_5m_task,
                candles_4h_task,
                return_exceptions=True
            )

            # Handle errors gracefully
            if isinstance(orderbook, Exception):
                orderbook = {"error": str(orderbook)}
            if isinstance(candles_1m, Exception):
                candles_1m = {"error": str(candles_1m)}
            if isinstance(candles_5m, Exception):
                candles_5m = {"error": str(candles_5m)}
            if isinstance(candles_4h, Exception):
                candles_4h = {"error": str(candles_4h)}

            return {
                "asset": asset,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "orderbook": orderbook,
                "candles_1m": candles_1m,
                "candles_5m": candles_5m,
                "candles_4h": candles_4h,
            }

        except Exception as e:
            self._logger.error(f"Comprehensive data fetch error for {asset}: {e}")
            return {"asset": asset, "error": str(e)}
