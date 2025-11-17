"""Crypto Fear & Greed Index client using Alternative.me free API.

The Fear & Greed Index aggregates multiple sentiment indicators:
- Volatility (25%)
- Market Momentum/Volume (25%)
- Social Media (15%)
- Surveys (15%)
- Dominance (10%)
- Trends (10%)

Index interpretation:
- 0-24: Extreme Fear (buy opportunity)
- 25-49: Fear (cautious)
- 50-74: Greed (take profits)
- 75-100: Extreme Greed (high risk)

API: https://alternative.me/crypto/fear-and-greed-index/
"""

import requests
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from src.utils.cache import cached


class FearGreedClient:
    """Client for Crypto Fear & Greed Index from Alternative.me."""

    def __init__(self):
        """Initialize Fear & Greed client."""
        self.base_url = "https://api.alternative.me/fng/"
        self.timeout = 10

    @cached(ttl_seconds=900)  # Cache for 15 minutes (updates hourly)
    def get_current(self) -> Optional[Dict[str, Any]]:
        """Get current Fear & Greed Index.

        Returns:
            Dict with 'value' (0-100), 'value_classification' (text), and 'timestamp'
            or None on error
        """
        try:
            response = requests.get(self.base_url, params={"limit": 1}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if "data" in data and len(data["data"]) > 0:
                entry = data["data"][0]
                return {
                    "value": int(entry["value"]),
                    "classification": entry["value_classification"],
                    "timestamp": int(entry["timestamp"]),
                    "time_until_update": entry.get("time_until_update"),
                }
            return None
        except requests.RequestException as e:
            logging.error(f"Fear & Greed API error: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logging.error(f"Fear & Greed parse error: {e}")
            return None

    def get_historical(self, days: int = 7) -> Optional[List[Dict[str, Any]]]:
        """Get historical Fear & Greed Index values.

        Args:
            days: Number of days to retrieve (max 365)

        Returns:
            List of dicts with value, classification, and timestamp
        """
        try:
            # API uses limit parameter (number of data points, not days)
            response = requests.get(self.base_url, params={"limit": days}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if "data" in data:
                return [
                    {
                        "value": int(entry["value"]),
                        "classification": entry["value_classification"],
                        "timestamp": int(entry["timestamp"]),
                    }
                    for entry in data["data"]
                ]
            return None
        except requests.RequestException as e:
            logging.error(f"Fear & Greed historical API error: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logging.error(f"Fear & Greed historical parse error: {e}")
            return None

    def get_sentiment_signal(self) -> Optional[Dict[str, Any]]:
        """Get actionable sentiment signal with interpretation.

        Returns:
            Dict with value, classification, signal (buy/sell/neutral), and strength
        """
        current = self.get_current()
        if not current:
            return None

        value = current["value"]
        classification = current["classification"]

        # Determine trading signal
        if value <= 24:
            signal = "buy"
            strength = "strong"
            interpretation = "Extreme Fear - Strong buy opportunity (contrarian)"
        elif value <= 40:
            signal = "buy"
            strength = "moderate"
            interpretation = "Fear - Moderate buy opportunity"
        elif value <= 60:
            signal = "neutral"
            strength = "weak"
            interpretation = "Neutral sentiment - No clear signal"
        elif value <= 75:
            signal = "sell"
            strength = "moderate"
            interpretation = "Greed - Consider taking profits"
        else:
            signal = "sell"
            strength = "strong"
            interpretation = "Extreme Greed - Strong sell signal (risk off)"

        return {
            "value": value,
            "classification": classification,
            "signal": signal,
            "strength": strength,
            "interpretation": interpretation,
            "timestamp": datetime.fromtimestamp(current["timestamp"]).isoformat(),
        }

    def get_trend(self, days: int = 7) -> Optional[str]:
        """Analyze Fear & Greed trend over recent period.

        Args:
            days: Number of days to analyze

        Returns:
            "increasing" (getting more greedy), "decreasing" (getting more fearful),
            or "stable"
        """
        historical = self.get_historical(days)
        if not historical or len(historical) < 3:
            return None

        values = [h["value"] for h in historical]

        # Calculate trend (simple linear regression would be better, but this is KISS)
        recent_avg = sum(values[:len(values)//2]) / (len(values)//2)
        older_avg = sum(values[len(values)//2:]) / (len(values) - len(values)//2)

        diff = recent_avg - older_avg

        if diff > 5:
            return "increasing"  # Getting more greedy
        elif diff < -5:
            return "decreasing"  # Getting more fearful
        else:
            return "stable"
