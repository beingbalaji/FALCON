# Runs on a free Hugging Face Space (Docker SDK, CPU basic) or any Docker host.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/.hf FALXON_DATA_DIR=/app/var
WORKDIR /app

COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r requirements.txt

COPY falxon falxon
COPY scripts scripts
RUN python -m scripts.download_models

COPY web web
COPY reports reports

RUN useradd -m app && mkdir -p /app/var && chown -R app /app
USER app
EXPOSE 7860
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
