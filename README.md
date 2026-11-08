# Glance Finance

**A synthetic-data financial wellness demo for HackUTD’s PNC challenge.**

[Try the live demo](https://glancefinance.us) · [Designs in Figma](https://www.figma.com/design/eiEJfY8thJW6nOXmmgVzJk/Glance-Finance-%E2%80%94-Web-and-Wallet-Display?node-id=0-1) · [PNC workshop toolkit](https://github.com/devfulcrum/pnc-utd-hackathon-2026)

## What it does

- Combines a synthetic checking balance, liquid cash, emergency-fund estimate, net worth, credit cards and other accounts.
- Simulates checking and credit-card purchases, and offers a car-purchase what-if calculator.
- Suggests editable budget soft limits using fixed illustrative weights, with quick or itemized expense entry.
- Offers an Ollama/llama3.2 AI coach and a browser-based compact wallet preview.

**Demo only:** No bank connection, real purchases, transfers, real-time transaction feed, or financial advice. Use synthetic data only. AI output may be inaccurate; check the calculations. Hosted model responses can take roughly two minutes. In-memory sessions expire and reset when the server restarts. This is not production-ready financial software.

## Run locally

Requirements: Python 3, Git, and the [PNC workshop repository](https://github.com/devfulcrum/pnc-utd-hackathon-2026). The commands below clone the toolkit separately and leave it unchanged. Run from a directory where you can create a sibling `pnc-utd-hackathon-2026` folder:

```bash
git clone https://github.com/devfulcrum/pnc-utd-hackathon-2026.git
git clone https://github.com/CarolinaJrz/glance-finance.git
cd glance-finance
python3 -m venv .venv
source .venv/bin/activate
export PNC_REPO="$(cd ../pnc-utd-hackathon-2026 && pwd)"
export WW_ORIGIN="http://127.0.0.1:5000"
export WW_SECURE_COOKIE=0
python3 app/glance_finance_public_v3.py --port 5000
```

Open http://127.0.0.1:5000/ (use this exact address, not localhost, because the local origin must match). The default server binds only to loopback. The `WW_SECURE_COOKIE=0` setting is for local HTTP only; use HTTPS and secure cookies for a properly configured public deployment. Do not expose the Python server directly. Ollama is optional for the dashboard and simulations; to use the coach, install and run Ollama and pull `llama3.2` on the machine running the app. If it is unavailable, the coach cannot answer.

## Project layout

- `app/` — current rebranded public-demo application.
- `hardware/` — separately prepared ESP32/LVGL screen firmware, connector, tests and driver license.
- `history/` — earlier local and public Python app versions, preserved for comparison; not the current deployed app.

## Hardware status

The wallet view in the web app is a **browser preview**, not a physical-device demonstration. The separate firmware compiled locally and the connector was tested with local synthetic state and simulated serial data. Hardware, touch, swipes and live refresh remain untested. The connector was tested against the earlier local app, not the public per-session app. Before flashing a borrowed display, obtain its owner's permission, preserve their existing work with a verified restore plan, and verify the hardware model and pins. See [hardware/README.md](hardware/README.md).

## Deployment and safety

The live demo uses a Vultr-hosted Ubuntu instance, an Nginx reverse proxy, HTTPS, per-visitor in-memory sessions, same-origin checks, bounded sessions and request limits. These are demo safeguards, not a security audit or a production privacy guarantee. No deployment keys, private data or server credentials are included. Hosting can incur charges while provisioned.

## Acknowledgments

Financial toolkit: [PNC workshop repository](https://github.com/devfulcrum/pnc-utd-hackathon-2026), provided separately under its Apache-2.0 license. Display drivers are copied from [AndyGJorgensen's ES3C35P starter](https://github.com/AndyGJorgensen/hosyond-esp32-s3-3.5-touchscreen-starter), revision `5e0fc4a8299a0de4c07aa71719060cf3b7a527c9`; their MIT license and copyright are in `hardware/DRIVER_LICENSE.txt`. Design records and earlier versions are included or linked for context, not as a claim that Figma automatically syncs with the app.
