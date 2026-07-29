# Prior-art recon

A claim can fail three ways, in increasing order of cost to discover:

1. **it is already known** — someone published it;
2. **it is false** — a counterexample exists;
3. **it is unproved** — nobody can establish it.

The workbench checks them in that order, because that is the order of cost.
Prior art is a search, refutation is a sweep, proof is a campaign. Finding out
on day two hundred that your theorem is Lemma 4.1 of a 1994 paper is the most
avoidable waste available in research.

This is day-zero work, not day-two work.

## What is being searched for

`claims` are the separately attackable contributions. They are not `targets`
(which may be true and already known) and not `conjectures` (which may be novel
and false):

```yaml
claims:
  - id: diagonal-enumeration
    kind: CONTRIBUTION
    statement: >
      We introduce a novel diagonal enumeration order that surfaces minimal
      counterexamples in multivariate predicate search.
    novelty_basis: "Ordering candidate assignments by increasing sum of variable indices."
    known_prior_art:
      - "Standard combinatorial generation orders (colex, shortlex)."
    search_terms:
      - "diagonal enumeration counterexample search"
      - "shell ordering multivariate predicate"
    adjacent_fields:
      - "combinatorial generation"
      - "property-based testing"
```

A claim is attackable only if someone could hand you a single paper that settles
it. "Our method is new" cannot be searched. The statement above can. If refuting
a claim would take three papers, it is three claims.

`known_prior_art` is conceded upfront on purpose. A search that starts from zero
known prior art usually means nobody has looked yet, and it lets the model spend
its effort finding what you *don't* already know about.

## Why the model cannot simply be asked

The model does the searching. The rules that make its answer mean something are
enforced here, because "we looked and found nothing" is a claim about the
search, not about the literature.

**Union over at least two independent passes.** A single search reliably misses
severe threats. Threats are unioned across passes and the worst verdict wins, so
a threat one pass missed still counts. A claim assessed by one pass comes back
`UNDER_SEARCHED`, never `CLEAR`. Passes that share a phrasing and engine count as
one — otherwise the rule is satisfied by running the same query twice.

**Angle coverage.** Concepts hide under other vocabularies, and the killing
citation is routinely in another literature under a name you would never think
to type. A clear verdict requires queries logged under all four angles:

| Angle            | What it means                                                            |
| ---------------- | ------------------------------------------------------------------------ |
| `MECHANISM`      | the thing itself, in the vocabulary its inventors would use               |
| `SYNONYM`        | the same idea renamed; older literature uses older words                  |
| `APPLICATION`    | where it would be used, rather than what it is                            |
| `ADJACENT_FIELD` | another literature entirely — statistics, OR, program analysis, …         |

**Negative searches are the evidence.** A query that returned nothing is the
only thing that can support a "no prior art" verdict, so every query is logged
with its result count and a clear verdict requires a minimum number of them. An
unlogged clear verdict is an opinion.

**Overclaims are detected, not trusted.** "First", "novel", "we introduce", "no
prior work", "state of the art" are priority claims. Each is flagged and is only
defensible behind a `CLEAR` verdict; behind anything else it is an overclaim to
cut before publication.

### The asymmetry

Finding a killer is evidence *however sloppily you looked*. Finding nothing is
evidence *only if you looked properly*. So the discipline checks apply only when
nothing was found — a `KILLS` from a one-query pass still kills, while silence
from that same pass establishes nothing.

This is the same shape as `VERIFIED_EXHAUSTIVE` in the refutation track: a
witness proves the claim false regardless of how the search was run, but "no
witness exists" requires the whole space to have actually been covered.

## Verdicts

Per source, against a specific claim:

| Verdict      | Meaning                                                                 |
| ------------ | ----------------------------------------------------------------------- |
| `KILLS`      | the source already reports this claim; it is dead as written             |
| `WOUNDS`     | the source forces the claim to be narrowed to survive                    |
| `ADJACENT`   | not a threat, but failing to cite it looks like ignorance or concealment |
| `BACKGROUND` | context only                                                             |

