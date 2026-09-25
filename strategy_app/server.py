"""Authenticated, same-origin WSGI companion. No dependency on Flask or ML packages."""
from __future__ import annotations

import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
import hmac
from http import HTTPStatus
import io
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from .config import Config
from .contracts import canonical, fingerprint, probability, text
from .demo import DEMO_QUESTION
from .engine import Engine
from .exporting import markdown
from .store import Store, TERMINAL, now


class Busy(RuntimeError):
    pass


def validate_input(data):
    if not isinstance(data,dict): raise ValueError('A JSON object is required')
    if type(data.get('demo',False)) is not bool: raise ValueError('demo must be a boolean')
    demo=data.get('demo',False)
    mode=data.get('mode','none')
    if mode not in ('none','existing','new'): raise ValueError('Invalid simulation mode')
    question=DEMO_QUESTION if demo else text(data.get('question'),'question',3000)
    result={'question':question,'demo':demo,'mode':'none' if demo else mode}
    for field,limit in (('context',12000),('constraints',4000)):
        value=data.get(field,'')
        if not isinstance(value,str) or len(value)>limit: raise ValueError(f'{field} exceeds its text limit')
        result[field]=value
    result['threshold']=probability(data.get('threshold',.95))
    if result['threshold']<.95: raise ValueError('Acceptance threshold cannot be below 0.95')
    for field,default,upper in (('max_iterations',3,4),('rounds',12,30)):
        value=data.get(field,default)
        if type(value) is not int or not 1<=value<=upper: raise ValueError(f'{field} must be an integer in [1,{upper}]')
        result[field]=value
    evidence=data.get('evidence',[])
    if not isinstance(evidence,list) or len(evidence)>8: raise ValueError('Provide at most eight evidence records')
    result['evidence']=[{'title':text(e.get('title'),'evidence title',160),'text':text(e.get('text'),'evidence text',10000)} for e in evidence if isinstance(e,dict)]
    if len(result['evidence'])!=len(evidence): raise ValueError('Invalid evidence record')
    if sum(len(e['text']) for e in result['evidence'])>40000: raise ValueError('Evidence exceeds 40,000 characters; narrow the extracts')
    if demo:
        result.update(context='Synthetic demonstration; no real provider calls.',constraints='No external actions',evidence=[])
    elif mode=='existing':
        sid=data.get('simulation_id','')
        if not isinstance(sid,str) or not re.fullmatch(r'sim_[A-Za-z0-9_-]{1,100}',sid): raise ValueError('A valid existing simulation ID is required')
        result['simulation_id']=sid
    elif mode=='new':
        if not 8 <= len(question) <= 400:
            raise ValueError('MiroShark /ask requires a question of 8-400 characters; put details in context')
        if data.get('authorize_simulation') is not True: raise ValueError('Explicit simulation compute authorization is required')
        result['authorize_simulation']=True
    return result


def extract_document(data):
    name=text(data.get('name'),'document name',160)
    encoded=data.get('base64')
    if not isinstance(encoded,str) or len(encoded)>1_400_000: raise ValueError('Document exceeds the 1 MB upload limit')
    try: raw=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error): raise ValueError('Invalid document encoding') from None
    suffix=Path(name).suffix.lower()
    try:
        if suffix in ('.txt','.md'):
            content=raw.decode('utf-8-sig')
        elif suffix=='.docx':
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members=archive.infolist()
                if len(members)>1000 or sum(m.file_size for m in members)>8_000_000:
                    raise ValueError('DOCX uncompressed size limit exceeded')
                target=archive.getinfo('word/document.xml')
                if target.file_size>2_000_000: raise ValueError('DOCX XML size limit exceeded')
                xml=archive.read(target)
                decoded=xml.decode('utf-8-sig')
                if '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper(): raise ValueError('DTD/entity declarations are not accepted')
                root=ET.fromstring(xml)
                ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                content='\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p',ns))
        else:
            raise ValueError('Use UTF-8 TXT, Markdown, DOCX, or paste an extract. PDF/image OCR is not included.')
    except (UnicodeDecodeError,zipfile.BadZipFile,KeyError,ET.ParseError):
        raise ValueError('Document could not be read') from None
    return {'title':name,'text':text(content,'document text',10000)}


