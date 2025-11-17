"""Risk management utilities for portfolio-level controls."""

import logging
from typing import Dict, List, Any, Optional


class RiskManager:
    """Portfolio-level risk management to prevent over-exposure."""

    def __init__(self, max_portfolio_heat: float = 0.30, max_simultaneous_positions: int = 3):
        """Initialize risk manager.

        Args:
            max_portfolio_heat: Maximum % of capital at risk (default: 30%)
            max_simultaneous_positions: Max number of open positions (default: 3)
        """
        self.max_portfolio_heat = max_portfolio_heat
        self.max_simultaneous_positions = max_simultaneous_positions

    def calculate_portfolio_heat(self, positions: List[Dict[str, Any]], account_value: float) -> float:
        """Calculate current portfolio heat (total exposure / account value).

        Args:
            positions: List of active positions
            account_value: Total account value

        Returns:
            Portfolio heat as decimal (0.30 = 30% exposure)
        """
        if not account_value or account_value <= 0:
            return 0.0

        total_exposure = 0.0
        for pos in positions:
            try:
                notional = abs(float(pos.get("quantity", 0)) * float(pos.get("entry_price", 0)))
                total_exposure += notional
            except (ValueError, TypeError):
                continue

        return total_exposure / account_value

    def calculate_dynamic_leverage(
        self,
        atr: Optional[float],
        atr_avg: float,
        confluence_score: int,
        risk_environment: str,
        leverage_min: float = 3.0,
        leverage_max: float = 10.0,
    ) -> float:
        """Calculate dynamic leverage based on market conditions.

        Args:
            atr: Current ATR (volatility)
            atr_avg: Average ATR for context
            confluence_score: Number of aligned signals (0-10)
            risk_environment: "risk_on", "neutral", "risk_off"
            leverage_min: Minimum leverage
            leverage_max: Maximum leverage

        Returns:
            Calculated leverage (between min and max)
        """
        leverage = leverage_min

        # Base leverage on confluence (more signals = higher leverage)
        if confluence_score >= 8:
            leverage = leverage_max
        elif confluence_score >= 6:
            leverage = (leverage_min + leverage_max) / 2
        else:
            leverage = leverage_min

        # Adjust for volatility (high volatility = lower leverage)
        if atr and atr_avg and atr_avg > 0:
            vol_ratio = atr / atr_avg
            if vol_ratio > 1.5:  # High volatility
                leverage *= 0.6  # Reduce by 40%
            elif vol_ratio > 1.2:  # Elevated volatility
                leverage *= 0.8  # Reduce by 20%

        # Adjust for macro risk environment
        if risk_environment == "risk_off":
            leverage *= 0.7  # Reduce by 30% in risk-off
        elif risk_environment == "moderate_risk_off":
            leverage *= 0.85  # Reduce by 15%

        # Ensure within bounds
        leverage = max(leverage_min, min(leverage_max, leverage))

        return round(leverage, 1)

    def can_open_position(
        self,
        current_positions: List[Dict[str, Any]],
        account_value: float,
        new_position_size: float,
    ) -> tuple[bool, str]:
        """Check if opening new position is allowed.

        Args:
            current_positions: List of active positions
            account_value: Total account value
            new_position_size: Notional size of new position

        Returns:
            (allowed: bool, reason: str)
        """
        # Check max simultaneous positions
        if len(current_positions) >= self.max_simultaneous_positions:
            return False, f"Max positions reached ({self.max_simultaneous_positions})"

        # Check portfolio heat
        current_heat = self.calculate_portfolio_heat(current_positions, account_value)
        new_exposure = new_position_size / account_value if account_value > 0 else 0
        projected_heat = current_heat + new_exposure

        if projected_heat > self.max_portfolio_heat:
            return False, f"Portfolio heat too high ({projected_heat:.1%} > {self.max_portfolio_heat:.1%})"

        return True, "OK"

    def adjust_position_size(
        self,
        desired_size: float,
        current_positions: List[Dict[str, Any]],
        account_value: float,
    ) -> float:
        """Adjust position size to respect portfolio heat limits.

        Args:
            desired_size: Desired notional position size
            current_positions: List of active positions
            account_value: Total account value

        Returns:
            Adjusted position size (may be smaller than desired)
        """
        if account_value <= 0:
            return 0.0

        current_heat = self.calculate_portfolio_heat(current_positions, account_value)
        available_heat = self.max_portfolio_heat - current_heat

        if available_heat <= 0:
            logging.warning("No available portfolio heat, position size set to 0")
            return 0.0

        max_allowed_size = available_heat * account_value
        adjusted_size = min(desired_size, max_allowed_size)

        if adjusted_size < desired_size:
            logging.info(
                f"Position size reduced: ${desired_size:.0f} → ${adjusted_size:.0f} "
                f"(portfolio heat: {current_heat:.1%})"
            )

        return adjusted_size
