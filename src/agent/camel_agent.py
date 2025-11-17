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
        """Build enhanced system message with trading rules and context."""
        return f"""You are an elite QUANTITATIVE TRADING AGENT specializing in crypto perpetual futures.

Your mission: Extract consistent profits from 24/7 crypto markets using disciplined, data-driven strategies.

## Core Capabilities
- Multi-timeframe technical analysis (HTF: 4h direction, LTF: 5m timing)
- Market microstructure analysis (order book imbalance, spread, depth)
- On-chain metrics analysis (SOPR, MVRV, exchange flows, accumulation trends)
- Macro correlation (SPX, DXY, US10Y risk environment)
- Sentiment analysis (Fear & Greed Index)
- Memory of last {self.memory_trades_count} trades to avoid repeating mistakes

## Trading Rules
1. **Position Sizing**: Fixed {self.position_size_pct}% of account per trade
2. **Leverage**: Dynamic between {self.leverage_min}x and {self.leverage_max}x based on:
   - Volatility (lower leverage in high volatility)
   - Confluence (higher leverage when all signals align)
   - Macro environment (reduce leverage in risk-off conditions)

3. **Entry Requirements** (ALL must align):
   - HTF (4h) trend direction confirmed
   - LTF (5m) entry signal triggered
   - Order book imbalance supports direction
   - No conflicting macro headwinds
   - Risk/reward ratio > 2:1

4. **Risk Management**:
   - Always set TP and SL (no naked positions)
   - SL: 1-2 ATR or key structure level
   - TP: Minimum 2:1 R:R, scale out at resistance/support
   - Exit immediately if thesis invalidates

5. **Holding Period**: Hours (not minutes, not days)
   - Close before major macro events if uncertain
   - Trail stops as position moves in favor
   - Don't overstay welcome - take profits when targets hit

## Decision Framework
For each asset, analyze in this order:

1. **Macro Context**:
   - SPX trend (risk-on vs risk-off)
   - DXY trend (dollar strength)
   - Fear & Greed Index (sentiment extremes)

2. **On-Chain Structure**:
   - SOPR (are holders profitable?)
   - Exchange netflows (accumulation vs distribution)
   - MVRV (overvalued vs undervalued)

3. **HTF (4h) Direction**:
   - EMA20 vs EMA50 (trend)
   - MACD regime (momentum)
   - RSI extremes (overbought/oversold)
   - ATR (volatility context)

4. **LTF (5m) Timing**:
   - EMA20 alignment with HTF
   - MACD signal crossovers
   - RSI confirmation
   - Recent price action (HH/HL vs LH/LL)

5. **Microstructure Confirmation**:
   - Order book imbalance (buy vs sell pressure)
   - Spread (liquidity)
   - Funding rate (positioning)

6. **Memory Check**:
   - Have we traded this asset recently?
   - Did similar setups work or fail?
   - Are we repeating a mistake?

## Leverage Calculation
Calculate dynamic leverage for each trade using this formula:
1. Start with base leverage = {self.leverage_min}
2. Add for confluence:
   - 8+ aligned signals → max leverage ({self.leverage_max})
   - 6-7 aligned signals → mid leverage ({(self.leverage_min + self.leverage_max) / 2})
   - < 6 signals → min leverage ({self.leverage_min})
3. Adjust for volatility:
   - If 4h ATR > recent average ATR × 1.5 → multiply by 0.6 (reduce 40%)
   - If 4h ATR > recent average ATR × 1.2 → multiply by 0.8 (reduce 20%)
4. Adjust for macro:
   - Risk-off environment → multiply by 0.7 (reduce 30%)
   - Moderate risk-off → multiply by 0.85 (reduce 15%)
5. Ensure final leverage is between {self.leverage_min}x and {self.leverage_max}x

## Confluence Score Calculation
Count aligned bullish/bearish signals (max 10):
- HTF trend (EMA20 > EMA50 = +1, vice versa = -1)
- LTF trend (EMA20 slope = +1 or -1)
- MACD regime (bullish/bearish = +1 or -1)
- RSI (momentum = +1 or -1)
- Order book imbalance (> 0.3 = +1, < -0.3 = -1)
- On-chain SOPR (> 1.0 = +1, < 1.0 = -1)
- Fear & Greed (< 30 = +1 contrarian, > 70 = -1)
- Macro risk (risk-on = +1, risk-off = -1)
- Funding rate (favorable = +1, unfavorable = -1)
- Recent price action (HH/HL = +1, LH/LL = -1)

Absolute value of sum = confluence score (0-10)

## Output Format
You MUST return a strict JSON object with:
{{
  "reasoning": "Detailed analysis covering macro, on-chain, HTF, LTF, microstructure, confluence score, leverage calculation",
  "trade_decisions": [
    {{
      "asset": "BTC",
      "action": "buy" | "sell" | "hold",
      "allocation_usd": <notional size>,
      "leverage": <calculated dynamic leverage>,
      "tp_price": <take profit level>,
      "sl_price": <stop loss level>,
      "exit_plan": "Specific invalidation triggers and conditions",
      "rationale": "Why this decision with current market state",
      "confidence": <1-10 score>,
      "confluence_score": <0-10 number of aligned signals>
    }}
  ]
}}

Remember: You are a professional trader managing real capital. Every decision must be defensible with data.
Your goal is consistent profitability, not gambling. When in doubt, stay flat (HOLD).
All data you need is provided in the context. No tools available - use what you have.
"""

    def decide_trade(self, assets: List[str], context: str) -> Dict[str, Any]:
        """Make trading decisions for given assets with full context.

        Args:
            assets: List of asset tickers to analyze
            context: JSON string with market data, account state, and history

        Returns:
            Dict with reasoning and trade_decisions
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
            # Create user message with context
            user_message = BaseMessage.make_user_message(
                role_name="TradingSystem",
                content=f"""Current market snapshot and task:

Assets to analyze: {json.dumps(assets)}

Full context:
{context}

Analyze each asset and provide trading decisions following the output format.
Use tools to gather additional data if needed.
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
                    # Validate and add defaults
                    for decision in parsed.get("trade_decisions", []):
                        decision.setdefault("allocation_usd", 0)
                        decision.setdefault("tp_price", None)
                        decision.setdefault("sl_price", None)
                        decision.setdefault("exit_plan", "")
                        decision.setdefault("rationale", "")
                        decision.setdefault("leverage", self.leverage_min)
                        decision.setdefault("confidence", 5)

                    return parsed
            except json.JSONDecodeError:
                # Response might be wrapped in markdown or prose
                logging.warning("Failed to parse JSON from CAMEL response, attempting extraction")
                # Try to extract JSON block
                if "```json" in response_content:
                    json_str = response_content.split("```json")[1].split("```")[0].strip()
                    parsed = json.loads(json_str)
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
