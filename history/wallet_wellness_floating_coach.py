#!/usr/bin/env python3
"""Local synthetic financial wellness demo. Requires the PNC workshop repo."""
import argparse
import json
import math
import os
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request
import socket
import re
from pathlib import Path
from urllib.parse import urlparse
import sys

# Load the existing workshop code without changing the downloaded repository.
sys.dont_write_bytecode = True
repo = Path(os.environ.get('PNC_REPO', Path.home() / 'pnc-utd-hackathon-2026')).expanduser()
sys.path.insert(0, str(repo))
try:
    from wellness.data_gen import generate_customer
    from wellness.profile import build_profile
    from wellness.metrics import compute_metrics
    from wellness.scenarios import car_purchase
    from wellness.llm import OllamaLLM
except ImportError as e:
    print(f'Cannot load the PNC toolkit: {e}\nExpected repository: {repo}\n'
          'Set PNC_REPO to your repository folder if it is elsewhere.', file=sys.stderr)
    sys.exit(1)

customer = generate_customer(seed=42)
last_purchase = None
last_scenario = None
budget = None
CATEGORIES = ('groceries', 'transport', 'dining', 'other')

def budget_suggestion(data):
    income = money(data.get('income'), 'Monthly take-home income')
    savings = money(data.get('savings'), 'Monthly savings target')
    if income <= 0: raise ValueError('Income must be greater than zero.')
    mode = data.get('mode', 'quick')
    if mode not in ('quick', 'detailed'): raise ValueError('Choose a budget setup option.')
    baseline = {c: Decimal('0') for c in CATEGORIES}
    items = []
    if mode == 'quick':
        fixed = Decimal(str(money(data.get('fixed'), 'Essential bills and minimum debt payments')))
    else:
        raw = data.get('items', [])
        if not isinstance(raw, list) or len(raw) > 20: raise ValueError('Add up to 20 expenses.')
        fixed = Decimal('0')
        factors = {'weekly': Decimal(52)/12, 'every_two_weeks': Decimal(26)/12, 'twice_monthly': Decimal(2), 'monthly': Decimal(1), 'yearly': Decimal(1)/12}
        for item in raw:
            if not isinstance(item, dict): raise ValueError('Check each expense.')
            name = item.get('name', '')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60: raise ValueError('Enter an expense name of up to 60 characters for each item.')
            category = item.get('category')
            frequency = item.get('frequency')
            if category not in ('bills', *CATEGORIES) or frequency not in factors: raise ValueError('Choose a valid category and frequency for each expense.')
            amount = money(item.get('amount'), name.strip())
            monthly = (Decimal(str(amount)) * factors[frequency]).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if category == 'bills': fixed += monthly
            else: baseline[category] += monthly
            items.append({'name': name.strip(), 'amount': amount, 'category': category, 'frequency': frequency, 'monthly': float(monthly)})
    available = Decimal(str(income)) - fixed - Decimal(str(savings)) - sum(baseline.values())
    if available < 0: raise ValueError('Bills, estimated category expenses, and savings exceed income. Adjust your inputs before creating a plan.')
    cents = int(available * 100)
    parts = [cents * w // 100 for w in (40, 25, 15)]
    parts.append(cents - sum(parts))
    limits = {c: float(baseline[c] + Decimal(parts[i])/100) for i,c in enumerate(CATEGORIES)}
    return {'income': income, 'fixed': float(fixed), 'savings': savings, 'mode':mode, 'items':items,
            'baseline':{c:float(baseline[c]) for c in CATEGORIES}, 'limits':limits}

def get_state():
    p = build_profile(customer)
    m = compute_metrics(p)
    return {'checking': p['balances_by_type'].get('checking', 0),
            'liquid_cash': p['liquid_cash'], 'net_worth': p['net_worth'],
            'emergency_months': m['values']['emergency_fund_months'],
            'emergency_status': m['status']['emergency_fund_months'],
            'last_purchase': last_purchase, 'budget': budget, 'last_scenario': last_scenario,
            'accounts': p['accounts'], 'total_assets': p['total_assets'],
            'total_liabilities': p['total_liabilities']}

def money(value, label):
    try:
        if isinstance(value, bool): raise InvalidOperation
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > 1000000 or n.as_tuple().exponent < -2:
            raise InvalidOperation
        return float(n)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label} must be a valid amount from 0 to 1,000,000 with at most 2 decimal places.')

def number(value, label, lo, hi):
    try:
        if isinstance(value, bool): raise ValueError
        n = float(value)
        if not math.isfinite(n) or not lo <= n <= hi: raise ValueError
        return n
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be between {lo} and {hi}.')

