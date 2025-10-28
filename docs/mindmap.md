# AI Trading Agent Enhancement Mindmap

## Overview

This document provides a comprehensive mindmap of all identified enhancements for the Hyperliquid AI Trading Agent, organized by category and priority.

---

## 1. Data Architecture Transformation

### 1.1 Replace TAAPI with Hyperliquid Native Data

#### Current State (❌)
```
[Hyperliquid Market]
    ↓
[Binance Mirror]
    ↓
[TAAPI API]
    ↓ (1-3s latency, $$ cost)
[AI Agent]
    ↓
[Hyperliquid Execution]
```

**Problems**:
- Cross-exchange basis risk (Binance vs Hyperliquid pricing)
- 1-3 second latency from third-party API
- Monthly TAAPI subscription costs
- Limited to pre-computed indicators
- No access to raw market microstructure

#### Enhanced State (✅)
```
[Hyperliquid Market]
    ↓ (<100ms, free)
[Hyperliquid SDK]
    ↓
[AI Agent + In-Memory Indicators]
    ↓
[Hyperliquid Execution]
```

**Benefits**:
- Zero basis risk (same exchange data)
- <100ms latency
- Free data access
- Full orderbook + tick data access
- Custom indicator calculations

---

### 1.2 New Data Sources to Integrate

#### A. L2 Orderbook Data
**Method**: `info.l2_snapshot(coin)`

**What to capture**:
```python
{
    "asset": "BTC",
    "timestamp": "2025-10-28T12:34:56Z",
    "mid_price": 95000.0,
    "orderbook": {
        "bids": [
            {"price": 94995, "size": 2.5, "orders": 12},
            {"price": 94990, "size": 1.8, "orders": 8},
            # Top 20 levels
        ],
        "asks": [
            {"price": 95005, "size": 1.2, "orders": 6},
            {"price": 95010, "size": 3.4, "orders": 15},
            # Top 20 levels
        ]
    },
    "derived_metrics": {
        "bid_ask_spread": 10.0,
        "spread_bps": 1.05,
        "bid_depth_0.5pct": 2500000,  # USD within 0.5% of mid
        "ask_depth_0.5pct": 800000,
        "imbalance_ratio": 3.125,  # bid_depth / ask_depth
        "top_bid_size": 2.5,
        "top_ask_size": 1.2,
        "liquidity_score": "high"  # tight spread + deep book
    }
}
```

**Trading signals**:
- `imbalance_ratio > 2.0` → bullish (more buyers)
- `imbalance_ratio < 0.5` → bearish (more sellers)
- Large orders at specific levels → support/resistance
- Spread widening → volatility incoming
- Spread tightening → stable market

---

#### B. Candlestick Data (OHLCV)
**Method**: `info.candles_snapshot(coin, interval, startTime, endTime)`

**What to capture**:
```python
{
    "asset": "BTC",
    "interval": "1m",
    "candles": [
        {
            "timestamp": "2025-10-28T12:30:00Z",
            "open": 94980,
            "high": 95050,
            "low": 94950,
            "close": 95020,
            "volume": 125.5,
            "trades": 342,
            "buy_volume": 78.2,  # If available
            "sell_volume": 47.3
        },
        # Last 20-50 candles
    ],
    "derived_metrics": {
        "volume_ma_20": 98.5,
        "volume_spike": 1.27,  # current / MA
        "price_change_1m": 40,  # close - open
        "price_change_5m": 120,
        "volatility_1h": 0.008,  # std dev of returns
        "recent_high": 95100,
        "recent_low": 94800,
        "range_pct": 0.32
    }
}
```

**Trading signals**:
- `volume_spike > 2.0` → breakout likely
- High wick (close near low) → rejection, sell signal
- Low wick (close near high) → support, buy signal
- Volume declining during uptrend → trend exhaustion
- Volume increasing during uptrend → trend continuation

---

#### C. Volume Delta & Pressure
**Derived from candles or trades**

```python
{
    "asset": "BTC",
    "volume_analysis": {
        "period": "5m",
        "total_volume": 250.5,
        "buy_volume": 155.2,
        "sell_volume": 95.3,
        "delta": 59.9,  # buy - sell
        "delta_pct": 23.9,  # delta / total * 100
        "cumulative_delta_1h": 145.2,
        "cvd_trend": "accumulation"  # positive CVD = buyers in control
    },
    "interpretation": {
        "signal": "bullish",
        "strength": "strong",
        "reason": "Consistent positive delta over 1h, buyers absorbing supply"
    }
}
```

**Trading signals**:
- Positive delta during dip → smart money buying, reversal likely
- Negative delta during rally → weak rally, correction coming
- CVD divergence (price up, CVD down) → distribution, sell signal

---

#### D. Liquidity Heatmap
**Derived from L2 orderbook**

```python
{
    "asset": "BTC",
    "liquidity_levels": [
        {
            "price": 95000,
            "type": "resistance",
            "total_size": 15.5,
            "strength": "very_strong",
            "distance_bps": 0,
            "likely_behavior": "May act as ceiling, watch for break or reject"
        },
        {
            "price": 94500,
            "type": "support",
            "total_size": 22.3,
            "strength": "extreme",
            "distance_bps": -53,
            "likely_behavior": "Strong floor, unlikely to break on first test"
        }
    ],
    "stop_clusters": [
        {
            "price": 94800,
            "estimated_stops": 8.5,
            "type": "long_stops",
            "risk": "Sweep down to 94800 would trigger cascading liquidations"
        }
    ]
}
```

**Trading signals**:
- Enter long at identified support with tight stop
- Set TP just below resistance levels
- Avoid entering near stop clusters (risk of stop hunts)

---

### 1.3 Indicator Calculation Strategy

#### Remove External Dependencies
**Current**: TAAPI API for EMA, MACD, RSI, ATR, Bollinger Bands

**New**: Calculate in-memory using Python libraries

