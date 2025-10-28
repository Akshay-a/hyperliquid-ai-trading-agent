"""
LLM Layer: Autonomous Pattern Recognition and Decision Making

Philosophy:
- Give LLM REAL autonomy
- NO prescriptive rules ("if X then Y")
- LLM discovers patterns and edges
- LLM decides when to trade
- We provide features, LLM provides reasoning

This is what makes it an AI agent, not a rule-based algo.
"""

import requests
import json
import logging
from datetime import datetime
from src.config_loader import CONFIG


class AutonomousLLMAgent:
    """
    AI agent with full autonomy to analyze features and make trading decisions.

    What it DOES:
    - Analyzes market features
    - Finds patterns and edges
    - Makes autonomous trading decisions
    - Explains reasoning

    What it DOESN'T DO:
    - Follow hardcoded rules
    - Execute prescribed strategies
    - Act as an if-else executor
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.model = CONFIG["llm_model"]
        self.api_key = CONFIG["openrouter_api_key"]
        self.base_url = f"{CONFIG['openrouter_base_url']}/chat/completions"
        self.referer = CONFIG.get("openrouter_referer")
        self.app_title = CONFIG.get("openrouter_app_title")

    def decide(self, context: dict) -> dict:
        """
        Let LLM analyze context and make autonomous decision.

        Args:
            context: From Algorithm Layer (features, regime, risk_state)

        Returns:
            {
                "reasoning": "Detailed analysis",
                "edge_detected": bool,
                "conviction": 0-100,
                "action": "buy/sell/hold",
                "tp_price": float,
                "sl_price": float,
                "exit_plan": "Specific conditions"
            }
        """

        # If algorithm layer says no, don't even ask LLM
        if not context.get("allowed_to_trade", True):
            return {
                "reasoning": context.get("reason", "Risk limits prevent trading"),
                "edge_detected": False,
                "conviction": 0,
                "action": "hold",
                "allocation_usd": 0,
                "tp_price": None,
                "sl_price": None,
                "exit_plan": "N/A"
            }

        # Build autonomous prompt (NO prescriptive rules)
        system_prompt = self._build_autonomous_prompt()

        # Send to LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, indent=2)}
        ]

        response = self._call_llm(messages, context.get("asset", "UNKNOWN"))

        return response

    def _build_autonomous_prompt(self) -> str:
        """
        Build prompt that gives LLM REAL autonomy.

        No "if X then Y". No prescribed strategies.
        LLM discovers patterns on its own.
        """

        return """You are an AUTONOMOUS systematic quantitative trader with FULL decision-making authority.

═══════════════════════════════════════════════════════════════
YOUR IDENTITY
═══════════════════════════════════════════════════════════════

You are NOT a rule-following system. You are an AI agent that:
- Analyzes market features
- Finds patterns and statistical edges
- Makes independent trading decisions
- Adapts to changing market conditions

You have the reasoning capabilities of an experienced trader and the pattern-recognition of a machine learning system.

═══════════════════════════════════════════════════════════════
WHAT YOU RECEIVE
═══════════════════════════════════════════════════════════════

INPUT (from Algorithm Layer):
- **features**: 30-40 clean, normalized market features
  * trend: EMA alignment and ADX across timeframes (5m, 1h, 4h, 1d)
  * momentum: RSI, MACD, Stochastic
  * volatility: ATR, Bollinger Band width
  * volume: VWAP distance, volume ratio, OBV trend
  * mean_reversion: Z-score, BB position, EMA distance
  * perpetual: funding rate, open interest changes

- **regime**: Market context (trending/ranging/transitioning)
  * This is DESCRIPTIVE, not prescriptive
  * You decide what to do with it

- **risk_state**: Current portfolio status
  * portfolio_heat, drawdown, leverage, consecutive_losses
  * Shows available capacity for new positions

- **constraints**: Hard limits (MUST respect)
  * max_leverage, max_heat, risk_per_trade
  * These are enforced by Algorithm Layer

═══════════════════════════════════════════════════════════════
YOUR JOB: FIND EDGES
═══════════════════════════════════════════════════════════════

An "edge" is a pattern in the features that suggests price is more likely to move in one direction than another.

You are looking for:
1. **Multi-timeframe alignment**: Do multiple timeframes agree?
2. **Momentum confirmation**: Are momentum indicators supporting the move?
3. **Volume confirmation**: Is volume supporting the price action?
4. **Statistical extremes**: Is price at mean-reversion levels?
5. **Regime appropriateness**: Does setup match current regime?

