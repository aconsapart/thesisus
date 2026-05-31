PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS theorem (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    statement_md TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    kind TEXT NOT NULL DEFAULT 'THEOREM',
    frontier_rank INTEGER,
    is_frontier INTEGER NOT NULL DEFAULT 0,
    importance INTEGER NOT NULL DEFAULT 3,
    parent_id INTEGER REFERENCES theorem(id),
    confidence REAL DEFAULT 0.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS theorem_relation (
    id INTEGER PRIMARY KEY,
    source_theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE,
    target_theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'DEPENDS_ON',
    note_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_theorem_id, target_theorem_id, relation_type)
);
CREATE TABLE IF NOT EXISTS claim (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    claim_md TEXT NOT NULL,
    proof_sketch_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS strategy (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description_md TEXT NOT NULL,
    rank INTEGER,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS attempt (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    strategy_id INTEGER REFERENCES strategy(id) ON DELETE SET NULL,
    run_id TEXT NOT NULL,
    title TEXT,
    prompt_md TEXT NOT NULL,
    result_md TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS falsification (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    strategy_id INTEGER REFERENCES strategy(id) ON DELETE SET NULL,
    obstruction_md TEXT NOT NULL,
    counterexample_md TEXT,
    severity TEXT CHECK (severity IN ('LOW','MEDIUM','HIGH','KILLS_STRATEGY')) DEFAULT 'MEDIUM',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS computation (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    code_path TEXT,
    data_path TEXT,
    report_path TEXT,
    summary_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS formalization_job (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    backend TEXT NOT NULL,
    status TEXT NOT NULL,
    lean_path TEXT,
    prompt_md TEXT,
    result_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS artifact (
    id INTEGER PRIMARY KEY,
    theorem_id INTEGER REFERENCES theorem(id) ON DELETE SET NULL,
    attempt_id INTEGER REFERENCES attempt(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    description_md TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tag (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT);
CREATE TABLE IF NOT EXISTS theorem_tag (theorem_id INTEGER NOT NULL REFERENCES theorem(id) ON DELETE CASCADE, tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE, PRIMARY KEY(theorem_id, tag_id));
CREATE VIEW IF NOT EXISTS v_current_frontier AS SELECT id, slug, title, status, kind, frontier_rank, importance, updated_at FROM theorem WHERE is_frontier=1 ORDER BY frontier_rank ASC, importance DESC;
CREATE VIEW IF NOT EXISTS v_status_counts AS SELECT status, count(*) count FROM theorem GROUP BY status;
CREATE VIEW IF NOT EXISTS v_recent_attempts AS SELECT a.id, a.created_at, t.slug theorem, s.slug strategy, a.status, a.run_id, a.title, a.model FROM attempt a LEFT JOIN theorem t ON t.id=a.theorem_id LEFT JOIN strategy s ON s.id=a.strategy_id ORDER BY a.created_at DESC;
CREATE VIEW IF NOT EXISTS v_strategy_health AS SELECT s.id, s.slug, s.name, s.status, s.rank, s.score, count(a.id) attempts, sum(case when a.status='PROVED' then 1 else 0 end) proved_attempts, sum(case when a.status='FAILED/OPEN' then 1 else 0 end) open_attempts FROM strategy s LEFT JOIN attempt a ON a.strategy_id=s.id GROUP BY s.id;
CREATE VIEW IF NOT EXISTS v_dependency_edges AS SELECT tr.id, src.slug theorem, tr.relation_type, tgt.slug depends_on, tr.note_md FROM theorem_relation tr JOIN theorem src ON src.id=tr.source_theorem_id JOIN theorem tgt ON tgt.id=tr.target_theorem_id;
