"""CAMEL-powered trading agent with memory and enhanced context engineering.

This agent replaces the standard TradingAgent with CAMEL's ChatAgent framework,
providing:
- Stateful memory of last N trades
- Multi-agent collaboration capabilities
- Enhanced tool integration
- Better context management
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# CAMEL imports - will be available after pip install completes
try:
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
    from camel.toolkits import FunctionTool
    from camel.memories import (
        ChatHistoryMemory,
        VectorDBMemory,
        MemoryRecord,
    )
    CAMEL_AVAILABLE = True
except ImportError:
    CAMEL_AVAILABLE = False
    logging.warning("CAMEL not installed - falling back to basic agent")

from src.config_loader import CONFIG
from src.indicators.taapi_client import TAAPIClient
from src.data.glassnode_client import GlassnodeClient
from src.data.feargreed_client import FearGreedClient
from src.data.macro_client import MacroDataClient
from src.utils.signal_calculator import validate_trade_decision


class CAMELTradingAgent:
    """Enhanced trading agent using CAMEL framework with memory and context engineering."""

    def __init__(self):
        """Initialize CAMEL agent with memory, tools, and external data clients."""
        self.taapi = TAAPIClient()
        self.glassnode = GlassnodeClient()
        self.feargreed = FearGreedClient()
        self.macro = MacroDataClient()

        # Configuration
        self.model_name = CONFIG.get("llm_model", "openai/gpt-4")
        self.memory_trades_count = int(CONFIG.get("memory_trades_count", 25))
        self.position_size_pct = float(CONFIG.get("position_size_pct", 2.0))
        self.leverage_min = float(CONFIG.get("leverage_min", 3.0))
        self.leverage_max = float(CONFIG.get("leverage_max", 10.0))

        if not CAMEL_AVAILABLE:
            logging.error("CAMEL framework not available - agent will not function properly")
            self.agent = None
            self.memory = None
            return

        # Initialize CAMEL components
        self._init_model()
        self._init_memory()
        self._init_tools()
        self._init_agent()

    def _init_model(self):
        """Initialize the LLM model through CAMEL's ModelFactory."""
        try:
            # Parse model platform from model name
            # E.g., "openai/gpt-4" -> platform=OpenAI, model=gpt-4
            # E.g., "anthropic/claude-3-5-sonnet" -> platform=Anthropic
            # E.g., "x-ai/grok-4" -> platform=OpenAI (via OpenRouter)

            model_str = self.model_name.lower()

            if "gpt" in model_str or "openai" in model_str:
                platform = ModelPlatformType.OPENAI
                # Extract model name after slash
                model_type_str = self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name
            elif "claude" in model_str or "anthropic" in model_str:
                platform = ModelPlatformType.ANTHROPIC
                model_type_str = self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name
            elif "gemini" in model_str:
                platform = ModelPlatformType.GEMINI
                model_type_str = self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name
            else:
                # Default to OpenAI-compatible (works with OpenRouter)
                platform = ModelPlatformType.OPENAI
                model_type_str = self.model_name

            # For OpenRouter, we'll use the base URL override
            model_config_extra = {}
            if CONFIG.get("openrouter_base_url"):
                model_config_extra["base_url"] = f"{CONFIG['openrouter_base_url']}/chat/completions"
                model_config_extra["api_key"] = CONFIG.get("openrouter_api_key")

            self.model = ModelFactory.create(
                model_platform=platform,
                model_type=model_type_str,
                model_config_dict=model_config_extra if model_config_extra else None,
            )

            logging.info(f"CAMEL model initialized: {self.model_name}")

        except Exception as e:
            logging.error(f"Failed to initialize CAMEL model: {e}")
            self.model = None

    def _init_memory(self):
        """Initialize memory system for trade history retention."""
        try:
            # Use ChatHistoryMemory for simplicity (can upgrade to VectorDB later)
            self.memory = ChatHistoryMemory()
            logging.info(f"Memory initialized (capacity: {self.memory_trades_count} trades)")
        except Exception as e:
            logging.error(f"Failed to initialize memory: {e}")
            self.memory = None

    def _init_tools(self):
        """Initialize tools for the agent to use.

        NOTE: Tools are optional since orchestrator provides all data in context.
        Kept minimal for emergency data verification only.
        """
        self.tools = []  # No tools - all data comes from orchestrator context
        logging.info("Agent configured without tools (all data from orchestrator)")

    def _init_agent(self):
        """Initialize the CAMEL ChatAgent with system message."""
        try:
            system_message = self._build_system_message()

            self.agent = ChatAgent(
                system_message=system_message,
                model=self.model,
                tools=self.tools if self.tools else None,
                memory=self.memory,
            )

            logging.info("CAMEL ChatAgent initialized successfully")

        except Exception as e:
            logging.error(f"Failed to initialize CAMEL agent: {e}")
            self.agent = None

    def _build_system_message(self) -> str:
        """Build simplified system message focused on validation, not calculation."""
        return f"""You are a QUANTITATIVE TRADING VALIDATOR for crypto perpetual futures.

Your role: Validate and adjust pre-computed trading signals based on market structure and portfolio context.

## Key Principles
- Think like a professional quant: neutral, data-driven, unbiased
- DO NOT rush into trades based on trends or emotions
- Your job is to VALIDATE signals, not compute from scratch
- All calculations (confluence, leverage) are already done programmatically
- Focus on portfolio risk, position sizing, and invalidation conditions

## What You Receive
You will be given:
1. **Pre-computed signals** for each asset with:
   - Calculated confluence score (0-10 = alignment strength)
   - Direction (bullish/bearish/neutral)
   - Signal breakdown: X bullish signals vs Y bearish signals (transparency!)
   - Recommended leverage (already adjusted for volatility + macro)
   - Suggested TP/SL levels
   - Market summary (trend, volatility, liquidity)

2. **Portfolio context**:
   - Current positions (with unrealized PnL)
   - Portfolio heat (total exposure %)
   - Account equity and buying power
   - Number of open longs/shorts

3. **Global environment**:
   - Macro risk environment (risk-on/off)
   - Sentiment (Fear & Greed Index)

4. **Recent performance** (to prevent recency bias):
   - Win rate % over last 20 trades
   - Recent streak (e.g., "WWL" = 2 wins, 1 loss)
   - Average PnL %
   - IMPORTANT: Do NOT over-react to recent streaks (normal variance)

## Your Validation Checklist

For each pre-computed signal, validate:

1. **Portfolio Risk**:
   - Can we open this position without exceeding portfolio heat limits?
   - Do we already have correlated positions (e.g., BTC + ETH)?
   - Is our buying power sufficient?

2. **Signal Quality**:
   - Is confluence score high enough to justify the trade?
   - Check bullish vs bearish signal counts - are there significant conflicts?
   - Example: 6 bullish + 4 bearish = low confidence despite confluence=2
   - Does the recommended leverage make sense for current volatility?

3. **Market Structure**:
   - Is this the right time to enter (not choppy, not overextended)?
   - Do the suggested TP/SL levels make sense?
   - Are we trading against portfolio momentum?

4. **Memory & Patterns**:
   - Did we recently close a similar position (win or loss)?
   - Are we repeating a mistake?
   - Is this signal different enough from recent trades?

5. **Invalidation Conditions**:
   - What would invalidate this trade immediately?
   - Clear exit triggers if thesis breaks

## Decision Guidelines

**When to APPROVE a signal (buy/sell)**:
- Confluence score ≥ 6
- Portfolio heat won't exceed limits
- No highly correlated positions
- Recommended leverage is reasonable
- TP/SL levels are logical
- Sufficient buying power

**When to MODIFY a signal**:
- Reduce leverage if portfolio heat is high
- Reduce position size if correlated positions exist
- Adjust TP/SL if levels don't match current structure

**When to REJECT (HOLD)**:
- Confluence score < 5 (weak signal)
- Portfolio heat already too high
- Too many open positions
- Conflicting with recent losing trade on same asset
- Macro environment too uncertain
- Insufficient buying power

## Output Format
Return STRICT JSON:
{{
  "reasoning": "Brief validation summary (2-3 sentences per asset)",
  "trade_decisions": [
    {{
      "asset": "BTC",
      "action": "buy" | "sell" | "hold",
      "allocation_usd": {self.position_size_pct}% of account (or adjusted),
      "leverage": <approved leverage (from signal or adjusted)>,
      "tp_price": <take profit level>,
      "sl_price": <stop loss level>,
      "exit_plan": "Clear invalidation triggers",
      "rationale": "Why approved/modified/rejected",
      "confidence": <1-10>,
      "confluence_score": <from pre-computed signal>
    }}
  ]
}}

## Critical Reminders
- You are NOT doing analysis from scratch - signals are pre-computed
- Your job is VALIDATION and risk management
- Stay NEUTRAL - no bias toward bullish or bearish
- When uncertain, choose HOLD (capital preservation > forced trades)
- Position sizing: default {self.position_size_pct}% per trade
- Leverage range: {self.leverage_min}x - {self.leverage_max}x
- No naked positions - always set TP and SL
"""

    def decide_trade(self, assets: List[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate pre-computed trade signals and make final decisions.

        Args:
            assets: List of asset tickers to analyze
            context: Dict with pre-computed signals, portfolio context, and environment
                Expected structure from orchestrator.fetch_signals_for_assets():
                {
                    "trade_signals": [pre-computed signals],
                    "portfolio": {portfolio metrics},
                    "global_context": {macro, sentiment},
                    "recent_trades": [last 10 trades]
                }

        Returns:
            Dict with reasoning and trade_decisions (validated and adjusted)
        """
        if not CAMEL_AVAILABLE or not self.agent:
            logging.error("CAMEL agent not initialized")
            return {
                "reasoning": "CAMEL framework not available",
                "trade_decisions": [
                    {
                        "asset": asset,
                        "action": "hold",
                        "allocation_usd": 0,
                        "tp_price": None,
                        "sl_price": None,
                        "exit_plan": "System error",
                        "rationale": "CAMEL not initialized",
                    }
                    for asset in assets
                ],
            }

        try:
            # Extract pre-computed signals for clarity
            trade_signals = context.get("trade_signals", [])
            portfolio = context.get("portfolio", {})
            global_ctx = context.get("global_context", {})
            recent_trades = context.get("recent_trades", [])
            recent_perf = context.get("recent_performance", {})

            # Build simplified message for LLM
            user_message = BaseMessage.make_user_message(
                role_name="TradingSystem",
                content=f"""Validate the following pre-computed trade signals:

**PRE-COMPUTED SIGNALS** (calculations already done):
{json.dumps(trade_signals, indent=2)}

**PORTFOLIO CONTEXT**:
- Account Equity: ${portfolio.get('equity_usd', 0):,.2f}
- Available Buying Power: ${portfolio.get('available_buying_power_usd', 0):,.2f}
- Current Exposure: ${portfolio.get('total_exposure_usd', 0):,.2f}
- Portfolio Heat: {portfolio.get('portfolio_heat_pct', 0):.1f}%
- Open Positions: {portfolio.get('num_positions', 0)} ({portfolio.get('num_longs', 0)} longs, {portfolio.get('num_shorts', 0)} shorts)
- Unrealized PnL: ${portfolio.get('unrealized_pnl_usd', 0):,.2f}

Current Positions:
{json.dumps(portfolio.get('open_positions', []), indent=2)}

**GLOBAL ENVIRONMENT**:
Macro: {global_ctx.get('macro', {}).get('risk_environment', 'unknown')}
Sentiment: {global_ctx.get('sentiment', {}).get('classification', 'unknown')} (F&G: {global_ctx.get('sentiment', {}).get('value', 'N/A')})

**RECENT PERFORMANCE** (last 20 trades):
- Win Rate: {recent_perf.get('win_rate_pct', 0):.1f}% ({recent_perf.get('wins', 0)}W / {recent_perf.get('losses', 0)}L)
- Recent Streak: {recent_perf.get('recent_streak', 'N/A')} (W=win, L=loss)
- Avg PnL per trade: {recent_perf.get('avg_pnl_pct', 0):.2f}%
REMINDER: Do not over-react to streaks - they are normal variance.

**YOUR TASK**:
For each pre-computed signal, validate and decide:
1. APPROVE (buy/sell) if signal is strong and portfolio allows
2. MODIFY if adjustments needed (reduce leverage, size, etc.)
3. REJECT (hold) if signal is weak or portfolio risk is too high

Return your validation in the required JSON format.
""",
            )

            # Get response from agent
            response = self.agent.step(user_message)

            # Extract and parse response
            response_content = response.msgs[0].content if response.msgs else "{}"

            # Try to parse JSON from response
            try:
                parsed = json.loads(response_content)
                if isinstance(parsed, dict) and "trade_decisions" in parsed:
                    # Validate each decision
                    validated_decisions = []
                    for decision in parsed.get("trade_decisions", []):
                        # Find corresponding signal to get current price
                        signal = next(
                            (s for s in trade_signals if s.get("asset") == decision.get("asset")),
                            None
                        )
                        current_price = signal.get("current_price") if signal else None

                        # Apply programmatic validation
                        if current_price:
                            validated = validate_trade_decision(
                                decision=decision,
                                current_price=current_price,
                                leverage_min=self.leverage_min,
                                leverage_max=self.leverage_max,
                            )
                        else:
                            validated = decision

                        # Add defaults
                        validated.setdefault("allocation_usd", 0)
                        validated.setdefault("tp_price", None)
                        validated.setdefault("sl_price", None)
                        validated.setdefault("exit_plan", "")
                        validated.setdefault("rationale", "")
                        validated.setdefault("leverage", self.leverage_min)
                        validated.setdefault("confidence", 5)

                        validated_decisions.append(validated)

                    parsed["trade_decisions"] = validated_decisions
                    return parsed

            except json.JSONDecodeError:
                # Response might be wrapped in markdown or prose
                logging.warning("Failed to parse JSON from CAMEL response, attempting extraction")
                # Try to extract JSON block
                if "```json" in response_content:
                    json_str = response_content.split("```json")[1].split("```")[0].strip()
                    parsed = json.loads(json_str)
                    if "trade_decisions" in parsed:
                        # Apply same validation
                        for decision in parsed["trade_decisions"]:
                            signal = next(
                                (s for s in trade_signals if s.get("asset") == decision.get("asset")),
                                None
                            )
                            if signal:
                                validate_trade_decision(
                                    decision,
                                    signal.get("current_price"),
                                    self.leverage_min,
                                    self.leverage_max,
                                )
                        return parsed
                elif "{" in response_content and "}" in response_content:
                    # Try to find JSON object
                    start = response_content.find("{")
                    end = response_content.rfind("}") + 1
                    json_str = response_content[start:end]
                    parsed = json.loads(json_str)
                    return parsed

            # Fallback: return hold for all assets
            return {
                "reasoning": "Failed to parse response from CAMEL agent",
                "trade_decisions": [
                    {
                        "asset": asset,
                        "action": "hold",
                        "allocation_usd": 0,
                        "tp_price": None,
                        "sl_price": None,
                        "exit_plan": "Parse error",
                        "rationale": "Could not parse agent response",
                    }
                    for asset in assets
                ],
            }

        except Exception as e:
            logging.error(f"CAMEL agent decision error: {e}")
            return {
                "reasoning": f"Agent error: {str(e)}",
                "trade_decisions": [
                    {
                        "asset": asset,
                        "action": "hold",
                        "allocation_usd": 0,
                        "tp_price": None,
                        "sl_price": None,
                        "exit_plan": "Error",
                        "rationale": str(e),
                    }
                    for asset in assets
                ],
            }

    def add_trade_to_memory(self, trade_data: Dict[str, Any]):
        """Add completed trade to memory for future reference.

        Args:
            trade_data: Dict with trade details (asset, action, outcome, etc.)
        """
        if not self.memory:
            return

        try:
            # Create memory record
            memory_text = f"""Trade: {trade_data.get('asset')} {trade_data.get('action')}
Entry: ${trade_data.get('entry_price')}
Exit: ${trade_data.get('exit_price', 'N/A')}
PnL: ${trade_data.get('pnl', 0):.2f}
Outcome: {trade_data.get('outcome', 'unknown')}
Reason: {trade_data.get('exit_reason', 'N/A')}
Timestamp: {trade_data.get('timestamp', datetime.now().isoformat())}
"""

            # Add to memory (CAMEL's memory will handle retention logic)
            message = BaseMessage.make_assistant_message(
                role_name="TradingAgent",
                content=memory_text,
            )

            self.memory.write_records([MemoryRecord(message=message)])

            logging.info(f"Added trade to memory: {trade_data.get('asset')} {trade_data.get('action')}")

        except Exception as e:
            logging.error(f"Failed to add trade to memory: {e}")

    def get_trade_memory_summary(self) -> str:
        """Get summary of recent trades from memory.

        Returns:
            String summary of recent trading history
        """
        if not self.memory:
            return "No memory available"

        try:
            records = self.memory.get_records()
            if not records:
                return "No trades in memory yet"

            # Get last N trades
            recent = records[-self.memory_trades_count:]

            summary = f"Last {len(recent)} trades:\n"
            for record in recent:
                summary += f"- {record.message.content}\n"

            return summary

        except Exception as e:
            logging.error(f"Failed to retrieve memory: {e}")
            return f"Memory error: {str(e)}"
