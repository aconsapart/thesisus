# Problem spec notes

A problem spec is a YAML file with these fields:

- `slug`: stable id.
- `title`: human title.
- `domain`: e.g. number_theory, algebra, topology, analysis, combinatorics.
- `background`: Markdown context.
- `definitions`: list of `{name, statement}`.
- `targets`: list of `{id, title, statement, status}`.
- `known_results`: list of status-labeled facts.
- `current_frontier`: exact theorem to attack now.
- `falsification_tests`: concrete ways to break proposed theorems.
- `computation_tasks`: symbolic/numeric experiments.
- `formalization_targets`: small Lean-friendly lemmas.
