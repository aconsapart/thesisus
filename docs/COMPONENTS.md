# Components

This combined artifact packages the modular pieces built during the proof-search workflow.

## `components/math_research_workbench`
Problem-agnostic LangGraph/LangChain proof-search workbench. Supports configurable problem specs, strategy portfolios, local settings, SQLite logging, symbolic checks, CAS hooks, and formalization hooks.

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
