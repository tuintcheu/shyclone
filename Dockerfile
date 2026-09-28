# Image unique : elle compile l'interface puis la sert depuis le même
# processus que l'API. Un seul service à déployer, une seule URL.

FROM node:22-slim AS interface
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY public/ ./public/
COPY src/ ./src/
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Rendu des sites construits en JavaScript. Optionnel : il ajoute environ
# 350 Mo à l'image et demande 300 Mo de mémoire à l'exécution, ce qui ne tient
# pas sur une instance gratuite de 512 Mo.
#   docker build --build-arg AVEC_NAVIGATEUR=1 -t shyclone .
ARG AVEC_NAVIGATEUR=0
RUN if [ "$AVEC_NAVIGATEUR" = "1" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends chromium fonts-liberation && \
      rm -rf /var/lib/apt/lists/*; \
    fi
ENV SHYCLONE_NAVIGATEUR=/usr/bin/chromium

COPY src/ ./src/
COPY gunicorn.conf.py ./
COPY --from=interface /build/dist ./dist

ENV PYTHONUNBUFFERED=1 \
    SHYCLONE_HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# Un seul worker : l'état des jobs vit en mémoire et les fichiers capturés sur
# le disque du processus. Deux workers ne verraient pas les jobs l'un de
# l'autre. Les threads absorbent la concurrence, timeout désactivé car une
# capture peut durer plusieurs minutes.
# Forme exec via « sh -c … exec » : le shell est nécessaire pour développer
# ${PORT}, et exec le fait remplacer par gunicorn, qui reçoit alors SIGTERM
# directement. Sans ça le conteneur ignore l'arrêt demandé et se fait tuer.
CMD ["sh", "-c", "exec gunicorn --config gunicorn.conf.py --chdir src --workers 1 --threads 24 --timeout 0 --bind 0.0.0.0:${PORT} --access-logfile - server:app"]
