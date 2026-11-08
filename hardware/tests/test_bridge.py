import json, math, unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bridge import make_packet

class BridgeTest(unittest.TestCase):
 def state(self):
  return {'checking': 100, 'liquid_cash':200, 'net_worth':-500, 'emergency_months':None,
   'emergency_status':'risk','accounts':[{'name':'Roth IRA','type':'ira','balance':400,'secret':'DO NOT SEND'},
    {'name':'Credit','type':'credit_card','balance':50,'credit_limit':100,'apr':.24}],
    'budget':{'income':9999}, 'last_purchase':{'amount':25,'account_name':'Credit','account_type':'credit_card'}}
 def test_allowlist_order_and_null(self):
  packet=make_packet(self.state()); d=json.loads(packet)
  self.assertEqual([a['type'] for a in d['accounts']],['credit_card','ira'])
  self.assertIsNone(d['emergency_months']); self.assertNotIn(b'DO NOT SEND',packet); self.assertNotIn('budget',d)
  self.assertEqual(d['last_purchase']['amount'],25); self.assertTrue(packet.endswith(b'\n'))
 def test_nonfinite_rejected(self):
  state=self.state(); state['checking']=math.nan
  with self.assertRaises(ValueError): make_packet(state)
 def test_too_many_accounts_rejected(self):
  state=self.state(); state['accounts']*=30
  with self.assertRaises(ValueError): make_packet(state)
 def test_other_account_types_ignored(self):
  state=self.state(); state['accounts'].append({'name':'Private','type':'unknown','balance':99})
  self.assertEqual(len(json.loads(make_packet(state))['accounts']),2)
if __name__=='__main__': unittest.main()
