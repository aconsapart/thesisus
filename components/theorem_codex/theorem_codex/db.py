from __future__ import annotations
import hashlib, json, sqlite3
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / 'schema.sql'


def connect(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA journal_mode=WAL')
    return con


def init_db(db_path: str | Path) -> None:
    con = connect(db_path)
    con.executescript(SCHEMA.read_text(encoding='utf-8'))
    con.commit(); con.close()


def _id(con, table: str, slug: str) -> Optional[int]:
    row = con.execute(f'SELECT id FROM {table} WHERE slug=?', (slug,)).fetchone()
    return int(row[0]) if row else None


def theorem_id(con, slug: str) -> Optional[int]: return _id(con, 'theorem', slug)
def strategy_id(con, slug: str) -> Optional[int]: return _id(con, 'strategy', slug)


def upsert_theorem(con, slug, title, statement_md, status, kind='THEOREM', frontier_rank=None, is_frontier=False, importance=3, parent_slug=None, confidence=0.0):
    parent = theorem_id(con, parent_slug) if parent_slug else None
    row = con.execute('''INSERT INTO theorem(slug,title,statement_md,status,kind,frontier_rank,is_frontier,importance,parent_id,confidence)
        VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET title=excluded.title, statement_md=excluded.statement_md, status=excluded.status, kind=excluded.kind, frontier_rank=excluded.frontier_rank, is_frontier=excluded.is_frontier, importance=excluded.importance, parent_id=excluded.parent_id, confidence=excluded.confidence, updated_at=CURRENT_TIMESTAMP RETURNING id''',
        (slug,title,statement_md,status,kind,frontier_rank,int(is_frontier),importance,parent,confidence)).fetchone()
    con.commit(); return int(row[0])


def upsert_strategy(con, slug, name, description_md, rank=None, status='ACTIVE', score=0.0):
    row = con.execute('''INSERT INTO strategy(slug,name,description_md,rank,status,score) VALUES (?,?,?,?,?,?)
        ON CONFLICT(slug) DO UPDATE SET name=excluded.name, description_md=excluded.description_md, rank=excluded.rank, status=excluded.status, score=excluded.score, updated_at=CURRENT_TIMESTAMP RETURNING id''',
        (slug,name,description_md,rank,status,score)).fetchone()
    con.commit(); return int(row[0])


def add_claim(con, theorem_slug, status, claim_md, proof_sketch_md=None):
    tid = theorem_id(con, theorem_slug)
    if tid is None: raise ValueError(f'Unknown theorem {theorem_slug}')
    row = con.execute('INSERT INTO claim(theorem_id,status,claim_md,proof_sketch_md) VALUES (?,?,?,?) RETURNING id', (tid,status,claim_md,proof_sketch_md)).fetchone()
    con.commit(); return int(row[0])


def add_dependency(con, source_slug, target_slug, relation_type='DEPENDS_ON', note_md=None):
    source, target = theorem_id(con, source_slug), theorem_id(con, target_slug)
    if source is None or target is None: raise ValueError('Unknown theorem dependency')
    con.execute('INSERT OR IGNORE INTO theorem_relation(source_theorem_id,target_theorem_id,relation_type,note_md) VALUES (?,?,?,?)', (source,target,relation_type,note_md))
    con.commit()


def add_attempt(con, theorem_slug=None, strategy_slug=None, run_id='manual', title=None, prompt_md='', result_md='', status='FAILED/OPEN', model=None):
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    sid = strategy_id(con, strategy_slug) if strategy_slug else None
    row = con.execute('INSERT INTO attempt(theorem_id,strategy_id,run_id,title,prompt_md,result_md,status,model) VALUES (?,?,?,?,?,?,?,?) RETURNING id', (tid,sid,run_id,title,prompt_md,result_md,status,model)).fetchone()
    con.commit(); return int(row[0])


def add_falsification(con, theorem_slug=None, strategy_slug=None, obstruction_md='', counterexample_md=None, severity='MEDIUM'):
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    sid = strategy_id(con, strategy_slug) if strategy_slug else None
    row = con.execute('INSERT INTO falsification(theorem_id,strategy_id,obstruction_md,counterexample_md,severity) VALUES (?,?,?,?,?) RETURNING id', (tid,sid,obstruction_md,counterexample_md,severity)).fetchone()
    con.commit(); return int(row[0])


def add_computation(con, theorem_slug=None, run_id='manual', name='', status='COMPUTATIONAL', code_path=None, data_path=None, report_path=None, summary=None):
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    row = con.execute('INSERT INTO computation(theorem_id,run_id,name,status,code_path,data_path,report_path,summary_json) VALUES (?,?,?,?,?,?,?,?) RETURNING id', (tid,run_id,name,status,code_path,data_path,report_path,json.dumps(summary or {}))).fetchone()
    con.commit(); return int(row[0])


def add_artifact(con, path, kind='file', theorem_slug=None, attempt_id=None, description_md=None):
    tid = theorem_id(con, theorem_slug) if theorem_slug else None
    p = Path(path); sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() and p.is_file() else None
    row = con.execute('INSERT INTO artifact(theorem_id,attempt_id,kind,path,sha256,description_md) VALUES (?,?,?,?,?,?) RETURNING id', (tid,attempt_id,kind,str(path),sha,description_md)).fetchone()
    con.commit(); return int(row[0])


def add_tag(con, name, description=None):
    row = con.execute('INSERT INTO tag(name,description) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET description=excluded.description RETURNING id', (name,description)).fetchone()
    con.commit(); return int(row[0])


def link_tag(con, theorem_slug, tag_name):
    tid = theorem_id(con, theorem_slug); tag = add_tag(con, tag_name)
    if tid is None: raise ValueError(f'Unknown theorem {theorem_slug}')
    con.execute('INSERT OR IGNORE INTO theorem_tag(theorem_id,tag_id) VALUES (?,?)', (tid,tag)); con.commit()