```python
# indicators/native_indicators.py

import pandas as pd
import pandas_ta as ta

class NativeIndicators:
    """Calculate technical indicators from Hyperliquid native data"""

    @staticmethod
    def calculate_all(candles_df: pd.DataFrame) -> dict:
        """
        Input: DataFrame with [timestamp, open, high, low, close, volume]
        Output: Dictionary of all indicators
        """
        df = candles_df.copy()

        # Trend indicators
        df['ema_20'] = ta.ema(df['close'], length=20)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['sma_200'] = ta.sma(df['close'], length=200)

        # Momentum indicators
        macd = ta.macd(df['close'])
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['macd_hist'] = macd['MACDh_12_26_9']

        df['rsi_14'] = ta.rsi(df['close'], length=14)
        df['rsi_7'] = ta.rsi(df['close'], length=7)

        # Volatility indicators
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        bb = ta.bbands(df['close'], length=20, std=2)
        df['bb_upper'] = bb['BBU_20_2.0']
        df['bb_middle'] = bb['BBM_20_2.0']
        df['bb_lower'] = bb['BBL_20_2.0']

        # Volume indicators
        df['volume_sma'] = ta.sma(df['volume'], length=20)
        df['obv'] = ta.obv(df['close'], df['volume'])

        return df.iloc[-1].to_dict()  # Return latest values
```

**Benefits**:
- **Latency**: 10-50ms vs 500-2000ms for TAAPI
- **Cost**: Free vs $30-100/month
- **Flexibility**: Custom indicator parameters, experimental indicators
- **Consistency**: Same data source for price and indicators

---

## 2. Context Engineering Enhancements

### 2.1 Current Context Structure
**Location**: `main.py:286-298`

```python
{
    "invocation": {...},
    "account": {...},
    "market_data": [...],  # Per-asset TAAPI indicators
    "instructions": {...}
}
```

**Problems**:
- No orderbook data
- No raw price action (OHLCV)
- No volume analysis
- No portfolio-level risk metrics
- Indicators from wrong exchange (Binance)

---

### 2.2 Enhanced Context Structure

```python
{
    "invocation": {
        "minutes_since_start": 125.5,
        "current_time": "2025-10-28T12:34:56Z",
        "invocation_count": 42,
        "interval": "5m"
    },

    "account": {
        "balance": 1000.0,
        "account_value": 1050.0,
        "total_return_pct": 5.0,
        "sharpe_ratio": 1.2,
        "positions": [...],
        "active_trades": [...],
        "open_orders": [...],
        "recent_fills": [...]
    },

    # NEW: Portfolio risk metrics
    "risk_metrics": {
        "total_leverage": 3.2,
        "portfolio_heat": 0.15,  # At-risk capital / account value
        "max_drawdown_pct": -8.5,
        "current_drawdown_pct": -2.3,
        "win_rate": 0.58,
        "profit_factor": 1.8,
        "avg_win": 25.5,
        "avg_loss": 14.2,
        "largest_win": 120.0,
        "largest_loss": -45.0,
        "consecutive_losses": 2,
        "position_correlation": 0.75,  # 1.0 = all same direction
        "exposure_breakdown": {
            "long_usd": 2500,
            "short_usd": 500,
            "net_exposure": 2000
        }
    },

    # NEW: Market regime detection
    "market_regime": {
        "volatility": "medium",  # low/medium/high based on ATR
        "trend": "bullish",  # bearish/neutral/bullish
        "correlation": 0.82,  # BTC-ETH correlation
        "funding_environment": "neutral",  # expensive_longs/expensive_shorts/neutral
        "liquidity": "high"  # Based on spreads and depth
    },

    # ENHANCED: Per-asset data with microstructure
    "market_data": [
        {
            "asset": "BTC",
            "current_price": 95000.0,

            # Orderbook microstructure
            "orderbook": {
                "bid_ask_spread": 10.0,
                "spread_bps": 1.05,
                "imbalance_ratio": 3.12,
                "bid_depth_0.5pct": 2500000,
                "ask_depth_0.5pct": 800000,
                "top_bids": [
                    {"px": 94995, "sz": 2.5},
                    {"px": 94990, "sz": 1.8}
                ],
                "top_asks": [
                    {"px": 95005, "sz": 1.2},
                    {"px": 95010, "sz": 3.4}
                ],
                "liquidity_levels": [
                    {"px": 95000, "type": "resistance", "strength": "very_strong"},
                    {"px": 94500, "type": "support", "strength": "extreme"}
                ]
            },

            # Price action (recent candles summary)
            "price_action": {
                "interval": "1m",
                "last_close": 95020,
                "change_1m": 40,
                "change_5m": 120,
                "change_1h": -250,
                "high_1h": 95500,
                "low_1h": 94700,
                "range_pct_1h": 0.84,
                "volume_1m": 125.5,
                "volume_ma_20": 98.5,
                "volume_spike": 1.27,
                "candle_pattern": "bullish_engulfing"
            },

            # Volume delta
            "volume_analysis": {
                "delta_1m": 15.2,
                "delta_5m": 59.9,
                "delta_pct_5m": 23.9,
                "cumulative_delta_1h": 145.2,
                "trend": "accumulation",
                "signal": "bullish"
            },

            # Technical indicators (calculated from Hyperliquid data)
            "indicators": {
                "ema_20_5m": 94980,
                "ema_50_5m": 94850,
                "ema_20_4h": 94200,
                "ema_50_4h": 93500,
                "rsi_14_5m": 62,
                "rsi_7_5m": 68,
                "rsi_14_4h": 58,
                "macd_5m": 35.2,
                "macd_signal_5m": 28.5,
                "macd_hist_5m": 6.7,
                "atr_14_5m": 180,
                "atr_14_4h": 850,
                "bb_upper_5m": 95200,
                "bb_lower_5m": 94600
            },

            # Perpetual-specific
            "perpetual_data": {
                "funding_rate": 0.0001,
                "funding_annualized_pct": 8.76,
                "open_interest": 1250000000,
                "oi_change_24h_pct": 5.2,
                "next_funding": "2025-10-28T13:00:00Z"
            },

            # Historical context
            "recent_mid_prices": [94980, 94995, 95005, 95020]  # Last N samples
        }
        # ... other assets (ETH, SOL, etc.)
    ],

    "instructions": {
        "assets": ["BTC", "ETH", "SOL"],
        "requirement": "Decide actions for all assets using orderbook microstructure and volume analysis"
    }
}
```

