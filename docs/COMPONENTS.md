# Components

This combined artifact packages the modular pieces built during the proof-search workflow.

## `components/math_research_workbench`
Problem-agnostic LangGraph/LangChain workbench that works three tracks, ordered by cost to discover: showing a claim is not already published (hostile prior-art recon), showing it is false (counterexample search), and proving it. Supports configurable problem specs, executable conjectures, independent double-checking of every witness, an enforced prior-art search standard, strategy portfolios with `PROVE`/`REFUTE` lanes, local settings, SQLite logging, symbolic checks, CAS hooks, and formalization hooks.

Two stages run standalone with no model and no API key:

```bash
cd components/math_research_workbench

# counterexample sweep — fully deterministic
python -m math_workbench.sweep --problem examples/counterexample_demo_problem.yaml

# prior-art recon — emit hostile search prompts, then grade the responses
python -m math_workbench.recon --problem examples/counterexample_demo_problem.yaml --emit-prompts
python -m math_workbench.recon --problem examples/counterexample_demo_problem.yaml --ingest pass1.md pass2.md
```

See `components/math_research_workbench/docs/ARCHITECTURE.md` for the graph and the verification discipline.

## `components/theorem_codex`
SQLite + Datasette + Streamlit theorem codex. Use this as the canonical theorem/claim/attempt/falsification ledger and UI.

## `components/math_frontier_langchain_template`
Reusable LangChain `ChatPromptTemplate` package for frontier-reduction prompts.

## `components/erdos_hybrid_strategy_agent`
Erdős-specific hybrid proof-search agent with combined strategy lanes and meta-strategy discovery.

## `components/erdos_multistrategy_aristotle_sage_agent`
Earlier Erdős-specific agent with Aristotle/Lean and Sage/Magma degeneracy lanes.

## `archives/`
Original source ZIPs are preserved here for reference.