Per claim, after unioning every pass:

| Status           | Meaning                                                           |
| ---------------- | ----------------------------------------------------------------- |
| `KILLED`         | at least one `KILLS`                                              |
| `WOUNDED`        | at least one `WOUNDS`, no `KILLS`                                 |
| `CLEAR`          | nothing found, **and** the search met the policy                  |
| `UNDER_SEARCHED` | nothing found, but the search has not earned the right to say so  |

`ADJACENT` work still has to be cited and distinguished even when the claim
comes back `CLEAR`. The report lists it under the clear claim for that reason.

## Running it

### Inside the pipeline

`prior_art` is the first node in the graph and runs once, before any strategy is
selected. Claims that come back damaged route through `claim_surgery` before any
budget is spent defending them.

```bash
python scripts/run_agent.py \
  --problem your_problem.yaml \
  --strategies your_strategies.yaml \
  --parallel-searches 4      # one hostile pass per angle
```

### Standalone

The search needs a model with retrieval, but the two halves around it do not,
and both are worth having separately. Emit the prompts, run them wherever the
literature access is best, then grade what comes back:

```bash
# 1. emit one hostile-search prompt per angle
python -m math_workbench.recon --problem your_problem.yaml --emit-prompts \
  --prompt-dir runs/recon/prompts

# 2. run them in separate sessions, save the responses, then grade them together
python -m math_workbench.recon --problem your_problem.yaml \
  --ingest runs/recon/mechanism.md runs/recon/adjacent.md \
  --db proof_codex.sqlite \
  --out runs/recon/threat_table.md \
  --claims-out CLAIMS.md
```

Exit codes: `0` every claim clear, `1` something was killed or wounded (the
search did its job), `2` something is under-searched — go again with different
phrasing.

Splitting it this way means the search can happen anywhere — a different model,
a librarian, a colleague — while the standard applied to the result stays fixed
and stays in version control.

## Output format

Search passes report in fenced blocks; prose outside them is commentary and is
not recorded.

```
​```search
{"pass": "p1", "angle": "MECHANISM", "query": "the exact query text",
 "engine": "where you searched", "results": 0, "notes": "claim:diagonal-enumeration"}
​```

​```threat
{"claim": "diagonal-enumeration", "verdict": "KILLS",
 "source": "Knuth (2011), TAOCP 4A", "locator": "7.2.1.3", "angle": "MECHANISM",
 "evidence": "Generation by increasing index sum is textbook combinatorial generation."}
​```
```

Blocks that cannot be used are listed in the report rather than dropped: a pass
that emitted three malformed threat blocks looks identical to one that found
nothing, and those are very different outcomes.

Untagged queries count towards every claim. Tag a query with `claim:<id>` in
`notes` to restrict it.

## CLAIMS.md

The run writes the maximally-defensible claim set to `CLAIMS.md`: what survives
as written, what needs surgery and why, and the banned overclaims. Supersede
this file rather than editing it quietly — what you were once willing to claim
is part of the record, and a reviewer who finds the earlier version elsewhere
should find your own correction first.

## Configuring the policy

```yaml
prior_art:
  min_passes: 2
  min_negative_queries: 3
  required_angles: [MECHANISM, SYNONYM, APPLICATION, ADJACENT_FIELD]
  require_distinct_phrasing: true
```

Loosening these is sometimes right — a narrow claim in a small literature does
not need four angles. Loosening them because the search keeps saying
`UNDER_SEARCHED` is not; that verdict is the tool working.

## What this does not do

It does not read papers for you. A threat block is only as good as the reading
behind it, and a model that has not opened the source can produce a plausible
locator for a paper that says something else entirely. Treat `KILLS` as a
pointer to go read, and confirm before rewriting a claim around it.

It also cannot find what it does not search for. A claim that is never declared
is never checked, and an empty prior-art tab means novelty was never assessed —
not that the work is novel.
