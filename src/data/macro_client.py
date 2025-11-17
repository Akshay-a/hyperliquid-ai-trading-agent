"""Macro data client for tracking traditional market indicators.

Tracks:
- SPX (S&P 500): General risk sentiment
- DXY (US Dollar Index): Dollar strength (inverse correlation with crypto)
- US10Y: Risk-free rate (affects discount rates)

Uses Yahoo Finance as free data source.
"""

import requests
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from src.utils.cache import cached


class MacroDataClient:
    """Client for fetching macro market data (SPX, DXY, yields)."""

    def __init__(self):
        """Initialize macro data client."""
        # Using Yahoo Finance API (free, no key required)
        self.timeout = 10

    def _get_yahoo_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest quote from Yahoo Finance.

        Args:
            symbol: Ticker symbol (^GSPC for SPX, DX-Y.NYB for DXY)

        Returns:
            Dict with price, change, and metadata
        """
        try:
            # Yahoo Finance chart API endpoint
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "range": "1d",
                "interval": "1h",
                "indicators": "quote",
                "includeTimestamps": "true",
            }

            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            # Extract latest data point
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            quotes = result.get("indicators", {}).get("quote", [{}])[0]

            current_price = meta.get("regularMarketPrice")
            prev_close = meta.get("chartPreviousClose")

            if current_price and prev_close:
                change = current_price - prev_close
                change_pct = (change / prev_close) * 100

                return {
                    "symbol": symbol,
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "previous_close": round(prev_close, 2),
                    "currency": meta.get("currency", "USD"),
                    "timestamp": datetime.now().isoformat(),
                }

            return None
        except requests.RequestException as e:
            logging.error(f"Yahoo Finance API error for {symbol}: {e}")
            return None
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logging.error(f"Yahoo Finance parse error for {symbol}: {e}")
            return None

    def _get_simple_trend(self, symbol: str, period_days: int = 7) -> Optional[str]:
        """Get simple trend (up/down/sideways) based on recent price action.

        Args:
            symbol: Ticker symbol
            period_days: Lookback period in days

        Returns:
            "up", "down", or "sideways"
        """
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "range": f"{period_days}d",
                "interval": "1d",
            }

            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            result = data.get("chart", {}).get("result", [{}])[0]
            quotes = result.get("indicators", {}).get("quote", [{}])[0]
            closes = quotes.get("close", [])

            if len(closes) < 3:
                return None

            # Filter out None values
            closes = [c for c in closes if c is not None]

            if not closes:
                return None

            # Simple trend: compare recent vs older
            recent_avg = sum(closes[-3:]) / 3
            older_avg = sum(closes[:3]) / 3

            diff_pct = ((recent_avg - older_avg) / older_avg) * 100

            if diff_pct > 1.5:
                return "up"
            elif diff_pct < -1.5:
                return "down"
            else:
                return "sideways"

        except Exception as e:
            logging.error(f"Trend calculation error for {symbol}: {e}")
            return None

    @cached(ttl_seconds=1800)  # Cache for 30 minutes
    def get_spx(self) -> Optional[Dict[str, Any]]:
        """Get S&P 500 index data.

        SPX is the primary risk sentiment indicator:
        - SPX up = Risk-on (bullish for crypto)
        - SPX down = Risk-off (bearish for crypto)

        Returns:
            Dict with price, change, change_pct, and trend
        """
        data = self._get_yahoo_quote("^GSPC")
        if data:
            data["trend"] = self._get_simple_trend("^GSPC", period_days=7)
        return data

    @cached(ttl_seconds=1800)  # Cache for 30 minutes
    def get_dxy(self) -> Optional[Dict[str, Any]]:
        """Get US Dollar Index (DXY).

        DXY has inverse correlation with crypto:
        - DXY up = Strong dollar (bearish for crypto)
        - DXY down = Weak dollar (bullish for crypto)

        Returns:
            Dict with price, change, change_pct, and trend
        """
        data = self._get_yahoo_quote("DX-Y.NYB")
        if data:
            data["trend"] = self._get_simple_trend("DX-Y.NYB", period_days=7)
        return data

    @cached(ttl_seconds=1800)  # Cache for 30 minutes
    def get_us10y(self) -> Optional[Dict[str, Any]]:
        """Get US 10-Year Treasury Yield.

        Higher yields = Less attractive risk assets (bearish for crypto)
        Lower yields = More attractive risk assets (bullish for crypto)

        Returns:
            Dict with yield, change, and trend
        """
        data = self._get_yahoo_quote("^TNX")
        if data:
            data["trend"] = self._get_simple_trend("^TNX", period_days=7)
        return data

    def get_all_macro(self) -> Dict[str, Any]:
        """Get all macro indicators in one call.

        Returns:
            Dict with spx, dxy, us10y data and overall risk assessment
        """
        logging.info("Fetching macro data (SPX, DXY, US10Y)")

        spx = self.get_spx()
        dxy = self.get_dxy()
        us10y = self.get_us10y()

        # Calculate overall risk sentiment
        risk_score = 0  # -3 (risk-off) to +3 (risk-on)

        if spx:
            if spx.get("trend") == "up":
                risk_score += 1
            elif spx.get("trend") == "down":
                risk_score -= 1

        if dxy:
            if dxy.get("trend") == "down":  # Weak dollar = bullish crypto
                risk_score += 1
            elif dxy.get("trend") == "up":
                risk_score -= 1

        if us10y:
            if us10y.get("trend") == "down":  # Lower yields = risk-on
                risk_score += 1
            elif us10y.get("trend") == "up":
                risk_score -= 1

        # Interpret risk score
        if risk_score >= 2:
            risk_environment = "risk_on"
            interpretation = "Strong risk-on environment (bullish for crypto)"
        elif risk_score == 1:
            risk_environment = "moderate_risk_on"
            interpretation = "Moderate risk-on environment"
        elif risk_score == 0:
            risk_environment = "neutral"
            interpretation = "Neutral macro environment"
        elif risk_score == -1:
            risk_environment = "moderate_risk_off"
            interpretation = "Moderate risk-off environment"
        else:
            risk_environment = "risk_off"
            interpretation = "Strong risk-off environment (bearish for crypto)"

        return {
            "spx": spx,
            "dxy": dxy,
            "us10y": us10y,
            "risk_score": risk_score,
            "risk_environment": risk_environment,
            "interpretation": interpretation,
        }

    def get_crypto_correlation_signal(self) -> Optional[str]:
        """Get simplified macro signal for crypto trading.

        Returns:
            "bullish", "neutral", or "bearish" based on macro conditions
        """
        macro = self.get_all_macro()

        risk_score = macro.get("risk_score", 0)

        if risk_score >= 1:
            return "bullish"
        elif risk_score <= -1:
            return "bearish"
        else:
            return "neutral"
