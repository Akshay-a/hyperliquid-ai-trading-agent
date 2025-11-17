"""Pre-calculate trading signals and metrics to avoid LLM hallucination.

This module computes confluence scores, leverage, and actionable signals
programmatically in Python, then passes simplified context to LLM.

The LLM should validate/adjust decisions, not perform calculations.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime


class SignalCalculator:
    """Calculate confluence scores and trading signals from raw market data."""

    def __init__(self, leverage_min: float = 3.0, leverage_max: float = 10.0):
        """Initialize signal calculator.

        Args:
            leverage_min: Minimum leverage allowed
            leverage_max: Maximum leverage allowed
        """
        self.leverage_min = leverage_min
        self.leverage_max = leverage_max

    def calculate_confluence_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate confluence score from all available signals.

        Counts aligned bullish/bearish signals across 10 indicators:
        1. HTF trend (EMA20 vs EMA50)
        2. LTF trend (EMA20 slope)
        3. MACD regime
        4. RSI momentum
        5. Order book imbalance
        6. On-chain SOPR
        7. Fear & Greed (contrarian)
        8. Macro risk environment
        9. Funding rate
        10. Recent price action

        Args:
            data: Dict with market data (ltf, htf, microstructure, onchain, etc.)

        Returns:
            Dict with:
                - confluence_score: 0-10 (absolute value of aligned signals)
                - direction: "bullish", "bearish", or "neutral"
                - aligned_signals: List of signal names that contributed
                - confidence: 1-10 based on score
        """
        signals = []
        signal_values = []

        # 1. HTF Trend (4h EMA alignment)
        htf = data.get("htf", {})
        if htf.get("ema20") and htf.get("ema50"):
            if htf["ema20"] > htf["ema50"]:
                signals.append("HTF uptrend (EMA20 > EMA50)")
                signal_values.append(1)
            else:
                signals.append("HTF downtrend (EMA20 < EMA50)")
                signal_values.append(-1)

        # 2. LTF Trend (5m EMA slope)
        ltf = data.get("ltf", {})
        if ltf.get("ema20") and data.get("current_price"):
            if ltf["ema20"] < data["current_price"]:
                signals.append("LTF bullish (price > EMA20)")
                signal_values.append(1)
            else:
                signals.append("LTF bearish (price < EMA20)")
                signal_values.append(-1)

        # 3. MACD Regime
        if htf.get("macd") and htf.get("macd_signal"):
            if htf["macd"] > htf["macd_signal"]:
                signals.append("MACD bullish")
                signal_values.append(1)
            else:
                signals.append("MACD bearish")
                signal_values.append(-1)

        # 4. RSI Momentum
        if htf.get("rsi"):
            rsi = htf["rsi"]
            if rsi > 55:
                signals.append("RSI bullish momentum")
                signal_values.append(1)
            elif rsi < 45:
                signals.append("RSI bearish momentum")
                signal_values.append(-1)

        # 5. Order Book Imbalance
        micro = data.get("microstructure", {})
        if micro.get("imbalance") is not None:
            imbalance = micro["imbalance"]
            if imbalance > 0.3:
                signals.append("Buy pressure (order book)")
                signal_values.append(1)
            elif imbalance < -0.3:
                signals.append("Sell pressure (order book)")
                signal_values.append(-1)

        # 6. On-Chain SOPR
        onchain = data.get("onchain", {})
        if onchain.get("sopr") is not None:
            sopr = onchain["sopr"]
            if sopr > 1.0:
                signals.append("On-chain: taking profits")
                signal_values.append(-1)  # Bearish (distribution)
            else:
                signals.append("On-chain: accumulation")
                signal_values.append(1)  # Bullish (buy the dip)

        # 7. Fear & Greed (Contrarian)
        sentiment = data.get("sentiment", {})
        if sentiment.get("value") is not None:
            fg_value = sentiment["value"]
            if fg_value < 30:
                signals.append("Extreme fear (contrarian buy)")
                signal_values.append(1)
            elif fg_value > 70:
                signals.append("Extreme greed (contrarian sell)")
                signal_values.append(-1)

        # 8. Macro Risk Environment
        macro = data.get("macro", {})
        if macro.get("risk_environment"):
            risk_env = macro["risk_environment"]
            if risk_env == "risk_on":
                signals.append("Macro: risk-on")
                signal_values.append(1)
            elif risk_env == "risk_off":
                signals.append("Macro: risk-off")
                signal_values.append(-1)

        # 9. Funding Rate
        if data.get("funding_rate") is not None:
            funding = data["funding_rate"]
            # Negative funding = shorts pay longs (bullish)
            # Positive funding = longs pay shorts (bearish)
            if funding < -0.01:
                signals.append("Funding: shorts paying (bullish)")
                signal_values.append(1)
            elif funding > 0.01:
                signals.append("Funding: longs paying (bearish)")
                signal_values.append(-1)

        # 10. Recent Price Action (simple trend check)
        if ltf.get("ema20") and htf.get("ema50"):
            # Both EMAs rising = uptrend
            if ltf["ema20"] > htf["ema50"]:
                signals.append("Price action: higher highs")
                signal_values.append(1)
            else:
                signals.append("Price action: lower lows")
                signal_values.append(-1)

        # Calculate final score
        if not signal_values:
            return {
                "confluence_score": 0,
                "direction": "neutral",
                "aligned_signals": [],
                "confidence": 1,
                "signal_strength": 0,
            }

        # Sum all signals (can be negative for bearish)
        signal_sum = sum(signal_values)

        # Absolute value is confluence score
        confluence_score = abs(signal_sum)

        # Direction
        if signal_sum > 2:
            direction = "bullish"
        elif signal_sum < -2:
            direction = "bearish"
        else:
            direction = "neutral"

        # Confidence (1-10 scale)
        confidence = min(10, max(1, confluence_score))

        # Signal strength (-1 to +1)
        signal_strength = signal_sum / len(signal_values) if signal_values else 0

        return {
            "confluence_score": confluence_score,
            "direction": direction,
            "aligned_signals": signals,
            "confidence": confidence,
            "signal_strength": signal_strength,  # -1 to +1
            "total_signals_checked": len(signal_values),
        }

    def calculate_dynamic_leverage(
        self,
        confluence_score: int,
        atr_current: float,
        atr_avg: float,
        risk_environment: str,
    ) -> Dict[str, Any]:
        """Calculate dynamic leverage based on confluence, volatility, and macro.

        Formula:
        1. Base leverage from confluence score
        2. Adjust for volatility (high ATR = lower leverage)
        3. Adjust for macro environment (risk-off = lower leverage)
        4. Clamp to min-max range

        Args:
            confluence_score: 0-10 aligned signals
            atr_current: Current 4h ATR value
            atr_avg: Recent average ATR
            risk_environment: "risk_on", "neutral", or "risk_off"

        Returns:
            Dict with:
                - leverage: Final leverage value
                - base_leverage: Before adjustments
                - volatility_adjustment: Multiplier applied
                - macro_adjustment: Multiplier applied
                - reasoning: Explanation of calculation
        """
        # Step 1: Base leverage from confluence
        if confluence_score >= 8:
            base_leverage = self.leverage_max  # High conviction
        elif confluence_score >= 6:
            base_leverage = (self.leverage_min + self.leverage_max) / 2  # Medium
        else:
            base_leverage = self.leverage_min  # Low conviction

        # Step 2: Volatility adjustment
        volatility_multiplier = 1.0
        volatility_reason = "normal volatility"

        if atr_current and atr_avg and atr_avg > 0:
            atr_ratio = atr_current / atr_avg
            if atr_ratio > 1.5:
                volatility_multiplier = 0.6
                volatility_reason = f"high volatility (ATR {atr_ratio:.1f}x normal) → reduce 40%"
            elif atr_ratio > 1.2:
                volatility_multiplier = 0.8
                volatility_reason = f"elevated volatility (ATR {atr_ratio:.1f}x normal) → reduce 20%"

        # Step 3: Macro adjustment
        macro_multiplier = 1.0
        macro_reason = "neutral macro"

        if risk_environment == "risk_off":
            macro_multiplier = 0.7
            macro_reason = "risk-off environment → reduce 30%"
        elif risk_environment == "moderate_risk_off":
            macro_multiplier = 0.85
            macro_reason = "moderate risk-off → reduce 15%"
        elif risk_environment == "risk_on":
            macro_reason = "risk-on environment → no reduction"

        # Calculate final leverage
        calculated_leverage = base_leverage * volatility_multiplier * macro_multiplier

        # Clamp to range
        final_leverage = max(self.leverage_min, min(self.leverage_max, calculated_leverage))

        reasoning = (
            f"Base: {base_leverage:.1f}x (confluence={confluence_score}), "
            f"{volatility_reason}, {macro_reason} "
            f"→ Final: {final_leverage:.1f}x"
        )

        return {
            "leverage": round(final_leverage, 1),
            "base_leverage": round(base_leverage, 1),
            "volatility_adjustment": volatility_multiplier,
            "macro_adjustment": macro_multiplier,
            "reasoning": reasoning,
        }

    def generate_trade_signal(
        self,
        asset: str,
        market_data: Dict[str, Any],
        current_price: float,
    ) -> Dict[str, Any]:
        """Generate complete trade signal with pre-computed metrics.

        This is what gets passed to the LLM as simplified context.

        Args:
            asset: Asset ticker (e.g., "BTC")
            market_data: All market data (ltf, htf, onchain, macro, etc.)
            current_price: Current asset price

        Returns:
            Dict with pre-computed signal ready for LLM validation
        """
        # Add current price to data
        market_data["current_price"] = current_price

        # Calculate confluence
        confluence = self.calculate_confluence_score(market_data)

        # Calculate leverage
        htf = market_data.get("htf", {})
        macro = market_data.get("macro", {})

        leverage_calc = self.calculate_dynamic_leverage(
            confluence_score=confluence["confluence_score"],
            atr_current=htf.get("atr"),
            atr_avg=htf.get("atr_avg"),
            risk_environment=macro.get("risk_environment", "neutral"),
        )

        # Calculate suggested TP/SL levels
        atr = htf.get("atr", current_price * 0.02)  # Fallback to 2% if no ATR

        # SL: 1.5 ATR from entry
        sl_distance = atr * 1.5

        # TP: 3 ATR (2:1 R:R minimum)
        tp_distance = atr * 3

        if confluence["direction"] == "bullish":
            suggested_sl = current_price - sl_distance
            suggested_tp = current_price + tp_distance
        elif confluence["direction"] == "bearish":
            suggested_sl = current_price + sl_distance
            suggested_tp = current_price - tp_distance
        else:
            suggested_sl = None
            suggested_tp = None

        # Build actionable signal
        signal = {
            "asset": asset,
            "current_price": current_price,

            # Pre-computed analysis
            "direction": confluence["direction"],
            "confluence_score": confluence["confluence_score"],
            "confidence": confluence["confidence"],
            "signal_strength": confluence["signal_strength"],

            # Aligned signals (for transparency)
            "aligned_signals": confluence["aligned_signals"],

            # Pre-calculated leverage
            "recommended_leverage": leverage_calc["leverage"],
            "leverage_reasoning": leverage_calc["reasoning"],

            # Suggested levels
            "suggested_tp": round(suggested_tp, 2) if suggested_tp else None,
            "suggested_sl": round(suggested_sl, 2) if suggested_sl else None,
            "risk_reward_ratio": 2.0,  # Based on 1.5 ATR SL, 3 ATR TP

            # Key market conditions (summary)
            "market_summary": self._build_market_summary(market_data),

            # Timestamp
            "calculated_at": datetime.now().isoformat(),
        }

        return signal

    def _build_market_summary(self, data: Dict[str, Any]) -> str:
        """Build human-readable market summary."""
        parts = []

        # HTF trend
        htf = data.get("htf", {})
        if htf.get("ema20") and htf.get("ema50"):
            trend = "uptrend" if htf["ema20"] > htf["ema50"] else "downtrend"
            parts.append(f"HTF: {trend}")

        # Volatility
        if htf.get("atr") and htf.get("atr_avg"):
            vol_ratio = htf["atr"] / htf["atr_avg"]
            if vol_ratio > 1.3:
                parts.append("volatility: HIGH")
            elif vol_ratio < 0.7:
                parts.append("volatility: LOW")
            else:
                parts.append("volatility: NORMAL")

        # Sentiment
        sentiment = data.get("sentiment", {})
        if sentiment.get("classification"):
            parts.append(f"sentiment: {sentiment['classification']}")

        # Macro
        macro = data.get("macro", {})
        if macro.get("risk_environment"):
            parts.append(f"macro: {macro['risk_environment']}")

        # Microstructure
        micro = data.get("microstructure", {})
        if micro.get("imbalance") is not None:
            imb = micro["imbalance"]
            if imb > 0.3:
                parts.append("order book: BUY PRESSURE")
            elif imb < -0.3:
                parts.append("order book: SELL PRESSURE")

        return ", ".join(parts) if parts else "insufficient data"


