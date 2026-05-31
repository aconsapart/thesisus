# Erdős Multi-Strategy Proof Agent with Aristotle + CAS Degeneracy Lane

This package implements a LangGraph/LangChain proof-search scaffold for the Erdős divisor-sum project.

It extends the previous multi-strategy Aristotle scaffold with a dedicated **CAS degeneracy lane** for the current algebraic bottleneck:

\[
F_R(z)F_R(z') \in \mathbb F_\ell(R)^2 ?
\]

The goal of this lane is to classify pairwise square degeneracies for the averaged product-fiber large-sieve theorem.

## Install

```bash
pip install -U langgraph langchain langchain-openai pydantic sympy pandas requests aristotlelib
```

Optional CAS tools:

```bash
# SageMath, if installed
export SAGE_CMD="sage"

# Magma, if available
export MAGMA_CMD="magma"
```

Optional formalization tools:

```bash
export LEAN_CMD="lake env lean"
export ARISTOTLE_API_KEY="..."
# or an Aristotle-compatible CLI endpoint:
export ARISTOTLE_CLI="..."
```

## Run the full agent

```bash
export OPENAI_API_KEY="YOUR_KEY"
export MODEL_NAME="gpt-4.1"

python src/erdos_agent.py \
  --iterations 3 \
  --parallel-strategies 3 \
  --out runs/run_001
```

Each iteration writes:

```text
iteration_00/
  selected_strategies.md
  strategy_*.md
  symbolic_checks.md
  cas_pairwise_degeneracy.md
  cas_pairwise_degeneracy.json
  formal_task_generation_raw.md
  formalization_report.md
  synthesis.md
```


## Hybrid attack and strategy discovery lanes

This package now includes two additional strategy lanes:

- `hybrid_combined_attack`: combines integer hyperbola/divisor bounds, finite-field shifted-product methods, exact `(A,B)`-curve incidence, near-injectivity, and geometric divisor-window rigidity.
- `meta_strategy_discovery`: searches for genuinely new strategies and appends them to the portfolio only when they include a concrete falsification test.

A new graph node, `discover_strategies`, runs after synthesis and can add up to three new strategies for later iterations.

For best coverage, run at least four parallel strategies:

```bash
python src/erdos_agent.py \
  --iterations 4 \
  --parallel-strategies 4 \
  --out runs/hybrid_run_001
```

The docs file `docs/HYBRID_ATTACK_AND_DISCOVERY.md` explains the new lanes and generated artifacts.

## Run only the CAS degeneracy checker

This standalone script does not require LangChain.

```bash
python src/cas_degeneracy_standalone.py --out runs/cas_pairwise_001
```

It writes:

```text
pairwise_degeneracy.sage
pairwise_degeneracy.magma
cas_degeneracy_report.json
cas_degeneracy_report.md
```

The SymPy fallback verifies the currently proved F1 pairwise facts and constructs F2 for further Sage/Magma factorization.

## Current CAS target

The key algebraic theorem is:

\[
F_R(z)F_R(z') \notin \mathbb F_\ell(R)^2
\]

except for:

- diagonal \(z=z'\),
- \(Q(R)=0\),
- \(s=0\),
- \(\alpha=0\),
- denominator-zero loci,
- small characteristic exceptions.

This is the exact symbolic bottleneck for the averaged product-fiber second moment.

## Notes

- The full theorem is not marked proved unless the agent produces a proof or a verified formal proof.
- Falsification remains mandatory before pursuit.
- The CAS lane is a support tool: it produces scripts and symbolic facts, not automatic theorem acceptance.
