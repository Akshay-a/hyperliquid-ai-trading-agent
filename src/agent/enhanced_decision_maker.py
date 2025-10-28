"""
Enhanced Decision Maker with Jim Simons-level rigor.

Key improvements:
1. No tool calling during inference (all features pre-computed)
2. Compressed context (20 features vs 500+ data points)
3. Realistic performance expectations (52-58% win rate)
4. Position sizing emphasis over directional prediction
5. Statistical decision framework
"""

import requests
from src.config_loader import CONFIG
import json
import logging
from datetime import datetime


class EnhancedTradingAgent:
    """
    Trading agent designed for systematic edge extraction with realistic expectations.

    Philosophy:
    - Features > raw data
    - Position sizing > directional prediction
    - Statistical rigor > hunches
    - Fast execution > perfect entries
    """

    def __init__(self):
        """Initialize LLM configuration."""
        self.model = CONFIG["llm_model"]
        self.api_key = CONFIG["openrouter_api_key"]
        base = CONFIG["openrouter_base_url"]
        self.base_url = f"{base}/chat/completions"
        self.referer = CONFIG.get("openrouter_referer")
        self.app_title = CONFIG.get("openrouter_app_title")
        self.sanitize_model = CONFIG.get("sanitize_model") or "openai/gpt-4o-mini"

    def decide_trade(self, assets, context):
        """
        Decide for multiple assets in one call using compressed features.

        Args:
            assets: List of asset tickers
            context: Compressed feature context (not raw market data)

        Returns:
            Dictionary with reasoning and trade_decisions array
        """
        return self._decide(context, assets=assets)

    def _decide(self, context, assets):
        """Core decision logic with Jim Simons-approved system prompt."""

        system_prompt = self._build_system_prompt(assets)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.referer:
            headers["HTTP-Referer"] = self.referer
        if self.app_title:
            headers["X-Title"] = self.app_title

        def _post(payload):
            """Send POST request to OpenRouter with logging."""
            logging.info("Sending request to OpenRouter (model: %s)", payload.get('model'))
            with open("llm_requests.log", "a", encoding="utf-8") as f:
                f.write(f"\n\n=== {datetime.now()} ===\n")
                f.write(f"Model: {payload.get('model')}\n")
                f.write(f"Payload:\n{json.dumps(payload, indent=2)}\n")

            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=90)
            logging.info("Received response from OpenRouter (status: %s)", resp.status_code)

            if resp.status_code != 200:
                logging.error("OpenRouter error: %s - %s", resp.status_code, resp.text)
                with open("llm_requests.log", "a", encoding="utf-8") as f:
                    f.write(f"ERROR Response: {resp.status_code} - {resp.text}\n")

            resp.raise_for_status()
            return resp.json()

        def _sanitize_output(raw_content: str, assets_list):
            """Coerce malformed output into required schema."""
            try:
                schema = {
                    "type": "object",
                    "properties": {
                        "reasoning": {"type": "string"},
                        "trade_decisions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "asset": {"type": "string", "enum": assets_list},
                                    "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                                    "conviction": {"type": "integer", "minimum": 0, "maximum": 100},
                                    "allocation_usd": {"type": "number"},
                                    "tp_price": {"type": ["number", "null"]},
                                    "sl_price": {"type": ["number", "null"]},
                                    "exit_plan": {"type": "string"},
                                    "rationale": {"type": "string"},
                                },
                                "required": ["asset", "action", "conviction", "allocation_usd", "tp_price", "sl_price", "exit_plan", "rationale"],
                                "additionalProperties": False,
                            },
                            "minItems": 1,
                        }
                    },
                    "required": ["reasoning", "trade_decisions"],
                    "additionalProperties": False,
                }

                payload = {
                    "model": self.sanitize_model,
                    "messages": [
                        {"role": "system", "content": (
                            "You are a strict JSON normalizer. Return ONLY a JSON object matching the provided schema. "
                            "Fix any formatting issues. Do not add extra fields."
                        )},
                        {"role": "user", "content": raw_content},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "trade_decisions",
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    "temperature": 0,
                }

                resp = _post(payload)
                msg = resp.get("choices", [{}])[0].get("message", {})
                parsed = msg.get("parsed")

                if isinstance(parsed, dict) and "trade_decisions" in parsed:
                    return parsed

                # Fallback to content
                content = msg.get("content") or "{}"
                try:
                    loaded = json.loads(content)
                    if isinstance(loaded, dict) and "trade_decisions" in loaded:
                        return loaded
                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    pass

                return {"reasoning": "", "trade_decisions": []}

            except Exception as se:
                logging.error("Sanitize failed: %s", se)
                return {"reasoning": "", "trade_decisions": []}

        # Build schema for structured output
        def _build_schema():
            return {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string"},
                    "trade_decisions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "asset": {"type": "string", "enum": assets},
                                "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                                "conviction": {"type": "integer", "minimum": 0, "maximum": 100},
                                "allocation_usd": {"type": "number", "minimum": 0},
                                "tp_price": {"type": ["number", "null"]},
                                "sl_price": {"type": ["number", "null"]},
                                "exit_plan": {"type": "string"},
                                "rationale": {"type": "string"},
                            },
                            "required": ["asset", "action", "conviction", "allocation_usd", "tp_price", "sl_price", "exit_plan", "rationale"],
                            "additionalProperties": False,
                        },
                        "minItems": 1,
                    }
                },
                "required": ["reasoning", "trade_decisions"],
                "additionalProperties": False,
            }

        # Main inference loop (no tool calling)
        allow_structured = True

        for attempt in range(3):  # Max 3 attempts
            data = {"model": self.model, "messages": messages, "temperature": 0.2}

            if allow_structured:
                data["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "trade_decisions",
                        "strict": True,
                        "schema": _build_schema(),
                    },
                }

            if CONFIG.get("reasoning_enabled"):
                data["reasoning"] = {
                    "enabled": True,
                    "effort": CONFIG.get("reasoning_effort") or "high",
                    "exclude": False,
                }

            if CONFIG.get("provider_config") or CONFIG.get("provider_quantizations"):
                provider_payload = dict(CONFIG.get("provider_config") or {})
                quantizations = CONFIG.get("provider_quantizations")
                if quantizations:
                    provider_payload["quantizations"] = quantizations
                data["provider"] = provider_payload

            try:
                resp_json = _post(data)
            except requests.HTTPError as e:
                err_text = ""
                try:
                    err = e.response.json()
                    err_text = json.dumps(err)
                except (json.JSONDecodeError, ValueError, AttributeError):
                    pass

                if allow_structured and ("response_format" in err_text or "structured" in err_text):
                    logging.warning("Provider rejected structured outputs; retrying without response_format.")
                    allow_structured = False
                    continue

                raise

            choice = resp_json["choices"][0]
            message = choice["message"]

            try:
                # Prefer parsed field from structured outputs
                if isinstance(message.get("parsed"), dict):
                    parsed = message.get("parsed")
                else:
                    content = message.get("content") or "{}"
                    parsed = json.loads(content)

                if not isinstance(parsed, dict):
                    logging.error("Expected dict, got: %s; attempting sanitize", type(parsed))
                    sanitized = _sanitize_output(content if 'content' in locals() else json.dumps(parsed), assets)
                    if sanitized.get("trade_decisions"):
                        return sanitized
                    return {"reasoning": "", "trade_decisions": []}

                reasoning_text = parsed.get("reasoning", "") or ""
                decisions = parsed.get("trade_decisions")

                if isinstance(decisions, list):
                    # Normalize decisions
                    normalized = []
                    for item in decisions:
                        if isinstance(item, dict):
                            item.setdefault("conviction", 50)
                            item.setdefault("allocation_usd", 0.0)
                            item.setdefault("tp_price", None)
                            item.setdefault("sl_price", None)
                            item.setdefault("exit_plan", "")
                            item.setdefault("rationale", "")
                            normalized.append(item)

                    return {"reasoning": reasoning_text, "trade_decisions": normalized}

                logging.error("trade_decisions missing or invalid; attempting sanitize")
                sanitized = _sanitize_output(content if 'content' in locals() else json.dumps(parsed), assets)
                if sanitized.get("trade_decisions"):
                    return sanitized

                return {"reasoning": reasoning_text, "trade_decisions": []}

            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                logging.error("JSON parse error: %s", e)
                content_str = message.get("content", "")[:200]
                sanitized = _sanitize_output(content_str, assets)
                if sanitized.get("trade_decisions"):
                    return sanitized

                return {
                    "reasoning": "Parse error",
                    "trade_decisions": [{
                        "asset": a,
                        "action": "hold",
                        "conviction": 0,
                        "allocation_usd": 0.0,
                        "tp_price": None,
                        "sl_price": None,
                        "exit_plan": "",
                        "rationale": "Parse error"
                    } for a in assets]
                }

        return {
            "reasoning": "Max attempts reached",
            "trade_decisions": [{
                "asset": a,
                "action": "hold",
                "conviction": 0,
                "allocation_usd": 0.0,
                "tp_price": None,
                "sl_price": None,
                "exit_plan": "",
                "rationale": "Max attempts"
            } for a in assets]
        }

    def _build_system_prompt(self, assets: list) -> str:
        """Build Jim Simons-approved system prompt."""
        return f"""You are an ELITE SYSTEMATIC QUANTITATIVE TRADER operating a statistical edge-extraction engine on Hyperliquid perpetual futures.

═══════════════════════════════════════════════════════════════
IDENTITY & MANDATE
═══════════════════════════════════════════════════════════════

You are NOT a generic assistant. You are a specialized trading system designed to:
1. Extract statistical edges from compressed market features
2. Size positions based on conviction (Kelly criterion inspired)
3. Manage risk through systematic rules, not discretion
4. Operate with Renaissance Technologies-level discipline

Assets under management: {json.dumps(assets)}

═══════════════════════════════════════════════════════════════
PERFORMANCE EXPECTATIONS (Realistic)
═══════════════════════════════════════════════════════════════

Target Metrics (over 100+ trades):
- Win Rate: 52-58% (anything above 55% is excellent)
- Average R:R: 1.5-2.5 (gain/loss ratio)
- Expected Value: 0.15-0.30R per trade
- Max Drawdown: <15%
- Sharpe Ratio: >1.5

DO NOT aim for 70%+ win rates - this is statistically improbable without overfitting.
DO NOT expect 5R-10R gains regularly - market doesn't pay that without huge risk.

Renaissance Technologies achieved 66% annualized returns with ~50.75% win rate.
You can be profitable at 52% win rate with proper position sizing.

═══════════════════════════════════════════════════════════════
INPUT: COMPRESSED FEATURES (NOT RAW DATA)
═══════════════════════════════════════════════════════════════

You receive PRE-COMPUTED FEATURES, not raw market data:

**Trend Features** (-1 to +1):
- strength_5m, strength_1h, strength_4h: EMA alignment across timeframes
- consistency: % of recent bars aligned with trend

**Momentum Features**:
- rsi_percentile: 0-100 (current RSI vs recent range)
- macd_regime: -1 (bearish) / 0 (neutral) / +1 (bullish)
- acceleration: -1 to +1 (is momentum accelerating?)

**Volatility Features**:
- atr_percentile: 0-100 (current volatility vs historical)
- regime: low/medium/high
- realized_vol: actual recent price movement

**Mean Reversion Features**:
- distance_from_ema20: -1 to +1 (how stretched is price?)
- bb_position: 0 to 1 (position in Bollinger Bands)
- recent_extreme: boolean (touched BB recently?)

**Microstructure Features**:
- spread_regime: tight/normal/wide (execution quality indicator)
- volume_surprise: -1 to +1 (volume vs average)
- pressure: -1 to +1 (orderbook pressure - for timing, NOT direction)

NOTE: All features are normalized to [-1, 1] or [0, 1] or [0, 100] ranges.
NO RAW DATA - everything is pre-processed for you.

═══════════════════════════════════════════════════════════════
DECISION FRAMEWORK (Statistical)
═══════════════════════════════════════════════════════════════

**Step 1: Regime Classification**
- Volatility regime from atr_percentile:
  * Low (<30): Tight stops, higher size
  * Medium (30-70): Normal operations
  * High (>70): Wide stops, lower size

**Step 2: Trend vs Mean Reversion**
- If strength_4h and strength_1h ALIGNED (both >0.3 or both <-0.3):
  → Trend mode: Follow momentum
  → Entry: On pullbacks (distance_from_ema20 < 0.3)
  → Target: 2-2.5 ATR

- If strength_4h and strength_5m DIVERGENT (opposite signs):
  → Mean reversion mode: Fade extremes
  → Entry: When bb_position >0.8 or <0.2
  → Target: Mean (EMA20)

**Step 3: Momentum Confirmation**
- rsi_percentile:
  * <20 or >80: Extreme (mean reversion candidate)
  * 40-60: Neutral (trend continuation OK)
- macd_regime:
  * Aligned with trend_strength → strong signal
  * Opposite trend_strength → weak signal, reduce size

**Step 4: Conviction Scoring (0-100)**
```
base_conviction = 30  # Neutral

# Trend alignment bonus
if all timeframes agree (all >0.3 or all <-0.3):
    conviction += 20

# Momentum confirmation
if macd_regime aligns with trend:
    conviction += 15

# Mean reversion setup
if bb_position >0.85 or <0.15:
    conviction += 15

# Volatility penalty
if atr_percentile >70:
    conviction -= 10  # High vol = lower conviction

# Risk state penalty
if portfolio_heat >0.20 or drawdown <-8%:
    conviction -= 20  # Already risky, reduce size

conviction = max(0, min(100, conviction))
```

**Step 5: Position Sizing**
```
risk_per_trade = 0.015  # 1.5% of account
atr_multiple = 1.5  # Stop distance

notional_size = (account_equity × risk_per_trade × conviction / 100) / (atr_multiple × atr)

# Leverage constraint
if (total_existing_notional + notional_size) / account_equity > 6:
    → Reduce size or hold
```

═══════════════════════════════════════════════════════════════
EXECUTION RULES
═══════════════════════════════════════════════════════════════

**Entry**:
- Use market orders if conviction >70 AND spread_regime = "tight"
- Otherwise, hold for better setup

**Stop Loss**:
- Long: price - (1.5 × ATR)
- Short: price + (1.5 × ATR)
- Place behind swing lows/highs if available

**Take Profit**:
- Trend mode: 2.5 × ATR
- Mean reversion: Distance to EMA20

**Exit Plan** (must be specific):
- "Close if trend_strength_5m reverses below -0.2"
- "Close if rsi_percentile crosses above 85 (overbought)"
- "Close if portfolio_heat exceeds 0.25"
- NOT: "Close if momentum fades" (too vague)

═══════════════════════════════════════════════════════════════
RISK MANAGEMENT (NON-NEGOTIABLE)
═══════════════════════════════════════════════════════════════

**Portfolio Constraints**:
1. Max leverage: 6x total notional / equity
2. Max portfolio heat: 25% (sum of at-risk capital / equity)
3. Max single position: 15% of equity at risk
4. If drawdown <-10%: HALT trading, return all "hold" decisions

**Position Correlation**:
- If already long BTC and considering long ETH:
  → Reduce ETH size by 30% (correlated positions)

**Drawdown Management**:
- If consecutive_losses >=3: Reduce all new sizes by 50%
- If drawdown <-8%: Only take conviction >65 setups

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT (STRICT)
═══════════════════════════════════════════════════════════════

{{
  "reasoning": "Step-by-step analysis:
    1. Regime: [volatility state, trend vs mean reversion]
    2. Per-asset features: [key observations]
    3. Conviction scores: [how calculated]
    4. Risk check: [portfolio heat, leverage, drawdowns]
    5. Final decisions: [buy/sell/hold with justification]",

  "trade_decisions": [
    {{
      "asset": "BTC",
      "action": "buy" | "sell" | "hold",
      "conviction": 0-100,  // Used for position sizing
      "allocation_usd": <notional size>,
      "tp_price": <price or null>,
      "sl_price": <price or null>,
      "exit_plan": "Specific invalidation condition",
      "rationale": "Concise 1-2 sentence summary"
    }}
  ]
}}

═══════════════════════════════════════════════════════════════
CRITICAL REMINDERS
═══════════════════════════════════════════════════════════════

1. Position sizing > directional prediction
   → A 52% win rate with proper sizing beats 65% with poor sizing

2. Features are already computed - DO NOT ask for more data
   → No tool calling, everything you need is in the context

3. Conviction drives size
   → conviction=30 = minimal size
   → conviction=70 = full size
   → conviction=100 = maximum allowed size

4. Exit plans must be testable
   → "trend_strength_5m < -0.3" ✓
   → "momentum weakens" ✗

5. When in doubt, HOLD
   → Missing a trade costs 0
   → Wrong trade costs 1R

6. Realistic expectations
   → You will lose 42-48% of trades (at 52-58% win rate)
   → Average gains will be 1.5-2.5R, not 5-10R
   → Focus on process, not outcome of individual trades

Now analyze the provided compressed features and make systematic decisions."""
