#!/usr/bin/env python3
"""Local synthetic financial wellness demo. Requires the PNC workshop repo."""
import argparse
import json
import math
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
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
except ImportError as e:
    print(f'Cannot load the PNC toolkit: {e}\nExpected repository: {repo}\n'
          'Set PNC_REPO to your repository folder if it is elsewhere.', file=sys.stderr)
    sys.exit(1)

customer = generate_customer(seed=42)
last_purchase = None

def get_state():
    p = build_profile(customer)
    m = compute_metrics(p)
    return {'checking': p['balances_by_type'].get('checking', 0),
            'liquid_cash': p['liquid_cash'], 'net_worth': p['net_worth'],
            'emergency_months': m['values']['emergency_fund_months'],
            'emergency_status': m['status']['emergency_fund_months'],
            'last_purchase': last_purchase}

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
        else:
            self.send(404, {'error': 'Not found'})

    def do_POST(self):
        global customer, last_purchase
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 4096: raise ValueError('Request too large.')
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict): raise ValueError('Invalid request.')
            path = urlparse(self.path).path
            if path == '/purchase':
                amount = money(data.get('amount'), 'Purchase amount')
                if amount <= 0: raise ValueError('Purchase amount must be greater than zero.')
                checking = next(a for a in customer['accounts'] if a['type'] == 'checking')
                if amount > checking['balance']: raise ValueError('Purchase exceeds the simulated checking balance.')
                before = get_state()
                checking['balance'] = round(checking['balance'] - amount, 2)
                customer['transactions'].append({'date': date.today().isoformat(), 'category': 'shopping', 'amount': -amount})
                last_purchase = amount
                self.send(200, {'before': before, 'after': get_state()})
            elif path == '/scenario':
                price, down = money(data.get('price'), 'Car price'), money(data.get('down'), 'Down payment')
                apr = number(data.get('apr'), 'APR', 0, 100)
                term = number(data.get('months'), 'Loan term', 1, 360)
                if not term.is_integer(): raise ValueError('Loan term must be a whole number of months.')
                if price <= 0: raise ValueError('Car price must be greater than zero.')
                if down > price: raise ValueError('Down payment cannot exceed the car price.')
                result = car_purchase(build_profile(customer), price, down, apr / 100, int(term))
                self.send(200, result)
            elif path == '/reset':
                customer = generate_customer(seed=42)
                last_purchase = None
                self.send(200, get_state())
            else:
                self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send(400, {'error': str(e)})

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wallet Wellness | Synthetic demo</title>
<style>
:root{color-scheme:light;--navy:#153b63;--navy2:#28587e;--accent:#1763a1;--ink:#172c45;--muted:#536b82;--bg:#f4f7fb;--surface:#fff;--line:#d8e3ee;--soft:#dcecf9}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}.layout{min-height:100vh;display:grid;grid-template-columns:216px minmax(0,1fr)}aside{background:var(--navy);color:white;padding:32px 18px;display:flex;flex-direction:column;gap:38px}.brand{display:flex;gap:12px;align-items:center;font-size:20px;font-weight:750;line-height:1.1}.brand-mark{display:grid;place-items:center;background:var(--soft);color:var(--navy);width:36px;height:36px;border-radius:9px}.brand small{display:block;font-size:10px;letter-spacing:.08em;font-weight:600;color:#c4dcf1;margin-top:3px}.nav-label{font-size:12px;color:#c4dcf1;margin:0 10px 12px;text-transform:uppercase;font-weight:700}.nav{display:grid;gap:6px}.nav a{color:#edf5fc;text-decoration:none;display:block;padding:12px;border-radius:8px}.nav a:hover,.nav a:focus-visible,.nav a.current{background:var(--navy2)}.sidebar-note{margin-top:auto;padding:16px;background:var(--navy2);border-radius:10px;font-size:14px;color:#eef6ff}.sidebar-note strong{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}.sidebar-note p{margin:0}.content{width:100%;max-width:1280px;margin:auto;padding:32px 40px 56px}.topline{display:flex;justify-content:space-between;gap:12px;align-items:center;color:var(--muted);font-weight:700;font-size:12px;letter-spacing:.04em}.pill{background:var(--soft);color:var(--navy);border-radius:100px;padding:7px 13px;font-size:12px}.intro{margin:28px 0 32px}.intro h1{margin:0 0 4px;font-size:clamp(30px,3vw,38px);line-height:1.15;letter-spacing:-.035em}.intro p,.muted{color:var(--muted);margin:0}.dashboard{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(320px,.93fr);gap:24px;align-items:start}.column{display:grid;gap:24px}.hero{background:var(--navy);color:white;border-radius:12px;padding:26px;min-height:230px;display:flex;flex-direction:column}.eyebrow{text-transform:uppercase;font-size:12px;font-weight:700;letter-spacing:.05em;color:#c4dcf1}.hero .balance{font-weight:750;letter-spacing:-.04em;font-size:clamp(34px,4vw,46px);line-height:1.1;margin:20px 0 8px}.hero p{margin:0;color:#e3f0fb}.hero .hero-foot{margin-top:auto;border-top:1px solid #547899;padding-top:14px;color:#d4e8f7;font-size:14px}.panel,.metric{background:var(--surface);border:1px solid var(--line);border-radius:12px}.panel{padding:24px}.panel h2,.snapshot h2{font-size:21px;line-height:1.25;margin:0 0 6px;letter-spacing:-.015em}.panel p{margin:0;color:var(--muted)}.section-sub{font-size:14px;margin:0 0 16px;color:var(--muted)}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.metric{padding:18px;min-height:140px}.metric-label{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase}.metric-value{font-size:clamp(19px,2vw,24px);font-weight:750;line-height:1.2;margin:14px 0 6px;overflow-wrap:anywhere}.metric-detail{font-size:14px;color:var(--muted)}label{display:block;margin:16px 0 6px;font-size:14px;font-weight:700}input{display:block;width:100%;min-height:44px;background:#f7faff;color:var(--ink);border:1px solid #bdccda;border-radius:7px;padding:9px 12px;font:inherit}button{min-height:44px;border:1px solid var(--accent);border-radius:7px;padding:10px 16px;background:var(--accent);color:white;font:inherit;font-weight:700;cursor:pointer;margin-top:16px}button:hover{background:#114d7f}.secondary{background:white;color:var(--navy);border-color:#a8bfd2;margin-top:12px}.secondary:hover{background:#edf5fc}button:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid #f3ad36;outline-offset:2px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.notice{margin-top:14px!important;color:var(--ink)!important;font-size:14px}.error{color:#ae302b!important}.results{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}.results p{margin:5px 0;color:var(--ink)}.activity{min-height:120px}.activity .notice{font-size:16px}.footer{margin-top:24px;padding:20px 24px;background:white;border:1px solid var(--line);border-radius:12px;color:var(--muted);font-size:14px}.footer strong{color:var(--ink);display:block;font-size:16px;margin-bottom:5px}.footer p{margin:0}.smallnote{font-size:14px!important;margin-top:10px!important} @media(max-width:950px){.layout{grid-template-columns:1fr}aside{padding:14px 20px;flex-direction:row;align-items:center;gap:24px}.brand small,.nav-label,.sidebar-note{display:none}.nav{display:flex;gap:4px;flex-wrap:wrap}.nav a{padding:10px}.content{padding:26px 24px 48px}}@media(max-width:700px){.dashboard{grid-template-columns:1fr}.content{padding:24px 16px 40px}.intro{margin:24px 0}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric:last-child{grid-column:1/-1}.hero{min-height:200px}.panel{padding:20px}.nav{font-size:14px}.topline{font-size:11px}}@media(max-width:400px){aside{align-items:flex-start;gap:10px;flex-direction:column}.fields{grid-template-columns:1fr}}
</style></head><body><div class="layout">
<aside aria-label="Site navigation"><div class="brand"><span class="brand-mark" aria-hidden="true">W</span><span>Wallet<small>WELLNESS</small></span></div><div><div class="nav-label">Your space</div><nav class="nav"><a class="current" href="#overview">Overview</a><a href="#purchase">Simulate purchase</a><a href="#scenario">What-if simulator</a></nav></div><div class="sidebar-note"><strong>Synthetic data</strong><p>A safe space to explore decisions. No bank connected.</p></div></aside>
<main class="content" id="overview"><div class="topline"><span>FINANCIAL WELLNESS / OVERVIEW</span><span class="pill">SIMULATED</span></div><header class="intro"><h1>Your money, in perspective.</h1><p>A clearer picture today. More confident choices tomorrow.</p></header>
<div class="dashboard"><div class="column">
<section class="hero" aria-label="Checking balance"><span class="eyebrow">Your checking balance</span><div class="balance" id="checking">Loading…</div><p>Available in this synthetic demo</p><div class="hero-foot">Demo account · No real transactions</div></section>
<section class="snapshot" aria-label="Financial snapshot"><h2>Your financial snapshot</h2><p class="section-sub">Based on the PNC workshop toolkit</p><div class="metrics"><div class="metric"><div class="metric-label">Liquid cash</div><div class="metric-value" id="cash">—</div><div class="metric-detail">Checking + savings</div></div><div class="metric"><div class="metric-label">Emergency fund</div><div class="metric-value" id="emergency">—</div><div class="metric-detail" id="status">Estimated months</div></div><div class="metric"><div class="metric-label">Net worth</div><div class="metric-value" id="worth">—</div><div class="metric-detail">Assets minus debts</div></div></div></section>
<section class="panel activity"><h2>Recent activity</h2><p>Latest simulated purchase</p><p class="notice" id="purchase-message" role="status" aria-live="polite">No purchases yet.</p><button class="secondary" type="button" id="reset">Reset demo</button></section></div>
<div class="column"><section class="panel" id="purchase"><h2>Try a purchase</h2><p>See the effect on your finances before spending.</p><form id="purchase-form"><label for="amount">Purchase amount ($)</label><input id="amount" type="number" min="0.01" max="1000000" step="0.01" value="25.00" required><button type="submit">Simulate purchase</button></form><p class="smallnote">Updates the demo—not your real account.</p></section>
<section class="panel" id="scenario"><h2>What if I buy a car?</h2><p>Estimate the effect of a loan without changing your balances.</p><form id="scenario-form"><div class="fields"><div><label for="price">Car price ($)</label><input id="price" type="number" min="0.01" max="1000000" step="0.01" value="30000" required></div><div><label for="down">Down payment ($)</label><input id="down" type="number" min="0" max="1000000" step="0.01" value="5000" required></div><div><label for="apr">APR (%)</label><input id="apr" type="number" min="0" max="100" step="0.01" value="7" required></div><div><label for="months">Loan term (months)</label><input id="months" type="number" min="1" max="360" step="1" value="60" required></div></div><button type="submit">Calculate scenario</button></form><div class="results" id="scenario-result" aria-live="polite" hidden></div></section></div></div>
<footer class="footer"><strong>Numbers first. Guidance second.</strong><p>Demo data only. Not connected to a bank and not financial advice. Estimates use simplified assumptions. Data resets when the server restarts. The AI coach and wallet LCD are not connected yet.</p></footer>
</main></div><script>
const el=id=>document.getElementById(id); const usd=n=>n==null?'Not available':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
function render(s){el('checking').textContent=usd(s.checking);el('cash').textContent=usd(s.liquid_cash);el('worth').textContent=usd(s.net_worth);el('emergency').textContent=s.emergency_months==null?'Unknown':s.emergency_months.toFixed(2)+' mo';el('status').textContent='Status: '+s.emergency_status;}
async function getState(){const r=await fetch('/state');if(!r.ok)throw Error('Could not load the demo.');render(await r.json())}
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(body.error||'Request failed.');return body}
function msg(id,text,error=false){el(id).textContent=text;el(id).classList.toggle('error',error)}
el('purchase-form').addEventListener('submit',async e=>{e.preventDefault();try{const x=await post('/purchase',{amount:el('amount').value});render(x.after);msg('purchase-message',`Simulated ${usd(x.after.last_purchase)} purchase. Checking: ${usd(x.before.checking)} → ${usd(x.after.checking)}.`);el('scenario-result').hidden=true;}catch(err){msg('purchase-message',err.message,true)}});
el('reset').addEventListener('click',async()=>{try{const s=await post('/reset',{});render(s);msg('purchase-message','Demo reset. No purchases yet.');el('scenario-result').hidden=true}catch(err){msg('purchase-message',err.message,true)}});
el('scenario-form').addEventListener('submit',async e=>{e.preventDefault();let result=el('scenario-result');result.hidden=false;result.textContent='Calculating…';try{const x=await post('/scenario',{price:el('price').value,down:el('down').value,apr:el('apr').value,months:el('months').value});result.replaceChildren();for(const line of [`Estimated monthly payment: ${usd(x.monthly_payment)}`,`Cash after down payment: ${usd(x.cash_after_down_payment)}`,`Emergency fund after: ${x.emergency_fund_months_after==null?'Unknown':x.emergency_fund_months_after.toFixed(2)+' months'}`,`Projected negative cash within 12 months: ${x.cash_goes_negative_within_12m?'Yes':'No'}`]){const p=document.createElement('p');p.textContent=line;result.appendChild(p)}}catch(err){result.textContent=err.message}});
getState().catch(()=>msg('purchase-message','Cannot reach the demo server. Check the terminal.',true));
</script></body></html>'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Synthetic wallet wellness demo')
    parser.add_argument('--host', default='127.0.0.1', help='Listening address (default: local computer only)')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    print(f'Wallet Wellness is running at http://localhost:{args.port} — press Ctrl+C to stop.', flush=True)
    try: HTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt: print('\nStopped.')
