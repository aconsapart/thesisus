from __future__ import annotations
import argparse, sqlite3, sys
from pathlib import Path
from typing import Any
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theorem_codex.db import connect, init_db, upsert_theorem, upsert_strategy, add_claim, add_attempt, add_falsification, add_dependency, add_computation


def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--db', default=str(ROOT / 'proof_codex.sqlite'))
    args, _ = parser.parse_known_args()
    return args

ARGS = parse_args()
DB_PATH = Path(ARGS.db)

st.set_page_config(page_title='Theorem Codex', layout='wide')


def ensure_db():
    if not DB_PATH.exists():
        init_db(DB_PATH)

@st.cache_data(ttl=2)
def q(sql: str, params: tuple[Any,...]=()) -> pd.DataFrame:
    ensure_db()
    con = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def write(fn, *args, **kwargs):
    ensure_db()
    con = connect(DB_PATH)
    try:
        out = fn(con, *args, **kwargs)
        st.cache_data.clear()
        return out
    finally:
        con.close()


def opts(table: str) -> list[str]:
    df = q(f'SELECT slug FROM {table} ORDER BY slug')
    return [''] + ([] if df.empty else df['slug'].tolist())

ensure_db()
st.title('Theorem Codex')
st.caption('SQLite theorem ledger + Datasette explorer + Streamlit dashboard')
with st.sidebar:
    st.header('Database')
    st.code(str(DB_PATH))
    if st.button('Initialize schema'):
        init_db(DB_PATH); st.success('Initialized'); st.cache_data.clear()
    page = st.radio('Page', ['Overview','Theorems','Add theorem','Claims','Attempts','Strategies','Falsifications','Dependencies','Computations','SQL','Help'])

if page == 'Overview':
    counts = q('SELECT * FROM v_status_counts')
    c1,c2,c3 = st.columns(3)
    c1.metric('Theorems', int(counts['count'].sum()) if not counts.empty else 0)
    c2.metric('Open', int(counts[counts.status.eq('FAILED/OPEN')]['count'].sum()) if not counts.empty else 0)
    c3.metric('Proved', int(counts[counts.status.eq('PROVED')]['count'].sum()) if not counts.empty else 0)
    if not counts.empty:
        st.plotly_chart(px.bar(counts, x='status', y='count', title='Theorems by status'), use_container_width=True)
    st.subheader('Current frontier')
    st.dataframe(q('SELECT * FROM v_current_frontier'), use_container_width=True)
    st.subheader('Strategy health')
    st.dataframe(q('SELECT * FROM v_strategy_health ORDER BY rank, score DESC'), use_container_width=True)
    st.subheader('Recent attempts')
    st.dataframe(q('SELECT * FROM v_recent_attempts LIMIT 25'), use_container_width=True)

elif page == 'Theorems':
    st.header('Theorem ledger')
    status = st.selectbox('Status', ['ALL','PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED'])
    search = st.text_input('Search')
    sql = 'SELECT id, slug, title, status, kind, frontier_rank, is_frontier, importance, updated_at FROM theorem'
    where=[]; params=[]
    if status!='ALL': where.append('status=?'); params.append(status)
    if search: where.append('(slug LIKE ? OR title LIKE ? OR statement_md LIKE ?)'); params += [f'%{search}%']*3
    if where: sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY frontier_rank IS NULL, frontier_rank, importance DESC, updated_at DESC'
    df = q(sql, tuple(params))
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        slug = st.selectbox('Inspect', df['slug'].tolist())
        row = q('SELECT * FROM theorem WHERE slug=?', (slug,)).iloc[0]
        st.subheader(row['title'])
        st.write({k: row[k] for k in ['status','kind','frontier_rank','is_frontier','importance','confidence','updated_at']})
        st.markdown(row['statement_md'])
        st.subheader('Claims')
        st.dataframe(q('SELECT status, claim_md, proof_sketch_md, created_at FROM claim WHERE theorem_id=? ORDER BY created_at DESC', (int(row['id']),)), use_container_width=True)
        st.subheader('Dependencies')
        st.dataframe(q('SELECT * FROM v_dependency_edges WHERE theorem=? OR depends_on=?', (slug, slug)), use_container_width=True)

elif page == 'Add theorem':
    st.header('Add/update theorem')
    with st.form('theorem'):
        slug = st.text_input('Slug')
        title = st.text_input('Title')
        statement_md = st.text_area('Statement Markdown', height=240)
        status = st.selectbox('Status', ['FAILED/OPEN','PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FALSIFIED'])
        kind = st.selectbox('Kind', ['THEOREM','LEMMA','CONJECTURE','FRONTIER','DEFINITION','COMPUTATION_TARGET'])
        rank = st.number_input('Frontier rank', min_value=0, value=0, step=1)
        is_frontier = st.checkbox('Is frontier', value=True)
        importance = st.slider('Importance', 1, 5, 3)
        parent = st.selectbox('Parent theorem', opts('theorem'))
        submit = st.form_submit_button('Save')
    if submit:
        if not slug or not title or not statement_md: st.error('Slug, title, statement required')
        else:
            write(upsert_theorem, slug=slug, title=title, statement_md=statement_md, status=status, kind=kind, frontier_rank=int(rank), is_frontier=is_frontier, importance=importance, parent_slug=parent or None)
            st.success('Saved')