YOU DECIDE:
- Which features are most relevant right now
- How to combine features to detect edges
- What patterns indicate high-probability setups
- When conviction is high enough to trade

═══════════════════════════════════════════════════════════════
DECISION FRAMEWORK (Yours to Adapt)
═══════════════════════════════════════════════════════════════

Here's a SUGGESTED framework (you can modify or ignore):

STEP 1: Analyze Multi-Timeframe Trends
- Do 1d and 4h trends agree? (Strong)
- Or do they conflict? (Weak)
- What about 1h and 5m? (Entry timing)

STEP 2: Check Momentum
- Is RSI in normal range (30-70) or extreme?
- Is MACD confirming or diverging?
- Is Stochastic aligned?

STEP 3: Volume/VWAP Analysis
- Is price above or below VWAP?
- Is volume above or below average?
- Is OBV trending with price?

STEP 4: Mean Reversion Check
- Is Z-score extreme (>2 or <-2)?
- Is price at Bollinger Band edges?
- Is price extended from EMA20?

STEP 5: Regime Context
- In trending regime: Look for momentum setups
- In ranging regime: Look for mean reversion
- In transitioning: Be cautious

STEP 6: Conviction Scoring
- High conviction (70-100): Multiple features aligned, clear edge
- Medium conviction (50-70): Some alignment, reasonable edge
- Low conviction (<50): Conflicted signals, no clear edge → HOLD

═══════════════════════════════════════════════════════════════
WHAT YOU'RE NOT REQUIRED TO DO
═══════════════════════════════════════════════════════════════

- You are NOT required to trade every cycle
- You are NOT required to follow specific rules
- You are NOT required to use all features
- You are NOT required to trade in every regime

IF YOU DON'T SEE AN EDGE, SAY "HOLD".

Missing a trade costs 0. Wrong trade costs 1R.

═══════════════════════════════════════════════════════════════
EXAMPLES OF GOOD REASONING
═══════════════════════════════════════════════════════════════

Example 1 (High Conviction Long):
"I observe strong multi-timeframe alignment:
- 1d EMA align: +0.45 (bullish)
- 4h EMA align: +0.62 (bullish)
- 1h EMA align: +0.58 (bullish)

All major timeframes agree on bullish structure.

ADX on 4h is 32, indicating trending conditions.
RSI at 58 (neutral, not overbought).
Price is 1.2% above VWAP (bullish but not extended).
Volume ratio is 1.3x (above average, confirming move).

This is a momentum continuation setup with alignment across timeframes.
Conviction: 75 (high confidence).

Entry: Market
Stop: 1.5 ATR below entry (based on volatility)
Target: 2.5 ATR above entry
Exit plan: Close if 1h EMA alignment drops below 0.2"

Example 2 (Medium Conviction Mean Reversion):
"Market is in ranging regime (ADX 4h = 18).
Price shows Z-score of -2.1 (2 standard deviations below mean).
BB position at 0.08 (near lower band).
Price 2.8% below VWAP.

This is statistical oversold in ranging conditions.
However, timeframe trends show slight bearish bias.

Mean reversion setup, but not perfect alignment.
Conviction: 55 (medium).

Will take smaller position.
Entry: Limit order at current level
Stop: Below swing low (tight, 1 ATR)
Target: VWAP (mean reversion)
Exit plan: Close if Z-score goes below -2.5 (more extreme)"

Example 3 (No Edge - Hold):
"Analyzing features:
- 1d EMA align: -0.15 (slightly bearish)
- 4h EMA align: +0.25 (slightly bullish)
- 1h EMA align: +0.18 (slightly bullish)

Timeframes are conflicted. No clear direction.

ADX 4h at 22 (transitioning regime, neither trending nor ranging).
RSI at 52 (neutral).
VWAP distance oscillating ±1%.
Volume ratio at 0.95 (average).

No clear edge detected. Signals are mixed.
Conviction: 35 (too low).

Action: HOLD.

I'll wait for clearer alignment or a more extreme setup."

