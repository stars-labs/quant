import unittest
import ssl
from unittest.mock import patch
from urllib.error import HTTPError,URLError
from starslab_runner.reporting import signal_snapshot


class SignalRetryTests(unittest.TestCase):
    def test_transient_read_is_retried_once(self):
        for error in (TimeoutError(),URLError('temporary'),HTTPError('https://example.test',503,'busy',{},None)):
            with self.subTest(error=type(error).__name__),patch('starslab_runner.reporting.rpc',side_effect=[error,{'version':1}]) as rpc,patch('starslab_runner.reporting.time.sleep') as sleep:
                self.assertEqual(signal_snapshot('https://example.test'),{'version':1})
                self.assertEqual(rpc.call_count,2)
                rpc.assert_called_with('https://example.test','runner_signals',{})
                sleep.assert_called_once_with(1)

    def test_second_failure_propagates(self):
        with patch('starslab_runner.reporting.rpc',side_effect=TimeoutError()) as rpc,patch('starslab_runner.reporting.time.sleep'):
            with self.assertRaises(TimeoutError):signal_snapshot('https://example.test')
            self.assertEqual(rpc.call_count,2)

    def test_auth_certificate_and_invalid_payload_fail_without_retry(self):
        for error in (HTTPError('https://example.test',401,'denied',{},None),URLError(ssl.SSLCertVerificationError()),ValueError('invalid payload')):
            with self.subTest(error=type(error).__name__),patch('starslab_runner.reporting.rpc',side_effect=error) as rpc,patch('starslab_runner.reporting.time.sleep') as sleep:
                with self.assertRaises(type(error)):signal_snapshot('https://example.test')
                self.assertEqual(rpc.call_count,1);sleep.assert_not_called()
