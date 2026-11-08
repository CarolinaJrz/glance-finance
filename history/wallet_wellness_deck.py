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
            'last_purchase': last_purchase,
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
                account_id = data.get('account_id', 'chk-1')
                account = next((a for a in customer['accounts'] if a['id'] == account_id and a['type'] in ('checking', 'credit_card')), None)
                if account is None: raise ValueError('Select an available checking account or credit card.')
                if account['type'] == 'checking' and amount > account['balance']:
                    raise ValueError('Purchase exceeds the simulated checking balance.')
                if account['type'] == 'credit_card' and amount > round(account['credit_limit'] - account['balance'], 2):
                    raise ValueError('Purchase exceeds the simulated available credit.')
                before = get_state()
                account['balance'] = round(account['balance'] + (amount if account['type'] == 'credit_card' else -amount), 2)
                customer['transactions'].append({'date': date.today().isoformat(), 'category': 'shopping', 'amount': -amount})
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
                self.send(200, result)
            elif path == '/reset':
                customer = generate_customer(seed=42)
                last_purchase = None
                self.send(200, get_state())
            else:
                self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send(400, {'error': str(e)})

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Wallet Wellness | Synthetic demo</title><style>
:root{color-scheme:light;--navy:#102e55;--ink:#142b49;--blue:#1b62a4;--muted:#506985;--line:#d8e4f1;--paper:#fff;--bg:#f2f6fb;--soft:#e4f0fb}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}button,input,select{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #edaf35;outline-offset:2px}.shell{min-height:100vh;display:grid;grid-template-columns:215px minmax(0,1fr)}.side{background:var(--navy);color:white;padding:28px 16px;display:flex;flex-direction:column;gap:36px}.brand{display:flex;align-items:center;gap:11px;font-weight:800;line-height:1.15;font-size:19px}.logo{background:#e4f0fb;color:var(--navy);border-radius:9px;width:36px;height:36px;display:grid;place-items:center}.brand small{display:block;color:#c5d9ed;font-size:10px;letter-spacing:.1em;margin-top:3px}.nav-caption{font-size:12px;color:#c5d9ed;text-transform:uppercase;font-weight:700;margin:0 12px 8px}.nav{display:grid;gap:4px}.tab{background:transparent;border:0;border-radius:8px;color:#e3eef8;text-align:left;min-height:44px;padding:10px 12px}.tab:hover,.tab[aria-selected=true]{background:#285581;color:#fff}.sidenote{margin-top:auto;background:#285581;border-radius:10px;padding:16px;font-size:14px;color:#edf6ff}.sidenote strong{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}.content{width:100%;max-width:1310px;margin:0 auto;padding:30px 38px 56px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:12px;font-weight:700;letter-spacing:.05em;color:var(--muted)}.pill{color:var(--navy);background:var(--soft);padding:6px 12px;border-radius:99px}.intro{margin:26px 0 30px}.intro h1{font-size:clamp(29px,3vw,39px);letter-spacing:-.035em;line-height:1.15;margin:0 0 6px}.intro p,.subtitle{color:var(--muted);margin:0}.cols{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.9fr);gap:22px;align-items:start}.stack{display:grid;gap:20px}.hero{background:var(--navy);color:white;border-radius:12px;padding:26px;min-height:215px;display:flex;flex-direction:column}.micro{font-size:12px;text-transform:uppercase;font-weight:700;letter-spacing:.05em;color:#c4d9ed}.hero-value{font-size:clamp(32px,4vw,46px);font-weight:750;line-height:1.1;letter-spacing:-.035em;margin:18px 0 7px}.hero p{margin:0;color:#dceaf7}.hero-footer{border-top:1px solid #4e7294;padding-top:13px;margin-top:auto;color:#dceaf7;font-size:14px}.panel,.metric,.acct-card{background:white;border:1px solid var(--line);border-radius:12px}.panel{padding:22px}.panel h2,.group-title{font-size:21px;line-height:1.25;margin:0 0 5px}.panel p{margin:0;color:var(--muted)}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:14px}.section-heading h2{font-size:21px;margin:0}.section-heading p{margin:0;color:var(--muted);font-size:14px}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.metric{padding:17px;min-height:135px}.metric .label{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase}.metric .value{font-size:clamp(18px,1.8vw,23px);font-weight:750;line-height:1.2;margin:14px 0 5px;overflow-wrap:anywhere}.metric .hint{font-size:14px;color:var(--muted)}label{display:block;font-weight:700;font-size:14px;margin:14px 0 5px}input,select{width:100%;min-height:44px;padding:9px 12px;border-radius:7px;border:1px solid #b7cadc;background:#f8fbff;color:var(--ink)}.btn{min-height:44px;border:1px solid var(--blue);border-radius:7px;background:var(--blue);color:white;font-weight:700;padding:9px 15px;margin-top:16px}.btn:hover{background:#124c81}.secondary{background:white;color:var(--navy);border-color:#a9bfd3}.secondary:hover{background:#edf5fc}.fields{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.notice{margin-top:14px!important;color:var(--ink)!important}.error{color:#a52723!important}.results{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}.results p{color:var(--ink);margin:5px 0}.foot{margin-top:24px;color:var(--muted);font-size:14px}.foot strong{color:var(--ink)}[hidden]{display:none!important}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.acct-card{overflow:hidden}.card-face{padding:20px;background:var(--navy);color:white;min-height:154px;display:flex;flex-direction:column;justify-content:space-between}.card-face small{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#d8e7f5}.card-face strong{font-size:24px;letter-spacing:-.02em}.card-info{padding:16px 20px}.pair{display:flex;justify-content:space-between;gap:12px;font-size:14px;padding:6px 0}.pair span{color:var(--muted)}.pair strong{text-align:right}.bar{height:6px;background:#dfebf6;border-radius:8px;margin:10px 0 4px;overflow:hidden}.bar span{display:block;height:100%;background:var(--blue)}.account-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.account-group{padding:20px}.account-row{display:flex;justify-content:space-between;gap:16px;border-top:1px solid var(--line);padding:13px 0}.account-row:first-of-type{margin-top:12px}.account-row .sub{font-size:13px;color:var(--muted);display:block}.account-row strong{text-align:right;white-space:nowrap}.wallet-layout{display:grid;grid-template-columns:320px minmax(0,1fr);gap:30px;align-items:start}.device{width:320px;height:480px;background:#102e55;color:#fff;border-radius:12px;overflow:hidden;display:flex;flex-direction:column;touch-action:pan-y;user-select:none}.device-top{padding:18px 20px 0;display:flex;justify-content:space-between;align-items:center;font-size:11px;font-weight:700;letter-spacing:.04em}.device-chip{background:#2a5d87;padding:5px 9px;border-radius:99px}.screen{padding:18px 20px 0;flex:1;min-height:0}.screen-kicker{color:#bbd5ed;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.screen-title{font-size:16px;margin-top:8px;color:#daeaf8}.screen-number{font-size:32px;font-weight:750;line-height:1.15;letter-spacing:-.03em;margin-top:7px;overflow-wrap:anywhere}.screen-note{font-size:13px;color:#d7e8f8;margin-top:7px}.screen-card{background:white;color:var(--ink);border-radius:10px;padding:16px;margin-top:19px}.screen-card-title{font-size:14px;font-weight:750;margin-bottom:10px}.screen-row{display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:4px 0}.screen-row span{color:#536b83}.screen-row b{text-align:right}.screen-hint{font-size:12px;color:#bfd5e8;margin-top:16px}.device-bottom{display:flex;align-items:center;justify-content:space-between;padding:0 16px 14px;gap:8px}.device-bottom button{height:42px;min-width:76px;border:1px solid #7b9ab8;border-radius:7px;background:transparent;color:white;font-weight:700;font-size:13px}.page-count{font-size:12px;color:#dceaf7}.callout{background:#e9f2fc;padding:18px;border-radius:10px;color:var(--ink);margin-top:16px}.callout p{margin:0}.wallet-copy{max-width:50ch}.wallet-copy h2{margin:0 0 8px}.wallet-copy p{color:var(--muted)}@media(max-width:1000px){.shell{grid-template-columns:1fr}.side{padding:14px 20px;gap:12px}.brand small,.nav-caption,.sidenote{display:none}.nav{display:flex;flex-wrap:wrap;gap:4px}.tab{padding:10px}.content{padding:26px 24px 48px}}@media(max-width:700px){.content{padding:24px 16px 42px}.intro{margin:24px 0}.cols,.wallet-layout{grid-template-columns:1fr}.cards{grid-template-columns:1fr}.account-grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric:last-child{grid-column:1/-1}.device{max-width:100%}.panel{padding:18px}.nav{font-size:14px}}@media(max-width:400px){.fields{grid-template-columns:1fr}.top{font-size:11px}}@media(prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
</style></head><body><div class="shell"><aside class="side"><div class="brand"><span class="logo">W</span><span>Wallet<small>WELLNESS</small></span></div><div><p class="nav-caption">Your space</p><nav class="nav" role="tablist" aria-label="Dashboard views"><button class="tab" role="tab" aria-selected="true" aria-controls="view-overview" data-view="overview">Overview</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-cards" data-view="cards">Credit cards</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-accounts" data-view="accounts">Other accounts</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-wallet" data-view="wallet">Wallet preview</button></nav></div><div class="sidenote"><strong>Synthetic data</strong>No bank connected. A safe space to explore decisions.</div></aside>
<main class="content"><div class="top"><span>FINANCIAL WELLNESS / <span id="top-label">OVERVIEW</span></span><span class="pill">SIMULATED</span></div><header class="intro"><h1 id="view-title">Your money, in perspective.</h1><p id="view-subtitle">A clearer picture today. More confident choices tomorrow.</p></header>
<section id="view-overview" role="tabpanel"><div class="cols"><div class="stack"><div class="hero"><div class="micro">Checking balance</div><div class="hero-value" id="checking">Loading…</div><p>Available in this synthetic demo</p><div class="hero-footer">Demo account · No real transactions</div></div><section><div class="section-heading"><div><h2>Your financial snapshot</h2><p>Based on the PNC workshop toolkit</p></div></div><div class="metrics"><div class="metric"><div class="label">Liquid cash</div><div class="value" id="cash">—</div><div class="hint">Checking + savings</div></div><div class="metric"><div class="label">Emergency fund</div><div class="value" id="emergency">—</div><div class="hint" id="status">Estimated months</div></div><div class="metric"><div class="label">Net worth</div><div class="value" id="worth">—</div><div class="hint">Assets minus debts</div></div></div></section><section class="panel"><h2>Recent activity</h2><p>Latest simulated purchase</p><p class="notice" id="purchase-message" role="status">No purchases yet.</p><button class="btn secondary" type="button" id="reset">Reset demo</button></section></div><div class="stack"><section class="panel"><h2>Try a purchase</h2><p>See the effect before spending.</p><form id="purchase-form"><label for="account">Pay with</label><select id="account"></select><label for="amount">Purchase amount ($)</label><input id="amount" type="number" min="0.01" max="1000000" step="0.01" value="25.00" required><button class="btn" type="submit">Simulate purchase</button></form><p class="notice" style="font-size:14px">Checking purchases reduce cash; card purchases increase debt.</p></section><section class="panel"><h2>What if I buy a car?</h2><p>Estimate a loan without changing your balances.</p><form id="scenario-form"><div class="fields"><div><label for="price">Car price ($)</label><input id="price" type="number" min="0.01" max="1000000" step="0.01" value="30000" required></div><div><label for="down">Down payment ($)</label><input id="down" type="number" min="0" max="1000000" step="0.01" value="5000" required></div><div><label for="apr">APR (%)</label><input id="apr" type="number" min="0" max="100" step="0.01" value="7" required></div><div><label for="months">Loan term (months)</label><input id="months" type="number" min="1" max="360" step="1" value="60" required></div></div><button class="btn">Calculate scenario</button></form><div class="results" id="scenario-result" aria-live="polite" hidden></div></section></div></div></section>
<section id="view-cards" role="tabpanel" hidden><div class="section-heading"><div><h2>Credit cards</h2><p>Each balance is the amount owed—not money available to spend.</p></div></div><div id="cards-list" class="cards"></div><p class="foot">Minimum payments are the starter toolkit’s original estimates; they do not recalculate after simulated purchases.</p></section>
<section id="view-accounts" role="tabpanel" hidden><div class="section-heading"><div><h2>Other accounts</h2><p>Assets and debts, grouped by their role.</p></div></div><div id="accounts-list" class="account-grid"></div></section>
<section id="view-wallet" role="tabpanel" hidden><div class="wallet-layout"><div class="device" id="device" aria-label="Wallet display preview"><div class="device-top"><span>WALLET WELLNESS</span><span class="device-chip">DEMO</span></div><div class="screen" id="wallet-screen" aria-live="polite"></div><div class="device-bottom"><button id="prev" type="button" aria-label="Previous wallet screen">← Prev</button><span id="page-count" class="page-count"></span><button id="next" type="button" aria-label="Next wallet screen">Next →</button></div></div><div class="wallet-copy"><h2>One glance at a time.</h2><p>Swipe left or right on the preview, or use the arrows. The deck starts with an overview, then shows each card and account separately.</p><div class="callout"><p><strong>Browser preview only.</strong> This isn’t running on the ESP32 display yet. No bank connection or real-time purchase feed is connected.</p></div></div></div></section>
<footer class="foot"><strong>Demo data only.</strong> Not connected to a bank; not financial advice. Figures use simplified assumptions. Demo resets when the server restarts.</footer></main></div>
<script>
const $=id=>document.getElementById(id);const usd=n=>n==null?'Not available':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);const pct=n=>n==null?'Not available':(100*n).toFixed(1)+'%';const rate=n=>n==null?'Not available':(100*n).toFixed(2)+'%';const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let state=null,slide=0;
const groups=[['Cash & savings',['checking','savings','cd']],['Retirement',['ira']],['Investments',['brokerage']],['Loans & mortgage',['auto_loan','personal_loan','mortgage']]];const debt=['credit_card','auto_loan','personal_loan','mortgage'];const desc={checking:'Checking',savings:'Savings',cd:'Certificate of deposit',ira:'Retirement',brokerage:'Brokerage',auto_loan:'Auto loan',personal_loan:'Personal loan',mortgage:'Mortgage'};
function row(name,value,sub=''){return `<div class="account-row"><div>${esc(name)}<span class="sub">${esc(sub)}</span></div><strong>${esc(value)}</strong></div>`}function pair(label,value){return `<div class="pair"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`}function wrow(label,value){return `<div class="screen-row"><span>${esc(label)}</span><b>${esc(value)}</b></div>`}
function render(s){state=s;$('checking').textContent=usd(s.checking);$('cash').textContent=usd(s.liquid_cash);$('worth').textContent=usd(s.net_worth);$('emergency').textContent=s.emergency_months==null?'Unknown':s.emergency_months.toFixed(2)+' mo';$('status').textContent='Status: '+s.emergency_status;
 const accounts=s.accounts,cards=accounts.filter(a=>a.type==='credit_card');const old=$('account').value;$('account').replaceChildren();accounts.filter(a=>['checking','credit_card'].includes(a.type)).forEach(a=>{const option=document.createElement('option');option.value=a.id;option.textContent=a.name+(a.type==='credit_card'?' · credit':' · checking');$('account').appendChild(option)});if([...$('account').options].some(o=>o.value===old))$('account').value=old;
 $('cards-list').innerHTML=cards.length?cards.map(a=>{let ratio=a.credit_limit>0?a.balance/a.credit_limit:0;return `<article class="acct-card"><div class="card-face"><small>Credit · synthetic</small><div><div>${esc(a.name)}</div><strong>${esc(usd(a.balance))}</strong><small style="display:block">Balance owed</small></div></div><div class="card-info">${pair('Available credit',usd(Math.max(0,a.credit_limit-a.balance)))}${pair('Credit limit',usd(a.credit_limit))}<div class="bar"><span style="width:${Math.min(100,Math.max(0,ratio*100))}%"></span></div>${pair('Utilization',pct(ratio))}${pair('APR',rate(a.apr))}${pair('Original min. estimate',usd(a.min_payment))}</div></article>`}).join(''):'<p>No credit cards in this demo.</p>';
 $('accounts-list').innerHTML=groups.map(([name,types])=>{const rows=accounts.filter(a=>types.includes(a.type));return rows.length?`<section class="panel account-group"><h2>${esc(name)}</h2>${rows.map(a=>row(a.name,usd(a.balance),(debt.includes(a.type)?'Owed · ':'Balance · ')+(desc[a.type]||a.type))).join('')}</section>`:''}).join('');renderWallet()}
