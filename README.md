# Nocturne: AI Trading Agent on Hyperliquid

This project implements an AI-powered trading agent that leverages LLM models to analyze real-time market data from TAAPI, make informed trading decisions, and execute trades on the Hyperliquid decentralized exchange. The agent runs in a continuous loop, monitoring specified cryptocurrency assets at configurable intervals, using technical indicators to decide on buy/sell/hold actions, and manages positions with take-profit and stop-loss orders.

## Table of Contents

- [Disclaimer](#disclaimer)
- [Architecture](#architecture)
- [Nocturne Live Agents](#nocturne-live-agents)
- [Structure](#structure)
- [Env Configuration](#env-configuration)
- [Usage](#usage)
- [Tool Calling](#tool-calling)
- [Deployment to EigenCloud](#deployment-to-eigencloud)

## Disclaimer

There is no guarantee of any returns. This code has not been audited. Please use at your own risk.

## Architecture

See the full [Architecture Documentation](docs/ARCHITECTURE.md) for subsystems, data flow, and design principles.

![Architecture Diagram](docs/architecture.png)

## Nocturne Live Agents 

- GPT-5 Pro: [Portfolio Dashboard](https://hypurrscan.io/address/0xa049db4b3dfcb25c3092891010a629d987d26113) | [Live Logs](https://35.190.43.182/logs/0xC0BE8E55f469c1a04c0F6d04356828C5793d8a9D) (Seeded with $200)
- DeepSeek R1: [Portfolio Dashboard](https://hypurrscan.io/address/0xa663c80d86fd7c045d9927bb6344d7a5827d31db) | [Live Logs](https://35.190.43.182/logs/0x4da68B78ef40D12f378b8498120f2F5A910Af1aD) (Seeded with $100) -- PAUSED
- Grok 4: [Portfolio Dashboard](https://hypurrscan.io/address/0x3c71f3cf324d0133558c81d42543115ef1a2be79) | [Live Logs](https://35.190.43.182/logs/0xe6a9f97f99847215ea5813812508e9354a22A2e0) (Seeded with $100) -- PAUSED

## Structure
- `src/main.py`: Entry point, handles user input and main trading loop.
- `src/agent/decision_maker.py`: LLM logic for trade decisions (OpenRouter with tool calling for TAAPI indicators).
- `src/indicators/taapi_client.py`: Fetches indicators from TAAPI.
- `src/trading/hyperliquid_api.py`: Executes trades on Hyperliquid.
- `src/config_loader.py`: Centralized config loaded from `.env`.

## Env Configuration
Populate `.env` (use `.env.example` as reference):
- TAAPI_API_KEY
- HYPERLIQUID_PRIVATE_KEY (or LIGHTER_PRIVATE_KEY)
- OPENROUTER_API_KEY
- LLM_MODEL 
- Optional: OPENROUTER_BASE_URL (`https://openrouter.ai/api/v1`), OPENROUTER_REFERER, OPENROUTER_APP_TITLE

### Obtaining API Keys
- **TAAPI_API_KEY**: Sign up at [TAAPI.io](https://taapi.io/) and generate an API key from your dashboard.
- **HYPERLIQUID_PRIVATE_KEY**: Generate an Ethereum-compatible private key for Hyperliquid. Use tools like MetaMask or `eth_account` library. For security, never share this key.
- **OPENROUTER_API_KEY**: Create an account at [OpenRouter.ai](https://openrouter.ai/), then generate an API key in your account settings.
- **LLM_MODEL**: No key needed; specify a model name like "x-ai/grok-4" (see OpenRouter models list).

## Usage
Run: `poetry run python src/main.py --assets BTC ETH --interval 1h`

## Testing Locally with Test Funds

### 1. Setup Hyperliquid Testnet Account

1. **Create a new Ethereum wallet** for testing (NEVER use your main wallet):
   ```bash
   python -c "from eth_account import Account; acc = Account.create(); print(f'Address: {acc.address}\nPrivate Key: {acc.key.hex()}')"
   ```

2. **Get testnet funds** from Hyperliquid:
   - Go to [Hyperliquid Testnet Faucet](https://app.hyperliquid-testnet.xyz/faucet)
   - Connect your test wallet
   - Request testnet USDC (you'll get ~1000 USDC for testing)

3. **Configure for testnet** in your `.env`:
   ```bash
   # Use testnet endpoint
   HYPERLIQUID_API_URL=https://api.hyperliquid-testnet.xyz
   HYPERLIQUID_PRIVATE_KEY=your_test_wallet_private_key_here

   # Small position sizes for testing
   ASSETS=BTC
   INTERVAL=5m

   # LLM API keys
   OPENROUTER_API_KEY=your_openrouter_key
   LLM_MODEL=anthropic/claude-3.5-sonnet
   ```

### 2. Validate Installation

```bash
# Install dependencies
poetry install

# Install TA-Lib (required for indicators)
# On Ubuntu/Debian:
sudo apt-get install ta-lib

# On macOS:
brew install ta-lib

# Or install from source: https://github.com/TA-Lib/ta-lib-python
```

### 3. Run in Test Mode

```bash
# Start with a single asset and short interval
poetry run python src/main.py --assets BTC --interval 5m
```

### 4. Monitor Your Test Agent

**Check the logs:**
```bash
# In another terminal
tail -f llm_requests.log
```

**Check diary entries (trade history):**
```bash
# View last 10 trades
curl http://localhost:3000/diary?limit=10 | jq
```

**Check Hyperliquid testnet dashboard:**
- Visit: https://app.hyperliquid-testnet.xyz/
- Connect your test wallet
- View positions, orders, and PnL

### 5. Testing Checklist

- [ ] Agent starts without errors
- [ ] Market data is fetched successfully (check logs for "Features calculated")
- [ ] Risk limits are respected (max leverage 6x, max heat 25%)
- [ ] LLM provides reasoning for decisions
- [ ] Trades are executed when conviction > 0
- [ ] Stop-loss and take-profit orders are placed
- [ ] Agent holds when no edge is detected
- [ ] Diary entries are logged correctly

### 6. Key Test Scenarios

**Test 1: Risk Limits**
- Manually check if agent respects max leverage (6x)
- Verify circuit breaker triggers at -10% drawdown

**Test 2: Autonomous Decision Making**
- Observe if LLM reasoning changes based on market conditions
- Check if agent holds during ranging markets
- Verify agent trades during trending markets with alignment

**Test 3: Multi-Timeframe Analysis**
- Add `--assets BTC ETH` to test multiple assets
- Verify each asset gets independent analysis
- Check if weekly/daily trends are considered (in reasoning)

**Test 4: Position Management**
- Create a position manually on testnet
- Verify agent tracks active positions
- Check if TP/SL orders are managed correctly

### 7. Troubleshooting

**Issue: "No module named 'talib'"**
```bash
pip install TA-Lib
# If fails, install system library first (see step 2)
```

**Issue: "hyperliquid_market_data.py not found"**
```bash
# Ensure you're on the correct branch
git checkout claude/session-011CUZ2rQ9LcrFzZeS9ms52h
git pull origin claude/session-011CUZ2rQ9LcrFzZeS9ms52h
```

**Issue: "Rate limit exceeded"**
- Increase `--interval` to reduce LLM API calls
- Use a cheaper model: `LLM_MODEL=anthropic/claude-3-haiku`

**Issue: "No edge detected, holding"**
- This is NORMAL behavior! The AI agent only trades when it sees a statistical edge
- Try during high volatility periods (US market open, macro news)
- Check `reasoning` in logs to understand why agent is holding

### 8. Safety Notes

⚠️ **CRITICAL SAFETY RULES:**
- NEVER use your main wallet private key for testing
- ALWAYS start with testnet before mainnet
- Test with SMALL amounts first ($10-50)
- Monitor the first 24 hours closely
- Set conservative risk limits (max_leverage=3.0 for first tests)
- Keep initial account value small ($100-200 for first mainnet test)

### 9. Mainnet Migration (After Successful Testing)

Once you've validated on testnet:

1. **Update `.env` for mainnet:**
   ```bash
   HYPERLIQUID_API_URL=https://api.hyperliquid.xyz
   HYPERLIQUID_PRIVATE_KEY=your_mainnet_wallet_private_key
   ```

2. **Start with small capital** ($100-500)

3. **Monitor closely for 48 hours**

4. **Scale gradually** based on performance

### Local API Endpoints
When the agent runs, it also serves a minimal API:
- `GET /diary?limit=200` — returns recent JSONL diary entries as JSON.
- `GET /logs?path=llm_requests.log&limit=2000` — tails the specified log file.

Configure bind host/port via env:
- `API_HOST` (default `0.0.0.0`)
- `API_PORT` or `APP_PORT` (default `3000`)

Docker:
```bash
docker build --platform linux/amd64 -t trading-agent .
docker run --rm -p 3000:3000 --env-file .env trading-agent
# Now: curl http://localhost:3000/diary
```

## Tool Calling
The agent can dynamically fetch any TAAPI indicator (e.g., EMA, RSI) via tool calls. See [TAAPI Indicators](https://taapi.io/indicators/) and [EMA Example](https://taapi.io/indicators/exponential-moving-average/) for details.

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
