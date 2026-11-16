"""Offline checks: python -m unittest test_diagnostics -v"""
import json
import unittest
from unittest.mock import Mock
from marorka_client import APIError, MarorkaClient, response_structure


class DiagnosticsTests(unittest.TestCase):
    def client(self, body, status=200, content_type='application/json'):
        client = MarorkaClient('private-user', 'private-password')
        response = Mock(status_code=status, content=b'body', headers={'Content-Type': content_type})
        response.json.return_value = body
        client.session.request = Mock(return_value=response)
        self.addCleanup(client.close)
        return client

    def test_documented_success_and_plan(self):
        client = self.client({'access_token': 'private-token', 'expires_in': 3600})
        client.authenticate()
        self.assertEqual(client.token, 'private-token')
        self.assertIsNotNone(client.expires_at)
        self.assertNotIn('private-token', json.dumps(client.auth_diagnostics))
        client.session.request.return_value.json.return_value = {'waypoints': []}
        self.assertEqual(client.latest_plan('1234567'), {'waypoints': []})
        self.assertEqual(client.session.request.call_args.kwargs['headers'], {'Authorization': 'Bearer private-token'})

    def test_observed_camelcase_success_and_plan(self):
        client = self.client({'accessToken': 'private-token', 'expiresIn': 3600, 'tokenType': 'Bearer'})
        client.authenticate()
        self.assertEqual(client.token, 'private-token')
        self.assertIsNotNone(client.expires_at)
        self.assertNotIn('private-token', json.dumps(client.auth_diagnostics))
        client.session.request.return_value.json.return_value = {'waypoints': []}
        self.assertEqual(client.latest_plan('1234567'), {'waypoints': []})
        self.assertEqual(client.session.request.call_args.kwargs['headers'], {'Authorization': 'Bearer private-token'})

    def test_nested_token_not_assumed(self):
        client = self.client({'data': {'accessToken': 'opaque-secret'}})
        with self.assertRaises(APIError) as caught:
            client.authenticate()
        report = json.dumps(caught.exception.diagnostics)
        self.assertIn('accessToken', report)
        self.assertNotIn('opaque-secret', report)
        self.assertIsNone(client.token)

    def test_missing_empty_and_nonobject_responses(self):
        for body in ({}, {'access_token': ''}, {'access_token': '  '}, None, [], 'opaque-token'):
            with self.subTest(body=body):
                client = self.client(body, status=201)
                with self.assertRaises(APIError) as caught:
                    client.authenticate()
                self.assertEqual(caught.exception.status, 201)
                self.assertIsNotNone(caught.exception.diagnostics)

    def test_error_responses_never_echo_values(self):
        for status in (200, 401, 403, 429):
            client = self.client({'message': 'unknown-opaque-secret', 'error': {'password': 'private-password'}}, status)
            with self.assertRaises(APIError) as caught:
                client.authenticate()
            rendered = str(caught.exception) + json.dumps(caught.exception.diagnostics)
            self.assertNotIn('unknown-opaque-secret', rendered)
            self.assertNotIn('private-password', rendered)

    def test_non_json(self):
        client = self.client(None, content_type='text/html')
        client.session.request.return_value.json.side_effect = ValueError('private body')
        with self.assertRaises(APIError) as caught:
            client.authenticate()
        self.assertEqual(caught.exception.diagnostics['response_structure']['type'], 'non-JSON')
        self.assertNotIn('private body', str(caught.exception))

    def test_schema_hides_dynamic_keys_and_all_scalars(self):
        report = json.dumps(response_structure({'private-key-secret': 987654321, 'token': 'private-token', 'data': [True, 'private-user']}))
        for secret in ('private-key-secret', '987654321', 'private-token', 'private-user'):
            self.assertNotIn(secret, report)

    def test_failed_reauthentication_clears_old_token(self):
        client = self.client({})
        client.token = 'stale-token'
        with self.assertRaises(APIError):
            client.authenticate()
        self.assertIsNone(client.token)


if __name__ == '__main__':
    unittest.main()
