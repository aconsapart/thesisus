You are selecting the next proof target.

Project setup:
{{project_setup}}

Current frontier:
{{current_frontier}}

Known facts:
{{known_facts}}

Strategy portfolio:
{{strategy_portfolio}}

Previous failures:
{{failed_strategies}}

Task:
Choose up to {{parallel_strategies}} strategies for this iteration.

Prioritize:
1. strategies that attack the current exact frontier;
2. strategies that can falsify a broad theorem quickly;
3. strategies that produce a sharper theorem;
4. strategies that connect to formalization or CAS checks.

Return JSON:
{
  "selected": [
    {"name": "...", "reason": "...", "falsification_test": "...", "expected_output": "..."}
  ],
  "do_not_run": [
    {"name": "...", "reason": "..."}
  ]
}
