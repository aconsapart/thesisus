DB ?= proof_codex.sqlite
PROMPT ?= data/current_frontier_prompt.md

.PHONY: install init streamlit datasette clean

install:
	pip install -r requirements.txt

init:
	python scripts/seed.py --db $(DB) --prompt $(PROMPT)

streamlit:
	streamlit run apps/streamlit_app.py -- --db $(DB)

datasette:
	datasette serve $(DB) --metadata datasette/metadata.json

clean:
	rm -f $(DB) $(DB)-wal $(DB)-shm
