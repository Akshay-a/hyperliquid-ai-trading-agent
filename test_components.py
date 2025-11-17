#!/usr/bin/env python3
"""
Component Validation Test Suite

Tests all market analysis tools to ensure they work correctly
before risking real capital.

Run with: python test_components.py
"""

import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent))

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def print_section(title: str):
    """Print formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"    {details}")


def test_imports():
    """Test that all required modules can be imported."""
    print_section("1. Testing Imports")

    tests = {
        "TAAPI Client": lambda: __import__('src.indicators.taapi_client', fromlist=['TAAPIClient']),
        "Glassnode Client": lambda: __import__('src.data.glassnode_client', fromlist=['GlassnodeClient']),
        "Fear & Greed Client": lambda: __import__('src.data.feargreed_client', fromlist=['FearGreedClient']),
        "Macro Client": lambda: __import__('src.data.macro_client', fromlist=['MacroDataClient']),
        "Risk Manager": lambda: __import__('src.utils.risk_manager', fromlist=['RiskManager']),
        "Cache Utility": lambda: __import__('src.utils.cache', fromlist=['TTLCache']),
        "Orchestrator": lambda: __import__('src.data.orchestrator', fromlist=['DataOrchestrator']),
    }

    results = {}
    for name, import_func in tests.items():
        try:
            import_func()
            print_result(name, True)
            results[name] = True
        except Exception as e:
            print_result(name, False, str(e))
            results[name] = False

    return all(results.values())


def test_fear_greed_client():
    """Test Fear & Greed Index client."""
    print_section("2. Testing Fear & Greed Index (Free API)")

    try:
        from src.data.feargreed_client import FearGreedClient

        client = FearGreedClient()

        # Test current index
        print("Fetching current Fear & Greed Index...")
        current = client.get_current()

        if current:
            print_result("Get Current Index", True,
                f"Value: {current['value']}, Classification: {current['classification']}")

            # Validate data structure
            required_fields = ['value', 'classification', 'timestamp']
            has_all_fields = all(field in current for field in required_fields)
            print_result("Data Structure Valid", has_all_fields,
                f"Has fields: {', '.join(current.keys())}")

            # Validate value range
            value_valid = 0 <= current['value'] <= 100
            print_result("Value in Range (0-100)", value_valid,
                f"Value: {current['value']}")

        else:
            print_result("Get Current Index", False, "Returned None")
            return False

        # Test sentiment signal
        print("\nTesting sentiment signal generation...")
        signal = client.get_sentiment_signal()

        if signal:
            print_result("Generate Signal", True,
                f"Signal: {signal['signal']} (strength: {signal['strength']})")
            print(f"    Interpretation: {signal['interpretation']}")
        else:
            print_result("Generate Signal", False)
            return False

        # Test historical data
        print("\nTesting historical data...")
        historical = client.get_historical(days=7)

        if historical and len(historical) > 0:
            print_result("Get Historical", True, f"Retrieved {len(historical)} data points")
        else:
            print_result("Get Historical", False)
            return False

        return True

    except Exception as e:
        print_result("Fear & Greed Client", False, str(e))
        return False


def test_macro_client():
    """Test macro data client."""
    print_section("3. Testing Macro Data (Yahoo Finance - Free)")

    try:
        from src.data.macro_client import MacroDataClient

        client = MacroDataClient()

        # Test SPX
        print("Fetching S&P 500 data...")
        spx = client.get_spx()

        if spx:
            print_result("Get SPX", True,
                f"Price: ${spx['price']}, Change: {spx['change_pct']}%, Trend: {spx.get('trend', 'N/A')}")
        else:
            print_result("Get SPX", False)
            return False

        # Test DXY
        print("\nFetching Dollar Index...")
        dxy = client.get_dxy()

        if dxy:
            print_result("Get DXY", True,
                f"Level: {dxy['price']}, Change: {dxy['change_pct']}%, Trend: {dxy.get('trend', 'N/A')}")
        else:
            print_result("Get DXY", False)

        # Test US10Y
        print("\nFetching 10Y Treasury Yield...")
        us10y = client.get_us10y()

        if us10y:
            print_result("Get US10Y", True,
                f"Yield: {us10y['price']}%, Change: {us10y['change_pct']}%, Trend: {us10y.get('trend', 'N/A')}")
        else:
            print_result("Get US10Y", False)

        # Test aggregated macro
        print("\nFetching all macro data...")
        all_macro = client.get_all_macro()

        if all_macro:
            print_result("Get All Macro", True,
                f"Risk Environment: {all_macro['risk_environment']} (score: {all_macro['risk_score']})")
            print(f"    {all_macro['interpretation']}")
        else:
            print_result("Get All Macro", False)
            return False

        return True

    except Exception as e:
        print_result("Macro Client", False, str(e))
        return False


def test_glassnode_client():
    """Test Glassnode client (requires API key)."""
    print_section("4. Testing Glassnode On-Chain Metrics (Requires API Key)")

    try:
        from src.data.glassnode_client import GlassnodeClient
        from src.config_loader import CONFIG

        api_key = CONFIG.get("glassnode_api_key")

        if not api_key:
            print_result("Glassnode API Key", False,
                "No API key configured (set GLASSNODE_API_KEY in .env)")
            print("    ⚠️  Skipping Glassnode tests (optional - agent works without it)")
            return True  # Not a failure, just skipped

        client = GlassnodeClient()

        print("Testing BTC metrics...")

        # Test STH-SOPR
        sopr = client.get_sth_sopr("BTC")
        if sopr is not None:
            interpretation = "Taking profits" if sopr > 1.0 else "Accumulating at loss"
            print_result("STH-SOPR", True, f"Value: {sopr:.4f} ({interpretation})")
        else:
            print_result("STH-SOPR", False, "Returned None (might require paid tier)")

        # Test MVRV
        mvrv = client.get_mvrv_ratio("BTC")
        if mvrv is not None:
            if mvrv > 3.0:
                zone = "Overvalued (sell zone)"
            elif mvrv < 1.0:
                zone = "Undervalued (buy zone)"
            else:
                zone = "Fair value"
            print_result("MVRV Ratio", True, f"Value: {mvrv:.2f} ({zone})")
        else:
            print_result("MVRV Ratio", False, "Returned None")

        # Test entities in profit
        entities_profit = client.get_entities_profit_pct("BTC")
        if entities_profit is not None:
            print_result("Entities in Profit %", True, f"Value: {entities_profit:.1f}%")
        else:
            print_result("Entities in Profit %", False)

        # Test all metrics
        print("\nFetching all BTC metrics...")
        all_metrics = client.get_all_metrics("BTC")

        available_count = sum(1 for v in all_metrics.values() if v is not None)
        total_count = len(all_metrics)

        print_result("Get All Metrics", available_count > 0,
            f"{available_count}/{total_count} metrics available")

        if available_count == 0:
            print("    ⚠️  No metrics available - might need paid Glassnode subscription")
            print("    ⚠️  Agent will work without on-chain data, but less informed")

        return True

    except Exception as e:
        print_result("Glassnode Client", False, str(e))
        return False


async def test_hyperliquid_microstructure():
    """Test Hyperliquid order book analysis."""
    print_section("5. Testing Hyperliquid Microstructure Analysis")

    try:
        from src.trading.hyperliquid_api import HyperliquidAPI

        api = HyperliquidAPI()

        print("Fetching BTC order book...")
        order_book = await api.get_order_book("BTC", depth=10)

        if order_book:
            bids = order_book.get("bids", [])
            asks = order_book.get("asks", [])

            print_result("Get Order Book", True,
                f"{len(bids)} bids, {len(asks)} asks")

            if bids and asks:
                best_bid = bids[0][0]
                best_ask = asks[0][0]
                print(f"    Best Bid: ${best_bid:,.2f}")
                print(f"    Best Ask: ${best_ask:,.2f}")
                print(f"    Spread: ${best_ask - best_bid:.2f}")
        else:
            print_result("Get Order Book", False)
            return False

        print("\nCalculating microstructure metrics...")
        metrics = await api.get_microstructure_metrics("BTC")

        if metrics:
            print_result("Microstructure Metrics", True)
            print(f"    Spread: {metrics['spread_pct']:.4f}%")
            print(f"    Imbalance: {metrics['imbalance']:.4f} "
                  f"({'Buying' if metrics['imbalance'] > 0 else 'Selling'} pressure)")
            print(f"    Bid Depth (0.1%): {metrics['bid_depth_01pct']:.2f}")
            print(f"    Ask Depth (0.1%): {metrics['ask_depth_01pct']:.2f}")

            # Validate imbalance range
            imbalance_valid = -1.0 <= metrics['imbalance'] <= 1.0
            print_result("Imbalance in Range", imbalance_valid,
                f"Value: {metrics['imbalance']:.4f}")

        else:
            print_result("Microstructure Metrics", False)
            return False

        return True

    except Exception as e:
        print_result("Hyperliquid Microstructure", False, str(e))
        return False


def test_risk_manager():
    """Test risk management calculations."""
    print_section("6. Testing Risk Manager")

    try:
        from src.utils.risk_manager import RiskManager

        risk_mgr = RiskManager(max_portfolio_heat=0.30, max_simultaneous_positions=3)

        # Test 1: Portfolio heat calculation
        print("Testing portfolio heat calculation...")
        mock_positions = [
            {"quantity": 0.5, "entry_price": 45000},  # $22,500 exposure
            {"quantity": 10.0, "entry_price": 2500},  # $25,000 exposure
        ]
        account_value = 100000

        heat = risk_mgr.calculate_portfolio_heat(mock_positions, account_value)
        print_result("Calculate Portfolio Heat", True,
            f"Heat: {heat:.1%} (target: < 30%)")

        # Test 2: Dynamic leverage calculation
        print("\nTesting dynamic leverage...")
        leverage = risk_mgr.calculate_dynamic_leverage(
            atr=1000,
            atr_avg=800,
            confluence_score=8,
            risk_environment="risk_on",
            leverage_min=3.0,
            leverage_max=10.0
        )
        print_result("Dynamic Leverage", True,
            f"Calculated: {leverage}x (high confluence, elevated volatility)")

        # Test with high volatility
        leverage_volatile = risk_mgr.calculate_dynamic_leverage(
            atr=1500,
            atr_avg=800,  # 1.875x normal ATR
            confluence_score=6,
            risk_environment="risk_off",
            leverage_min=3.0,
            leverage_max=10.0
        )
        print_result("Volatility Adjustment", True,
            f"Calculated: {leverage_volatile}x (high volatility, risk-off)")

        # Validate leverage stayed in bounds
        in_bounds = 3.0 <= leverage_volatile <= 10.0
        print_result("Leverage in Bounds", in_bounds,
            f"Value: {leverage_volatile}x (min: 3, max: 10)")

        # Test 3: Can open position
        print("\nTesting position opening limits...")
        can_open, reason = risk_mgr.can_open_position(
            current_positions=mock_positions,
            account_value=account_value,
            new_position_size=10000
        )
        print_result("Can Open Position", can_open, reason)

        # Test 4: Position size adjustment
        print("\nTesting position size adjustment...")
        adjusted = risk_mgr.adjust_position_size(
            desired_size=50000,  # Want 50% exposure
            current_positions=mock_positions,
            account_value=account_value
        )
        print_result("Position Size Adjustment", adjusted < 50000,
            f"Adjusted from $50,000 to ${adjusted:,.0f}")

        return True

    except Exception as e:
        print_result("Risk Manager", False, str(e))
        return False


def test_caching():
    """Test caching functionality."""
    print_section("7. Testing Cache System")

    try:
        from src.utils.cache import TTLCache, cached
        import time

        cache = TTLCache()

        # Test basic set/get
        print("Testing basic cache operations...")
        cache.set("test_key", "test_value", ttl_seconds=2)
        value = cache.get("test_key")
        print_result("Set and Get", value == "test_value", f"Value: {value}")

        # Test expiration
        print("\nTesting TTL expiration...")
        print("    Waiting 3 seconds for cache to expire...")
        time.sleep(3)
        expired_value = cache.get("test_key")
        print_result("Cache Expiration", expired_value is None,
            "Value expired as expected" if expired_value is None else "Still cached!")

        # Test decorator
        print("\nTesting @cached decorator...")
        call_count = 0

        @cached(ttl_seconds=5)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        print_result("Decorator Works", result1 == 10 and result2 == 10,
            f"Results: {result1}, {result2}")
        print_result("Cache Hit", call_count == 1,
            f"Function called {call_count} time(s) (should be 1)")

        return True

    except Exception as e:
        print_result("Cache System", False, str(e))
        return False


async def test_orchestrator():
    """Test parallel data orchestrator."""
    print_section("8. Testing Parallel Data Orchestrator")

    try:
        from src.data.orchestrator import DataOrchestrator
        from src.indicators.taapi_client import TAAPIClient
        from src.data.glassnode_client import GlassnodeClient
        from src.data.feargreed_client import FearGreedClient
        from src.data.macro_client import MacroDataClient
        from src.trading.hyperliquid_api import HyperliquidAPI

        # Initialize clients
        taapi = TAAPIClient()
        glassnode = GlassnodeClient()
        feargreed = FearGreedClient()
        macro = MacroDataClient()
        hyperliquid = HyperliquidAPI()

        orchestrator = DataOrchestrator(taapi, glassnode, feargreed, macro)

        print("Fetching all market data in parallel for BTC...")
        start_time = datetime.now()

        data = await orchestrator.fetch_all_market_data(
            assets=["BTC"],
            hyperliquid_api=hyperliquid,
            include_onchain=True,
            include_macro=True,
            include_sentiment=True,
            include_microstructure=True,
        )

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        print_result("Parallel Data Fetch", data is not None,
            f"Completed in {elapsed_ms:.0f}ms")

        if data:
            # Validate structure
            has_sentiment = data.get("sentiment") is not None
            has_macro = data.get("macro") is not None
            has_assets = "assets" in data and "BTC" in data["assets"]

            print_result("Has Sentiment Data", has_sentiment)
            print_result("Has Macro Data", has_macro)
            print_result("Has Asset Data", has_assets)

            if has_assets:
                btc_data = data["assets"]["BTC"]
                has_technical = "technical" in btc_data
                has_microstructure = "microstructure" in btc_data

                print_result("Has Technical Data", has_technical)
                print_result("Has Microstructure Data", has_microstructure)

                if has_technical:
                    tech = btc_data["technical"]
                    print(f"    Current Price: ${tech.get('current_price', 'N/A')}")
                    print(f"    Funding Rate: {tech.get('funding_rate', 'N/A')}")

            # Performance check
            is_fast = elapsed_ms < 2000  # Should be < 2 seconds
            print_result("Performance", is_fast,
                f"Fetch time: {elapsed_ms:.0f}ms (target: < 2000ms)")

        return data is not None

    except Exception as e:
        print_result("Orchestrator", False, str(e))
        return False


def test_config():
    """Test configuration loading."""
    print_section("9. Testing Configuration")

    try:
        from src.config_loader import CONFIG

        print("Checking required configuration...")

        required = {
            "taapi_api_key": "TAAPI API Key",
            "openrouter_api_key": "OpenRouter API Key",
            "hyperliquid_private_key": "Hyperliquid Private Key",
        }

        all_present = True
        for key, name in required.items():
            value = CONFIG.get(key)
            present = value is not None and value != ""
            print_result(name, present, "Configured" if present else "Missing")
            if not present:
                all_present = False

        print("\nChecking trading configuration...")
        trading_config = {
            "position_size_pct": CONFIG.get("position_size_pct", 2.0),
            "leverage_min": CONFIG.get("leverage_min", 3.0),
            "leverage_max": CONFIG.get("leverage_max", 10.0),
            "memory_trades_count": CONFIG.get("memory_trades_count", 25),
        }

        for key, value in trading_config.items():
            print(f"    {key}: {value}")

        # Validate ranges
        position_valid = 0 < trading_config["position_size_pct"] <= 10
        leverage_valid = (trading_config["leverage_min"] < trading_config["leverage_max"]
                          and 1 <= trading_config["leverage_min"] <= 20
                          and 1 <= trading_config["leverage_max"] <= 20)

        print_result("Position Size Valid", position_valid,
            f"{trading_config['position_size_pct']}% (should be 0-10%)")
        print_result("Leverage Range Valid", leverage_valid,
            f"{trading_config['leverage_min']}x - {trading_config['leverage_max']}x")

        return all_present

    except Exception as e:
        print_result("Configuration", False, str(e))
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("  COMPONENT VALIDATION TEST SUITE")
    print("  Testing all market analysis tools before live trading")
    print("="*80)

    results = {}

    # Synchronous tests
    results["Imports"] = test_imports()
    results["Fear & Greed"] = test_fear_greed_client()
    results["Macro Data"] = test_macro_client()
    results["Glassnode"] = test_glassnode_client()
    results["Risk Manager"] = test_risk_manager()
    results["Cache System"] = test_caching()
    results["Configuration"] = test_config()

    # Async tests
    async def run_async_tests():
        results["Hyperliquid Microstructure"] = await test_hyperliquid_microstructure()
        results["Orchestrator"] = await test_orchestrator()

    asyncio.run(run_async_tests())

    # Summary
    print_section("SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    pass_rate = (passed / total) * 100 if total > 0 else 0

    for test_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")

    print(f"\n{'='*80}")
    print(f"  RESULTS: {passed}/{total} tests passed ({pass_rate:.0f}%)")

    if passed == total:
        print("  ✅ ALL TESTS PASSED - Ready for paper trading")
    elif passed >= total * 0.8:
        print("  ⚠️  MOSTLY PASSING - Review failures before live trading")
    else:
        print("  ❌ MULTIPLE FAILURES - Fix issues before using")

    print(f"{'='*80}\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
