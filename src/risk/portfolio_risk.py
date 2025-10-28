"""
Portfolio Risk Management

Jim Simons principle: "Risk management is more important than alpha generation"

This module:
1. Tracks portfolio-level risk metrics
2. Enforces position size limits
3. Implements drawdown circuit breakers
4. Monitors position correlation
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
import statistics
import math


class PortfolioRiskManager:
    """
    Systematic risk management for AI trading agent.

    Enforces:
    - Maximum leverage constraints
    - Portfolio heat limits (at-risk capital)
    - Drawdown circuit breakers
    - Position correlation limits
    """

    def __init__(self, max_leverage: float = 6.0, max_heat: float = 0.25):
        """
        Initialize risk manager.

        Args:
            max_leverage: Maximum total notional / equity (default 6x)
            max_heat: Maximum portfolio heat as fraction (default 25%)
        """
        self.max_leverage = max_leverage
        self.max_heat = max_heat

        self.trade_history = []  # List of completed trades
        self.peak_equity = None  # For drawdown calculation
        self.daily_pnl_history = []  # For Sharpe calculation

    def calculate_risk_metrics(
        self,
        account_equity: float,
        positions: List[Dict],
        active_trades: List[Dict],
        recent_fills: List[Dict]
    ) -> Dict:
        """
        Calculate comprehensive portfolio risk metrics.

        Returns dictionary with:
        - total_leverage
        - portfolio_heat
        - current_drawdown_pct
        - max_drawdown_pct
        - win_rate
        - profit_factor
        - sharpe_estimate
        - position_correlation
        - consecutive_losses
        """

        # Update peak equity for drawdown
        if self.peak_equity is None or account_equity > self.peak_equity:
            self.peak_equity = account_equity

        # Total leverage (notional / equity)
        total_notional = sum(
            abs(float(p.get('szi', 0))) * float(p.get('entryPx', 0))
            for p in positions
            if p.get('szi') and p.get('entryPx')
        )
        total_leverage = total_notional / account_equity if account_equity > 0 else 0

        # Portfolio heat (at-risk capital / equity)
        portfolio_heat = self._calculate_portfolio_heat(
            active_trades, account_equity
        )

        # Drawdown
        current_drawdown_pct = ((account_equity - self.peak_equity) / self.peak_equity * 100) if self.peak_equity else 0

        # Historical max drawdown
        max_drawdown_pct = current_drawdown_pct  # Simplified (should track historically)

        # Trading performance metrics
        perf_metrics = self._calculate_performance_metrics()

        # Position correlation
        correlation = self._calculate_position_correlation(positions)

        # Consecutive losses
        consecutive_losses = self._count_consecutive_losses()

        # Net exposure
        long_notional = sum(
            float(p.get('szi', 0)) * float(p.get('entryPx', 0))
            for p in positions
            if p.get('szi') and float(p.get('szi', 0)) > 0
        )

        short_notional = sum(
            abs(float(p.get('szi', 0))) * float(p.get('entryPx', 0))
            for p in positions
            if p.get('szi') and float(p.get('szi', 0)) < 0
        )

        return {
            "total_leverage": round(total_leverage, 2),
            "portfolio_heat": round(portfolio_heat, 4),
            "current_drawdown_pct": round(current_drawdown_pct, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "win_rate": perf_metrics["win_rate"],
            "profit_factor": perf_metrics["profit_factor"],
            "avg_win": perf_metrics["avg_win"],
            "avg_loss": perf_metrics["avg_loss"],
            "sharpe_estimate": perf_metrics["sharpe"],
            "position_correlation": round(correlation, 2),
            "consecutive_losses": consecutive_losses,
            "long_exposure_usd": round(long_notional, 0),
            "short_exposure_usd": round(short_notional, 0),
            "net_exposure_usd": round(long_notional - short_notional, 0)
        }

    def _calculate_portfolio_heat(
        self,
        active_trades: List[Dict],
        account_equity: float
    ) -> float:
        """
        Calculate total at-risk capital as fraction of equity.

        Heat = sum of (entry_price - stop_loss) * size / equity
        """
        total_risk = 0.0

        for trade in active_trades:
            entry = trade.get('entry_price', 0)
            stop = trade.get('sl_price', 0)
            amount = trade.get('amount', 0)

            if entry and stop and amount:
                risk_per_unit = abs(entry - stop)
                trade_risk = risk_per_unit * amount
                total_risk += trade_risk

        heat = total_risk / account_equity if account_equity > 0 else 0
        return heat

    def _calculate_performance_metrics(self) -> Dict:
        """Calculate win rate, profit factor, Sharpe from trade history."""
        if len(self.trade_history) < 5:
            return {
                "win_rate": 0.5,
                "profit_factor": 1.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "sharpe": 0.0
            }

        # Separate wins and losses
        wins = [t for t in self.trade_history if t.get('pnl', 0) > 0]
        losses = [t for t in self.trade_history if t.get('pnl', 0) < 0]

        win_rate = len(wins) / len(self.trade_history) if self.trade_history else 0

        # Profit factor
        total_wins = sum(t['pnl'] for t in wins) if wins else 0
        total_losses = abs(sum(t['pnl'] for t in losses)) if losses else 1

        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Average win/loss
        avg_win = total_wins / len(wins) if wins else 0
        avg_loss = total_losses / len(losses) if losses else 0

        # Sharpe estimate (from trade PnLs)
        if len(self.trade_history) >= 10:
            pnls = [t.get('pnl', 0) for t in self.trade_history]
            mean_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 1
            sharpe = (mean_pnl / std_pnl) * math.sqrt(len(pnls)) if std_pnl > 0 else 0
        else:
            sharpe = 0

        return {
            "win_rate": round(win_rate, 3),
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "sharpe": round(sharpe, 2)
        }

    def _calculate_position_correlation(self, positions: List[Dict]) -> float:
        """
        Estimate position correlation (simplified).

        1.0 = all positions same direction (highly correlated)
        0.0 = perfectly balanced (uncorrelated)
        """
        if not positions:
            return 0.0

        long_count = sum(1 for p in positions if float(p.get('szi', 0)) > 0)
        short_count = sum(1 for p in positions if float(p.get('szi', 0)) < 0)

        total = long_count + short_count
        if total == 0:
            return 0.0

        # High correlation = all long or all short
        imbalance = abs(long_count - short_count) / total

        return imbalance

    def _count_consecutive_losses(self) -> int:
        """Count consecutive losing trades from most recent."""
        if not self.trade_history:
            return 0

        count = 0
        for trade in reversed(self.trade_history):
            if trade.get('pnl', 0) < 0:
                count += 1
            else:
                break

        return count

    def check_risk_limits(
        self,
        proposed_trades: List[Dict],
        current_equity: float,
        current_positions: List[Dict],
        risk_metrics: Dict
    ) -> List[Dict]:
        """
        Apply risk limits to proposed trades.

        Returns:
            Modified trade list with adjusted sizes or rejected trades
        """
        validated_trades = []

        # Circuit breaker: Halt trading if drawdown too severe
        if risk_metrics.get('current_drawdown_pct', 0) < -10:
            for trade in proposed_trades:
                trade['action'] = 'hold'
                trade['rationale'] = f"Circuit breaker: Drawdown {risk_metrics['current_drawdown_pct']:.1f}% exceeds -10% limit"
                validated_trades.append(trade)
            return validated_trades

        # Check leverage limit
        current_notional = sum(
            abs(float(p.get('szi', 0))) * float(p.get('entryPx', 0))
            for p in current_positions
        )

        for trade in proposed_trades:
            if trade['action'] == 'hold':
                validated_trades.append(trade)
                continue

            # Proposed notional
            trade_notional = trade.get('allocation_usd', 0)

            # Check if this would exceed leverage limit
            new_total_notional = current_notional + trade_notional
            new_leverage = new_total_notional / current_equity if current_equity > 0 else 0

            if new_leverage > self.max_leverage:
                # Reduce size to fit within leverage limit
                max_allowed_notional = (self.max_leverage * current_equity) - current_notional
                if max_allowed_notional > 0:
                    trade['allocation_usd'] = max_allowed_notional
                    trade['rationale'] += f" [Size reduced to respect {self.max_leverage}x leverage limit]"
                else:
                    trade['action'] = 'hold'
                    trade['rationale'] = f"Rejected: Would exceed {self.max_leverage}x leverage limit"

            # Check portfolio heat limit
            if trade.get('sl_price') and trade.get('allocation_usd'):
                entry = trade.get('tp_price', 0)  # Approximate
                stop = trade.get('sl_price', 0)
                size = trade.get('allocation_usd', 0) / entry if entry else 0

                trade_risk = abs(entry - stop) * size if entry and stop else 0
                new_heat = risk_metrics['portfolio_heat'] + (trade_risk / current_equity)

                if new_heat > self.max_heat:
                    trade['action'] = 'hold'
                    trade['rationale'] = f"Rejected: Would exceed {self.max_heat*100:.0f}% heat limit"

            validated_trades.append(trade)

        return validated_trades

    def record_trade(self, trade: Dict):
        """Record completed trade for performance tracking."""
        self.trade_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "asset": trade.get('asset'),
            "pnl": trade.get('pnl', 0),
            "entry": trade.get('entry_price'),
            "exit": trade.get('exit_price'),
            "duration_minutes": trade.get('duration_minutes', 0)
        })

        # Keep only last 100 trades
        if len(self.trade_history) > 100:
            self.trade_history.pop(0)

    def should_reduce_size(self, risk_metrics: Dict) -> bool:
        """
        Determine if position sizes should be reduced due to poor performance.

        Returns True if:
        - 3+ consecutive losses
        - Drawdown > -8%
        - Win rate < 45% (over 20+ trades)
        """
        if risk_metrics.get('consecutive_losses', 0) >= 3:
            return True

        if risk_metrics.get('current_drawdown_pct', 0) < -8:
            return True

        if len(self.trade_history) >= 20:
            if risk_metrics.get('win_rate', 0.5) < 0.45:
                return True

        return False

    def get_size_multiplier(self, risk_metrics: Dict) -> float:
        """
        Get position size multiplier based on performance.

        Returns:
            0.5 if should reduce size
            1.0 if normal
        """
        if self.should_reduce_size(risk_metrics):
            return 0.5
        return 1.0
