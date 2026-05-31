pragma journal_mode = wal;
pragma foreign_keys = on;

create table if not exists problem (
    id integer primary key,
    slug text unique not null,
    title text not null,
    domain text,
    background_md text,
    current_frontier_md text,
    source_path text,
    created_at text default current_timestamp,
    updated_at text default current_timestamp
);

create table if not exists theorem (
    id integer primary key,
    problem_id integer references problem(id),
    slug text not null,
    title text not null,
    statement_md text not null,
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN')),
    frontier_rank integer,
    parent_id integer references theorem(id),
    created_at text default current_timestamp,
    updated_at text default current_timestamp,
    unique(problem_id, slug)
);

create table if not exists definition (
    id integer primary key,
    problem_id integer not null references problem(id),
    name text not null,
    statement_md text not null,
    created_at text default current_timestamp
);

create table if not exists claim (
    id integer primary key,
    theorem_id integer references theorem(id),
    problem_id integer references problem(id),
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN')),
    claim_md text not null,
    proof_sketch_md text,
    dependencies_md text,
    created_at text default current_timestamp
);

create table if not exists strategy (
    id integer primary key,
    slug text unique not null,
    name text not null,
    rank integer,
    status text not null default 'ACTIVE',
    score real default 0,
    description_md text not null,
    config_json text,
    created_at text default current_timestamp,
    updated_at text default current_timestamp
);

create table if not exists attempt (
    id integer primary key,
    problem_id integer references problem(id),
    theorem_id integer references theorem(id),
    strategy_id integer references strategy(id),
    run_id text not null,
    iteration integer,
    prompt_md text not null,
    result_md text not null,
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN')),
    created_at text default current_timestamp
);

create table if not exists falsification (
    id integer primary key,
    problem_id integer references problem(id),
    theorem_id integer references theorem(id),
    strategy_id integer references strategy(id),
    obstruction_md text not null,
    counterexample_md text,
    severity text check(severity in ('LOW','MEDIUM','HIGH','KILLS_STRATEGY')) default 'MEDIUM',
    created_at text default current_timestamp
);

create table if not exists computation (
    id integer primary key,
    problem_id integer references problem(id),
    theorem_id integer references theorem(id),
    run_id text not null,
    iteration integer,
    name text not null,
    code_path text,
    data_path text,
    report_path text,
    summary_json text,
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN')),
    created_at text default current_timestamp
);

create table if not exists formalization_job (
    id integer primary key,
    problem_id integer references problem(id),
    theorem_id integer references theorem(id),
    backend text not null check(backend in ('LEAN_LOCAL','ARISTOTLE_CLI','ARISTOTLE_API','OTHER')),
    lean_path text,
    prompt_md text,
    result_md text,
    status text not null check(status in ('QUEUED','RUNNING','VERIFIED','FAILED','SKIPPED')),
    created_at text default current_timestamp,
    updated_at text default current_timestamp
);

create table if not exists dependency (
    id integer primary key,
    problem_id integer references problem(id),
    from_theorem_id integer references theorem(id),
    to_theorem_id integer references theorem(id),
    relation text not null,
    notes_md text,
    created_at text default current_timestamp
);

create table if not exists artifact (
    id integer primary key,
    problem_id integer references problem(id),
    theorem_id integer references theorem(id),
    attempt_id integer references attempt(id),
    kind text not null,
    path text not null,
    sha256 text,
    description_md text,
    created_at text default current_timestamp
);

create table if not exists tag (
    id integer primary key,
    name text unique not null
);

create table if not exists theorem_tag (
    theorem_id integer not null references theorem(id),
    tag_id integer not null references tag(id),
    primary key(theorem_id, tag_id)
);

create table if not exists run_log (
    id integer primary key,
    problem_id integer references problem(id),
    run_id text not null,
    iteration integer,
    event_type text not null,
    event_json text,
    created_at text default current_timestamp
);
