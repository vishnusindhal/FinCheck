# Read the doc: https://huggingface.co/docs/hub/spaces-sdks-docker
# Serves the API on :7860 and the frontend at /ui/ (same origin).

FROM python:3.11

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --chown=user ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# .dockerignore keeps .env, .venv, local Postgres data and models out of the image
COPY --chown=user . /app
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