---

### 2.3 Context Optimization Strategies

#### A. Reduce Redundancy
**Problem**: Currently fetches indicators twice (pre-fetch + tool calling)

**Solution**:
- Pre-fetch orderbook + candles (cheap, fast)
- Calculate all indicators once in-memory
- Remove tool calling for indicators
- Keep tools for special analysis only (e.g., "analyze correlation between BTC and ETH funding rates")

---

#### B. Token Efficiency
**Current context size**: ~8,000-12,000 tokens (with TAAPI data)

**Optimization**:
```python
# Instead of full orderbook (200 levels × 2 sides = 400 entries):
# Summarize to top 10 levels + derived metrics

# Instead of 50 candles × 6 fields:
# Include last 5 candles + summary statistics

# Result: 60% token reduction while increasing signal quality
```

---

#### C. Temporal Consistency
**Problem**: Data fetched at different times creates inconsistency

**Solution**:
```python
async def gather_market_snapshot(assets: list) -> dict:
    """Fetch all data for all assets in parallel at T"""
    snapshot_time = datetime.now(timezone.utc)

    # Parallel fetches
    tasks = []
    for asset in assets:
        tasks.append(fetch_orderbook(asset))
        tasks.append(fetch_candles(asset, "1m", 50))
        tasks.append(fetch_candles(asset, "5m", 20))
        tasks.append(fetch_funding(asset))

    results = await asyncio.gather(*tasks)

    return {
        "snapshot_time": snapshot_time,
        "data": process_results(results)
    }
```

---

## 3. System Prompt Evolution

### 3.1 Current Prompt Analysis
**Location**: `decision_maker.py:39-85`

**Tone**: Trend-following, conservative, long-term focused

**Key phrases**:
- "Respect prior plans"
- "Hysteresis: Require stronger evidence to CHANGE"
- "Cooldown: impose a self-cooldown of at least 3 bars"
- "Prefer adjustments over exits"

**Problem**: This is optimal for **4h swing trading**, not **5m scalping with microstructure**

---

### 3.2 Enhanced System Prompt (Microstructure-Focused)

