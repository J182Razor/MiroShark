"""Environment-only provider configuration; no browser-side provider secrets."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path

from .contracts import fingerprint
from .providers import HTTPTransport, JevClient, LLMClient, MiroSharkClient


def load_env(path):
    """Load literal KEY=value entries; never evaluate shell expressions."""
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'): continue
        key, separator, value = line.partition('=')
        if not separator or not key.strip().replace('_','').isalnum(): continue
        value = value.strip()
        if len(value)>1 and value[0]==value[-1] and value[0] in ('"', "'"): value=value[1:-1]
        os.environ.setdefault(key.strip(), value)


@dataclass
class Config:
    token: str = ''
    data_dir: str = 'strategy_app/.data'
    live_enabled: bool = False
    demo_enabled: bool = True
    frontier_url: str = ''
    frontier_key: str = ''
    frontier_model: str = ''
    executor_url: str = ''
    executor_key: str = ''
    executor_model: str = ''
    jev_key: str = ''
    jev_model: str = 'jev-1.13.0'
    miro_url: str = 'http://127.0.0.1:5001'
    miro_key: str = ''
    deadline_seconds: int = 1800
    model_call_limit: int = 80

    @classmethod
    def environment(cls):
        e = os.environ
        def pick(*keys, default=''): return next((e[k] for k in keys if e.get(k)), default)
        return cls(token=pick('STRATEGY_ACCESS_TOKEN'), data_dir=pick('STRATEGY_DATA_DIR',default='strategy_app/.data'),
            live_enabled=pick('STRATEGY_LIVE_ENABLED',default='false').lower()=='true',
            demo_enabled=pick('STRATEGY_DEMO_ENABLED',default='true').lower()=='true',
            frontier_url=pick('STRATEGY_FRONTIER_BASE_URL','SMART_BASE_URL','LLM_BASE_URL'),
            frontier_key=pick('STRATEGY_FRONTIER_API_KEY','SMART_API_KEY','LLM_API_KEY'),
            frontier_model=pick('STRATEGY_FRONTIER_MODEL','SMART_MODEL_NAME','LLM_MODEL_NAME'),
            executor_url=pick('STRATEGY_EXECUTOR_BASE_URL','LLM_BASE_URL'),
            executor_key=pick('STRATEGY_EXECUTOR_API_KEY','LLM_API_KEY'),
            executor_model=pick('STRATEGY_EXECUTOR_MODEL','LLM_MODEL_NAME'),
            jev_key=pick('TYPESAFE_API_KEY'), jev_model=pick('JEV_MODEL', default='jev-1.13.0'),
            miro_url=pick('MIROSHARK_API_URL',default='http://127.0.0.1:5001'),
            miro_key=pick('MIROSHARK_INTERNAL_KEY'))

    def missing(self, simulation=False):
        fields = {'frontier endpoint':self.frontier_url,'frontier API key':self.frontier_key,
                  'frontier model':self.frontier_model,'executor endpoint':self.executor_url,
                  'executor API key':self.executor_key,'executor model':self.executor_model,
                  'TYPESAFE_API_KEY':self.jev_key}
        if simulation: fields['MIROSHARK_INTERNAL_KEY']=self.miro_key
        return [key for key, value in fields.items() if not value]

    def public(self):
        return {'live_enabled':self.live_enabled,'demo_enabled':self.demo_enabled,
                'missing':self.missing(), 'simulation_missing':self.missing(True),
                'models':{'frontier':self.frontier_model or 'Not configured',
                          'executor':self.executor_model or 'Not configured','jev':self.jev_model},
                'calibration_status':'unvalidated', 'threshold':.95}


class Clients:
    def __init__(self, config, before, observed, check):
        wire = HTTPTransport(before, observed)
        self.frontier = LLMClient(config.frontier_url,config.frontier_key,config.frontier_model,wire,'frontier')
        self.executor = LLMClient(config.executor_url,config.executor_key,config.executor_model,wire,'executor')
        self.jev = JevClient(config.jev_key,config.jev_model,wire)
        self.miro = MiroSharkClient(config.miro_url,config.miro_key,wire,check)
        self.identity = {'frontier':config.frontier_model,'executor':config.executor_model,'jev':config.jev_model,
                         'provider_endpoints_hash':fingerprint([config.frontier_url,config.executor_url,config.miro_url])}