def validate_trade_decision(
    decision: Dict[str, Any],
    current_price: float,
    leverage_min: float,
    leverage_max: float,
) -> Dict[str, Any]:
    """Validate and sanitize LLM trade decision output.

    Ensures:
    - Leverage in bounds
    - TP/SL make sense for direction
    - Allocation is positive
    - Confluence score in 0-10 range

    Args:
        decision: LLM output for a single trade decision
        current_price: Current market price
        leverage_min: Minimum allowed leverage
        leverage_max: Maximum allowed leverage

    Returns:
        Validated and corrected decision dict
    """
    validated = decision.copy()

    # Validate action
    action = validated.get("action", "hold").lower()
    if action not in ["buy", "sell", "hold"]:
        logging.warning(f"Invalid action '{action}', defaulting to HOLD")
        validated["action"] = "hold"

    # Validate leverage
    leverage = validated.get("leverage", leverage_min)
    if leverage < leverage_min or leverage > leverage_max:
        logging.warning(f"Leverage {leverage} out of bounds, clamping to [{leverage_min}, {leverage_max}]")
        validated["leverage"] = max(leverage_min, min(leverage_max, leverage))

    # Validate confluence score
    confluence = validated.get("confluence_score", 0)
    if confluence < 0 or confluence > 10:
        logging.warning(f"Confluence score {confluence} out of bounds, clamping to [0, 10]")
        validated["confluence_score"] = max(0, min(10, confluence))

    # Validate allocation
    allocation = validated.get("allocation_usd", 0)
    if allocation < 0:
        logging.warning(f"Negative allocation {allocation}, setting to 0")
        validated["allocation_usd"] = 0

    # Validate TP/SL logic
    tp = validated.get("tp_price")
    sl = validated.get("sl_price")

    if action == "buy" and tp and sl:
        # For long: TP should be above current price, SL below
        if tp < current_price:
            logging.warning(f"Long TP {tp} below current price {current_price}, removing")
            validated["tp_price"] = None
        if sl > current_price:
            logging.warning(f"Long SL {sl} above current price {current_price}, removing")
            validated["sl_price"] = None

    elif action == "sell" and tp and sl:
        # For short: TP should be below current price, SL above
        if tp > current_price:
            logging.warning(f"Short TP {tp} above current price {current_price}, removing")
            validated["tp_price"] = None
        if sl < current_price:
            logging.warning(f"Short SL {sl} below current price {current_price}, removing")
            validated["sl_price"] = None

    return validated
