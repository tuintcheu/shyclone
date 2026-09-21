# Image du moteur ShyClone, pour un hébergeur qui exécute un vrai processus
# (Render, Railway, Fly.io, VPS). Vercel ne convient pas : voir le README.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONUNBUFFERED=1 \
    SHYCLONE_HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# Un seul worker : l'état des jobs vit en mémoire et les fichiers capturés sur
# le disque du processus. Deux workers ne verraient pas les jobs l'un de
# l'autre. Les threads absorbent la concurrence, timeout désactivé car une
# capture peut durer plusieurs minutes.
CMD gunicorn --chdir src --workers 1 --threads 24 --timeout 0 --bind 0.0.0.0:${PORT} server:app