class Scheduler:
    def __init__(self,store,config):
        self.store,self.config=store,config
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='strategy')
        self.active=set(); self.lock=threading.RLock()

    def start(self,identifier,method):
        with self.lock:
            if identifier in self.active: return
            if len(self.active)>=4: raise Busy('Queue is full; try after a current analysis finishes')
            self.active.add(identifier)
            def work():
                try: getattr(Engine(self.store,config=self.config),method)(identifier)
                finally:
                    with self.lock: self.active.discard(identifier)
            self.pool.submit(work)

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True)


class Application:
    def __init__(self,config):
        self.config=config
        directory=Path(config.data_dir)
        directory.mkdir(parents=True,exist_ok=True); os.chmod(directory,0o700)
        # Hold an OS lease before recovering jobs: another process may still
        # be executing them. Process exit releases the lease, including crashes.
        lock_path=directory/'.instance.lock'
        self._instance_lock=lock_path.open('a+b')
        os.chmod(lock_path,0o600)
        try:
            if os.name=='nt':
                import msvcrt
                if lock_path.stat().st_size==0:
                    self._instance_lock.write(b'0'); self._instance_lock.flush()
                self._instance_lock.seek(0)
                msvcrt.locking(self._instance_lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self._instance_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self._instance_lock.close()
            raise RuntimeError('Another strategy workspace is using this data directory') from None
        try:
            self.store=Store(directory/'strategy.sqlite3')
            self.store.recover_interrupted()
            self.scheduler=Scheduler(self.store,config)
        except Exception:
            self._instance_lock.close()
            raise

    def close(self):
        self.scheduler.close()
        self._instance_lock.close()

    def __call__(self,env,start_response):
        headers=[('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),
                 ('Referrer-Policy','no-referrer'),('Content-Security-Policy',
                  "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
        def respond(value,status=200,content_type='application/json; charset=utf-8',extra=()):
            body=value if isinstance(value,bytes) else canonical(value).encode()
            start_response(f'{status} {HTTPStatus(status).phrase}',headers+[('Content-Type',content_type),('Content-Length',str(len(body))),*extra])
            return [body]
        path=env.get('PATH_INFO','/'); method=env.get('REQUEST_METHOD','GET')
        assets={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}
        if method=='GET' and path in assets:
            file=Path(__file__).parent/'static'/assets[path]
            mime={'html':'text/html','js':'text/javascript','css':'text/css'}[file.suffix[1:]]
            return respond(file.read_bytes(),content_type=mime+'; charset=utf-8')
        if method=='GET' and path=='/health': return respond({'status':'ok','service':'MiroShark Strategy'})
        if not path.startswith('/api/'): return respond({'error':'Not found'},404)
        if len(self.config.token)<24: return respond({'error':'Workspace access token is not configured (minimum 24 characters)'},503)
        given=env.get('HTTP_AUTHORIZATION','')
        if len(given)>2048 or not hmac.compare_digest(given.encode(),('Bearer '+self.config.token).encode()):
            return respond({'error':'Workspace access token required'},401)
        origin=env.get('HTTP_ORIGIN')
        if origin and (urlsplit(origin).netloc!=env.get('HTTP_HOST') or urlsplit(origin).scheme not in ('http','https')):
            return respond({'error':'Cross-origin requests are not permitted'},403)
        if env.get('HTTP_SEC_FETCH_SITE')=='cross-site': return respond({'error':'Cross-site request denied'},403)
        try:
            data={}
            if method=='POST':
                if env.get('CONTENT_TYPE','').split(';')[0]!='application/json':
                    return respond({'error':'Content-Type must be application/json'},415)
                length=int(env.get('CONTENT_LENGTH') or 0)
                if length<1 or length>1_500_000: return respond({'error':'Request body must be 1 byte to 1.5 MB'},413)
                def bad_constant(_): raise ValueError('Nonfinite JSON number')
                data=json.loads(env['wsgi.input'].read(length),parse_constant=bad_constant)
                if not isinstance(data,dict): raise ValueError('A JSON object is required')
            if path=='/api/config' and method=='GET': return respond(self.config.public())
            if path=='/api/documents' and method=='POST': return respond(extract_document(data))
            if path=='/api/runs' and method=='GET': return respond({'runs':self.store.list()})
            if path=='/api/runs' and method=='POST':
                payload=validate_input(data)
                if payload['demo'] and not self.config.demo_enabled: return respond({'error':'Demo mode is disabled'},403)
                if not payload['demo']:
                    missing=self.config.missing(payload['mode']!='none')
                    if not self.config.live_enabled or missing:
                        return respond({'error':'Live analysis is disabled or provider configuration is incomplete','missing':missing},503)
                with self.scheduler.lock:
                    if len(self.scheduler.active)>=4: raise Busy('Queue is full; retry after an analysis finishes')
                    run=self.store.create(payload,env.get('HTTP_IDEMPOTENCY_KEY',''))
                    if run['status']=='queued': self.scheduler.start(run['id'],'prepare')
                return respond(run,202)
            match=re.fullmatch(r'/api/runs/(str_[0-9a-f]{32})(?:/(approve|cancel|export|review))?',path)
            if match:
                identifier,action=match.groups(); run=self.store.get(identifier)
                if not action and method=='GET':
                    return respond({**run,'events':self.store.events(identifier)})
                if action=='approve' and method=='POST':
                    with self.scheduler.lock:
                        if identifier in self.scheduler.active:
                            raise Busy('Planner is finishing its checkpoint; retry approval shortly')
                        if len(self.scheduler.active)>=4: raise Busy('Queue is full; approval was not changed')
                        run=self.store.approve(identifier,data.get('plan_hash'))
                        self.scheduler.start(identifier,'execute')
                    return respond(run,202)
                if action=='cancel' and method=='POST': return respond(self.store.cancel(identifier))
                if action=='review' and method=='POST':
                    if run['status'] not in TERMINAL: raise ValueError('Review is available after the analysis stops')
                    if data.get('verdict') not in ('useful','needs_revision'): raise ValueError('Invalid review verdict')
                    note=data.get('note','')
                    if not isinstance(note,str) or len(note)>3000: raise ValueError('Review note exceeds its limit')
                    review={'verdict':data['verdict'],'note':note,'created_at':now(),'report_hash':fingerprint(run.get('report'))}
                    self.store.event(identifier,'human_review',review)
                    return respond(self.store.update(identifier,review=review))
                if action=='export' and method=='GET':
                    fmt=parse_qs(env.get('QUERY_STRING','')).get('format',['md'])[0]
                    if fmt not in ('md','json'): raise ValueError('Export must be md or json')
                    content=markdown(run).encode() if fmt=='md' else canonical({**run,'events':self.store.events(identifier,10000)}).encode()
                    return respond(content,content_type='text/markdown; charset=utf-8' if fmt=='md' else 'application/json',
                        extra=[('Content-Disposition',f'attachment; filename="{identifier}.{fmt}"')])
            return respond({'error':'Unknown route or method'},404)
        except Busy as exc: return respond({'error':str(exc)},429)
        except KeyError: return respond({'error':'Analysis not found'},404)
        except (ValueError,TypeError,UnicodeDecodeError) as exc: return respond({'error':str(exc)},400)
        except Exception: return respond({'error':'Internal error; no automatic replay occurred'},500)


def create_app(config=None):
    return Application(config or Config.environment())