class Handler(BaseHTTPRequestHandler):
    def send(self, code, data, content_type='application/json; charset=utf-8'):
        data = data if isinstance(data, bytes) else json.dumps(data, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self.send(200, HTML.encode(), 'text/html; charset=utf-8')
        elif path == '/state':
            self.send(200, get_state())
        elif path == '/coach/status':
            try:
                with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=4) as response:
                    info = json.load(response)
                if not isinstance(info, dict) or not isinstance(info.get('models'), list): raise ValueError('Invalid model list')
                names = [m.get('name', m.get('model', '')) for m in info['models'] if isinstance(m, dict)]
                found = any(isinstance(name, str) and name.split(':')[0] == 'llama3.2' for name in names)
                if found: self.send(200, {'ready': True, 'message': 'Ollama is running and llama3.2 is listed. Try asking a question; model startup may take time.'})
                else: self.send(200, {'ready': False, 'message': 'Ollama is running, but llama3.2 is not in its model list. In a terminal run: ollama pull llama3.2'})
            except (OSError, ValueError, TypeError, urllib.error.URLError):
                self.send(200, {'ready': False, 'message': 'The app cannot connect to Ollama on this computer. In a terminal check: ollama --version and ollama list'})
        else:
            self.send(404, {'error': 'Not found'})

    def do_POST(self):
        global customer, last_purchase, budget, last_scenario
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 8192: raise ValueError('Request too large.')
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict): raise ValueError('Invalid request.')
            path = urlparse(self.path).path
            if path == '/purchase':
                amount = money(data.get('amount'), 'Purchase amount')
                if amount <= 0: raise ValueError('Purchase amount must be greater than zero.')
                account_id = data.get('account_id', 'chk-1')
                account = next((a for a in customer['accounts'] if a['id'] == account_id and a['type'] in ('checking', 'credit_card')), None)
                if account is None: raise ValueError('Select an available checking account or credit card.')
                if account['type'] == 'checking' and amount > account['balance']:
                    raise ValueError('Purchase exceeds the simulated checking balance.')
                if account['type'] == 'credit_card' and amount > round(account['credit_limit'] - account['balance'], 2):
                    raise ValueError('Purchase exceeds the simulated available credit.')
                category = data.get('category', 'other')
                if category not in CATEGORIES: raise ValueError('Choose a valid budget category.')
                before = get_state()
                account['balance'] = round(account['balance'] + (amount if account['type'] == 'credit_card' else -amount), 2)
                customer['transactions'].append({'date': date.today().isoformat(), 'category': category, 'amount': -amount})
                if budget is not None: budget['spent'][category] = round(budget['spent'][category] + amount, 2)
                last_scenario = None
                last_purchase = {'amount': amount, 'account_id': account['id'], 'account_name': account['name'], 'account_type': account['type']}
                self.send(200, {'before': before, 'after': get_state()})
            elif path == '/scenario':
                price, down = money(data.get('price'), 'Car price'), money(data.get('down'), 'Down payment')
                apr = number(data.get('apr'), 'APR', 0, 100)
                term = number(data.get('months'), 'Loan term', 1, 360)
                if not term.is_integer(): raise ValueError('Loan term must be a whole number of months.')
                if price <= 0: raise ValueError('Car price must be greater than zero.')
                if down > price: raise ValueError('Down payment cannot exceed the car price.')
                result = car_purchase(build_profile(customer), price, down, apr / 100, int(term))
                last_scenario = result
                self.send(200, result)
            elif path == '/budget/suggest':
                self.send(200, budget_suggestion(data))
            elif path == '/budget/save':
                proposal = budget_suggestion(data)
                proposed = data.get('limits')
                if not isinstance(proposed, dict): raise ValueError('Enter a limit for each category.')
                limits = {c: money(proposed.get(c), c.title() + ' limit') for c in CATEGORIES}
                if sum(Decimal(str(x)) for x in limits.values()) > Decimal(str(proposal['income'])) - Decimal(str(proposal['fixed'])) - Decimal(str(proposal['savings'])):
                    raise ValueError('Category limits exceed the amount left after bills and savings.')
                saved = money(data.get('saved', 0), 'Amount saved toward goal')
                prior_spent = budget['spent'] if budget else {c: 0 for c in CATEGORIES}
                budget = {**proposal, 'limits': limits, 'saved': saved, 'spent': prior_spent}
                self.send(200, budget)
            elif path == '/coach':
                question = data.get('question', '')
                if not isinstance(question, str) or not question.strip() or len(question) > 1000: raise ValueError('Enter a question of up to 1,000 characters.')
                evidence = {'snapshot': get_state(), 'monthly_income_synthetic': customer['monthly_income']}
                system = ("You are a friendly educational financial wellness coach for a SYNTHETIC demo, not an adviser. "
                  "Use only the supplied evidence for this customer's circumstances. Never assert an account is real. "
                  "Do not calculate, invent figures, interest rates or account details. Do not recommend a specific financial product. "
                  "If the question requires a calculation not in evidence, ask the user to use the car scenario or budget planner, "
                  "or say that calculation is not available. Keep the response under 150 words. Mention relevant uncertainty. "
                  "Educational principles: track income and spending; include irregular expenses; review and adjust a budget when circumstances change. "
                  "This information is educational, not financial advice.")
                try:
                    text = OllamaLLM(model='llama3.2').chat([{'role':'system','content':system}, {'role':'user','content':'DEMO EVIDENCE: '+json.dumps(evidence)+'\nUSER QUESTION: '+question}])
                    if not isinstance(text, str) or not text.strip(): raise ValueError('The model returned an empty response.')
                    self.send(200, {'answer': text[:6000], 'notice': 'AI explanations may be inaccurate; check the calculated values and sources.'})
                except urllib.error.HTTPError as e:
                    try:
                        detail = json.loads(e.read(4096).decode('utf-8', errors='replace')).get('error', '')
                        detail = str(detail).replace('\n', ' ')[:350]
                    except (ValueError, TypeError, AttributeError): detail = ''
                    if e.code == 404:
                        message = 'Ollama returned 404. The llama3.2 model or chat endpoint may be missing. Run: ollama list'
                    else:
                        message = f'Ollama returned error {e.code}. Try running the model directly: ollama run llama3.2 "Say hello"'
                    if detail: message += ' Details: ' + detail
                    self.send(503, {'error': message})
                except (TimeoutError, socket.timeout):
                    self.send(503, {'error': 'The model took too long to respond. Try running it directly in a terminal: ollama run llama3.2 "Say hello"'})
                except urllib.error.URLError as e:
                    if isinstance(e.reason, (TimeoutError, socket.timeout)):
                        message = 'Ollama timed out. Try the model in a terminal: ollama run llama3.2 "Say hello"'
                    else:
                        message = 'The app cannot connect to Ollama. Check ollama --version and ollama list in a terminal.'
                    self.send(503, {'error': message})
                except (OSError, KeyError, TypeError, ValueError):
                    self.send(503, {'error': 'Ollama returned an unexpected or empty response. Try running: ollama run llama3.2 "Say hello"'})
            elif path == '/reset':
                customer = generate_customer(seed=42)
                last_purchase = None
                last_scenario = None
                budget = None
                self.send(200, get_state())
            else:
                self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send(400, {'error': str(e)})

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Wallet Wellness | Synthetic demo</title><style>
:root{color-scheme:light;--navy:#102e55;--ink:#142b49;--blue:#1b62a4;--muted:#506985;--line:#d8e4f1;--paper:#fff;--bg:#f2f6fb;--soft:#e4f0fb}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}button,input,select,textarea{font:inherit}textarea{display:block;width:100%;padding:12px;border-radius:7px;border:1px solid #b7cadc;background:#f8fbff;color:var(--ink);resize:vertical;line-height:1.5}a{color:#175d9c}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #edaf35;outline-offset:2px}.shell{min-height:100vh;display:grid;grid-template-columns:215px minmax(0,1fr)}.side{background:var(--navy);color:white;padding:28px 16px;display:flex;flex-direction:column;gap:36px}.brand{display:flex;align-items:center;gap:11px;font-weight:800;line-height:1.15;font-size:19px}.logo{background:#e4f0fb;color:var(--navy);border-radius:9px;width:36px;height:36px;display:grid;place-items:center}.brand small{display:block;color:#c5d9ed;font-size:10px;letter-spacing:.1em;margin-top:3px}.nav-caption{font-size:12px;color:#c5d9ed;text-transform:uppercase;font-weight:700;margin:0 12px 8px}.nav{display:grid;gap:4px}.tab{background:transparent;border:0;border-radius:8px;color:#e3eef8;text-align:left;min-height:44px;padding:10px 12px}.tab:hover,.tab[aria-selected=true]{background:#285581;color:#fff}.sidenote{margin-top:auto;background:#285581;border-radius:10px;padding:16px;font-size:14px;color:#edf6ff}.sidenote strong{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}.content{width:100%;max-width:1310px;margin:0 auto;padding:30px 38px 56px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:12px;font-weight:700;letter-spacing:.05em;color:var(--muted)}.pill{color:var(--navy);background:var(--soft);padding:6px 12px;border-radius:99px}.intro{margin:26px 0 30px}.intro h1{font-size:clamp(29px,3vw,39px);letter-spacing:-.035em;line-height:1.15;margin:0 0 6px}.intro p,.subtitle{color:var(--muted);margin:0}.cols{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.9fr);gap:22px;align-items:start}.stack{display:grid;gap:20px}.hero{background:var(--navy);color:white;border-radius:12px;padding:26px;min-height:215px;display:flex;flex-direction:column}.micro{font-size:12px;text-transform:uppercase;font-weight:700;letter-spacing:.05em;color:#c4d9ed}.hero-value{font-size:clamp(32px,4vw,46px);font-weight:750;line-height:1.1;letter-spacing:-.035em;margin:18px 0 7px}.hero p{margin:0;color:#dceaf7}.hero-footer{border-top:1px solid #4e7294;padding-top:13px;margin-top:auto;color:#dceaf7;font-size:14px}.panel,.metric,.acct-card{background:white;border:1px solid var(--line);border-radius:12px}.panel{padding:22px}.panel h2,.group-title{font-size:21px;line-height:1.25;margin:0 0 5px}.panel p{margin:0;color:var(--muted)}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:14px}.section-heading h2{font-size:21px;margin:0}.section-heading p{margin:0;color:var(--muted);font-size:14px}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.metric{padding:17px;min-height:135px}.metric .label{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase}.metric .value{font-size:clamp(18px,1.8vw,23px);font-weight:750;line-height:1.2;margin:14px 0 5px;overflow-wrap:anywhere}.metric .hint{font-size:14px;color:var(--muted)}label{display:block;font-weight:700;font-size:14px;margin:14px 0 5px}input,select{width:100%;min-height:44px;padding:9px 12px;border-radius:7px;border:1px solid #b7cadc;background:#f8fbff;color:var(--ink)}.btn{min-height:44px;border:1px solid var(--blue);border-radius:7px;background:var(--blue);color:white;font-weight:700;padding:9px 15px;margin-top:16px}.btn:hover{background:#124c81}.secondary{background:white;color:var(--navy);border-color:#a9bfd3}.secondary:hover{background:#edf5fc}.fields{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.notice{margin-top:14px!important;color:var(--ink)!important}.error{color:#a52723!important}.results{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}.results p{color:var(--ink);margin:5px 0}.foot{margin-top:24px;color:var(--muted);font-size:14px}.foot strong{color:var(--ink)}[hidden]{display:none!important}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.acct-card{overflow:hidden}.card-face{padding:20px;background:var(--navy);color:white;min-height:154px;display:flex;flex-direction:column;justify-content:space-between}.card-face small{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#d8e7f5}.card-face strong{font-size:24px;letter-spacing:-.02em}.card-info{padding:16px 20px}.pair{display:flex;justify-content:space-between;gap:12px;font-size:14px;padding:6px 0}.pair span{color:var(--muted)}.pair strong{text-align:right}.bar{height:6px;background:#dfebf6;border-radius:8px;margin:10px 0 4px;overflow:hidden}.bar span{display:block;height:100%;background:var(--blue)}.account-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.account-group{padding:20px}.account-row{display:flex;justify-content:space-between;gap:16px;border-top:1px solid var(--line);padding:13px 0}.account-row:first-of-type{margin-top:12px}.account-row .sub{font-size:13px;color:var(--muted);display:block}.account-row strong{text-align:right;white-space:nowrap}.wallet-layout{display:grid;grid-template-columns:320px minmax(0,1fr);gap:30px;align-items:start}.device{width:320px;height:480px;background:#102e55;color:#fff;border-radius:12px;overflow:hidden;display:flex;flex-direction:column;touch-action:pan-y;user-select:none}.device-top{padding:18px 20px 0;display:flex;justify-content:space-between;align-items:center;font-size:11px;font-weight:700;letter-spacing:.04em}.device-chip{background:#2a5d87;padding:5px 9px;border-radius:99px}.screen{padding:18px 20px 0;flex:1;min-height:0}.screen-kicker{color:#bbd5ed;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.screen-title{font-size:16px;margin-top:8px;color:#daeaf8}.screen-number{font-size:32px;font-weight:750;line-height:1.15;letter-spacing:-.03em;margin-top:7px;overflow-wrap:anywhere}.screen-note{font-size:13px;color:#d7e8f8;margin-top:7px}.screen-card{background:white;color:var(--ink);border-radius:10px;padding:16px;margin-top:19px}.screen-card-title{font-size:14px;font-weight:750;margin-bottom:10px}.screen-row{display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:4px 0}.screen-row span{color:#536b83}.screen-row b{text-align:right}.screen-hint{font-size:12px;color:#bfd5e8;margin-top:16px}.device-bottom{display:flex;align-items:center;justify-content:space-between;padding:0 16px 14px;gap:8px}.device-bottom button{height:42px;min-width:76px;border:1px solid #7b9ab8;border-radius:7px;background:transparent;color:white;font-weight:700;font-size:13px}.page-count{font-size:12px;color:#dceaf7}.callout{background:#e9f2fc;padding:18px;border-radius:10px;color:var(--ink);margin-top:16px}.callout p{margin:0}.wallet-copy{max-width:50ch}.wallet-copy h2{margin:0 0 8px}.wallet-copy p{color:var(--muted)}@media(max-width:1000px){.shell{grid-template-columns:1fr}.side{padding:14px 20px;gap:12px}.brand small,.nav-caption,.sidenote{display:none}.nav{display:flex;flex-wrap:wrap;gap:4px}.tab{padding:10px}.content{padding:26px 24px 48px}}@media(max-width:700px){.content{padding:24px 16px 42px}.intro{margin:24px 0}.cols,.wallet-layout{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.account-grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric:last-child{grid-column:1/-1}.device{max-width:100%}.panel{padding:18px}.nav{font-size:14px}}@media(max-width:400px){.fields{grid-template-columns:1fr}.top{font-size:11px}}@media(prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
.mode-choice{border:1px solid var(--line);border-radius:9px;margin:18px 0 0;padding:12px 14px}.mode-choice legend,.expense-entry legend{font-weight:700;font-size:14px;padding:0 5px}.mode-choice label{display:flex;align-items:center;gap:10px;margin:8px 0;font-weight:500}.mode-choice input{width:18px;min-height:18px;margin:0}.expense-entry{border:1px solid var(--line);border-radius:9px;margin:16px 0 0;padding:14px}.expense-entry label{margin-top:8px}.expense-entry .btn{margin-top:12px}.expense-detail{font-size:14px;color:var(--muted)}
.coach-launch{position:fixed;right:24px;bottom:24px;z-index:9;border:0;border-radius:999px;background:#175d9c;color:white;font-weight:750;padding:14px 22px;min-height:48px;box-shadow:0 4px 12px rgba(16,46,85,.22)}.coach-launch:hover{background:#104a7d}.coach-dock{position:fixed;right:24px;bottom:88px;width:min(390px,calc(100vw - 32px));max-height:min(660px,calc(100dvh - 112px));z-index:10;display:flex;flex-direction:column;background:white;color:var(--ink);border:1px solid #bdcfdf;border-radius:12px;box-shadow:0 12px 36px rgba(16,46,85,.25);overflow:hidden}.coach-head{background:var(--navy);color:#fff;padding:16px 18px;display:flex;justify-content:space-between;gap:10px;align-items:center}.coach-head h2{font-size:19px;margin:0}.coach-head p{font-size:13px;color:#d4e5f4;margin:2px 0 0}.coach-close{border:1px solid #a5c0d9;color:white;background:transparent;border-radius:7px;padding:8px 12px;min-height:40px}.coach-body{overflow-y:auto;padding:16px 18px}.coach-body p{font-size:14px;margin:0 0 10px;color:var(--muted)}.coach-body .btn{margin-top:12px}.coach-body .results{margin-top:14px}.coach-body .results p{font-size:15px;color:var(--ink)}.coach-body .results .notice{font-size:13px;color:var(--muted)}.coach-body details{margin-top:16px;color:var(--ink);font-size:14px}.coach-body summary{cursor:pointer;font-weight:700}.coach-body ul{padding-left:20px}.coach-status{margin:9px 0 0!important;color:var(--ink)!important;overflow-wrap:anywhere}textarea:focus-visible{outline:3px solid #edaf35;outline-offset:2px}@media(max-width:700px){.coach-launch{right:16px;bottom:16px}.coach-dock{right:16px;bottom:76px;max-height:calc(100dvh - 92px)}}
</style></head><body><div class="shell"><aside class="side"><div class="brand"><span class="logo">W</span><span>Wallet<small>WELLNESS</small></span></div><div><p class="nav-caption">Your space</p><nav class="nav" role="tablist" aria-label="Dashboard views"><button class="tab" role="tab" aria-selected="true" aria-controls="view-overview" data-view="overview">Overview</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-cards" data-view="cards">Credit cards</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-accounts" data-view="accounts">Other accounts</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-budget" data-view="budget">Budget planner</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-wallet" data-view="wallet">Wallet preview</button></nav></div><div class="sidenote"><strong>Synthetic data</strong>No bank connected. A safe space to explore decisions.</div></aside>
<main class="content"><div class="top"><span>FINANCIAL WELLNESS / <span id="top-label">OVERVIEW</span></span><span class="pill">SIMULATED</span></div><header class="intro"><h1 id="view-title">Your money, in perspective.</h1><p id="view-subtitle">A clearer picture today. More confident choices tomorrow.</p></header>
<section id="view-overview" role="tabpanel"><div class="cols"><div class="stack"><div class="hero"><div class="micro">Checking balance</div><div class="hero-value" id="checking">Loading…</div><p>Available in this synthetic demo</p><div class="hero-footer">Demo account · No real transactions</div></div><section><div class="section-heading"><div><h2>Your financial snapshot</h2><p>Based on the PNC workshop toolkit</p></div></div><div class="metrics"><div class="metric"><div class="label">Liquid cash</div><div class="value" id="cash">—</div><div class="hint">Checking + savings</div></div><div class="metric"><div class="label">Emergency fund</div><div class="value" id="emergency">—</div><div class="hint" id="status">Estimated months</div></div><div class="metric"><div class="label">Net worth</div><div class="value" id="worth">—</div><div class="hint">Assets minus debts</div></div></div></section><section class="panel"><h2>Recent activity</h2><p>Latest simulated purchase</p><p class="notice" id="purchase-message" role="status">No purchases yet.</p><button class="btn secondary" type="button" id="reset">Reset demo</button></section></div><div class="stack"><section class="panel"><h2>Try a purchase</h2><p>See the effect before spending.</p><form id="purchase-form"><label for="account">Pay with</label><select id="account"></select><label for="purchase-category">Budget category</label><select id="purchase-category"><option value="groceries">Groceries</option><option value="transport">Transport</option><option value="dining">Dining</option><option value="other" selected>Other</option></select><label for="amount">Purchase amount ($)</label><input id="amount" type="number" min="0.01" max="1000000" step="0.01" value="25.00" required><button class="btn" type="submit">Simulate purchase</button></form><p class="notice" style="font-size:14px">Checking purchases reduce cash; card purchases increase debt.</p></section><section class="panel"><h2>What if I buy a car?</h2><p>Estimate a loan without changing your balances.</p><form id="scenario-form"><div class="fields"><div><label for="price">Car price ($)</label><input id="price" type="number" min="0.01" max="1000000" step="0.01" value="30000" required></div><div><label for="down">Down payment ($)</label><input id="down" type="number" min="0" max="1000000" step="0.01" value="5000" required></div><div><label for="apr">APR (%)</label><input id="apr" type="number" min="0" max="100" step="0.01" value="7" required></div><div><label for="months">Loan term (months)</label><input id="months" type="number" min="1" max="360" step="1" value="60" required></div></div><button class="btn">Calculate scenario</button></form><div class="results" id="scenario-result" aria-live="polite" hidden></div></section></div></div></section>
<section id="view-cards" role="tabpanel" hidden><div class="section-heading"><div><h2>Credit cards</h2><p>Each balance is the amount owed—not money available to spend.</p></div></div><div id="cards-list" class="cards"></div><p class="foot">Minimum payments are the starter toolkit’s original estimates; they do not recalculate after simulated purchases.</p></section>
<section id="view-accounts" role="tabpanel" hidden><div class="section-heading"><div><h2>Other accounts</h2><p>Assets and debts, grouped by their role.</p></div></div><div id="accounts-list" class="account-grid"></div></section>
<section id="view-budget" role="tabpanel" hidden><div class="cols"><div class="stack"><section class="panel"><h2>Build your monthly plan</h2><p>Choose a quick estimate or list individual expenses. Include minimum debt payments under bills; don’t enter an expense twice. Use synthetic examples only.</p><form id="suggest-form"><label for="bi">Monthly take-home income ($)</label><input id="bi" type="number" min="0.01" max="1000000" step="0.01" value="5000" required><fieldset class="mode-choice"><legend>Choose your setup</legend><label><input type="radio" name="budget-mode" value="quick" checked> Quick: enter a total</label><label><input type="radio" name="budget-mode" value="detailed"> Detailed: add individual expenses</label></fieldset><div id="quick-fields"><label for="bf">Monthly bills &amp; minimum debt payments ($)</label><input id="bf" type="number" min="0" max="1000000" step="0.01" value="2500"></div><div id="detailed-fields" hidden><p class="notice">Add bills and estimates in one place. Gas, groceries and similar items become part of their category limit—not a second bill. Use synthetic examples only.</p><div id="expense-list"></div><button class="btn secondary" id="add-expense" type="button">+ Add expense</button><p class="notice">Weekly, every-two-week and yearly amounts are converted to monthly averages. You can add up to 20 items.</p></div><label for="bs">Monthly savings goal ($)</label><input id="bs" type="number" min="0" max="1000000" step="0.01" value="300" required><button class="btn">Suggest soft limits</button></form><p class="notice" id="suggest-message" role="status"></p><div id="expense-preview" class="results" aria-live="polite" hidden></div></section><section class="panel" id="limits-panel" hidden><h2>Make it yours</h2><p>The app first reserves your listed bills, savings and category estimates. It then divides what remains: groceries 40%, transport 25%, dining 15%, other 20%. These are example weights, not personalized advice; edit the limits before saving.</p><form id="budget-form"><div class="fields"><div><label for="bgroceries">Groceries ($)</label><input id="bgroceries" type="number" min="0" max="1000000" step="0.01" required></div><div><label for="btransport">Transport ($)</label><input id="btransport" type="number" min="0" max="1000000" step="0.01" required></div><div><label for="bdining">Dining ($)</label><input id="bdining" type="number" min="0" max="1000000" step="0.01" required></div><div><label for="bother">Other ($)</label><input id="bother" type="number" min="0" max="1000000" step="0.01" required></div></div><label for="bsaved">Amount already set aside toward this month’s goal ($)</label><input id="bsaved" type="number" min="0" max="1000000" step="0.01" value="0" required><button class="btn">Save demo plan</button></form><p id="budget-message" class="notice" role="status"></p></section></div><div class="stack"><section class="panel"><h2>Your saved plan at a glance</h2><p id="budget-empty">No plan saved yet. Nothing moves money or blocks spending.</p><p>After saving, ask the AI coach to discuss your plan; the starting split itself is calculated using fixed example weights.</p><div id="budget-summary" aria-live="polite"></div></section><section class="panel"><h2>Celebrate small steps</h2><p>Record what you have already saved when saving your plan. This is a manual demo entry—not a transfer or a bank balance.</p><div class="callout"><p>Listed category expenses are estimates used to suggest limits, not purchases already spent. Simulated purchases after you save count toward those limits. Limits never block a purchase.</p></div></section></div></div><p class="foot">No automatic habit learning yet. This starter plan uses fixed example weights, not a month of observed behavior. It resets when the server or demo resets.</p></section>
<section id="view-wallet" role="tabpanel" hidden><div class="wallet-layout"><div class="device" id="device" aria-label="Wallet display preview"><div class="device-top"><span>WALLET WELLNESS</span><span class="device-chip">DEMO</span></div><div class="screen" id="wallet-screen" aria-live="polite"></div><div class="device-bottom"><button id="prev" type="button" aria-label="Previous wallet screen">← Prev</button><span id="page-count" class="page-count"></span><button id="next" type="button" aria-label="Next wallet screen">Next →</button></div></div><div class="wallet-copy"><h2>One glance at a time.</h2><p>Swipe left or right on the preview, or use the arrows. The deck starts with an overview, then shows each card and account separately.</p><div class="callout"><p><strong>Browser preview only.</strong> This isn’t running on the ESP32 display yet. No bank connection or real-time purchase feed is connected.</p></div></div></div></section>
<footer class="foot"><strong>Demo data only.</strong> Not connected to a bank; not financial advice. Figures use simplified assumptions. Demo resets when the server restarts.</footer></main></div>
<div id="coach-container"><button type="button" class="coach-launch" id="coach-toggle" aria-expanded="false" aria-controls="coach-dock">Ask AI coach</button><aside id="coach-dock" class="coach-dock" aria-label="AI coach" hidden><div class="coach-head"><div><h2>AI coach</h2><p>Local model · Synthetic demo</p></div><button class="coach-close" id="coach-close" type="button" aria-label="Close AI coach">Close</button></div><div class="coach-body"><p>Ask one question at a time. For car estimates, first use the calculator in Overview.</p><form id="coach-form"><label for="question">Your question</label><textarea id="question" rows="3" maxlength="1000" required placeholder="How can I improve my budget?"></textarea><button class="btn" id="ask">Ask the coach</button></form><div class="results" id="coach-result" aria-live="polite"><p>Ollama runs on this computer. Check AI answers against the app’s calculations.</p></div><button class="btn secondary" type="button" id="coach-check">Check Ollama connection</button><p class="coach-status" id="coach-status" role="status"></p><details><summary>Sources &amp; limitations</summary><p>The coach uses the current synthetic profile, saved budget and latest car scenario. No bank is connected; not financial advice. It does not search the web live, and its answers are not automatically source-verified.</p><ul><li><a href="https://files.consumerfinance.gov/f/201508_cfpb_savings-plan-tool.pdf" target="_blank" rel="noopener noreferrer">CFPB savings worksheet</a></li><li><a href="https://www.consumerfinance.gov/owning-a-home/prepare/assess-your-spending/" target="_blank" rel="noopener noreferrer">CFPB spending guide</a></li></ul></details></div></aside></div>
<script>
const $=id=>document.getElementById(id);const usd=n=>n==null?'Not available':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);const pct=n=>n==null?'Not available':(100*n).toFixed(1)+'%';const rate=n=>n==null?'Not available':(100*n).toFixed(2)+'%';const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let state=null,slide=0;
const groups=[['Cash & savings',['checking','savings','cd']],['Retirement',['ira']],['Investments',['brokerage']],['Loans & mortgage',['auto_loan','personal_loan','mortgage']]];const debt=['credit_card','auto_loan','personal_loan','mortgage'];const desc={checking:'Checking',savings:'Savings',cd:'Certificate of deposit',ira:'Retirement',brokerage:'Brokerage',auto_loan:'Auto loan',personal_loan:'Personal loan',mortgage:'Mortgage'};
function row(name,value,sub=''){return `<div class="account-row"><div>${esc(name)}<span class="sub">${esc(sub)}</span></div><strong>${esc(value)}</strong></div>`}function pair(label,value){return `<div class="pair"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`}function wrow(label,value){return `<div class="screen-row"><span>${esc(label)}</span><b>${esc(value)}</b></div>`}
function render(s){state=s;renderBudget(s.budget);$('checking').textContent=usd(s.checking);$('cash').textContent=usd(s.liquid_cash);$('worth').textContent=usd(s.net_worth);$('emergency').textContent=s.emergency_months==null?'Unknown':s.emergency_months.toFixed(2)+' mo';$('status').textContent='Status: '+s.emergency_status;
 const accounts=s.accounts,cards=accounts.filter(a=>a.type==='credit_card');const old=$('account').value;$('account').replaceChildren();accounts.filter(a=>['checking','credit_card'].includes(a.type)).forEach(a=>{const option=document.createElement('option');option.value=a.id;option.textContent=a.name+(a.type==='credit_card'?' · credit':' · checking');$('account').appendChild(option)});if([...$('account').options].some(o=>o.value===old))$('account').value=old;
 $('cards-list').innerHTML=cards.length?cards.map(a=>{let ratio=a.credit_limit>0?a.balance/a.credit_limit:0;return `<article class="acct-card"><div class="card-face"><small>Credit · synthetic</small><div><div>${esc(a.name)}</div><strong>${esc(usd(a.balance))}</strong><small style="display:block">Balance owed</small></div></div><div class="card-info">${pair('Available credit',usd(Math.max(0,a.credit_limit-a.balance)))}${pair('Credit limit',usd(a.credit_limit))}<div class="bar"><span style="width:${Math.min(100,Math.max(0,ratio*100))}%"></span></div>${pair('Utilization',pct(ratio))}${pair('APR',rate(a.apr))}${pair('Original min. estimate',usd(a.min_payment))}</div></article>`}).join(''):'<p>No credit cards in this demo.</p>';
 $('accounts-list').innerHTML=groups.map(([name,types])=>{const rows=accounts.filter(a=>types.includes(a.type));return rows.length?`<section class="panel account-group"><h2>${esc(name)}</h2>${rows.map(a=>row(a.name,usd(a.balance),(debt.includes(a.type)?'Owed · ':'Balance · ')+(desc[a.type]||a.type))).join('')}</section>`:''}).join('');renderWallet()}
function renderWallet(){if(!state)return;let accounts=state.accounts,cards=accounts.filter(a=>a.type==='credit_card'),others=groups.flatMap(([_,types])=>accounts.filter(a=>types.includes(a.type)));const slides=[{kind:'overview'},...cards.map(a=>({kind:'card',a})),...others.map(a=>({kind:'account',a}))];slide=(slide+slides.length)%slides.length;let v=slides[slide],html='';if(v.kind==='overview'){html=`<div class="screen-kicker">Overview</div><div class="screen-title">Checking balance</div><div class="screen-number">${esc(usd(state.checking))}</div><div class="screen-note">Synthetic demo account</div><div class="screen-card"><div class="screen-card-title">Financial snapshot</div>${wrow('Liquid cash',usd(state.liquid_cash))}${wrow('Emergency fund',state.emergency_months==null?'Unknown':state.emergency_months.toFixed(2)+' mo')}${wrow('Net worth',usd(state.net_worth))}</div><div class="screen-hint">Swipe for cards and accounts</div>`}else if(v.kind==='card'){let a=v.a;html=`<div class="screen-kicker">Credit card</div><div class="screen-title">${esc(a.name)}</div><div class="screen-number">${esc(usd(a.balance))}</div><div class="screen-note">Balance owed</div><div class="screen-card"><div class="screen-card-title">Card details</div>${wrow('Available credit',usd(Math.max(0,a.credit_limit-a.balance)))}${wrow('Credit limit',usd(a.credit_limit))}${wrow('Utilization',pct(a.credit_limit>0?a.balance/a.credit_limit:null))}${wrow('APR',rate(a.apr))}</div><div class="screen-hint">Synthetic data · Not financial advice</div>`}else{let a=v.a;html=`<div class="screen-kicker">${esc(debt.includes(a.type)?'Loan & mortgage':'Account')}</div><div class="screen-title">${esc(a.name)}</div><div class="screen-number">${esc(usd(a.balance))}</div><div class="screen-note">${debt.includes(a.type)?'Balance owed':'Account balance'}</div><div class="screen-card"><div class="screen-card-title">Account details</div>${wrow('Type',desc[a.type]||a.type)}${a.apy!=null?wrow('APY',rate(a.apy)):''}${a.apr!=null?wrow('APR',rate(a.apr)):''}${a.monthly_payment!=null?wrow('Monthly payment',usd(a.monthly_payment)):''}</div><div class="screen-hint">Synthetic data · Not financial advice</div>`}$('wallet-screen').innerHTML=html;$('page-count').textContent=`${slide+1} / ${slides.length}`}
const viewText={overview:['Overview','Your money, in perspective.','A clearer picture today. More confident choices tomorrow.'],cards:['Credit cards','Know what you owe.','Each card, its balance and available credit.'],accounts:['Other accounts','Everything in its place.','Explore cash, retirement, investments, and loans.'],wallet:['Wallet preview','Your finances, in your pocket.','A compact view designed for your 320 × 480 display.'],budget:['Budget planner','A plan you can shape.','Soft limits and small steps toward your goals.']};document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{const view=button.dataset.view;setCoachAvailability(view!=='wallet');document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-selected',String(b===button)));Object.keys(viewText).forEach(id=>$("view-"+id).hidden=id!==view);[$('top-label').textContent,$('view-title').textContent,$('view-subtitle').textContent]=viewText[view]}));$('prev').onclick=()=>{slide--;renderWallet()};$('next').onclick=()=>{slide++;renderWallet()};let startX=null;$('device').addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;startX=e.clientX});$('device').addEventListener('pointerup',e=>{if(startX===null)return;let dx=e.clientX-startX;startX=null;if(Math.abs(dx)>40){slide+=dx<0?1:-1;renderWallet()}});$('device').addEventListener('pointercancel',()=>startX=null);
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(body.error||'Request failed.');return body}function msg(text,error=false){$('purchase-message').textContent=text;$('purchase-message').classList.toggle('error',error)}
$('purchase-form').addEventListener('submit',async e=>{e.preventDefault();try{const x=await post('/purchase',{amount:$('amount').value,account_id:$('account').value,category:$('purchase-category').value});render(x.after);const p=x.after.last_purchase;msg(`Simulated ${usd(p.amount)} on ${p.account_name}. ${p.account_type==='credit_card'?'Card debt increased.':'Checking balance decreased.'}`);$('scenario-result').hidden=true}catch(err){msg(err.message,true)}});$('reset').onclick=async()=>{try{render(await post('/reset',{}));slide=0;renderWallet();msg('Demo reset. No purchases yet.');$('scenario-result').hidden=true;renderBudget(null);$('limits-panel').hidden=true;$('coach-result').textContent='Demo reset.'}catch(e){msg(e.message,true)}};
$('scenario-form').addEventListener('submit',async e=>{e.preventDefault();let r=$('scenario-result');r.hidden=false;r.textContent='Calculating…';try{const x=await post('/scenario',{price:$('price').value,down:$('down').value,apr:$('apr').value,months:$('months').value});r.replaceChildren();for(const line of [`Estimated monthly payment: ${usd(x.monthly_payment)}`,`Cash after down payment: ${usd(x.cash_after_down_payment)}`,`Emergency fund after: ${x.emergency_fund_months_after==null?'Unknown':x.emergency_fund_months_after.toFixed(2)+' months'}`,`Projected negative cash within 12 months: ${x.cash_goes_negative_within_12m?'Yes':'No'}`]){const p=document.createElement('p');p.textContent=line;r.appendChild(p)}}catch(err){r.textContent=err.message}});fetch('/state').then(r=>{if(!r.ok)throw Error('Could not load demo');return r.json()}).then(s=>{render(s);renderBudget(s.budget)}).catch(()=>msg('Cannot reach the demo server. Check the terminal.',true));

const cats=['groceries','transport','dining','other'];let draft=null, expenseCounter=0;
function renderBudget(b){if(!b){$('budget-empty').hidden=false;$('budget-summary').replaceChildren();return}$('budget-empty').hidden=true;let spare=b.income-b.fixed-b.savings-Object.values(b.limits).reduce((a,x)=>a+x,0);let el=$('budget-summary');el.replaceChildren();function add(text){let p=document.createElement('p');p.className='notice';p.textContent=text;el.appendChild(p)}add('Income '+usd(b.income)+' · Bills '+usd(b.fixed)+' · Savings goal '+usd(b.savings));add('Unallocated: '+usd(Math.max(0,spare)));cats.forEach(c=>add(c[0].toUpperCase()+c.slice(1)+': '+usd(b.spent[c])+' spent of '+usd(b.limits[c])+' soft limit'+(b.spent[c]>b.limits[c]?' · Over limit':'') ));add('Savings recorded: '+usd(b.saved)+' of '+usd(b.savings)+' monthly goal'+(b.savings>0&&b.saved>=b.savings?' · Goal reached!':''));add('Only purchases simulated after the plan was saved are counted. Listed expenses are estimates, not actual purchases.');}
function invalidate(){$('budget-message').textContent='';draft=null;$('limits-panel').hidden=true;$('expense-preview').hidden=true;$('suggest-message').textContent='Inputs changed. Suggest limits again before saving.'}
function selectedMode(){return document.querySelector('input[name="budget-mode"]:checked').value}
function showMode(){let detailed=selectedMode()==='detailed';$('quick-fields').hidden=detailed;$('detailed-fields').hidden=!detailed;invalidate()}
document.querySelectorAll('input[name="budget-mode"]').forEach(e=>e.addEventListener('change',showMode));['bi','bf','bs'].forEach(id=>$(id).addEventListener('input',invalidate));
function addExpense(name='',amount='',category='bills',frequency='monthly'){
 if($('expense-list').children.length>=20){$('suggest-message').textContent='You can add up to 20 expenses.';return}
 let n=++expenseCounter, row=document.createElement('fieldset');row.className='expense-entry';row.innerHTML=`<legend>Expense ${n}</legend><div class="fields"><div><label for="en${n}">Name</label><input id="en${n}" class="expense-name" maxlength="60" placeholder="e.g. Wi-Fi"></div><div><label for="ea${n}">Amount ($)</label><input id="ea${n}" class="expense-amount" type="number" min="0" max="1000000" step="0.01" placeholder="0.00"></div><div><label for="ec${n}">Category</label><select id="ec${n}" class="expense-category"><option value="bills">Bills &amp; debt minimums</option><option value="groceries">Groceries</option><option value="transport">Transport (including gas)</option><option value="dining">Dining</option><option value="other">Other spending</option></select></div><div><label for="ef${n}">Frequency</label><select id="ef${n}" class="expense-frequency"><option value="monthly">Monthly</option><option value="weekly">Weekly</option><option value="every_two_weeks">Every two weeks</option><option value="twice_monthly">Twice a month</option><option value="yearly">Yearly</option></select></div></div><button class="btn secondary remove-expense" type="button">Remove expense</button>`;
 row.querySelector('.expense-name').value=name;row.querySelector('.expense-amount').value=amount;row.querySelector('.expense-category').value=category;row.querySelector('.expense-frequency').value=frequency;row.addEventListener('input',invalidate);row.addEventListener('change',invalidate);row.querySelector('.remove-expense').onclick=()=>{row.remove();invalidate()};$('expense-list').appendChild(row);invalidate();}
$('add-expense').onclick=()=>addExpense();addExpense('Wi-Fi','120','bills','monthly');addExpense('Gas','80','transport','weekly');$('suggest-message').textContent='';
function inputs(){return {income:$('bi').value,fixed:$('bf').value,savings:$('bs').value,mode:selectedMode(),items:[...document.querySelectorAll('.expense-entry')].map(r=>({name:r.querySelector('.expense-name').value,amount:r.querySelector('.expense-amount').value,category:r.querySelector('.expense-category').value,frequency:r.querySelector('.expense-frequency').value}))}}
function preview(p){let target=$('expense-preview');target.replaceChildren();if(p.mode!=='detailed') {target.hidden=true;return}let title=document.createElement('strong');title.textContent='Estimated monthly amounts';target.appendChild(title);if(!p.items.length){let empty=document.createElement('p');empty.textContent='No individual expenses entered.';target.appendChild(empty)}p.items.forEach(x=>{let line=document.createElement('p');line.textContent=x.name+': '+usd(x.monthly)+' / month · '+(x.category==='bills'?'Bills':x.category);target.appendChild(line)});let note=document.createElement('p');note.textContent='Bills total: '+usd(p.fixed)+'. Category estimates are already included in the suggested category limits.';target.appendChild(note);target.hidden=false}
$('suggest-form').onsubmit=async e=>{e.preventDefault();$('budget-message').textContent='';$('suggest-message').textContent='';try{const raw=inputs();draft={input:raw,proposal:await post('/budget/suggest',raw)};cats.forEach(c=>$('b'+c).value=draft.proposal.limits[c].toFixed(2));preview(draft.proposal);$('limits-panel').hidden=false;$('suggest-message').textContent='Suggestions are ready below; review and edit before saving.'}catch(err){draft=null;$('limits-panel').hidden=true;$('expense-preview').hidden=true;$('suggest-message').textContent=err.message}};
$('budget-form').onsubmit=async e=>{e.preventDefault();if(!draft)return;let limits={};cats.forEach(c=>limits[c]=$('b'+c).value);try{let b=await post('/budget/save',{...draft.input,limits,saved:$('bsaved').value});renderBudget(b);$('budget-message').textContent='Demo plan saved. You can edit and save again.'}catch(err){$('budget-message').textContent=err.message}};
function setCoachAvailability(available){$('coach-container').hidden=!available;if(!available){$('coach-dock').hidden=true;$('coach-toggle').setAttribute('aria-expanded','false')}}
function closeCoach(focus=true){$('coach-dock').hidden=true;$('coach-toggle').setAttribute('aria-expanded','false');if(focus&&!$('coach-container').hidden)$('coach-toggle').focus()}
$('coach-toggle').onclick=()=>{let opening=$('coach-dock').hidden;$('coach-dock').hidden=!opening;$('coach-toggle').setAttribute('aria-expanded',String(opening));if(opening)$('question').focus()};$('coach-close').onclick=()=>closeCoach();document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('coach-dock').hidden)closeCoach()});
$('coach-check').onclick=async()=>{let status=$('coach-status');status.textContent='Checking Ollama…';try{let response=await fetch('/coach/status');let data=await response.json();if(!response.ok)throw Error('Status check failed.');status.textContent=data.message}catch(e){status.textContent='Could not contact the app server. Check its terminal.'}};
$('coach-form').onsubmit=async e=>{e.preventDefault();let result=$('coach-result'),btn=$('ask');btn.disabled=true;result.textContent='Thinking locally… The first response can take a while.';try{let r=await post('/coach',{question:$('question').value});result.replaceChildren();let p=document.createElement('p');p.style.whiteSpace='pre-wrap';p.textContent=r.answer;let n=document.createElement('p');n.className='notice';n.textContent=r.notice;result.append(p,n)}catch(err){result.textContent=err.message}finally{btn.disabled=false}};
</script></body></html>
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Synthetic wallet wellness demo')
    parser.add_argument('--host', default='127.0.0.1', help='Listening address (default: local computer only)')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    if args.host not in ('127.0.0.1', 'localhost'): parser.error('This demo must remain local to your computer.')
    print(f'Wallet Wellness is running at http://localhost:{args.port} — press Ctrl+C to stop.', flush=True)
    try: ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt: print('\nStopped.')