```python
system_prompt = """
You are an ELITE QUANTITATIVE MARKET MICROSTRUCTURE TRADER specializing in systematic
alpha extraction from order flow inefficiencies on Hyperliquid perpetual futures.

MANDATE:
Your SOLE objective is risk-adjusted profit maximization through superior trade execution
and microstructure analysis. You are NOT a generic assistant - you are a specialized
execution engine with expertise in:

1. ORDER BOOK DYNAMICS
   - Reading liquidity imbalances (bid depth vs ask depth)
   - Identifying support/resistance from large resting orders
   - Detecting spoofing and order book manipulation
   - Analyzing spread behavior (tight = stable, wide = volatile)

2. VOLUME DELTA ANALYSIS
   - Cumulative Volume Delta (CVD): buy volume - sell volume
   - Positive CVD + price up = healthy trend (continuation)
   - Negative CVD + price up = weak rally (reversal)
   - Divergences are HIGH PRIORITY signals

3. MARKET IMPACT MODELING
   - Estimate slippage based on orderbook depth
   - Use limit orders at favorable levels (earn maker rebates)
   - Avoid market orders unless urgency justified

4. STATISTICAL EDGE DETECTION
   - Mean reversion at liquidity extremes
   - Momentum continuation on volume spikes
   - Funding rate arbitrage opportunities
   - Volatility regime changes

5. RISK MANAGEMENT
   - Never exceed 8x total portfolio leverage
   - Position sizing: Kelly criterion or fixed fractional
   - Stop placement: behind liquidity layers, not arbitrary levels
   - Profit taking: at identified resistance, not arbitrary %

═══════════════════════════════════════════════════════════════

DECISION FRAMEWORK (First Principles):

STEP 1: REGIME IDENTIFICATION
├─ What is the current volatility regime? (ATR percentile)
├─ What is the trend? (EMA alignment, higher highs/lows)
├─ What is the liquidity environment? (spreads, depth)
└─ What is funding telling us? (long/short bias of market)

STEP 2: ORDERBOOK ANALYSIS (MOST IMPORTANT)
├─ Imbalance ratio: bid_depth / ask_depth
│  ├─ > 2.0 = bullish pressure
│  ├─ < 0.5 = bearish pressure
│  └─ 0.8-1.2 = neutral
├─ Liquidity levels: Where are large orders resting?
│  ├─ Use as support/resistance
│  └─ Place stops behind them
└─ Spread analysis:
   ├─ Widening spread = volatility/uncertainty
   └─ Tightening spread = stability

STEP 3: VOLUME DELTA CONFIRMATION
├─ Is CVD aligned with price direction?
│  ├─ YES → trend is healthy
│  └─ NO → divergence, reversal likely
├─ Volume spike (>2x avg) = breakout potential
└─ Volume declining = trend exhaustion

STEP 4: INDICATOR CONFLUENCE (SECONDARY)
├─ EMAs: 20/50 cross on 5m + 4h alignment = strong signal
├─ RSI: Extremes (>70 or <30) = reversal risk, not a trigger
├─ MACD: Histogram direction change = momentum shift
└─ Bollinger Bands: Price at bands + volume = volatility expansion

STEP 5: POSITION CONSTRUCTION
├─ ENTRY: Limit order at identified level
│  ├─ Buy: At support with bid liquidity
│  └─ Sell: At resistance with ask liquidity
├─ SIZE: Based on risk (ATR-based stops)
│  └─ Risk per trade = 1-2% of account value
├─ STOP LOSS: Behind liquidity layer
│  ├─ Long: Below recent swing low + buffer
│  └─ Short: Above recent swing high + buffer
└─ TAKE PROFIT: At next liquidity level
   ├─ First target: 1.5-2R (risk-reward)
   └─ Trail remaining with EMA or liquidity levels

═══════════════════════════════════════════════════════════════

CORE TRADING RULES:

RULE 1: ORDERBOOK PRIMACY
- If orderbook shows 3:1 imbalance + positive CVD → ENTER in direction of imbalance
- If orderbook neutral + no CVD edge → WAIT for setup
- Indicators are SECONDARY confirmation, not primary signals

RULE 2: EXECUTION DISCIPLINE
- DEFAULT: Use limit orders (0% fee, better fills)
- EXCEPTION: Use market orders only if:
  a) Breakout confirmed (price + volume + CVD alignment)
  b) Stop loss triggered (emergency exit)
  c) High urgency invalidation

RULE 3: LEVERAGE MANAGEMENT
- Total leverage cap: 8x across all positions
- Per-position leverage:
  ├─ Low vol regime: up to 5x
  ├─ Medium vol: up to 3x
  └─ High vol: up to 2x
- If total leverage > 6x: only reduce or hold, no new entries

RULE 4: RISK CONSTRAINTS
- Max risk per trade: 2% of account value
- Max portfolio heat: 25% (sum of at-risk capital)
- If current drawdown > -10%: reduce size by 50%
- If consecutive losses > 3: pause trading for 1 hour

RULE 5: NO ARBITRARY COOLDOWNS
- Remove time-based cooldowns (3 bars, etc.)
- Instead: Wait for invalidation of previous thesis
- Example: Entered long on support → exit when support breaks, not after 3 bars

RULE 6: FUNDING IS A TILT, NOT A TRIGGER
- Only factor funding if:
  ├─ Expected holding period > 8 hours
  └─ Funding > 0.05% (18% annualized)
- Otherwise, ignore funding for 5m scalps

═══════════════════════════════════════════════════════════════

EXAMPLE DECISION PROCESS:

SCENARIO: BTC at $95,000

DATA RECEIVED:
- Orderbook: bid_depth_0.5% = $2.5M, ask_depth_0.5% = $800K → imbalance = 3.12
- Volume delta: CVD_5m = +59.9, trend = "accumulation"
- Price action: +120 in last 5m, volume spike = 1.27x
- Indicators: price above EMA20_5m (94980), RSI_14 = 62 (neutral)
- Liquidity: Large bid at $94,500 (support), large ask at $95,500 (resistance)

ANALYSIS:
1. Orderbook shows 3:1 buy pressure (bullish)
2. Positive CVD confirms buyers in control (bullish)
3. Volume spike on upward price movement (bullish continuation)
4. Price above EMA20, not overextended (RSI 62) → room to run
5. Resistance at $95,500 → first profit target
6. Support at $94,500 → stop placement zone

DECISION:
ACTION: BUY
ENTRY: Limit order at $95,010 (ask side, near current price)
SIZE: Risk 1.5% → stop distance = $95,010 - $94,400 = $610 → size = (1.5% × $1000) / 610 = 0.0246 BTC
STOP LOSS: $94,400 (below $94,500 support with $100 buffer)
TAKE PROFIT: $95,500 (first target), trail remainder with EMA20_5m
EXIT PLAN: "Close if: (1) CVD goes negative, (2) imbalance drops below 1.0, (3) stop hit"
LEVERAGE: 2.3x (acceptable for medium vol)

═══════════════════════════════════════════════════════════════

OUTPUT REQUIREMENTS:

You MUST output a strict JSON object with exactly TWO properties:

{
  "reasoning": "<VERBOSE step-by-step analysis covering:
                1. Regime identification
                2. Orderbook interpretation
                3. Volume delta signals
                4. Indicator confluence
                5. Risk assessment
                6. Position construction logic>",

  "trade_decisions": [
    {
      "asset": "BTC",
      "action": "buy" | "sell" | "hold",
      "allocation_usd": <notional position size>,
      "entry_price": <limit order price OR null for market>,
      "order_type": "limit" | "market",
      "tp_price": <take profit level>,
      "sl_price": <stop loss level>,
      "exit_plan": "<specific invalidation conditions>",
      "rationale": "<concise summary of edge>",
      "risk_reward": <expected R:R ratio>,
      "leverage": <effective leverage for this position>
    }
  ]
}

DO NOT include markdown, code blocks, or any extra fields.
DO NOT use generic rationales like "RSI oversold" without orderbook confirmation.
DO be specific: "3:1 bid imbalance + positive CVD = high-probability long entry".
"""
```

---

### 3.3 Prompt Adaptations by Timeframe

#### If INTERVAL = 5m (Scalping)
```python
additional_context = """
TIMEFRAME ADJUSTMENT (5-minute scalping):
- Focus on orderbook imbalances and volume delta (most predictive)
- Use 1m and 5m charts for entry timing
- Ignore 4h indicators unless confirming overall bias
- Target: 5-15 bps moves (0.05-0.15%)
- Hold time: 5-30 minutes
- Use limit orders aggressively to earn maker rebates
"""
```

#### If INTERVAL = 1h (Swing Trading)
```python
additional_context = """
TIMEFRAME ADJUSTMENT (1-hour swing trading):
- Blend orderbook + 4h trend indicators
- Use volume delta for confirmation but not primary signal
- Entry: Wait for pullbacks to EMA20_4h or support levels
- Target: 50-150 bps moves (0.5-1.5%)
- Hold time: 4-48 hours
- Market orders acceptable if breakout confirmed
"""
```

