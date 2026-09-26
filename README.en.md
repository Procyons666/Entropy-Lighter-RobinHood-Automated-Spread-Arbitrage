# Entropy & Lighter / Robinhood Hood Automated Spread Arbitrage Bot

**[繁體中文說明 → README.md](README.md)**

Open-source two-venue perp arbitrage bot. One leg is always **Entropy**
(the `io` builder dex on Hyperliquid); the other leg — the hedge — is one of:

| `--hedge` | venue | quote | taker fee | protocol |
|---|---|---|---|---|
| `lighter` | Lighter mainnet | USDC | 0 bps | zkLighter ws (diff books, async settle) |
| `lighter-rh` | Lighter Robinhood chain | **USDG** | 0 bps | zkLighter ws |
| `tradexyz` | Hyperliquid trade.xyz dex | USDC | ~1 bps | HL l2Book, sync IOC settle |

> **Referral links** — signing up through these supports this project:
> - Entropy — 25% fee discount: <https://entropy.io/?r=procyons>
> - Lighter Robinhood chain: <https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none>

When the same symbol trades rich on one venue and cheap on the other, the bot
simultaneously sells the rich book and buys the cheap book with taker orders,
carrying a delta-neutral position until the premium reverts and the opposite
crossing unwinds it.

## Quick start

```bash
git clone https://github.com/Procyons666/Entropy-Lighter-RobinHood-Automated-Spread-Arbitrage.git
cd Entropy-Lighter-RobinHood-Automated-Spread-Arbitrage
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

**1. Collect data first** (no credentials needed):
```bash
python3 main.py --record-only --symbol SNDK --hedge lighter-rh
```

**2. Analyze and set thresholds:**
```bash
python3 tools/analyze.py
```

**3. Go live:**
```bash
pip install -r requirements-live.txt
python3 main.py --symbol SNDK --hedge lighter-rh
```

There is **no paper mode** — running without `--record-only` sends real orders immediately.

## Credentials

**Hyperliquid (Entropy leg):**
- Go to [https://app.hyperliquid.xyz/API](https://app.hyperliquid.xyz/API)
- Create an API (agent) wallet → copy the Agent Private Key into `HL_PRIVATE_KEY`
- Copy your main account address into `HL_ACCOUNT_ADDRESS`

**Lighter (hedge leg):**
- Register at [https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none](https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none)
- Follow [lighter-python](https://github.com/elliottech/lighter-python) to generate API keys

## License

[MIT](LICENSE)
