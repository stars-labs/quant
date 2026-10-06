from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.remote_lock import RemoteLock


class RemoteLockTest(unittest.TestCase):
    def test_roundtrip_lock_channel_and_disconnect_fail_closed(self):
        original = subprocess.Popen
        requests = []
        script = "import sys; print('READY',flush=True); [print('PONG '+line[5:].strip(),flush=True) for line in sys.stdin]"
        def start(command,**options):
            requests.append(command)
            return original([sys.executable,'-u','-c',script],**options)
        owner = {'ssh':'root@example','user':'runner','home':'/private/state','executable':'/usr/bin/runner'}
        with patch('starslab_runner.remote_lock.subprocess.Popen',side_effect=start):
            lock = RemoteLock(owner,'a'*64)
        try:
            lock.check()
            self.assertIn('BatchMode=yes',requests[0])
            self.assertIn('sudo -n -H -u runner',requests[0][-1])
            lock.process.kill()
            lock.process.wait()
            with self.assertRaises(RuntimeError):
                lock.check()
        finally:
            lock.close()

    def test_partial_protocol_line_obeys_timeout(self):
        import time
        lock = RemoteLock.__new__(RemoteLock)
        lock.buffer = b''
        lock.process = subprocess.Popen([sys.executable,'-u','-c',
            "import sys,time; sys.stdout.write('REA');sys.stdout.flush();time.sleep(10)"],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            with self.assertRaises(RuntimeError):
                lock.read(.15)
            self.assertLess(time.monotonic()-started,1)
        finally:
            lock.close()