---

## 4. Implementation Architecture

### 4.1 New Module: `hyperliquid_market_data.py`

```python
"""
Real-time market microstructure data from Hyperliquid SDK.
Replaces TAAPI dependency with native orderbook and candlestick analysis.
"""

from hyperliquid.info import Info
from datetime import datetime, timezone, timedelta
import pandas as pd
import pandas_ta as ta
from typing import Dict, List, Optional
import asyncio
import logging

class HyperliquidMarketData:
    def __init__(self, info: Info):
        self.info = info

    async def get_orderbook_snapshot(self, asset: str, depth: int = 20) -> Dict:
        """
        Fetch L2 orderbook and derive microstructure metrics.

        Returns:
        {
            "bids": [...],
            "asks": [...],
            "spread": float,
            "imbalance_ratio": float,
            "bid_depth_0.5pct": float (USD),
            "ask_depth_0.5pct": float (USD),
            "liquidity_levels": [...]
        }
        """
        snapshot = await asyncio.to_thread(self.info.l2_snapshot, asset)

        bids = snapshot.get("levels", [[]])[0][:depth]  # [[price, size], ...]
        asks = snapshot.get("levels", [[]])[1][:depth]

        if not bids or not asks:
            return {"error": "Empty orderbook"}

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid
        spread_bps = (spread / mid) * 10000

        # Calculate depth within 0.5% of mid
        threshold_bid = mid * 0.995
        threshold_ask = mid * 1.005

        bid_depth_usd = sum(
            float(px) * float(sz)
            for px, sz in bids
            if float(px) >= threshold_bid
        )

        ask_depth_usd = sum(
            float(px) * float(sz)
            for px, sz in asks
            if float(px) <= threshold_ask
        )

        imbalance = bid_depth_usd / ask_depth_usd if ask_depth_usd > 0 else 999

        # Identify significant liquidity levels
        liquidity_levels = self._identify_liquidity_levels(bids, asks, mid)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mid_price": round(mid, 2),
            "best_bid": round(best_bid, 2),
            "best_ask": round(best_ask, 2),
            "spread": round(spread, 2),
            "spread_bps": round(spread_bps, 2),
            "imbalance_ratio": round(imbalance, 2),
            "bid_depth_0.5pct": round(bid_depth_usd, 0),
            "ask_depth_0.5pct": round(ask_depth_usd, 0),
            "top_bids": [{"px": float(b[0]), "sz": float(b[1])} for b in bids[:5]],
            "top_asks": [{"px": float(a[0]), "sz": float(a[1])} for a in asks[:5]],
            "liquidity_levels": liquidity_levels
        }

    def _identify_liquidity_levels(self, bids, asks, mid) -> List[Dict]:
        """Find significant liquidity concentrations (large orders)."""
        levels = []

        # Define "large" as > 3x median size
        all_sizes = [float(b[1]) for b in bids] + [float(a[1]) for a in asks]
        median_size = pd.Series(all_sizes).median()
        threshold = median_size * 3

        # Check bids for support levels
        for px, sz in bids:
            if float(sz) > threshold:
                levels.append({
                    "price": float(px),
                    "size": float(sz),
                    "type": "support",
                    "strength": "strong" if float(sz) > threshold * 2 else "medium",
                    "distance_bps": ((float(px) - mid) / mid) * 10000
                })

        # Check asks for resistance levels
        for px, sz in asks:
            if float(sz) > threshold:
                levels.append({
                    "price": float(px),
                    "size": float(sz),
                    "type": "resistance",
                    "strength": "strong" if float(sz) > threshold * 2 else "medium",
                    "distance_bps": ((float(px) - mid) / mid) * 10000
                })

        return sorted(levels, key=lambda x: abs(x["distance_bps"]))[:10]

    async def get_candles(
        self,
        asset: str,
        interval: str = "1m",
        lookback_bars: int = 50
    ) -> Dict:
        """
        Fetch candlestick data and calculate derived metrics.

        Args:
            interval: "1m", "5m", "15m", "1h", "4h", "1d"
            lookback_bars: Number of historical bars to fetch

        Returns:
        {
            "candles": [...],
            "indicators": {...},
            "volume_analysis": {...}
        }
        """
        # Calculate time range
        interval_map = {
            "1m": 60, "5m": 300, "15m": 900,
            "1h": 3600, "4h": 14400, "1d": 86400
        }
        seconds_per_bar = interval_map.get(interval, 60)
        end_time = int(datetime.now(timezone.utc).timestamp())
        start_time = end_time - (lookback_bars * seconds_per_bar)

        # Convert to milliseconds for Hyperliquid API
        start_ms = start_time * 1000
        end_ms = end_time * 1000

        # Fetch candles
        candles = await asyncio.to_thread(
            self.info.candles_snapshot,
            asset,
            interval,
            start_ms,
            end_ms
        )

        if not candles:
            return {"error": "No candles data"}

        # Convert to DataFrame for indicator calculation
        df = pd.DataFrame(candles)
        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])

        # Calculate indicators
        indicators = self._calculate_indicators(df)

        # Volume analysis
        volume_analysis = self._analyze_volume(df)

        # Recent candles summary
        recent_candles = df.tail(5).to_dict('records')

        return {
            "interval": interval,
            "bar_count": len(df),
            "candles": recent_candles,  # Last 5 for context
            "indicators": indicators,
            "volume_analysis": volume_analysis,
            "price_action": {
                "last_close": float(df.iloc[-1]['close']),
                "change_1bar": float(df.iloc[-1]['close'] - df.iloc[-2]['close']) if len(df) > 1 else 0,
                "high_lookback": float(df['high'].max()),
                "low_lookback": float(df['low'].min()),
                "range_pct": float((df['high'].max() - df['low'].min()) / df['close'].iloc[-1] * 100)
            }
        }

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate all technical indicators from OHLCV data."""
        # Trend
        df['ema_20'] = ta.ema(df['close'], length=20)
        df['ema_50'] = ta.ema(df['close'], length=50)

        # Momentum
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['macd_hist'] = macd['MACDh_12_26_9']

        df['rsi_14'] = ta.rsi(df['close'], length=14)
        df['rsi_7'] = ta.rsi(df['close'], length=7)

        # Volatility
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        bb = ta.bbands(df['close'], length=20, std=2)
        df['bb_upper'] = bb['BBU_20_2.0']
        df['bb_lower'] = bb['BBL_20_2.0']

        # Volume
        df['volume_sma'] = ta.sma(df['volume'], length=20)

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
            "bb_lower": round(float(latest['bb_lower']), 2) if pd.notna(latest['bb_lower']) else None,
        }

    def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """Analyze volume patterns and delta."""
        latest_volume = float(df.iloc[-1]['volume'])
        avg_volume = float(df['volume'].rolling(20).mean().iloc[-1])
        volume_spike = latest_volume / avg_volume if avg_volume > 0 else 1.0

        # Simple volume delta estimation (would need tick data for exact)
        # Approximation: if close > open → buy volume dominant
        df['price_change'] = df['close'] - df['open']
        df['buy_volume'] = df.apply(
            lambda row: row['volume'] if row['price_change'] > 0 else 0, axis=1
        )
        df['sell_volume'] = df.apply(
            lambda row: row['volume'] if row['price_change'] < 0 else 0, axis=1
        )

        total_buy = float(df['buy_volume'].tail(10).sum())
        total_sell = float(df['sell_volume'].tail(10).sum())
        delta = total_buy - total_sell

        return {
            "current_volume": round(latest_volume, 2),
            "avg_volume": round(avg_volume, 2),
            "volume_spike": round(volume_spike, 2),
            "delta_estimate": round(delta, 2),
            "signal": "bullish" if delta > 0 else "bearish"
        }
```