function renderWallet(){if(!state)return;let accounts=state.accounts,cards=accounts.filter(a=>a.type==='credit_card'),others=groups.flatMap(([_,types])=>accounts.filter(a=>types.includes(a.type)));const slides=[{kind:'overview'},...cards.map(a=>({kind:'card',a})),...others.map(a=>({kind:'account',a}))];slide=(slide+slides.length)%slides.length;let v=slides[slide],html='';if(v.kind==='overview'){html=`<div class="screen-kicker">Overview</div><div class="screen-title">Checking balance</div><div class="screen-number">${esc(usd(state.checking))}</div><div class="screen-note">Synthetic demo account</div><div class="screen-card"><div class="screen-card-title">Financial snapshot</div>${wrow('Liquid cash',usd(state.liquid_cash))}${wrow('Emergency fund',state.emergency_months==null?'Unknown':state.emergency_months.toFixed(2)+' mo')}${wrow('Net worth',usd(state.net_worth))}</div><div class="screen-hint">Swipe for cards and accounts</div>`}else if(v.kind==='card'){let a=v.a;html=`<div class="screen-kicker">Credit card</div><div class="screen-title">${esc(a.name)}</div><div class="screen-number">${esc(usd(a.balance))}</div><div class="screen-note">Balance owed</div><div class="screen-card"><div class="screen-card-title">Card details</div>${wrow('Available credit',usd(Math.max(0,a.credit_limit-a.balance)))}${wrow('Credit limit',usd(a.credit_limit))}${wrow('Utilization',pct(a.credit_limit>0?a.balance/a.credit_limit:null))}${wrow('APR',rate(a.apr))}</div><div class="screen-hint">Synthetic data · Not financial advice</div>`}else{let a=v.a;html=`<div class="screen-kicker">${esc(debt.includes(a.type)?'Loan & mortgage':'Account')}</div><div class="screen-title">${esc(a.name)}</div><div class="screen-number">${esc(usd(a.balance))}</div><div class="screen-note">${debt.includes(a.type)?'Balance owed':'Account balance'}</div><div class="screen-card"><div class="screen-card-title">Account details</div>${wrow('Type',desc[a.type]||a.type)}${a.apy!=null?wrow('APY',rate(a.apy)):''}${a.apr!=null?wrow('APR',rate(a.apr)):''}${a.monthly_payment!=null?wrow('Monthly payment',usd(a.monthly_payment)):''}</div><div class="screen-hint">Synthetic data · Not financial advice</div>`}$('wallet-screen').innerHTML=html;$('page-count').textContent=`${slide+1} / ${slides.length}`}
const viewText={overview:['Overview','Your money, in perspective.','A clearer picture today. More confident choices tomorrow.'],cards:['Credit cards','Know what you owe.','Each card, its balance and available credit.'],accounts:['Other accounts','Everything in its place.','Explore cash, retirement, investments, and loans.'],wallet:['Wallet preview','Your finances, in your pocket.','A compact view designed for your 320 × 480 display.']};document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{const view=button.dataset.view;document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-selected',String(b===button)));Object.keys(viewText).forEach(id=>$("view-"+id).hidden=id!==view);[$('top-label').textContent,$('view-title').textContent,$('view-subtitle').textContent]=viewText[view]}));$('prev').onclick=()=>{slide--;renderWallet()};$('next').onclick=()=>{slide++;renderWallet()};let startX=null;$('device').addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;startX=e.clientX});$('device').addEventListener('pointerup',e=>{if(startX===null)return;let dx=e.clientX-startX;startX=null;if(Math.abs(dx)>40){slide+=dx<0?1:-1;renderWallet()}});$('device').addEventListener('pointercancel',()=>startX=null);
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(body.error||'Request failed.');return body}function msg(text,error=false){$('purchase-message').textContent=text;$('purchase-message').classList.toggle('error',error)}
$('purchase-form').addEventListener('submit',async e=>{e.preventDefault();try{const x=await post('/purchase',{amount:$('amount').value,account_id:$('account').value});render(x.after);const p=x.after.last_purchase;msg(`Simulated ${usd(p.amount)} on ${p.account_name}. ${p.account_type==='credit_card'?'Card debt increased.':'Checking balance decreased.'}`);$('scenario-result').hidden=true}catch(err){msg(err.message,true)}});$('reset').onclick=async()=>{try{render(await post('/reset',{}));slide=0;renderWallet();msg('Demo reset. No purchases yet.');$('scenario-result').hidden=true}catch(e){msg(e.message,true)}};
$('scenario-form').addEventListener('submit',async e=>{e.preventDefault();let r=$('scenario-result');r.hidden=false;r.textContent='Calculating…';try{const x=await post('/scenario',{price:$('price').value,down:$('down').value,apr:$('apr').value,months:$('months').value});r.replaceChildren();for(const line of [`Estimated monthly payment: ${usd(x.monthly_payment)}`,`Cash after down payment: ${usd(x.cash_after_down_payment)}`,`Emergency fund after: ${x.emergency_fund_months_after==null?'Unknown':x.emergency_fund_months_after.toFixed(2)+' months'}`,`Projected negative cash within 12 months: ${x.cash_goes_negative_within_12m?'Yes':'No'}`]){const p=document.createElement('p');p.textContent=line;r.appendChild(p)}}catch(err){r.textContent=err.message}});fetch('/state').then(r=>{if(!r.ok)throw Error('Could not load demo');return r.json()}).then(render).catch(()=>msg('Cannot reach the demo server. Check the terminal.',true));
</script></body></html>
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Synthetic wallet wellness demo')
    parser.add_argument('--host', default='127.0.0.1', help='Listening address (default: local computer only)')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    print(f'Wallet Wellness is running at http://localhost:{args.port} — press Ctrl+C to stop.', flush=True)
    try: HTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt: print('\nStopped.')
