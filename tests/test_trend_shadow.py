import json
import hashlib
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from trend_shadow import evaluate,replay

START=datetime(2026,10,7,17,tzinfo=timezone.utc)
PLAN={'implementation_sha256':hashlib.sha256(Path(replay.__code__.co_filename).read_bytes()).hexdigest(),'start':START.isoformat(),'assets':['BTC'],'monthly':100,'order_cap':20,'minimum':5,
      'rules':[{'name':'baseline','entry':2,'exit':1,'buffer':0}],
      'costs':[{'fee':.002,'slippage':.0005}]}


def download(directory,start,end,assets):
    directory.mkdir(exist_ok=True)
    rows=[];t=start
    while t<end:
        rows.append([int(t.timestamp()*1000),10,10,10,10]);t+=timedelta(hours=1)
    (directory/'BTC.json').write_text(json.dumps(rows))


def test_future_registration_and_immutable_plan(tmp_path):
    r=evaluate(tmp_path,PLAN,START-timedelta(minutes=1),download)
    assert r['status']=='waiting' and r['results']==[]
    with pytest.raises(ValueError): evaluate(tmp_path,{**PLAN,'monthly':200},START,download)


def test_past_registration_refused(tmp_path):
    with pytest.raises(ValueError): evaluate(tmp_path,PLAN,START,download)


def test_checkpoint_idempotence_and_prefix_preservation(tmp_path):
    evaluate(tmp_path,PLAN,START-timedelta(minutes=1),download)
    r=evaluate(tmp_path,PLAN,START+timedelta(hours=1,minutes=5),download)
    assert r['status']=='observing' and r['results'][0]['equity_usdt']==100
    def fail(*args): raise AssertionError('Repeated checkpoint fetched new prices')
    assert evaluate(tmp_path,PLAN,START+timedelta(hours=1,minutes=9),fail)==r
    def revised(directory,start,end,assets):
        download(directory,start,end,assets)
        p=directory/'BTC.json';rows=json.loads(p.read_text());rows[0][1]=11;p.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='Previously observed'):
        evaluate(tmp_path,PLAN,START+timedelta(hours=2),revised)
    assert not (tmp_path/'checkpoints'/'20261007T19.json').exists()