---

### 4.2 Integration into Main Loop

**Update `main.py`**:

```python
# After line 68 (initialization)
from src.indicators.hyperliquid_market_data import HyperliquidMarketData

# In main():
market_data_client = HyperliquidMarketData(hyperliquid.info)

# In run_loop(), replace TAAPI calls (lines 224-283) with:
async def gather_asset_data(asset):
    try:
        # Parallel fetch of all data sources
        orderbook_task = market_data_client.get_orderbook_snapshot(asset)
        candles_1m_task = market_data_client.get_candles(asset, "1m", 50)
        candles_5m_task = market_data_client.get_candles(asset, "5m", 50)
        candles_4h_task = market_data_client.get_candles(asset, "4h", 50)

        current_price = await hyperliquid.get_current_price(asset)
        oi = await hyperliquid.get_open_interest(asset)
        funding = await hyperliquid.get_funding_rate(asset)

        # Await all market data
        orderbook, candles_1m, candles_5m, candles_4h = await asyncio.gather(
            orderbook_task, candles_1m_task, candles_5m_task, candles_4h_task
        )

        return {
            "asset": asset,
            "current_price": round(current_price, 2),
            "orderbook": orderbook,
            "price_action_1m": candles_1m.get("price_action"),
            "price_action_5m": candles_5m.get("price_action"),
            "volume_analysis": candles_5m.get("volume_analysis"),
            "indicators_5m": candles_5m.get("indicators"),
            "indicators_4h": candles_4h.get("indicators"),
            "perpetual_data": {
                "funding_rate": funding,
                "funding_annualized_pct": round(funding * 24 * 365 * 100, 2) if funding else None,
                "open_interest": oi
            }
        }
    except Exception as e:
        logging.error(f"Data gather error {asset}: {e}")
        return None

# Gather all assets in parallel
market_sections = await asyncio.gather(*[gather_asset_data(a) for a in args.assets])
market_sections = [m for m in market_sections if m is not None]
```

---

## 5. Execution Strategy Enhancements

### 5.1 Limit Order Implementation

**Add to `hyperliquid_api.py`**:

```python
async def place_limit_buy(self, asset, amount, limit_price, post_only=True):
    """
    Place limit buy order to earn maker rebates.

    Args:
        post_only: If True, order is cancelled if it would take liquidity
    """
    amount = self.round_size(asset, amount)
    order_type = {"limit": {"tif": "Gtc"}}
    if post_only:
        order_type["limit"]["post_only"] = True

    return await self._retry(
        lambda: self.exchange.order(asset, True, amount, limit_price, order_type)
    )

async def place_limit_sell(self, asset, amount, limit_price, post_only=True):
    """Place limit sell order to earn maker rebates."""
    amount = self.round_size(asset, amount)
    order_type = {"limit": {"tif": "Gtc"}}
    if post_only:
        order_type["limit"]["post_only"] = True

    return await self._retry(
        lambda: self.exchange.order(asset, False, amount, limit_price, order_type)
    )

async def monitor_order_fill(self, asset, oid, timeout_seconds=120):
    """
    Monitor order until filled or timeout.

    Returns:
        "filled" | "partial" | "timeout" | "cancelled"
    """
    start = datetime.now()
    while (datetime.now() - start).total_seconds() < timeout_seconds:
        orders = await self.get_open_orders()
        matching = [o for o in orders if o.get('oid') == oid and o.get('coin') == asset]

        if not matching:
            # Order no longer open → filled or cancelled
            fills = await self.get_recent_fills(limit=10)
            for fill in reversed(fills):
                if fill.get('oid') == oid:
                    return "filled"
            return "cancelled"

        await asyncio.sleep(2)

    return "timeout"
```

---

### 5.2 Smart Order Routing

**New decision logic in `main.py`**:

