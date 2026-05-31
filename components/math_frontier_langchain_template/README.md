# Math Frontier LangChain Prompt Templates

Reusable LangChain prompt templates for rigorous mathematical proof-search workflows.

## What this package contains

- `templates/frontier_master_prompt.md`: the main prompt template.
- `templates/planner_prompt.md`: strategy selection.
- `templates/strategy_prompt.md`: single-strategy falsify/prove/reduce lane.
- `templates/synthesis_prompt.md`: conservative iteration synthesis.
- `templates/meta_strategy_prompt.md`: new strategy discovery.
- `src/math_frontier_templates/prompts.py`: LangChain `ChatPromptTemplate` constructors.
- `examples/use_frontier_prompt.py`: minimal usage example.

## Install

```bash
pip install -U langchain-core langchain-openai
pip install -e .
```

## Usage

```python
from langchain_openai import ChatOpenAI
from math_frontier_templates import frontier_master_prompt, default_inputs

llm = ChatOpenAI(model="gpt-4.1", temperature=0.2)
prompt = frontier_master_prompt()
messages = prompt.format_messages(**default_inputs())
response = llm.invoke(messages)
print(response.content)
```

## Why Mustache templates?

The templates use `template_format="mustache"` to avoid escaping mathematical braces in LaTeX-heavy prompts.

## Intended LangGraph nodes

Use these templates in a LangGraph `StateGraph` with nodes:

1. planner
2. strategy lanes
3. symbolic/CAS checks
4. formalization
5. synthesis
6. strategy discovery

The current mathematical frontier is expected as runtime variables, not hardcoded.
