"""Single-operator durable runs, approvals and append-only decision events."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .contracts import canonical, fingerprint

TERMINAL = {'completed', 'needs_review', 'failed', 'cancelled', 'interrupted'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                input_hash TEXT NOT NULL, data TEXT NOT NULL, updated TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                created TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS events_run ON events(run_id, seq);
            ''')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db: yield db
        finally: db.close()

    @staticmethod
    def valid_id(identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'str_[0-9a-f]{32}', identifier):
            raise ValueError('Invalid analysis ID')
        return identifier

    def create(self, payload, request_key):
        if not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_key):
            raise ValueError('A safe Idempotency-Key is required')
        digest = fingerprint(payload)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT input_hash, data FROM runs WHERE request_key=?', (request_key,)).fetchone()
            if existing:
                if existing[0] != digest: raise ValueError('Idempotency-Key was used for different input')
                return json.loads(existing[1])
            identifier = 'str_' + uuid.uuid4().hex
            value = {'id':identifier, 'created_at':now(), 'updated_at':now(), 'status':'queued',
                     'progress':0, 'input':payload, 'demo':payload.get('demo', False),
                     'cancel_requested':False, 'revisions':[], 'outputs':{}, 'model_requests':0,
                     'notice':'Advisory analysis. Jev acceptance scores are uncalibrated and do not predict real-world success.'}
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?)', (identifier, request_key, digest, canonical(value), now()))
            return value

    def get(self, identifier):
        self.valid_id(identifier)
        with self.connection() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (identifier,)).fetchone()
        if not row: raise KeyError('Analysis not found')
        return json.loads(row[0])

    def update(self, identifier, **changes):
        self.valid_id(identifier)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM runs WHERE id=?', (identifier,)).fetchone()
            if not row: raise KeyError('Analysis not found')
            data = json.loads(row[0])
            cancelled = data.get('cancel_requested', False)
            data.update(changes)
            if cancelled:
                data['cancel_requested'] = True
                data['status'] = 'cancelled'
            data['updated_at'] = now()
            db.execute('UPDATE runs SET data=?,updated=? WHERE id=?', (canonical(data), now(), identifier))
        return data

    def event(self, identifier, kind, data):
        with self.connection() as db:
            db.execute('INSERT INTO events(run_id,created,kind,data) VALUES (?,?,?,?)',
                       (identifier, now(), kind, canonical(data)))

    def events(self, identifier, limit=200):
        self.valid_id(identifier)
        with self.connection() as db:
            rows = db.execute('SELECT seq,created,kind,data FROM events WHERE run_id=? ORDER BY seq DESC LIMIT ?',
                              (identifier, limit)).fetchall()
            count = db.execute('SELECT COUNT(*) FROM events WHERE run_id=?', (identifier,)).fetchone()[0]
        return {'items':[{'seq':r[0], 'time':r[1], 'kind':r[2], 'data':json.loads(r[3])} for r in reversed(rows)],
                'total':count, 'truncated':count>limit}

    def list(self):
        with self.connection() as db:
            rows = db.execute('SELECT data FROM runs ORDER BY updated DESC LIMIT 100').fetchall()
        return [{'id':v['id'], 'question':v['input']['question'], 'status':v['status'],
                 'updated_at':v['updated_at'], 'demo':v['demo']} for (raw,) in rows for v in [json.loads(raw)]]

    def approve(self, identifier, plan_hash):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM runs WHERE id=?', (self.valid_id(identifier),)).fetchone()
            if not row: raise KeyError('Analysis not found')
            data = json.loads(row[0])
            if data['status'] != 'awaiting_approval' or data.get('cancel_requested'):
                raise ValueError('Analysis is not awaiting approval')
            if not plan_hash or plan_hash != data.get('plan_hash') or fingerprint(data['plan']) != plan_hash:
                raise ValueError('Plan changed; reload and review it again')
            data.update(status='queued_execution', approved_plan_hash=plan_hash, approved_at=now(), updated_at=now())
            db.execute('UPDATE runs SET data=?,updated=? WHERE id=?', (canonical(data), now(), identifier))
        self.event(identifier, 'outcome_approved', {'plan_hash':plan_hash})
        return data

    def cancel(self, identifier):
        data = self.get(identifier)
        if data['status'] in TERMINAL: return data
        return self.update(identifier, status='cancelled', cancel_requested=True,
                           message='Local analysis cancelled. Remote graph/simulation work may still be running; use its recorded ID in MiroShark to inspect or stop it.')

    def recover_interrupted(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for identifier, raw in db.execute('SELECT id,data FROM runs').fetchall():
                value = json.loads(raw)
                if value['status'] not in TERMINAL | {'awaiting_approval'}:
                    value.update(status='interrupted', updated_at=now(), message='Worker restarted. Reconcile recorded MiroShark IDs before creating a new run. No work was automatically replayed.')
                    db.execute('UPDATE runs SET data=?,updated=? WHERE id=?', (canonical(value), now(), identifier))
