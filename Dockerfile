# Étape 1 : build du frontend
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Étape 2 : image finale Python servant l'API et les statiques
FROM python:3.12-slim
WORKDIR /srv
COPY backend/pyproject.toml backend/
COPY backend/app backend/app
RUN pip install --no-cache-dir ./backend
COPY menu-tree/ menu-tree/
COPY --from=frontend-build /build/dist frontend/dist
# /srv/data : base SQLite et clé client TV, à monter en volume pour persister.
VOLUME /srv/data
EXPOSE 8000
WORKDIR /srv/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