```python
# In trade execution section (after line 374)
if action in ("buy", "sell"):
    is_buy = action == "buy"
    alloc_usd = float(output.get("allocation_usd", 0.0))

    if alloc_usd <= 0:
        continue

    amount = alloc_usd / current_price
    entry_price = output.get("entry_price")  # NEW: LLM can specify limit price
    order_type = output.get("order_type", "limit")  # NEW: LLM chooses order type

    if order_type == "limit" and entry_price:
        # Place limit order at specified price
        if is_buy:
            order = await hyperliquid.place_limit_buy(asset, amount, entry_price)
        else:
            order = await hyperliquid.place_limit_sell(asset, amount, entry_price)

        oid = hyperliquid.extract_oids(order)[0] if hyperliquid.extract_oids(order) else None

        if oid:
            # Monitor fill status
            add_event(f"Limit {action} order placed for {asset} at {entry_price}, monitoring...")
            fill_status = await hyperliquid.monitor_order_fill(asset, oid, timeout_seconds=120)

            if fill_status == "timeout":
                # Order not filled, decide: cancel or adjust price
                add_event(f"Limit order timeout for {asset}, cancelling...")
                await hyperliquid.cancel_order(asset, oid)
                continue  # Skip this trade
            elif fill_status == "filled":
                add_event(f"Limit order filled for {asset} at {entry_price}")

    else:
        # Market order (immediate execution)
        order = await hyperliquid.place_buy_order(asset, amount) if is_buy else await hyperliquid.place_sell_order(asset, amount)
        add_event(f"Market {action} order executed for {asset}")

    # ... rest of TP/SL logic ...
```

---

## 6. Risk Management System

### 6.1 Portfolio Risk Calculator

**New module: `risk/portfolio_risk.py`**:

```python
class PortfolioRiskManager:
    def __init__(self):
        self.trade_history = []
        self.peak_value = None

    def calculate_metrics(self, account_value: float, positions: list, active_trades: list) -> dict:
        """Calculate comprehensive risk metrics."""

        # Update peak for drawdown calculation
        if self.peak_value is None or account_value > self.peak_value:
            self.peak_value = account_value

        # Total leverage
        total_notional = sum(
            abs(float(p.get('szi', 0))) * float(p.get('entryPx', 0))
            for p in positions
        )
        total_leverage = total_notional / account_value if account_value > 0 else 0

        # Portfolio heat (at-risk capital)
        portfolio_heat = 0
        for trade in active_trades:
            entry = trade.get('entry_price', 0)
            stop = trade.get('sl_price', 0)
            if entry and stop:
                risk_per_unit = abs(entry - stop)
                amount = trade.get('amount', 0)
                risk_usd = risk_per_unit * amount
                portfolio_heat += risk_usd

        heat_pct = portfolio_heat / account_value if account_value > 0 else 0

        # Drawdown
        current_dd = ((account_value - self.peak_value) / self.peak_value * 100) if self.peak_value else 0

        # Win rate and profit factor
        if len(self.trade_history) >= 5:
            wins = [t for t in self.trade_history if t.get('pnl', 0) > 0]
            losses = [t for t in self.trade_history if t.get('pnl', 0) < 0]

            win_rate = len(wins) / len(self.trade_history)

            total_profit = sum(t['pnl'] for t in wins) if wins else 0
            total_loss = abs(sum(t['pnl'] for t in losses)) if losses else 1
            profit_factor = total_profit / total_loss if total_loss > 0 else 0

            avg_win = total_profit / len(wins) if wins else 0
            avg_loss = total_loss / len(losses) if losses else 0
        else:
            win_rate = 0
            profit_factor = 0
            avg_win = 0
            avg_loss = 0

        # Position correlation (simplified: same direction = correlated)
        long_positions = [p for p in positions if float(p.get('szi', 0)) > 0]
        short_positions = [p for p in positions if float(p.get('szi', 0)) < 0]

        if len(positions) > 0:
            correlation = abs(len(long_positions) - len(short_positions)) / len(positions)
        else:
            correlation = 0

        return {
            "total_leverage": round(total_leverage, 2),
            "portfolio_heat": round(heat_pct, 4),
            "current_drawdown_pct": round(current_dd, 2),
            "max_drawdown_pct": round(current_dd, 2),  # Track max separately
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "position_correlation": round(correlation, 2),
            "long_exposure": sum(float(p.get('szi', 0)) * float(p.get('entryPx', 0)) for p in long_positions),
            "short_exposure": sum(abs(float(p.get('szi', 0))) * float(p.get('entryPx', 0)) for p in short_positions)
        }
```

---

## 7. Testing & Validation Strategy

### 7.1 Unit Tests

```python
# tests/test_orderbook_analysis.py
def test_imbalance_calculation():
    orderbook = {
        "bids": [[100, 10], [99, 5]],  # $1000 + $495 = $1495
        "asks": [[101, 3], [102, 2]]   # $303 + $204 = $507
    }
    imbalance = calculate_imbalance(orderbook)
    assert 2.9 < imbalance < 3.0  # ~2.95

def test_liquidity_level_detection():
    bids = [[100, 2], [99, 15], [98, 1]]  # 15 at 99 is large
    median_size = 2
    levels = identify_liquidity_levels(bids, [], median_size)
    assert len(levels) == 1
    assert levels[0]["price"] == 99
    assert levels[0]["type"] == "support"
```

---

### 7.2 Backtesting Framework

```python
# backtest/orderbook_backtest.py
class OrderbookBacktest:
    """
    Replay historical orderbook snapshots and candle data
    to validate microstructure signals.
    """

    def run(self, start_date, end_date, assets):
        # Fetch historical data
        # Replay tick-by-tick
        # Generate signals
        # Calculate PnL
        # Compare vs baseline (TAAPI indicators only)
        pass
```

---

### 7.3 A/B Testing Plan

| **Variant** | **Description** | **Metrics** |
|------------|----------------|------------|
| **Control** | Current TAAPI-based system (1h interval) | Sharpe, total return, max DD |
| **Test A** | Hyperliquid native data + same indicators (1h) | Compare data quality impact |
| **Test B** | Hyperliquid + orderbook signals (5m, market orders) | Test microstructure edge |
| **Test C** | Hyperliquid + orderbook signals (5m, limit orders) | Optimize execution |

