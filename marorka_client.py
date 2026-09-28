"""Marorka Weather Routing client. No credentials are written to disk."""
import json
import re
import time
import requests
from requests.auth import AuthBase

BASE_URL = 'https://am-api-gateway.northeu-prod-001.ascenzmarorka.com'


class ExplicitAuth(AuthBase):
    """Prevent .netrc Basic credentials overriding the documented headers."""
    def __call__(self, request):
        return request


class APIError(Exception):
    def __init__(self, stage, status, message, diagnostics=None):
        self.stage, self.status = stage, status
        self.diagnostics = diagnostics
        super().__init__(f'{stage}: ' + (f'HTTP {status}. ' if status else '') + message)


# Only known schema labels are shown. Arbitrary keys can themselves contain secrets.
_SCHEMA_KEYS = {
    'access_token', 'accessToken', 'AccessToken', 'token', 'Token', 'bearerToken',
    'refresh_token', 'refreshToken', 'id_token', 'token_type', 'tokenType',
    'expires_in', 'expiresIn', 'expires', 'expiration', 'expires_at',
    'data', 'Data', 'result', 'Result', 'response', 'Response', 'body',
    'auth', 'authentication', 'value', 'Value', 'payload',
    'success', 'Success', 'status', 'statusCode', 'code', 'error', 'errors',
    'message', 'Message', 'detail', 'title', 'error_description',
    'username', 'password', 'email', 'user', 'name', 'roles', 'scope',
}


def response_structure(value, depth=0):
    """Schema only: never return response scalar values or arbitrary key text."""
    if depth >= 8:
        return {'type': type(value).__name__, 'truncated': True}
    if isinstance(value, dict):
        fields = []
        for i, (key, item) in enumerate(value.items()):
            if i >= 50:
                break
            fields.append({'field': key if key in _SCHEMA_KEYS else f'[unrecognized field {i + 1}]',
                           'schema': response_structure(item, depth + 1)})
        return {'type': 'object', 'fields': fields, 'truncated': len(value) > 50}
    if isinstance(value, list):
        return {'type': 'array', 'sample_items': [response_structure(v, depth + 1) for v in value[:3]],
                'truncated': len(value) > 3}
    if isinstance(value, str):
        return {'type': 'string', 'empty_or_whitespace': not bool(value.strip()), 'value': '[HIDDEN]'}
    return {'type': 'null' if value is None else type(value).__name__, 'value': '[HIDDEN]'}


