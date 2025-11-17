"""Data fetching orchestrator for parallel execution of multiple data sources.

Coordinates fetching from:
- Technical indicators (TAAPI)
- On-chain metrics (Glassnode)
- Sentiment (Fear & Greed)
- Macro data (SPX, DXY, US10Y)
- Market microstructure (Hyperliquid order book)

All fetches happen in parallel using asyncio for maximum efficiency.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.indicators.taapi_client import TAAPIClient
from src.data.glassnode_client import GlassnodeClient
from src.data.feargreed_client import FearGreedClient
from src.data.macro_client import MacroDataClient
from src.utils.signal_calculator import SignalCalculator


class DataOrchestrator:
    """Orchestrates parallel data fetching from multiple sources."""

    def __init__(self, taapi: TAAPIClient, glassnode: GlassnodeClient,
                 feargreed: FearGreedClient, macro: MacroDataClient,
                 leverage_min: float = 3.0, leverage_max: float = 10.0):
        """Initialize orchestrator with data clients.

        Args:
            taapi: Technical indicators client
            glassnode: On-chain metrics client
            feargreed: Fear & Greed index client
            macro: Macro data client
            leverage_min: Minimum leverage for signal calculator
            leverage_max: Maximum leverage for signal calculator
        """
        self.taapi = taapi
        self.glassnode = glassnode
        self.feargreed = feargreed
        self.macro = macro
        self.signal_calculator = SignalCalculator(leverage_min, leverage_max)

    async def fetch_all_market_data(
        self,
        assets: List[str],
        hyperliquid_api,
        include_onchain: bool = True,
        include_macro: bool = True,
        include_sentiment: bool = True,
        include_microstructure: bool = True,
    ) -> Dict[str, Any]:
        """Fetch all market data in parallel.

        Args:
            assets: List of asset tickers to fetch data for
            hyperliquid_api: HyperliquidAPI instance for price/microstructure
            include_onchain: Whether to fetch Glassnode data
            include_macro: Whether to fetch macro data (SPX, DXY, etc.)
            include_sentiment: Whether to fetch Fear & Greed index
            include_microstructure: Whether to fetch order book data

        Returns:
            Dict with all fetched data organized by source
        """
        start_time = datetime.now()
        logging.info(f"Starting parallel data fetch for {len(assets)} assets")

        # Create tasks list
        tasks = []

        # 1. Global data (fetch once, applies to all assets)
        if include_sentiment:
            tasks.append(self._fetch_sentiment())

        if include_macro:
            tasks.append(self._fetch_macro())

        # 2. Asset-specific data (fetch for each asset in parallel)
        for asset in assets:
            # Technical indicators
            tasks.append(self._fetch_ta_data(asset, hyperliquid_api))

            # On-chain metrics (only for major assets)
            if include_onchain and asset in ["BTC", "ETH"]:
                tasks.append(self._fetch_onchain(asset))

            # Microstructure
            if include_microstructure:
                tasks.append(self._fetch_microstructure(asset, hyperliquid_api))

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Organize results
        data = {
            "sentiment": None,
            "macro": None,
            "assets": {asset: {} for asset in assets},
            "fetch_time_ms": (datetime.now() - start_time).total_seconds() * 1000,
        }

        # Parse results (order matches task creation order)
        result_idx = 0

        if include_sentiment:
            data["sentiment"] = results[result_idx] if not isinstance(results[result_idx], Exception) else None
            result_idx += 1

        if include_macro:
            data["macro"] = results[result_idx] if not isinstance(results[result_idx], Exception) else None
            result_idx += 1

        # Asset-specific results
        for asset in assets:
            # TA data
            ta_data = results[result_idx] if not isinstance(results[result_idx], Exception) else {}
            data["assets"][asset]["technical"] = ta_data
            result_idx += 1

            # On-chain
            if include_onchain and asset in ["BTC", "ETH"]:
                onchain_data = results[result_idx] if not isinstance(results[result_idx], Exception) else {}
                data["assets"][asset]["onchain"] = onchain_data
                result_idx += 1

            # Microstructure
            if include_microstructure:
                micro_data = results[result_idx] if not isinstance(results[result_idx], Exception) else {}
                data["assets"][asset]["microstructure"] = micro_data
                result_idx += 1

        logging.info(f"Data fetch completed in {data['fetch_time_ms']:.0f}ms")

        return data

    async def _fetch_sentiment(self) -> Optional[Dict[str, Any]]:
        """Fetch Fear & Greed Index."""
        try:
            return await asyncio.to_thread(self.feargreed.get_sentiment_signal)
        except Exception as e:
            logging.error(f"Sentiment fetch error: {e}")
            return None

    async def _fetch_macro(self) -> Optional[Dict[str, Any]]:
        """Fetch macro data (SPX, DXY, US10Y)."""
        try:
            return await asyncio.to_thread(self.macro.get_all_macro)
        except Exception as e:
            logging.error(f"Macro fetch error: {e}")
            return None

    async def _fetch_onchain(self, asset: str) -> Optional[Dict[str, Any]]:
        """Fetch on-chain metrics for asset."""
        try:
            return await asyncio.to_thread(self.glassnode.get_all_metrics, asset)
        except Exception as e:
            logging.error(f"On-chain fetch error for {asset}: {e}")
            return None

    async def _fetch_ta_data(self, asset: str, hyperliquid_api) -> Dict[str, Any]:
        """Fetch technical analysis data (TAAPI + Hyperliquid basics).

        Returns data for both LTF (5m) and HTF (4h) timeframes.
        """
        try:
            # Fetch in parallel
            ltf_task = asyncio.to_thread(self._fetch_ta_timeframe, asset, "5m")
            htf_task = asyncio.to_thread(self._fetch_ta_timeframe, asset, "4h")
            price_task = hyperliquid_api.get_current_price(asset)
            funding_task = hyperliquid_api.get_funding_rate(asset)
            oi_task = hyperliquid_api.get_open_interest(asset)

            ltf, htf, price, funding, oi = await asyncio.gather(
                ltf_task, htf_task, price_task, funding_task, oi_task,
                return_exceptions=True
            )

            return {
                "current_price": price if not isinstance(price, Exception) else None,
                "funding_rate": funding if not isinstance(funding, Exception) else None,
                "open_interest": oi if not isinstance(oi, Exception) else None,
                "ltf": ltf if not isinstance(ltf, Exception) else {},
                "htf": htf if not isinstance(htf, Exception) else {},
            }

        except Exception as e:
            logging.error(f"TA data fetch error for {asset}: {e}")
            return {}

    def _fetch_ta_timeframe(self, asset: str, interval: str) -> Dict[str, Any]:
        """Fetch TA indicators for a specific timeframe."""
        try:
            symbol = f"{asset}/USDT"

            # Fetch key indicators
            ema20 = self.taapi.fetch_value("ema", symbol, interval, params={"period": 20})
            ema50 = self.taapi.fetch_value("ema", symbol, interval, params={"period": 50})
            rsi = self.taapi.fetch_value("rsi", symbol, interval, params={"period": 14})
            macd_data = self.taapi.fetch_value("macd", symbol, interval, key="valueMACD")
            atr = self.taapi.fetch_value("atr", symbol, interval, params={"period": 14})

            # Fetch short series for trend analysis
            ema20_series = self.taapi.fetch_series("ema", symbol, interval, results=5, params={"period": 20})
            rsi_series = self.taapi.fetch_series("rsi", symbol, interval, results=5, params={"period": 14})

            return {
                "interval": interval,
                "ema20": ema20,
                "ema50": ema50,
                "rsi": rsi,
                "macd": macd_data,
                "atr": atr,
                "ema20_series": ema20_series,
                "rsi_series": rsi_series,
            }

        except Exception as e:
            logging.error(f"TA timeframe fetch error {asset} {interval}: {e}")
            return {"interval": interval}

    async def _fetch_microstructure(self, asset: str, hyperliquid_api) -> Optional[Dict[str, Any]]:
        """Fetch order book microstructure metrics."""
        try:
            return await hyperliquid_api.get_microstructure_metrics(asset)
        except Exception as e:
            logging.error(f"Microstructure fetch error for {asset}: {e}")
            return None

    async def fetch_enhanced_context(
        self,
        assets: List[str],
        hyperliquid_api,
        account_state: Dict[str, Any],
        recent_diary: List[Dict[str, Any]],
    ) -> str:
        """Fetch all data and build enhanced context for the agent.

        This is the main entry point that combines all data sources into a
        structured context string for the CAMEL agent.

        Args:
            assets: List of assets to analyze
            hyperliquid_api: Hyperliquid API instance
            account_state: Current account state (balance, positions, etc.)
            recent_diary: Recent trade history

        Returns:
            JSON string with complete market context
        """
        # Fetch all data in parallel
        market_data = await self.fetch_all_market_data(
            assets=assets,
            hyperliquid_api=hyperliquid_api,
            include_onchain=True,
            include_macro=True,
            include_sentiment=True,
            include_microstructure=True,
        )

        # Build context structure
        context = {
            "timestamp": datetime.now().isoformat(),
            "account": account_state,
            "market": {
                "sentiment": market_data.get("sentiment"),
                "macro": market_data.get("macro"),
                "assets": [],
            },
            "recent_trades": recent_diary,
            "fetch_time_ms": market_data.get("fetch_time_ms"),
        }

        # Add asset-specific data
        for asset in assets:
            asset_data = market_data["assets"].get(asset, {})

            asset_context = {
                "asset": asset,
                "price": asset_data.get("technical", {}).get("current_price"),
                "funding_rate": asset_data.get("technical", {}).get("funding_rate"),
                "open_interest": asset_data.get("technical", {}).get("open_interest"),
                "ltf": asset_data.get("technical", {}).get("ltf"),
                "htf": asset_data.get("technical", {}).get("htf"),
                "microstructure": asset_data.get("microstructure"),
                "onchain": asset_data.get("onchain"),
            }

            context["market"]["assets"].append(asset_context)

        return context

    async def fetch_signals_for_assets(
        self,
        assets: List[str],
        hyperliquid_api,
        account_state: Dict[str, Any],
        open_positions: List[Dict[str, Any]],
        recent_diary: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Fetch market data and generate pre-computed trade signals.

        This is the optimized method for context engineering:
        - All calculations done programmatically
        - Confluence scores pre-computed
        - Dynamic leverage pre-calculated
        - Flat, actionable structure for LLM

        The LLM receives simplified signals to validate/adjust, not raw data to analyze.

        Args:
            assets: List of assets to analyze
            hyperliquid_api: Hyperliquid API instance
            account_state: Current account state (balance, equity, etc.)
            open_positions: List of currently open positions with PnL
            recent_diary: Recent trade history for memory

        Returns:
            Dict with:
                - signals: Pre-computed trade signals for each asset
                - portfolio: Portfolio context (positions, PnL, exposure)
                - global_context: Macro/sentiment environment
                - raw_data: Original data for logging/debugging
        """
        # Fetch all market data
        market_data = await self.fetch_all_market_data(
            assets=assets,
            hyperliquid_api=hyperliquid_api,
            include_onchain=True,
            include_macro=True,
            include_sentiment=True,
            include_microstructure=True,
        )

        # Calculate current portfolio metrics
        portfolio_summary = self._calculate_portfolio_summary(
            account_state, open_positions
        )

        # Generate pre-computed signals for each asset
        signals = []
        for asset in assets:
            asset_market_data = market_data["assets"].get(asset, {})

            # Combine all data sources for this asset
            combined_data = {
                "ltf": asset_market_data.get("technical", {}).get("ltf", {}),
                "htf": asset_market_data.get("technical", {}).get("htf", {}),
                "microstructure": asset_market_data.get("microstructure", {}),
                "onchain": asset_market_data.get("onchain", {}),
                "sentiment": market_data.get("sentiment", {}),
                "macro": market_data.get("macro", {}),
                "funding_rate": asset_market_data.get("technical", {}).get("funding_rate"),
            }

            # Get current price
            current_price = asset_market_data.get("technical", {}).get("current_price")

            if current_price:
                # Generate pre-computed signal
                signal = self.signal_calculator.generate_trade_signal(
                    asset=asset,
                    market_data=combined_data,
                    current_price=current_price,
                )
                signals.append(signal)
            else:
                logging.warning(f"No current price for {asset}, skipping signal generation")

        # Build simplified context for LLM
        context = {
            "timestamp": datetime.now().isoformat(),

            # Pre-computed signals (THIS is what LLM primarily sees)
            "trade_signals": signals,

            # Portfolio context (critical for risk management)
            "portfolio": portfolio_summary,

            # Global environment (macro + sentiment)
            "global_context": {
                "macro": market_data.get("macro"),
                "sentiment": market_data.get("sentiment"),
            },

            # Recent trades (for memory)
            "recent_trades": recent_diary[-10:] if recent_diary else [],  # Last 10 trades

            # Metadata
            "fetch_time_ms": market_data.get("fetch_time_ms"),

            # Raw data (for debugging, not for LLM)
            "raw_data": market_data,
        }

        return context

    def _calculate_portfolio_summary(
        self,
        account_state: Dict[str, Any],
        open_positions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate portfolio-level metrics for context.

        Args:
            account_state: Account data from Hyperliquid
            open_positions: List of open positions

        Returns:
            Dict with portfolio metrics
        """
        # Extract account metrics
        account_value = account_state.get("account_value", 0)
        equity = account_state.get("equity", account_value)
        margin_used = account_state.get("margin_used", 0)
        withdrawable = account_state.get("withdrawable", 0)

        # Calculate position metrics
        total_exposure = 0
        total_unrealized_pnl = 0
        num_longs = 0
        num_shorts = 0
        position_assets = []

        for pos in open_positions:
            size = abs(pos.get("position_value", 0))
            total_exposure += size

            pnl = pos.get("unrealized_pnl", 0)
            total_unrealized_pnl += pnl

            if pos.get("side") == "long":
                num_longs += 1
            else:
                num_shorts += 1

            position_assets.append({
                "asset": pos.get("coin"),
                "side": pos.get("side"),
                "size_usd": round(size, 2),
                "leverage": pos.get("leverage", 1.0),
                "unrealized_pnl": round(pnl, 2),
                "entry_price": pos.get("entry_price"),
            })

        # Portfolio heat (exposure / equity)
        portfolio_heat = (total_exposure / equity * 100) if equity > 0 else 0

        return {
            "account_value_usd": round(account_value, 2),
            "equity_usd": round(equity, 2),
            "margin_used_usd": round(margin_used, 2),
            "withdrawable_usd": round(withdrawable, 2),
            "total_exposure_usd": round(total_exposure, 2),
            "portfolio_heat_pct": round(portfolio_heat, 1),
            "unrealized_pnl_usd": round(total_unrealized_pnl, 2),
            "num_positions": len(open_positions),
            "num_longs": num_longs,
            "num_shorts": num_shorts,
            "open_positions": position_assets,
            "available_buying_power_usd": round(withdrawable, 2),
        }