**Run duration**: 2 weeks per variant with $500 capital each

---

## 8. Monitoring & Observability

### 8.1 New Metrics to Track

```python
# Add to diary entries
{
    "timestamp": "...",
    "asset": "BTC",
    "action": "buy",

    # NEW: Market microstructure at decision time
    "microstructure_snapshot": {
        "imbalance_ratio": 3.12,
        "spread_bps": 1.05,
        "volume_delta_5m": 59.9,
        "cvd_trend": "accumulation"
    },

    # NEW: Execution quality
    "execution": {
        "order_type": "limit",
        "requested_price": 95010,
        "fill_price": 95008,  # Got better fill!
        "slippage_bps": -0.21,  # Negative = favorable
        "time_to_fill_seconds": 45
    },

    # Existing fields
    "entry_price": 95008,
    "tp_price": 95500,
    "sl_price": 94400,
    "leverage": 2.3,
    "risk_reward": 2.4
}
```

---

### 8.2 Alert System

```python
# risk/alerts.py
class RiskAlerts:
    def check_and_alert(self, risk_metrics: dict):
        alerts = []

        if risk_metrics["total_leverage"] > 8:
            alerts.append("CRITICAL: Total leverage exceeded 8x")

        if risk_metrics["portfolio_heat"] > 0.25:
            alerts.append("WARNING: Portfolio heat above 25%")

        if risk_metrics["current_drawdown_pct"] < -10:
            alerts.append("CRITICAL: Drawdown exceeded -10%, halting trading")
            # Trigger circuit breaker

        return alerts
```

---

## 9. Documentation Updates

### 9.1 New README Sections

```markdown
## Market Data Sources

This agent uses **native Hyperliquid market data** for superior execution:

- L2 Orderbook (bid/ask depth, liquidity levels)
- Candlestick data (OHLCV at multiple timeframes)
- Volume delta analysis (buy vs sell pressure)
- Calculated indicators (EMA, RSI, MACD) from Hyperliquid data

### Why Not TAAPI?

TAAPI pulls data from Binance, which creates:
- Cross-exchange basis risk
- 1-3 second latency
- Monthly subscription costs

By using Hyperliquid's native API, we achieve:
- Zero basis risk (same exchange)
- <100ms latency
- Free data access

## Trading Strategy

The agent operates as a **market microstructure trader**, not a traditional indicator-following bot.

**Primary Signals** (in order of importance):
1. Orderbook imbalance ratio (bid depth / ask depth)
2. Volume delta (cumulative buy volume - sell volume)
3. Liquidity levels (support/resistance from large orders)
4. Price action (breakouts, rejections, volume spikes)

**Secondary Confirmation**:
5. EMA alignment (trend filter)
6. RSI extremes (reversal risk)
7. MACD histogram (momentum confirmation)

**Execution**:
- Default: Limit orders at identified levels (0% maker fees)
- Exception: Market orders for breakouts or emergencies
```

---

## 10. Migration Checklist

### Phase 1: Preparation (Week 1)
- [ ] Review this mindmap with team
- [ ] Set up testing environment (testnet or paper trading)
- [ ] Install additional dependencies (`pandas-ta` or `ta-lib`)
- [ ] Validate Hyperliquid SDK methods work as expected

### Phase 2: Implementation (Week 2)
- [ ] Create `hyperliquid_market_data.py` module
- [ ] Write unit tests for orderbook analysis
- [ ] Write unit tests for indicator calculations
- [ ] Integrate into main loop (parallel to TAAPI initially)
- [ ] Log both TAAPI and Hyperliquid data to compare quality

### Phase 3: Prompt Engineering (Week 3)
- [ ] Rewrite system prompt for microstructure focus
- [ ] Add orderbook interpretation guidelines
- [ ] Remove time-based cooldowns
- [ ] Add risk constraint checks

### Phase 4: Execution Layer (Week 4)
- [ ] Implement limit order methods
- [ ] Add order monitoring logic
- [ ] Test fill rates and execution quality
- [ ] Compare fees: market vs limit orders

### Phase 5: Testing (Week 5-6)
- [ ] Run A/B test: TAAPI vs Hyperliquid data
- [ ] Run A/B test: market orders vs limit orders
- [ ] Run A/B test: 1h interval vs 5m interval
- [ ] Analyze results, pick winning configuration

### Phase 6: Deployment (Week 7)
- [ ] Remove TAAPI dependency entirely
- [ ] Update documentation (README, ARCHITECTURE.md)
- [ ] Deploy to production (EigenCloud or other)
- [ ] Monitor for 2 weeks with daily reviews

### Phase 7: Optimization (Ongoing)
- [ ] Tune orderbook imbalance thresholds
- [ ] Experiment with volume delta parameters
- [ ] Refine liquidity level detection
- [ ] Add machine learning for pattern recognition (optional)

---

## Conclusion

The current system is **fundamentally limited** by its reliance on TAAPI (Binance data) instead of native Hyperliquid market microstructure data. This enhancement roadmap transforms the agent from a **lagging indicator follower** into a **market microstructure trader** with:

1. **Real-time orderbook analysis** (bid/ask imbalances, liquidity levels)
2. **Volume delta tracking** (buy vs sell pressure)
3. **Superior execution** (limit orders, lower fees)
4. **Tighter feedback loop** (5m interval viable with microstructure edge)

**Expected Outcomes**:
- 95% reduction in data latency (3s → <100ms)
- 100% reduction in trading fees (0.035% taker → 0% maker)
- Elimination of cross-exchange basis risk
- Access to alpha signals unavailable in lagging indicators

This is not an incremental improvement—it's a **paradigm shift** in how the agent perceives and reacts to markets.
