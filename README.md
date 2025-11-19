# Nocturne: AI Trading Agent on Hyperliquid

**Version 2.0** - CAMEL-powered trading agent with optimized context engineering

An AI-powered trading agent that uses **pre-computed signals** and **LLM validation** to trade crypto perpetual futures on Hyperliquid. Built with:
- ✅ **CAMEL framework** for intelligent orchestration
- ✅ **Multi-source data** (TA, on-chain, macro, sentiment, microstructure)
- ✅ **Portfolio-level risk management** (prevents over-exposure)
- ✅ **Bias-free decision making** (shows both bullish and bearish signals)

## 📚 **[→ READ THE COMPLETE GUIDE: claude.md](claude.md)** ← START HERE

## Table of Contents

- [Quick Start](#quick-start)
- [Disclaimer](#disclaimer)
- [Architecture](#architecture)
- [Nocturne Live Agents](#nocturne-live-agents)
- [Documentation](#documentation)
- [Env Configuration](#env-configuration)
- [Usage](#usage)
- [Deployment to EigenCloud](#deployment-to-eigencloud)

## Quick Start

```bash
# 1. Install dependencies
poetry install

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Test
python test_components.py

# 4. Run (paper trade first!)
poetry run python src/main.py --assets BTC ETH --interval 5m
```

**For detailed setup, testing, and deployment**: See **[claude.md](claude.md)**

## Disclaimer

⚠️ **There is no guarantee of any returns. This code has not been audited. Use at your own risk.**

**Recommended**:
- Start with **$500**, not $5000
- Paper trade for 24-48 hours first
- Use conservative settings (see `.env.example`)
- Review all documentation before deploying

## Architecture

**High-level flow**:

```
Data Collection → Signal Calculation → LLM Validation → Risk Management → Execution
     (1s)              (Python)         (CAMEL)       (Portfolio Heat)   (Hyperliquid)
```

**Key innovation**: LLM **validates** pre-computed signals, doesn't calculate from scratch.

**For detailed architecture**: See **[claude.md - System Architecture](claude.md#-system-architecture-end-to-end-flow)**

## Nocturne Live Agents

- GPT-5 Pro: [Portfolio Dashboard](https://hypurrscan.io/address/0xa049db4b3dfcb25c3092891010a629d987d26113) | [Live Logs](https://35.190.43.182/logs/0xC0BE8E55f469c1a04c0F6d04356828C5793d8a9D) (Seeded with $200)
- DeepSeek R1: [Portfolio Dashboard](https://hypurrscan.io/address/0xa663c80d86fd7c045d9927bb6344d7a5827d31db) | [Live Logs](https://35.190.43.182/logs/0x4da68B78ef40D12f378b8498120f2F5A910Af1aD) (Seeded with $100) -- PAUSED
- Grok 4: [Portfolio Dashboard](https://hypurrscan.io/address/0x3c71f3cf324d0133558c81d42543115ef1a2be79) | [Live Logs](https://35.190.43.182/logs/0xe6a9f97f99847215ea5813812508e9354a22A2e0) (Seeded with $100) -- PAUSED

## Documentation

**Read in this order**:

1. **[claude.md](claude.md)** ← **START HERE** (Master guide)
   - Complete end-to-end flow
   - Configuration guide
   - Testing guide
   - All you need to get started

2. **[CONTEXT_ENGINEERING_ANALYSIS.md](CONTEXT_ENGINEERING_ANALYSIS.md)** (Deep dive)
   - How we eliminated LLM hallucination
   - Bias removal strategies
   - Industry best practices
   - Read if you want to understand the why

3. **[.env.example](.env.example)** (Configuration reference)
   - All available settings
   - Conservative defaults for $5000 accounts
   - Copy to `.env` and customize

4. **[test_components.py](test_components.py)** (Testing)
   - Validates all components
   - Run before deploying

5. **Other docs** (Historical context):
   - CONTEXT_ENGINEERING_OPTIMIZATION.md - Implementation report
   - LLM_VALIDATION_ANALYSIS.md - Original forensic analysis
   - CRITICAL_FIXES_ANALYSIS.md - First round fixes
   - CAMEL_INTEGRATION.md - Initial CAMEL implementation

## Code Structure

```
src/
├── agent/
│   ├── camel_agent.py          # CAMEL-powered LLM validator (current)
│   └── decision_maker.py       # Legacy agent (fallback)
├── data/
│   ├── orchestrator.py         # Parallel data fetcher + signal generator
│   ├── glassnode_client.py     # On-chain metrics (SOPR, MVRV, etc.)
│   ├── feargreed_client.py     # Crypto Fear & Greed Index
│   └── macro_client.py         # Traditional markets (SPX, DXY, US10Y)
├── indicators/
│   └── taapi_client.py         # Technical indicators (EMA, MACD, RSI, ATR)
├── trading/
│   └── hyperliquid_api.py      # Exchange API + order book microstructure
├── utils/
│   ├── signal_calculator.py    # Pre-compute confluence scores & leverage
│   ├── risk_manager.py         # Portfolio-level risk management
│   └── cache.py                # TTL caching for external APIs
├── config_loader.py            # Load configuration from .env
└── main.py                     # Main trading loop
```

**For detailed flow**: See **[claude.md - System Architecture](claude.md#-system-architecture-end-to-end-flow)**

## Env Configuration

**Quick setup**:
```bash
cp .env.example .env
# Edit .env with your settings
```

**Required API Keys**:
- `HYPERLIQUID_PRIVATE_KEY` - Your Ethereum wallet private key ([Get one](https://metamask.io/))
- `OPENROUTER_API_KEY` - LLM access ([Sign up](https://openrouter.ai/))
- `TAAPI_API_KEY` - Technical indicators ([Sign up](https://taapi.io/))

**Optional (Recommended)**:
- `GLASSNODE_API_KEY` - On-chain metrics for BTC/ETH ([Sign up](https://glassnode.com/))

**Trading Settings** (for $5000 account):
- `POSITION_SIZE_PCT=2.0` - 2% per trade ($100)
- `LEVERAGE_MAX=5.0` - Max 5x (conservative)
- `MAX_PORTFOLIO_HEAT=0.20` - 20% max exposure
- `ASSETS="BTC ETH"` - Start with 2 assets

**For full configuration guide**: See **[claude.md - Configuration Guide](claude.md#-configuration-guide)**

## Usage

**Basic usage**:
```bash
poetry run python src/main.py --assets BTC ETH SOL --interval 5m
```

**Before live trading**:
1. Run tests: `python test_components.py`
2. Paper trade for 24-48 hours
3. Start with **$500** (not $5000)
4. Review `prompts.log` and `diary.jsonl`

**For detailed testing guide**: See **[claude.md - Testing Guide](claude.md#-testing-guide)**

### Monitoring

The agent serves a local API for monitoring:
- `GET /diary?limit=200` - Recent trades (JSON)
- `GET /logs?path=llm_requests.log&limit=2000` - LLM logs

Configure via env:
- `API_HOST` (default `0.0.0.0`)
- `API_PORT` (default `8080`)

### Docker

```bash
docker build --platform linux/amd64 -t trading-agent .
docker run --rm -p 8080:8080 --env-file .env trading-agent
# Monitor: curl http://localhost:8080/diary
```

## Deployment to EigenCloud

EigenCloud (via EigenX CLI) allows deploying this trading agent in a Trusted Execution Environment (TEE) with secure key management.

### Prerequisites
- Allowlisted Ethereum account (Sepolia for testnet). Request onboarding at [EigenCloud Onboarding](https://onboarding.eigencloud.xyz).
- Docker installed.
- Sepolia ETH for deployments.

### Installation
#### macOS/Linux
```bash
curl -fsSL https://eigenx-scripts.s3.us-east-1.amazonaws.com/install-eigenx.sh | bash
```

#### Windows
```bash
curl -fsSL https://eigenx-scripts.s3.us-east-1.amazonaws.com/install-eigenx.ps1 | powershell -
```

### Initial Setup
```bash
docker login
eigenx auth login  # Or eigenx auth generate --store (if you don't have a eth account, keep this account separate from your trading account)
```

### Deploy the Agent
From the project directory:
```bash
cp .env.example .env
# Edit .env: set ASSETS, INTERVAL, API keys
eigenx app deploy
```

### Monitoring
```bash
eigenx app info --watch
eigenx app logs --watch
```

### Updates
Edit code or .env, then:
```bash
eigenx app upgrade <app-name>
```

For full CLI reference, see the [EigenX Documentation](https://github.com/Layr-Labs/eigenx-cli).