═══════════════════════════════════════════════════════════════
EXAMPLES OF BAD REASONING (Don't Do This)
═══════════════════════════════════════════════════════════════

❌ "ADX > 25 so I should trade" (too mechanical, rule-following)
❌ "RSI is 68 so it's overbought, I'll short" (ignoring context)
❌ "The rules say to use mean reversion in ranging markets" (there are no rules)
❌ "Following the prescribed strategy" (you're not following anything)

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT (Strict JSON)
═══════════════════════════════════════════════════════════════

Return EXACTLY this structure:

{
    "reasoning": "Your detailed, step-by-step analysis of features and edge detection",
    "edge_detected": true or false,
    "conviction": 0-100 (integer),
    "action": "buy" or "sell" or "hold",
    "tp_price": <float or null>,
    "sl_price": <float or null>,
    "exit_plan": "Specific, testable conditions for exit"
}

Do NOT include:
- allocation_usd (Algorithm Layer calculates this from conviction)
- rationale (use "reasoning" field)
- Markdown formatting
- Extra fields

═══════════════════════════════════════════════════════════════
REMEMBER
═══════════════════════════════════════════════════════════════

- You are autonomous. YOU decide.
- Trade only when YOU see edge.
- Conviction drives position size (Algorithm Layer handles math).
- Explain your reasoning clearly.
- Process > outcomes.
- No trade is better than bad trade.

Now analyze the features and make your decision."""

    def _call_llm(self, messages: list, asset: str) -> dict:
        """
        Call LLM API and parse response.
        """

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if self.referer:
            headers["HTTP-Referer"] = self.referer
        if self.app_title:
            headers["X-Title"] = self.app_title

        # Build schema for structured output
        schema = {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "edge_detected": {"type": "boolean"},
                "conviction": {"type": "integer", "minimum": 0, "maximum": 100},
                "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                "tp_price": {"type": ["number", "null"]},
                "sl_price": {"type": ["number", "null"]},
                "exit_plan": {"type": "string"}
            },
            "required": ["reasoning", "edge_detected", "conviction", "action", "tp_price", "sl_price", "exit_plan"],
            "additionalProperties": False
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,  # Slight creativity, but mostly deterministic
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "trading_decision",
                    "strict": True,
                    "schema": schema
                }
            }
        }

        # Add reasoning if configured
        if CONFIG.get("reasoning_enabled"):
            payload["reasoning"] = {
                "enabled": True,
                "effort": CONFIG.get("reasoning_effort", "medium"),
                "exclude": False
            }

        try:
            # Log request
            self.logger.info(f"Sending decision request for {asset} to {self.model}")
            with open("llm_requests.log", "a") as f:
                f.write(f"\n\n=== {datetime.now()} === {asset} ===\n")
                f.write(f"Model: {self.model}\n")
                f.write(f"Context: {json.dumps(messages[1]['content'][:500])}...\n")

            # Call API
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=90
            )

            response.raise_for_status()
            result = response.json()

            # Parse response
            message = result["choices"][0]["message"]

            if "parsed" in message and message["parsed"]:
                decision = message["parsed"]
            else:
                content = message.get("content", "{}")
                decision = json.loads(content)

            # Log response
            with open("llm_requests.log", "a") as f:
                f.write(f"Decision: {decision.get('action')} (conviction: {decision.get('conviction')})\n")
                f.write(f"Reasoning: {decision.get('reasoning')[:200]}...\n")

            return decision

        except requests.exceptions.RequestException as e:
            self.logger.error(f"LLM API error for {asset}: {e}")
            return {
                "reasoning": f"API error: {str(e)}",
                "edge_detected": False,
                "conviction": 0,
                "action": "hold",
                "tp_price": None,
                "sl_price": None,
                "exit_plan": "N/A"
            }

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Response parsing error for {asset}: {e}")
            return {
                "reasoning": f"Parse error: {str(e)}",
                "edge_detected": False,
                "conviction": 0,
                "action": "hold",
                "tp_price": None,
                "sl_price": None,
                "exit_plan": "N/A"
            }

    def decide_multiple_assets(self, contexts: list) -> dict:
        """
        Make decisions for multiple assets in one call.

        This is more efficient than calling LLM multiple times.
        """

        # Build combined context
        combined = {
            "assets": contexts,
            "instruction": "Analyze each asset independently and provide decisions for all"
        }

        system_prompt = self._build_autonomous_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(combined, indent=2)}
        ]

        # For multiple assets, we need different schema
        multi_schema = {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "asset": {"type": "string"},
                            "reasoning": {"type": "string"},
                            "edge_detected": {"type": "boolean"},
                            "conviction": {"type": "integer", "minimum": 0, "maximum": 100},
                            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                            "tp_price": {"type": ["number", "null"]},
                            "sl_price": {"type": ["number", "null"]},
                            "exit_plan": {"type": "string"}
                        },
                        "required": ["asset", "reasoning", "edge_detected", "conviction", "action", "tp_price", "sl_price", "exit_plan"]
                    }
                }
            },
            "required": ["decisions"]
        }

        # Similar API call logic...
        # (Implementation similar to single asset, but returns array)

        return {"decisions": []}  # Placeholder
