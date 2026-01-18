FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential \
	&& rm -rf /var/lib/apt/lists/*

COPY . /app

RUN mkdir -p obj && make
RUN pip install --no-cache-dir -r web/api/requirements.txt

ENV SOLVER_PATH=/app/sudokusolver

EXPOSE 8000

CMD ["sh", "-c", "uvicorn web.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
