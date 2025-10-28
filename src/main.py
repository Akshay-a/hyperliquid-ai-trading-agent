"""Entry-point script that wires together the trading agent, data feeds, and API."""

import sys
import argparse
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))
from src.core.algorithm_layer import AlgorithmLayer
from src.core.llm_layer import AutonomousLLMAgent
from src.indicators.hyperliquid_market_data import HyperliquidMarketData
from src.risk.portfolio_risk import PortfolioRiskManager
from src.trading.hyperliquid_api import HyperliquidAPI
import asyncio
import logging
from collections import deque, OrderedDict
from datetime import datetime, timezone
import math  # For Sharpe
from dotenv import load_dotenv
import os
import json
from aiohttp import web
from src.utils.formatting import format_number as fmt, format_size as fmt_sz
from src.utils.prompt_utils import json_default, round_or_none, round_series

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def clear_terminal():
    """Clear the terminal screen on Windows or POSIX systems."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_interval_seconds(interval_str):
    """Convert interval strings like '5m' or '1h' to seconds."""
    if interval_str.endswith('m'):
        return int(interval_str[:-1]) * 60
    elif interval_str.endswith('h'):
        return int(interval_str[:-1]) * 3600
    elif interval_str.endswith('d'):
        return int(interval_str[:-1]) * 86400
    else:
        raise ValueError(f"Unsupported interval: {interval_str}")

def main():
    """Parse CLI args, bootstrap dependencies, and launch the trading loop."""
    clear_terminal()
    parser = argparse.ArgumentParser(description="LLM-based Trading Agent on Hyperliquid")
    parser.add_argument("--assets", type=str, nargs="+", required=False, help="Assets to trade, e.g., BTC ETH")
    parser.add_argument("--interval", type=str, required=False, help="Interval period, e.g., 1h")
    args = parser.parse_args()

    # Allow assets/interval via .env (CONFIG) if CLI not provided
    from src.config_loader import CONFIG
    assets_env = CONFIG.get("assets")
    interval_env = CONFIG.get("interval")
    if (not args.assets or len(args.assets) == 0) and assets_env:
        # Support space or comma separated
        if "," in assets_env:
            args.assets = [a.strip() for a in assets_env.split(",") if a.strip()]
        else:
            args.assets = [a.strip() for a in assets_env.split(" ") if a.strip()]
    if not args.interval and interval_env:
        args.interval = interval_env

    if not args.assets or not args.interval:
        parser.error("Please provide --assets and --interval, or set ASSETS and INTERVAL in .env")

    # Initialize new two-layer architecture
    hyperliquid = HyperliquidAPI()
    market_data = HyperliquidMarketData()
    algorithm_layer = AlgorithmLayer(max_leverage=6.0, max_heat=0.25)
    llm_agent = AutonomousLLMAgent()
    risk_manager = PortfolioRiskManager(
        max_leverage=6.0,
        max_heat=0.25,
        max_drawdown=-0.10,
        risk_per_trade=0.015
    )


    start_time = datetime.now(timezone.utc)
    invocation_count = 0
    trade_log = []  # For Sharpe: list of returns
    active_trades = []  # {'asset','is_long','amount','entry_price','tp_oid','sl_oid','exit_plan'}
    recent_events = deque(maxlen=200)
    diary_path = "diary.jsonl"
    initial_account_value = None
    # Perp mid-price history sampled each loop (authoritative, avoids spot/perp basis mismatch)
    price_history = {}

    print(f"Starting trading agent for assets: {args.assets} at interval: {args.interval}")

    def add_event(msg: str):
        """Log an informational event and push it into the recent events deque."""
        logging.info(msg)

    async def run_loop():
        """Main trading loop that gathers data, calls the agent, and executes trades."""
        nonlocal invocation_count, initial_account_value
        while True:
            invocation_count += 1
            minutes_since_start = (datetime.now(timezone.utc) - start_time).total_seconds() / 60

            # Global account state
            state = await hyperliquid.get_user_state()
            total_value = state.get('total_value') or state['balance'] + sum(p.get('pnl', 0) for p in state['positions'])
            sharpe = calculate_sharpe(trade_log)

            account_value = total_value
            if initial_account_value is None:
                initial_account_value = account_value
            total_return_pct = ((account_value - initial_account_value) / initial_account_value * 100.0) if initial_account_value else 0.0

            positions = []
            for pos_wrap in state['positions']:
                pos = pos_wrap
                coin = pos.get('coin')
                current_px = await hyperliquid.get_current_price(coin) if coin else None
                positions.append({
                    "symbol": coin,
                    "quantity": round_or_none(pos.get('szi'), 6),
                    "entry_price": round_or_none(pos.get('entryPx'), 2),
                    "current_price": round_or_none(current_px, 2),
                    "liquidation_price": round_or_none(pos.get('liquidationPx') or pos.get('liqPx'), 2),
                    "unrealized_pnl": round_or_none(pos.get('pnl'), 4),
                    "leverage": pos.get('leverage')
                })

            recent_diary = []
            try:
                with open(diary_path, "r") as f:
                    lines = f.readlines()
                    for line in lines[-10:]:
                        entry = json.loads(line)
                        recent_diary.append(entry)
            except Exception:
                pass

            open_orders_struct = []
            try:
                open_orders = await hyperliquid.get_open_orders()
                for o in open_orders[:50]:
                    open_orders_struct.append({
                        "coin": o.get('coin'),
                        "oid": o.get('oid'),
                        "is_buy": o.get('isBuy'),
                        "size": round_or_none(o.get('sz'), 6),
                        "price": round_or_none(o.get('px'), 2),
                        "trigger_price": round_or_none(o.get('triggerPx'), 2),
                        "order_type": o.get('orderType')
                    })
            except Exception:
                open_orders = []

            # Reconcile active trades
            try:
                assets_with_positions = set()
                for pos in state['positions']:
                    try:
                        if abs(float(pos.get('szi') or 0)) > 0:
                            assets_with_positions.add(pos.get('coin'))
                    except Exception:
                        continue
                assets_with_orders = {o.get('coin') for o in (open_orders or []) if o.get('coin')}
                for tr in active_trades[:]:
                    asset = tr.get('asset')
                    if asset not in assets_with_positions and asset not in assets_with_orders:
                        add_event(f"Reconciling stale active trade for {asset} (no position, no orders)")
                        active_trades.remove(tr)
                        with open(diary_path, "a") as f:
                            f.write(json.dumps({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "asset": asset,
                                "action": "reconcile_close",
                                "reason": "no_position_no_orders",
                                "opened_at": tr.get('opened_at')
                            }) + "\n")
            except Exception:
                pass

            recent_fills_struct = []
            try:
                fills = await hyperliquid.get_recent_fills(limit=50)
                for f_entry in fills[-20:]:
                    try:
                        t_raw = f_entry.get('time') or f_entry.get('timestamp')
                        timestamp = None
                        if t_raw is not None:
                            try:
                                t_int = int(t_raw)
                                if t_int > 1e12:
                                    timestamp = datetime.fromtimestamp(t_int / 1000, tz=timezone.utc).isoformat()
                                else:
                                    timestamp = datetime.fromtimestamp(t_int, tz=timezone.utc).isoformat()
                            except Exception:
                                timestamp = str(t_raw)
                        recent_fills_struct.append({
                            "timestamp": timestamp,
                            "coin": f_entry.get('coin') or f_entry.get('asset'),
                            "is_buy": f_entry.get('isBuy'),
                            "size": round_or_none(f_entry.get('sz') or f_entry.get('size'), 6),
                            "price": round_or_none(f_entry.get('px') or f_entry.get('price'), 2)
                        })
                    except Exception:
                        continue
            except Exception:
                pass

            dashboard = {
                "total_return_pct": round(total_return_pct, 2),
                "balance": round_or_none(state['balance'], 2),
                "account_value": round_or_none(account_value, 2),
                "sharpe_ratio": round_or_none(sharpe, 3),
                "positions": positions,
                "active_trades": [
                    {
                        "asset": tr.get('asset'),
                        "is_long": tr.get('is_long'),
                        "amount": round_or_none(tr.get('amount'), 6),
                        "entry_price": round_or_none(tr.get('entry_price'), 2),
                        "tp_oid": tr.get('tp_oid'),
                        "sl_oid": tr.get('sl_oid'),
                        "exit_plan": tr.get('exit_plan'),
                        "opened_at": tr.get('opened_at')
                    }
                    for tr in active_trades
                ],
                "open_orders": open_orders_struct,
                "recent_diary": recent_diary,
                "recent_fills": recent_fills_struct,
            }

            # Calculate portfolio risk metrics
            risk_metrics = risk_manager.calculate_risk_metrics(
                account_equity=account_value,
                positions=positions,
                active_trades=active_trades,
                recent_fills=recent_fills_struct
            )

            # Gather data and prepare context for ALL assets using new architecture
            market_contexts = []
            asset_prices = {}
            for asset in args.assets:
                try:
                    current_price = await hyperliquid.get_current_price(asset)
                    asset_prices[asset] = current_price
                    if asset not in price_history:
                        price_history[asset] = deque(maxlen=60)
                    price_history[asset].append({"t": datetime.now(timezone.utc).isoformat(), "mid": round_or_none(current_price, 2)})

                    # Get funding and OI
                    funding = await hyperliquid.get_funding_rate(asset)
                    oi = await hyperliquid.get_open_interest(asset)

                    # Fetch multi-timeframe candles from Hyperliquid
                    candles_5m = await market_data.get_candles(asset, "5m", lookback_bars=100)
                    candles_1h = await market_data.get_candles(asset, "1h", lookback_bars=100)
                    candles_4h = await market_data.get_candles(asset, "4h", lookback_bars=100)
                    candles_1d = await market_data.get_candles(asset, "1d", lookback_bars=100)

                    # Use Algorithm Layer to prepare context with features
                    context = algorithm_layer.prepare_context(
                        asset=asset,
                        candles_5m=candles_5m.get("candles", []),
                        candles_1h=candles_1h.get("candles", []),
                        candles_4h=candles_4h.get("candles", []),
                        candles_1d=candles_1d.get("candles", []),
                        current_price=current_price,
                        account_equity=account_value,
                        positions=positions,
                        active_trades=active_trades,
                        risk_metrics=risk_metrics,
                        funding_rate=funding,
                        open_interest=oi
                    )

                    market_contexts.append(context)

                except Exception as e:
                    add_event(f"Data gather error {asset}: {e}")
                    import traceback
                    add_event(f"Traceback: {traceback.format_exc()}")
                    continue

            # Use new Autonomous LLM Agent for each asset
            trade_decisions = []

            for ctx in market_contexts:
                try:
                    asset = ctx.get("asset")
                    if not ctx.get("allowed_to_trade", True):
                        add_event(f"{asset}: Not allowed to trade - {ctx.get('reason')}")
                        trade_decisions.append({
                            "asset": asset,
                            "action": "hold",
                            "rationale": ctx.get("reason"),
                            "allocation_usd": 0
                        })
                        continue

                    # Log context for debugging
                    add_event(f"{asset}: Regime = {ctx.get('regime', {}).get('type', 'unknown')}, " +
                             f"Features calculated: {len(ctx.get('features', {}))} feature groups")

                    # Let LLM Agent decide autonomously
                    decision = llm_agent.decide(ctx)

                    # Add asset to decision
                    decision["asset"] = asset

                    # Calculate allocation based on conviction and Kelly
                    if decision.get("action") in ["buy", "sell"] and decision.get("conviction", 0) > 0:
                        conviction = decision["conviction"]
                        atr = ctx.get("features", {}).get("volatility", {}).get("4h", {}).get("atr")
                        if atr:
                            allocation = algorithm_layer.calculate_position_size(
                                conviction=conviction,
                                account_equity=account_value,
                                atr=atr,
                                current_price=asset_prices.get(asset, 0)
                            )
                            decision["allocation_usd"] = allocation
                        else:
                            decision["allocation_usd"] = 0
                            decision["action"] = "hold"
                            decision["rationale"] = decision.get("reasoning", "") + " [No ATR available]"

                    trade_decisions.append(decision)

                    reasoning = decision.get("reasoning", "")
                    if reasoning:
                        add_event(f"{asset} LLM Decision: {decision.get('action', 'hold')} " +
                                 f"(conviction: {decision.get('conviction', 0)})")
                        add_event(f"{asset} Reasoning: {reasoning[:200]}...")

                except Exception as e:
                    import traceback
                    add_event(f"Decision error {asset}: {e}")
                    add_event(f"Traceback: {traceback.format_exc()}")
                    trade_decisions.append({
                        "asset": asset,
                        "action": "hold",
                        "rationale": f"Error: {str(e)}",
                        "allocation_usd": 0
                    })

            # Execute trades for each asset
            for output in trade_decisions:
                try:
                    asset = output.get("asset")
                    if not asset or asset not in args.assets:
                        continue
                    action = output.get("action")
                    current_price = asset_prices.get(asset, 0)
                    rationale = output.get("reasoning", output.get("rationale", ""))
                    if rationale and action != "hold":
                        add_event(f"Decision reasoning for {asset}: {rationale[:100]}...")
                    if action in ("buy", "sell"):
                        is_buy = action == "buy"
                        alloc_usd = float(output.get("allocation_usd", 0.0))
                        if alloc_usd <= 0:
                            add_event(f"Holding {asset}: zero/negative allocation")
                            continue
                        amount = alloc_usd / current_price

                        order = await hyperliquid.place_buy_order(asset, amount) if is_buy else await hyperliquid.place_sell_order(asset, amount)
                        # Confirm by checking recent fills for this asset shortly after placing
                        await asyncio.sleep(1)
                        fills_check = await hyperliquid.get_recent_fills(limit=10)
                        filled = False
                        for fc in reversed(fills_check):
                            try:
                                if (fc.get('coin') == asset or fc.get('asset') == asset):
                                    filled = True
                                    break
                            except Exception:
                                continue
                        trade_log.append({"type": action, "price": current_price, "amount": amount, "exit_plan": output["exit_plan"], "filled": filled})
                        tp_oid = None
                        sl_oid = None
                        if output["tp_price"]:
                            tp_order = await hyperliquid.place_take_profit(asset, is_buy, amount, output["tp_price"])
                            tp_oids = hyperliquid.extract_oids(tp_order)
                            tp_oid = tp_oids[0] if tp_oids else None
                            add_event(f"TP placed {asset} at {output['tp_price']}")
                        if output["sl_price"]:
                            sl_order = await hyperliquid.place_stop_loss(asset, is_buy, amount, output["sl_price"])
                            sl_oids = hyperliquid.extract_oids(sl_order)
                            sl_oid = sl_oids[0] if sl_oids else None
                            add_event(f"SL placed {asset} at {output['sl_price']}")
                        # Reconcile: if opposite-side position exists or TP/SL just filled, clear stale active_trades for this asset
                        for existing in active_trades[:]:
                            if existing.get('asset') == asset:
                                try:
                                    active_trades.remove(existing)
                                except ValueError:
                                    pass
                        active_trades.append({
                            "asset": asset,
                            "is_long": is_buy,
                            "amount": amount,
                            "entry_price": current_price,
                            "tp_oid": tp_oid,
                            "sl_oid": sl_oid,
                            "exit_plan": output["exit_plan"],
                            "opened_at": datetime.now().isoformat()
                        })
                        add_event(f"{action.upper()} {asset} amount {amount:.4f} at ~{current_price}")
                        # Write to diary after confirming fills status
                        with open(diary_path, "a") as f:
                            diary_entry = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "asset": asset,
                                "action": action,
                                "allocation_usd": alloc_usd,
                                "amount": amount,
                                "entry_price": current_price,
                                "tp_price": output.get("tp_price"),
                                "tp_oid": tp_oid,
                                "sl_price": output.get("sl_price"),
                                "sl_oid": sl_oid,
                                "exit_plan": output.get("exit_plan", ""),
                                "reasoning": rationale,
                                "conviction": output.get("conviction", 0),
                                "order_result": str(order),
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "filled": filled
                            }
                            f.write(json.dumps(diary_entry) + "\n")
                    else:
                        reasoning = output.get('reasoning', output.get('rationale', ''))
                        add_event(f"Hold {asset}: {reasoning[:80]}...")
                        # Write hold to diary
                        with open(diary_path, "a") as f:
                            diary_entry = {
                                "timestamp": datetime.now().isoformat(),
                                "asset": asset,
                                "action": "hold",
                                "reasoning": reasoning,
                                "conviction": output.get("conviction", 0)
                            }
                            f.write(json.dumps(diary_entry) + "\n")
                except Exception as e:
                    import traceback
                    add_event(f"Execution error {asset}: {e}")

            await asyncio.sleep(get_interval_seconds(args.interval))

    async def handle_diary(request):
        """Return diary entries as JSON or newline-delimited text."""
        try:
            raw = request.query.get('raw')
            download = request.query.get('download')
            if raw or download:
                if not os.path.exists(diary_path):
                    return web.Response(text="", content_type="text/plain")
                with open(diary_path, "r") as f:
                    data = f.read()
                headers = {}
                if download:
                    headers["Content-Disposition"] = f"attachment; filename=diary.jsonl"
                return web.Response(text=data, content_type="text/plain", headers=headers)
            limit = int(request.query.get('limit', '200'))
            with open(diary_path, "r") as f:
                lines = f.readlines()
            start = max(0, len(lines) - limit)
            entries = [json.loads(l) for l in lines[start:]]
            return web.json_response({"entries": entries})
        except FileNotFoundError:
            return web.json_response({"entries": []})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_logs(request):
        """Stream log files with optional download or tailing behaviour."""
        try:
            path = request.query.get('path', 'llm_requests.log')
            download = request.query.get('download')
            limit_param = request.query.get('limit')
            if not os.path.exists(path):
                return web.Response(text="", content_type="text/plain")
            with open(path, "r") as f:
                data = f.read()
            if download or (limit_param and (limit_param.lower() == 'all' or limit_param == '-1')):
                headers = {}
                if download:
                    headers["Content-Disposition"] = f"attachment; filename={os.path.basename(path)}"
                return web.Response(text=data, content_type="text/plain", headers=headers)
            limit = int(limit_param) if limit_param else 2000
            return web.Response(text=data[-limit:], content_type="text/plain")
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def start_api(app):
        """Register HTTP endpoints for observing diary entries and logs."""
        app.router.add_get('/diary', handle_diary)
        app.router.add_get('/logs', handle_logs)

    async def main_async():
        """Start the aiohttp server and kick off the trading loop."""
        app = web.Application()
        await start_api(app)
        from src.config_loader import CONFIG as CFG
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, CFG.get("api_host"), int(CFG.get("api_port")))
        await site.start()
        await run_loop()

    def calculate_total_return(state, trade_log):
        """Compute percent return relative to an assumed initial balance."""
        initial = 10000
        current = state['balance'] + sum(p.get('pnl', 0) for p in state.get('positions', []))
        return ((current - initial) / initial) * 100 if initial else 0

    def calculate_sharpe(returns):
        """Compute a naive Sharpe-like ratio from the trade log."""
        if not returns:
            return 0
        vals = [r.get('pnl', 0) if 'pnl' in r else 0 for r in returns]
        if not vals:
            return 0
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(var) if var > 0 else 0
        return mean / std if std > 0 else 0


    asyncio.run(main_async())


if __name__ == "__main__":
    main()
