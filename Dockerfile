FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=3000
COPY app/ ./app/
COPY static/ ./static/
COPY data/football.db ./data/football.db
COPY data/schema.sql ./data/schema.sql
COPY data/semantic_model.md ./data/semantic_model.md
RUN chmod 444 /app/data/football.db && useradd --create-home --uid 10001 runner
USER runner
EXPOSE 3000
CMD ["python", "-m", "app.server"]