elif page == 'Claims':
    st.header('Claims')
    with st.form('claim'):
        theorem = st.selectbox('Theorem', opts('theorem'))
        status = st.selectbox('Status', ['PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED'])
        claim = st.text_area('Claim', height=120)
        proof = st.text_area('Proof sketch / notes', height=160)
        submit = st.form_submit_button('Add')
    if submit and theorem and claim:
        write(add_claim, theorem, status, claim, proof)
        st.success('Claim added')
    st.dataframe(q('SELECT c.id, t.slug theorem, c.status, c.claim_md, c.proof_sketch_md, c.created_at FROM claim c JOIN theorem t ON t.id=c.theorem_id ORDER BY c.created_at DESC'), use_container_width=True)

elif page == 'Attempts':
    st.header('Attempts')
    with st.form('attempt'):
        theorem = st.selectbox('Theorem', opts('theorem'))
        strategy = st.selectbox('Strategy', opts('strategy'))
        run_id = st.text_input('Run ID', 'manual')
        title = st.text_input('Title')
        status = st.selectbox('Status', ['FAILED/OPEN','PROVED','CONDITIONAL','COMPUTATIONAL','HEURISTIC','FALSIFIED'])
        model = st.text_input('Model')
        prompt = st.text_area('Prompt', height=160)
        result = st.text_area('Result', height=220)
        submit = st.form_submit_button('Add')
    if submit:
        write(add_attempt, theorem_slug=theorem or None, strategy_slug=strategy or None, run_id=run_id, title=title or None, prompt_md=prompt, result_md=result, status=status, model=model or None)
        st.success('Attempt added')
    st.dataframe(q('SELECT * FROM v_recent_attempts LIMIT 100'), use_container_width=True)

elif page == 'Strategies':
    st.header('Strategies')
    with st.form('strategy'):
        slug=st.text_input('Slug'); name=st.text_input('Name'); desc=st.text_area('Description', height=150)
        rank=st.number_input('Rank', min_value=0, value=1, step=1); status=st.selectbox('Status',['ACTIVE','DEMOTED','FALSIFIED','PAUSED','RESOLVED'])
        score=st.number_input('Score', value=0.0, step=0.5); submit=st.form_submit_button('Save')
    if submit and slug and name:
        write(upsert_strategy, slug=slug, name=name, description_md=desc, rank=int(rank), status=status, score=float(score)); st.success('Saved')
    st.dataframe(q('SELECT * FROM v_strategy_health ORDER BY rank, score DESC'), use_container_width=True)

elif page == 'Falsifications':
    st.header('Falsifications')
    with st.form('falsification'):
        theorem=st.selectbox('Theorem', opts('theorem')); strategy=st.selectbox('Strategy', opts('strategy'))
        severity=st.selectbox('Severity',['LOW','MEDIUM','HIGH','KILLS_STRATEGY'])
        obstruction=st.text_area('Obstruction', height=120); counter=st.text_area('Counterexample/evidence', height=120)
        submit=st.form_submit_button('Add')
    if submit and obstruction:
        write(add_falsification, theorem_slug=theorem or None, strategy_slug=strategy or None, obstruction_md=obstruction, counterexample_md=counter or None, severity=severity); st.success('Added')
    st.dataframe(q('SELECT f.id, t.slug theorem, s.slug strategy, f.severity, f.obstruction_md, f.counterexample_md, f.created_at FROM falsification f LEFT JOIN theorem t ON t.id=f.theorem_id LEFT JOIN strategy s ON s.id=f.strategy_id ORDER BY f.created_at DESC'), use_container_width=True)

elif page == 'Dependencies':
    st.header('Dependencies')
    with st.form('dep'):
        src=st.selectbox('Source theorem', opts('theorem')); tgt=st.selectbox('Target theorem', opts('theorem'))
        rel=st.selectbox('Relation',['DEPENDS_ON','SUPPORTED_BY','REFINES','FALSIFIES','EQUIVALENT_TO'])
        note=st.text_area('Note', height=120); submit=st.form_submit_button('Add dependency')
    if submit and src and tgt:
        write(add_dependency, src, tgt, rel, note); st.success('Added')
    st.dataframe(q('SELECT * FROM v_dependency_edges'), use_container_width=True)

elif page == 'Computations':
    st.header('Computations')
    with st.form('comp'):
        theorem=st.selectbox('Theorem', opts('theorem')); run_id=st.text_input('Run ID','manual')
        name=st.text_input('Name'); status=st.selectbox('Status',['COMPUTATIONAL','PROVED','CONDITIONAL','HEURISTIC','FAILED/OPEN','FALSIFIED'])
        code=st.text_input('Code path'); data=st.text_input('Data path'); report=st.text_input('Report path')
        summary=st.text_area('Summary JSON or notes', height=120); submit=st.form_submit_button('Add computation')
    if submit and name:
        write(add_computation, theorem_slug=theorem or None, run_id=run_id, name=name, status=status, code_path=code or None, data_path=data or None, report_path=report or None, summary={'notes': summary})
        st.success('Added')
    st.dataframe(q('SELECT c.id, t.slug theorem, c.name, c.status, c.code_path, c.data_path, c.report_path, c.created_at FROM computation c LEFT JOIN theorem t ON t.id=c.theorem_id ORDER BY c.created_at DESC'), use_container_width=True)

elif page == 'SQL':
    st.header('SQL explorer')
    sql = st.text_area('SQL', 'SELECT * FROM v_current_frontier;', height=160)
    if st.button('Run SQL'):
        try: st.dataframe(q(sql), use_container_width=True)
        except Exception as e: st.error(str(e))

elif page == 'Help':
    st.header('Running the codex')
    st.markdown('''
### Datasette
```bash
datasette serve proof_codex.sqlite --metadata datasette/metadata.json
```

### Streamlit
```bash
streamlit run apps/streamlit_app.py -- --db proof_codex.sqlite
```

### Seed database
```bash
python scripts/seed.py --db proof_codex.sqlite --prompt data/current_frontier_prompt.md
```
''')