class MarorkaClient:
    def __init__(self, username, password):
        self.username = username.strip()
        self.password = password  # Preserve password exactly, including whitespace.
        self.token = None
        self.expires_at = None
        self.auth_diagnostics = None
        self.session = requests.Session()
        self.session.auth = ExplicitAuth()

    def close(self):
        self.session.close()
        self.password = self.token = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _safe_message(self, value):
        text = str(value)
        for secret in (self.password, self.token, self.username):
            if secret:
                text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'(?i)bearer\s+\S+', 'Bearer [REDACTED]', text)
        text = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', text)
        # Avoid reflecting embedded credentials or token-shaped diagnostics.
        if re.search(r'(?i)(password|access_token|refresh_token|id_token|authorization)\s*[=:]', text):
            return 'Server diagnostic omitted because it may contain credentials.'
        return text[:700]

    def _request(self, method, path, stage, **kwargs):
        try:
            response = self.session.request(
                method, BASE_URL + path, timeout=(15, 90),
                allow_redirects=False, **kwargs)
        except requests.exceptions.SSLError:
            raise APIError(stage, None, 'TLS certificate verification failed. Check your network/IT configuration; verification remains enabled.') from None
        except requests.exceptions.Timeout:
            raise APIError(stage, None, 'Connection or response timed out.') from None
        except requests.exceptions.RequestException as exc:
            raise APIError(stage, None, f'Network request failed ({type(exc).__name__}).') from None
        auth_request = stage == 'Token request'
        if auth_request:
            try:
                schema = response_structure(response.json())
            except ValueError:
                schema = {'type': 'non-JSON', 'body': '[HIDDEN]'}
            content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
            self.auth_diagnostics = {
                'diagnostic_version': 2,
                'endpoint': '/api/auth/online/token',
                'http_status': response.status_code,
                'content_type': content_type if content_type in (
                    'application/json', 'application/problem+json', 'text/plain', 'text/html'
                ) else 'other or absent',
                'response_structure': schema,
                'note': 'All scalar values and unrecognized field names are hidden. HTTP success alone does not confirm authentication.',
            }
        if not 200 <= response.status_code < 300:
            explanation = {
                401: 'Authentication was rejected. This does not identify whether credentials, account configuration, or the authentication environment caused it.',
                403: 'Access was refused. Verify permissions with the provider.',
                404: 'Resource not found; this alone does not establish that no approved plan exists.',
                429: 'Rate limit reached. Stop and retry later.'
            }.get(response.status_code, 'The API returned an unsuccessful response.')
            if 300 <= response.status_code < 400:
                explanation = 'Redirect received; not followed. Confirm the documented endpoint.'
            try:
                body = response.json()
                if isinstance(body, dict) and not auth_request:
                    for key in ('message', 'error_description', 'detail'):
                        value = body.get(key)
                        if isinstance(value, str) and value:
                            explanation += ' Server message: ' + self._safe_message(value)
                            break
            except ValueError:
                pass
            raise APIError(stage, response.status_code, explanation,
                           self.auth_diagnostics if auth_request else None)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise APIError(stage, response.status_code, 'The response was not valid JSON.',
                           self.auth_diagnostics if auth_request else None) from None

    def authenticate(self):
        self.token = self.expires_at = self.auth_diagnostics = None
        if not self.username or not self.password:
            raise APIError('Token request', None, 'Username and password are required.')
        body = self._request('POST', '/api/auth/online/token', 'Token request',
                             json={'username': self.username, 'password': self.password})
        token = body.get('access_token') if isinstance(body, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise APIError('Token request', self.auth_diagnostics['http_status'],
                           'Response did not contain a nonempty top-level access_token. See the safe authentication diagnostics.',
                           self.auth_diagnostics)
        self.token = token
        self.expires_at = None
        # Only use standard expires_in when supplied; never assume a lifetime.
        try:
            lifetime = float(body.get('expires_in'))
            if lifetime > 0:
                self.expires_at = time.monotonic() + lifetime
        except (ValueError, TypeError):
            pass

    def latest_plan(self, imo):
        imo = str(imo).strip()
        if not re.fullmatch(r'[0-9]{7}', imo):
            raise APIError('Vessel input', None, 'IMO must contain exactly seven digits.')
        if self.token is None or (self.expires_at is not None and time.monotonic() >= self.expires_at - 5):
            self.authenticate()
        try:
            return self._get_plan(imo)
        except APIError as exc:
            if exc.status != 401:
                raise
            # One renewal/retry only. Never repeatedly retry rejected logins.
            self.authenticate()
            return self._get_plan(imo)

    def _get_plan(self, imo):
        return self._request('GET', '/wrs/latestapprovedpassageplan', 'Passage-plan request',
                             params={'shipimo': imo}, headers={'Authorization': 'Bearer ' + self.token})


def parse_fleet(text):
    import csv
    import io
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not reader.fieldnames or not {'ShipName', 'IMONo'}.issubset(reader.fieldnames):
        raise ValueError('CSV must have ShipName and IMONo column headers (comma-separated).')
    rows, seen = [], set()
    for row in reader:
        imo = (row.get('IMONo') or '').strip()
        name = (row.get('ShipName') or '').strip()
        if not imo and not name:
            continue
        if imo in seen and imo:
            continue
        if imo:
            seen.add(imo)
        rows.append({'ShipName': name, 'IMONo': imo})
    if not rows:
        raise ValueError('The fleet file has no vessel rows.')
    return rows


def fetch_fleet(client, rows, progress=None):
    results, stopped = [], None
    for i, row in enumerate(rows):
        result = dict(row, Status='', HTTPStatus=None, Error=None, Plan=None)
        if stopped:
            result.update(Status='Not attempted', Error=stopped)
        else:
            try:
                plan = client.latest_plan(row['IMONo'])
                empty = plan is None or plan == {} or plan == []
                result.update(Status='Empty response' if empty else 'Retrieved', Plan=plan)
            except APIError as exc:
                result.update(Status='Failed', HTTPStatus=exc.status, Error=str(exc))
                if exc.status in (401, 429) or exc.stage == 'Token request':
                    stopped = 'Stopped after authentication failure or rate limit; fix the issue before retrying.'
        results.append(result)
        if progress:
            progress(i + 1, len(rows))
    return results
