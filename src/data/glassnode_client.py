"""Glassnode API client for on-chain metrics.

Fetches the most predictive on-chain indicators for crypto trading:
- STH-SOPR (Short Term Holder Spent Output Profit Ratio)
- Entities in Profit %
- MVRV Ratio (Market Value to Realized Value)
- Exchange Net Position Change
- Accumulation Trend Score

Reference: https://docs.glassnode.com/api/
"""

import requests
import logging
from typing import Optional, Dict, Any
from src.config_loader import CONFIG


class GlassnodeClient:
    """Client for fetching on-chain metrics from Glassnode API."""

    def __init__(self):
        """Initialize Glassnode client with API key and base URL."""
        self.api_key = CONFIG.get("glassnode_api_key", "")
        self.base_url = "https://api.glassnode.com/v1/metrics"
        self.timeout = 10

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Make GET request to Glassnode API with error handling.

        Args:
            endpoint: API endpoint path (e.g., "indicators/sopr")
            params: Query parameters (asset, timestamp, etc.)

        Returns:
            JSON response data or None on error
        """
        if not self.api_key:
            logging.warning("Glassnode API key not configured, skipping on-chain metrics")
            return None

        url = f"{self.base_url}/{endpoint}"
        query_params = {"a": params.get("asset", "BTC"), "api_key": self.api_key}

        # Add optional parameters
        if params:
            for key in ["s", "u", "i", "timestamp_format", "format"]:
                if key in params:
                    query_params[key] = params[key]

        try:
            response = requests.get(url, params=query_params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            # Extract latest value from time series
            if isinstance(data, list) and len(data) > 0:
                return data[-1]  # Most recent data point
            return data
        except requests.HTTPError as e:
            if e.response.status_code == 402:
                logging.error(f"Glassnode: Metric '{endpoint}' requires paid subscription")
            else:
                logging.error(f"Glassnode API error [{e.response.status_code}]: {e}")
            return None
        except requests.RequestException as e:
            logging.error(f"Glassnode request failed for {endpoint}: {e}")
            return None
        except Exception as e:
            logging.error(f"Glassnode unexpected error: {e}")
            return None

    def get_sth_sopr(self, asset: str = "BTC") -> Optional[float]:
        """Get Short Term Holder SOPR (Spent Output Profit Ratio).

        Values > 1: STHs selling at profit (bullish)
        Values < 1: STHs selling at loss (bearish/capitulation)

        Args:
            asset: Asset symbol (BTC, ETH, etc.)

        Returns:
            SOPR value or None
        """
        result = self._get("indicators/sopr", {"asset": asset, "i": "24h"})
        return result.get("v") if result else None

    def get_entities_profit_pct(self, asset: str = "BTC") -> Optional[float]:
        """Get percentage of entities (addresses) in profit.

        High % (>75%): Strong bull market
        Medium % (40-75%): Neutral/consolidation
        Low % (<40%): Bear market/opportunity

        Args:
            asset: Asset symbol

        Returns:
            Percentage (0-100) or None
        """
        result = self._get("addresses/profit_relative", {"asset": asset})
        if result and "v" in result:
            return round(result["v"] * 100, 2)  # Convert to percentage
        return None

    def get_mvrv_ratio(self, asset: str = "BTC") -> Optional[float]:
        """Get MVRV Ratio (Market Value to Realized Value).

        MVRV > 3.0: Overvalued, take profit zone
        MVRV 1.0-3.0: Fair value
        MVRV < 1.0: Undervalued, accumulation zone

        Args:
            asset: Asset symbol

        Returns:
            MVRV ratio or None
        """
        result = self._get("market/mvrv", {"asset": asset})
        return result.get("v") if result else None

    def get_exchange_netflow(self, asset: str = "BTC") -> Optional[float]:
        """Get net position change on exchanges (24h).

        Positive: Inflow to exchanges (bearish - selling pressure)
        Negative: Outflow from exchanges (bullish - accumulation)

        Args:
            asset: Asset symbol

        Returns:
            Net flow in native units or None
        """
        result = self._get("transactions/transfers_volume_exchanges_net", {"asset": asset, "i": "24h"})
        return result.get("v") if result else None

    def get_accumulation_trend(self, asset: str = "BTC") -> Optional[float]:
        """Get accumulation trend score.

        Positive: Net accumulation by holders
        Negative: Net distribution by holders

        Args:
            asset: Asset symbol

        Returns:
            Trend score or None
        """
        result = self._get("indicators/accumulation_trend_score", {"asset": asset})
        return result.get("v") if result else None

    def get_nupl(self, asset: str = "BTC") -> Optional[float]:
        """Get NUPL (Net Unrealized Profit/Loss).

        NUPL > 0.75: Euphoria (sell signal)
        NUPL 0.5-0.75: Greed (caution)
        NUPL 0-0.5: Optimism (hold)
        NUPL < 0: Fear/Capitulation (buy opportunity)

        Args:
            asset: Asset symbol

        Returns:
            NUPL value or None
        """
        result = self._get("indicators/net_unrealized_profit_loss", {"asset": asset})
        return result.get("v") if result else None

    def get_all_metrics(self, asset: str = "BTC") -> Dict[str, Any]:
        """Fetch all key on-chain metrics in parallel (or sequentially with caching).

        Args:
            asset: Asset symbol (BTC, ETH, etc.)

        Returns:
            Dictionary with all metrics
        """
        logging.info(f"Fetching Glassnode metrics for {asset}")

        metrics = {
            "sth_sopr": self.get_sth_sopr(asset),
            "entities_profit_pct": self.get_entities_profit_pct(asset),
            "mvrv_ratio": self.get_mvrv_ratio(asset),
            "exchange_netflow": self.get_exchange_netflow(asset),
            "accumulation_trend": self.get_accumulation_trend(asset),
            "nupl": self.get_nupl(asset),
        }

        # Log which metrics are available
        available = [k for k, v in metrics.items() if v is not None]
        unavailable = [k for k, v in metrics.items() if v is None]

        if available:
            logging.info(f"Glassnode metrics available: {', '.join(available)}")
        if unavailable:
            logging.warning(f"Glassnode metrics unavailable: {', '.join(unavailable)}")

        return metrics
