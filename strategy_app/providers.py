"""Native Jev, configurable text models, and the existing MiroShark HTTP API."""
from __future__ import annotations

import json
import math
import re
import time
from urllib import request, error, parse

from .contracts import canonical, probability, validate_question


class ProviderError(RuntimeError):
    """Safe operator-facing error; never includes raw upstream response bodies."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials through redirects.


def validate_base_url(url):
    url = url.rstrip('/')
    parsed = parse.urlsplit(url)
    local = parsed.hostname in ('localhost', '127.0.0.1', '::1')
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and local)) or not parsed.hostname:
        raise ValueError('Provider URL requires HTTPS, except loopback development endpoints')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Provider URL cannot contain credentials, query parameters or fragments')
    return url


class HTTPTransport:
    def __init__(self, before=None, observed=None, timeout=120, opener=None, sleep=None):
        self.before = before or (lambda provider: None)
        self.observed = observed or (lambda provider, data: None)
        self.timeout = timeout
        self.opener = opener or request.build_opener(NoRedirect())
        self.sleep = sleep or time.sleep

    def request(self, method, url, *, body=None, headers=None, form=False, safe=False, provider='miroshark'):
        headers = {'Accept': 'application/json', **(headers or {})}
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
            data = (parse.urlencode(body) if form else canonical(body)).encode()
        attempts = 3 if safe else 1
        for attempt in range(attempts):
            self.before(provider)
            started = time.monotonic()
            try:
                req = request.Request(url, data=data, headers=headers, method=method)
                with self.opener.open(req, timeout=self.timeout) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000: raise ProviderError(f'{provider}: response size limit exceeded')
                payload = json.loads(raw)
                if not isinstance(payload, dict): raise ProviderError(f'{provider}: invalid response envelope')
                self.observed(provider, {'latency_ms': round((time.monotonic()-started)*1000),
                                         'usage': payload.get('usage') or {}})
                return payload
            except error.HTTPError as exc:
                code = exc.code
                retry_after = exc.headers.get('Retry-After', '') if exc.headers else ''
                exc.close()
                self.observed(provider, {'http_status': code, 'attempt': attempt + 1})
                if safe and code in (429, 500, 502, 503, 504, 529) and attempt + 1 < attempts:
                    delay = min(float(retry_after), 10) if retry_after.isdigit() else 2 ** attempt
                    self.sleep(max(0, delay)); continue
                raise ProviderError(f'{provider}: HTTP {code}. Check credentials, configuration or provider status.') from None
            except (error.URLError, TimeoutError, OSError):
                suffix = ' Operation was not retried; reconcile any remotely created work before resubmitting.' if not safe else ''
                raise ProviderError(f'{provider}: connection or timeout error.{suffix}') from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ProviderError(f'{provider}: response is not valid JSON') from None
        raise ProviderError(f'{provider}: retry budget exhausted')


class JevClient:
    def __init__(self, api_key, model='jev-1.13.0', transport=None):
        if not api_key: raise ProviderError('TYPESAFE_API_KEY is not configured')
        self.api_key, self.model = api_key, model
        self.transport = transport or HTTPTransport()

    def decide(self, state, questions):
        if not isinstance(questions, dict) or not questions: raise ValueError('Questions are required')
        for question in questions.values(): validate_question(question)
        result = self.transport.request('POST', 'https://api.typesafe.ai/v1/systemone',
            body={'model': self.model, 'state': state, 'questions': questions},
            headers={'Authorization': f'Bearer {self.api_key}'}, safe=True, provider='jev')
        if result.get('model') != self.model: raise ProviderError('jev: returned model differs from pinned model')
        answers = result.get('answers')
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ProviderError('jev: missing or unexpected answer IDs')
        try:
            for key, question in questions.items():
                answer = answers[key]
                if not isinstance(answer, dict) or answer.get('type') != question['type']:
                    raise ValueError('Wrong answer type')
                if question['type'] == 'noul':
                    probability(answer.get('noul')); continue
                probabilities = answer.get('probabilities')
                expected = set(question['criteria']) if question['type'] == 'choice' else {str(i) for i in range(len(question['criteria']))}
                if not isinstance(probabilities, dict) or set(probabilities) != expected:
                    raise ValueError('Incomplete probability distribution')
                if abs(sum(probability(v) for v in probabilities.values()) - 1) > .01:
                    raise ValueError('Invalid probability sum')
                probability(answer.get('confidence'))
                if question['type'] == 'choice' and answer.get('choice') not in expected:
                    raise ValueError('Unknown choice')
                if question['type'] == 'score':
                    score = answer.get('score')
                    if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= len(expected)-1:
                        raise ValueError('Invalid score')
        except (ValueError, TypeError, KeyError):
            raise ProviderError('jev: malformed typed decision') from None
        return result


class LLMClient:
    def __init__(self, base_url, api_key, model, transport=None, role='frontier'):
        self.base_url = validate_base_url(base_url)
        if not api_key or not model: raise ProviderError(f'{role}: model or API key is not configured')
        self.api_key, self.model, self.role = api_key, model, role
        self.transport = transport or HTTPTransport()

    def generate(self, instructions, state):
        response = self.transport.request('POST', self.base_url + '/chat/completions', safe=True,
            provider=self.role, headers={'Authorization': f'Bearer {self.api_key}'}, body={
                'model': self.model, 'messages': [{'role':'system','content':instructions},
                    {'role':'user','content':canonical(state)}],
                'response_format': {'type':'json_object'}, 'max_tokens': 7000})
        try:
            value = json.loads(response['choices'][0]['message']['content'])
            if not isinstance(value, dict): raise ValueError()
            return value
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError(f'{self.role}: model did not return the required JSON object') from None


class MiroSharkClient:
    def __init__(self, base_url, api_key, transport=None, check=None, sleep=None):
        self.base_url = validate_base_url(base_url)
        self.api_key = api_key
        self.transport = transport or HTTPTransport()
        self.check = check or (lambda: None)
        self.sleep = sleep or time.sleep

    def api(self, method, path, body=None, form=False):
        self.check()
        response = self.transport.request(method, self.base_url + path, body=body, form=form,
            headers={'x-miroshark-internal-key': self.api_key}, safe=method=='GET', provider='miroshark')
        if response.get('success') is not True or 'data' not in response:
            raise ProviderError(f'miroshark: unsuccessful {method} {path.split("?")[0]}')
        return response['data']

    @staticmethod
    def identifier(value, prefix):
        if not isinstance(value, str) or not re.fullmatch(prefix + r'_[A-Za-z0-9_-]{1,100}', value):
            raise ProviderError('miroshark: invalid identifier')
        return value

    def wait(self, path, field, completed, emit):
        for _ in range(600):
            self.check()
            data = self.api('GET', path)
            status = data.get(field) or data.get('status')
            if status in completed: return data
            if status in ('failed', 'stopped', 'cancelled'): raise ProviderError(f'miroshark: operation {status}')
            emit('simulation_progress', {'status':status, 'current_round':data.get('current_round')})
            self.sleep(3)
        raise ProviderError('miroshark: polling limit reached; inspect the recorded simulation ID')

    def existing(self, simulation_id, emit):
        sid = self.identifier(simulation_id, 'sim')
        data = self.api('GET', f'/api/simulation/{sid}/run-status')
        if (data.get('runner_status') or data.get('status')) != 'completed':
            raise ProviderError('miroshark: an attached simulation must be completed')
        observations = self.api('GET', f'/api/simulation/{sid}/actions?limit=100&offset=0')
        serialized = canonical(observations)
        return {'id':'E_SIM', 'title':f'MiroShark run {sid}', 'kind':'simulation_observation',
                'simulation_id':sid, 'text':serialized[:24000],
                'coverage':'First 100 action records requested; not a full-run census.',
                'truncated':len(serialized)>24000}

    def new(self, question, evidence, rounds, emit):
        if type(rounds) is not int or not 1 <= rounds <= 30: raise ValueError('Rounds must be 1-30')
        seed = self.api('POST', '/api/simulation/ask', {'question': question})
        requirement = seed.get('simulation_requirement')
        background = seed.get('seed_document')
        if not isinstance(requirement, str) or not isinstance(background, str):
            raise ProviderError('miroshark: invalid scenario response')
        # Preserve the distinction inside the simulation input as well as in the final report.
        content = 'USER-SUPPLIED QUESTION AND CONTEXT\n' + question + '\n' + canonical(evidence)
        content += '\nMODEL-GENERATED SCENARIO BACKGROUND; NOT VERIFIED FACT\n' + background[:18000]
        generated = self.api('POST', '/api/graph/ontology/generate', {
            'project_name':question[:100], 'simulation_requirement':requirement,
            'additional_context':'Strategic scenario exploration. Preserve uncertainties; no real-world outcome claims.',
            'url_docs':canonical([{'title':'Strategy input and hypothetical background','url':'','text':content}])}, form=True)
        pid = self.identifier(generated.get('project_id'), 'proj')
        emit('project_created', {'project_id':pid})
        built = self.api('POST', '/api/graph/build', {'project_id':pid})
        tid = self.identifier(built.get('task_id'), 'task')
        self.wait(f'/api/graph/task/{tid}', 'status', {'completed'}, emit)
        created = self.api('POST', '/api/simulation/create', {
            'project_id':pid, 'enable_twitter':False, 'enable_reddit':True, 'enable_polymarket':False})
        sid = self.identifier(created.get('simulation_id'), 'sim')
        emit('simulation_created', {'simulation_id':sid, 'project_id':pid})
        self.api('POST', '/api/simulation/prepare', {'simulation_id':sid, 'parallel_profile_count':3})
        self.wait(f'/api/simulation/{sid}', 'status', {'ready'}, emit)
        self.api('POST', '/api/simulation/start', {'simulation_id':sid, 'platform':'reddit', 'max_rounds':rounds})
        self.wait(f'/api/simulation/{sid}/run-status', 'runner_status', {'completed'}, emit)
        return self.existing(sid, emit)
