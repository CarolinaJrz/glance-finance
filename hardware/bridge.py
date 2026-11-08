#!/usr/bin/env python3
"""Local synthetic app to wallet bridge. Default: read and print once; NEVER writes to USB."""
import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request

MAX_PACKET = 8000
TYPES = {'checking', 'savings', 'cd', 'ira', 'brokerage', 'credit_card', 'auto_loan', 'personal_loan', 'mortgage'}
FIELDS = ('name', 'type', 'balance', 'credit_limit', 'apr', 'apy', 'monthly_payment')

def clean_number(x):
    if x is None: return None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError('invalid numeric value')
    return x

def make_packet(state):
    if not isinstance(state, dict) or not isinstance(state.get('accounts'), list):
        raise ValueError('unexpected account data')
    out = {'version': 1}
    for key in ('checking', 'liquid_cash', 'net_worth', 'emergency_months'):
        out[key] = clean_number(state.get(key))
    out['emergency_status'] = str(state.get('emergency_status') or 'unknown')[:30]
    accounts = []
    for a in state['accounts']:
        if not isinstance(a, dict) or a.get('type') not in TYPES: continue
        item = {k: clean_number(a.get(k)) for k in FIELDS[2:] if a.get(k) is not None}
        item['name'] = str(a.get('name') or 'Account')[:36]
        item['type'] = a['type']
        accounts.append(item)
    if len(accounts) > 40: raise ValueError('more than 40 display accounts')
    # Keep the browser's order: cards first, then categorized non-card accounts.
    order = ['credit_card','checking','savings','cd','ira','brokerage','auto_loan','personal_loan','mortgage']
    out['accounts'] = sorted(accounts, key=lambda a: order.index(a['type']))
    purchase = state.get('last_purchase')
    if isinstance(purchase, dict):
        out['last_purchase'] = {'amount': clean_number(purchase.get('amount')),
                                'account_name': str(purchase.get('account_name') or '')[:36],
                                'account_type': str(purchase.get('account_type') or '')[:24]}
    else: out['last_purchase'] = None
    encoded = json.dumps(out, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
    if len(encoded) > MAX_PACKET: raise ValueError('wallet packet exceeds size limit')
    return encoded

def fetch():
    # Always use loopback: don't expose the demo or allow arbitrary URLs.
    with urllib.request.urlopen('http://127.0.0.1:5000/state', timeout=3) as response:
        return json.load(response)

def main():
    p = argparse.ArgumentParser(description='Wallet display connector. Default is safe preview, no USB writes.')
    p.add_argument('--port', help='Serial device, only after approved wallet firmware is installed')
    p.add_argument('--allow-device-write', action='store_true', help='Explicitly enable serial writes')
    args = p.parse_args()
    if bool(args.port) != bool(args.allow_device_write):
        p.error('Serial mode requires both --port and --allow-device-write. Default mode never touches the board.')
    if not args.port:
        try: sys.stdout.write(make_packet(fetch()).decode())
        except (ValueError, OSError, urllib.error.URLError) as e:
            print(f'Cannot read the local demo: {e}. Start the web app, then retry.', file=sys.stderr); return 1
        return 0
    try:
        import serial
    except ImportError:
        print('Serial mode needs pyserial; install it in your virtual environment.', file=sys.stderr); return 1
    print('Serial mode: synthetic demo only. Stop with Ctrl+C.', file=sys.stderr)
    try:
        with serial.Serial(args.port, 115200, timeout=1, write_timeout=2) as device:
            while True:
                try:
                    packet = make_packet(fetch())
                    device.write(packet)
                    device.flush()
                except (ValueError, OSError, urllib.error.URLError, serial.SerialException) as e:
                    print(f'Update failed: {e}', file=sys.stderr)
                time.sleep(1)
    except (OSError, serial.SerialException) as e:
        print(f'Cannot open display port: {e}', file=sys.stderr); return 1
    except KeyboardInterrupt:
        print('\nConnector stopped.', file=sys.stderr)
    return 0
if __name__ == '__main__': sys.exit(main())
