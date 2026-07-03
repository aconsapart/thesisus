FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY components/theorem_codex/ ./

# SQLite database lives on a volume so data survives container restarts.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8501

# PORT is honored for platforms like Render/Railway/Heroku; defaults to 8501.
CMD streamlit run apps/streamlit_app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    -- --db ${THESIUS_DB:-/data/proof_codex.sqlite}
