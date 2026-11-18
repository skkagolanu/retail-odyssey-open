FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RO_DATABASE_PATH=/app/var/sessions.sqlite3
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home retail
COPY src ./src
COPY data ./data
COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir var && chown retail:retail var
USER retail
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request,json; r=json.load(urllib.request.urlopen('http://localhost:8000/api/health')); assert r['status']=='ready'"
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
