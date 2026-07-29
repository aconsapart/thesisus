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
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
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
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
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
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
    created_at text default current_timestamp
);

create table if not exists falsification (
    id integer primary key,
    problem_id integer references problem(id),
    theorem_id integer references theorem(id),
    strategy_id integer references strategy(id),
    run_id text,
    iteration integer,
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
    status text not null check(status in ('PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED')),
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

-- A conjecture is the refutable counterpart of a theorem: a universally
-- quantified claim carrying a machine-checkable predicate and declared variable
-- domains, so that a counterexample search can act on it directly.
create table if not exists conjecture (
    id integer primary key,
    problem_id integer references problem(id),
    slug text not null,
    statement_md text not null,
    quantifier text not null default 'FORALL',
    predicate text not null,
    variables_json text,
    assumptions_json text,
    targets_json text,
    status text not null check(status in ('OPEN','FALSIFIED','VERIFIED_EXHAUSTIVE','CONTESTED','PROVED')) default 'OPEN',
    space_size integer,
    notes_md text,
    created_at text default current_timestamp,
    updated_at text default current_timestamp,
    unique(problem_id, slug)
);

-- A counterexample is a concrete witness plus the record of how it was checked.
-- `verification` is the load-bearing column: VERIFIED_EXACT means two
-- independent evaluators agreed, and nothing weaker may be cited as a
-- refutation without saying so.
create table if not exists counterexample (
    id integer primary key,
    problem_id integer references problem(id),
    conjecture_id integer references conjecture(id),
    theorem_id integer references theorem(id),
    strategy_id integer references strategy(id),
    falsification_id integer references falsification(id),
    run_id text,
    iteration integer,
    source text not null check(source in ('AUTO_SEARCH','LLM_LANE','MANUAL','CAS')) default 'AUTO_SEARCH',
    witness_json text not null,
    witness_md text,
    verification text not null check(verification in ('VERIFIED_EXACT','VERIFIED_SINGLE','CONTESTED','REJECTED','UNCHECKED')) default 'UNCHECKED',
    verifier_notes_md text,
    rationale_md text,
    minimal integer not null default 0,
    created_at text default current_timestamp,
    unique(conjecture_id, witness_json)
);

create index if not exists idx_counterexample_verification on counterexample(verification);
create index if not exists idx_conjecture_status on conjecture(status);

-- A claim is a separately attackable contribution -- the unit prior art can
-- kill. Distinct from `theorem` (which may be true and already known) and from
-- `conjecture` (which may be novel and false).
create table if not exists claim_contribution (
    id integer primary key,
    problem_id integer references problem(id),
    slug text not null,
    statement_md text not null,
    kind text not null default 'CONTRIBUTION',
    novelty_basis_md text,
    status text not null check(status in ('KILLED','WOUNDED','CLEAR','UNDER_SEARCHED')) default 'UNDER_SEARCHED',
    passes_searched integer default 0,
    angles_covered_json text,
    missing_angles_json text,
    negative_queries integer default 0,
    reasons_md text,
    overclaims_json text,
    surgery_required integer not null default 0,
    created_at text default current_timestamp,
    updated_at text default current_timestamp,
    unique(problem_id, slug)
);

-- One sweep of the literature. Two passes must differ in phrasing or engine to
-- count as independent; re-running one query twice is one search.
create table if not exists prior_art_pass (
    id integer primary key,
    problem_id integer references problem(id),
    run_id text,
    iteration integer,
    slug text not null,
    phrasing text,
    engine text,
    angle text,
    notes_md text,
    created_at text default current_timestamp,
    unique(problem_id, run_id, slug)
);

-- The search log. A query with results = 0 is a negative search, and negative
-- searches are the only evidence that can earn a CLEAR verdict.
create table if not exists prior_art_query (
    id integer primary key,
    pass_id integer references prior_art_pass(id),
    problem_id integer references problem(id),
    query_text text not null,
    angle text,
    engine text,
    results integer not null default 0,
    notes_md text,
    created_at text default current_timestamp
);

-- A piece of prior art aimed at a specific claim.
create table if not exists prior_art_threat (
    id integer primary key,
    problem_id integer references problem(id),
    claim_id integer references claim_contribution(id),
    pass_id integer references prior_art_pass(id),
    verdict text not null check(verdict in ('KILLS','WOUNDS','ADJACENT','BACKGROUND')),
    source text not null,
    locator text,
    angle text,
    evidence_md text,
    created_at text default current_timestamp,
    unique(claim_id, source, locator)
);

create index if not exists idx_claim_status on claim_contribution(status);
create index if not exists idx_threat_verdict on prior_art_threat(verdict);

-- The claims board: what survives, what needs surgery, what has not been
-- searched hard enough to say either way.
create view if not exists v_claim_board as
select c.slug,
       c.status,
       c.statement_md,
       c.passes_searched,
       c.negative_queries,
       c.surgery_required,
       (select count(*) from prior_art_threat t
         where t.claim_id = c.id and t.verdict = 'KILLS') as kills,
       (select count(*) from prior_art_threat t
         where t.claim_id = c.id and t.verdict = 'WOUNDS') as wounds,
       (select count(*) from prior_art_threat t
         where t.claim_id = c.id and t.verdict = 'ADJACENT') as adjacent,
       c.updated_at
from claim_contribution c
order by case c.status
             when 'KILLED' then 0
             when 'WOUNDED' then 1
             when 'UNDER_SEARCHED' then 2
             else 3
         end,
         c.updated_at desc;

-- Everything that must be cited and distinguished, whether or not it wounds.
create view if not exists v_prior_art_threats as
select t.id, p.slug as problem, c.slug as claim, t.verdict, t.source, t.locator,
       t.angle, t.evidence_md, t.created_at
from prior_art_threat t
left join problem p on p.id = t.problem_id
left join claim_contribution c on c.id = t.claim_id
where t.verdict in ('KILLS','WOUNDS','ADJACENT')
order by case t.verdict when 'KILLS' then 0 when 'WOUNDS' then 1 else 2 end, t.created_at desc;

-- The negative search log. A CLEAR verdict with nothing here is unsupported.
create view if not exists v_negative_searches as
select q.id, p.slug as problem, ps.slug as search_pass, q.angle, q.query_text,
       q.engine, q.notes_md, q.created_at
from prior_art_query q
left join problem p on p.id = q.problem_id
left join prior_art_pass ps on ps.id = q.pass_id
where q.results = 0
order by q.created_at desc;

-- Refutations that survived independent checking.
create view if not exists v_verified_counterexamples as
select c.id,
       p.slug as problem,
       cj.slug as conjecture,
       cj.statement_md as conjecture_statement,
       c.witness_md,
       c.verification,
       c.source,
       c.minimal,
       c.iteration,
       c.created_at
from counterexample c
left join problem p on p.id = c.problem_id
left join conjecture cj on cj.id = c.conjecture_id
where c.verification in ('VERIFIED_EXACT','VERIFIED_SINGLE')
order by c.created_at desc;

-- Witnesses the evaluators disagreed on. A non-empty result here is a bug in
-- one of the evaluators and blocks any refutation claim that depends on it.
create view if not exists v_contested_counterexamples as
select c.id, p.slug as problem, cj.slug as conjecture, c.witness_md, c.verifier_notes_md, c.created_at
from counterexample c
left join problem p on p.id = c.problem_id
left join conjecture cj on cj.id = c.conjecture_id
where c.verification = 'CONTESTED'
order by c.created_at desc;

-- Proof and refutation side by side, which is the point of the refactor.
create view if not exists v_conjecture_board as
select cj.slug,
       cj.status,
       cj.statement_md,
       cj.space_size,
       (select count(*) from counterexample x
         where x.conjecture_id = cj.id and x.verification = 'VERIFIED_EXACT') as verified_counterexamples,
       (select count(*) from counterexample x
         where x.conjecture_id = cj.id and x.verification = 'CONTESTED') as contested_counterexamples,
       (select count(*) from counterexample x
         where x.conjecture_id = cj.id and x.verification = 'REJECTED') as discarded_claims,
       cj.updated_at
from conjecture cj
order by case cj.status
             when 'CONTESTED' then 0
             when 'FALSIFIED' then 1
             when 'OPEN' then 2
             else 3
         end,
         cj.updated_at desc;
