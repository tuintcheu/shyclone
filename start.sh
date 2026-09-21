#!/usr/bin/env bash
# ShyClone — démarre le moteur Flask puis l'interface Vite dans un seul terminal.
set -u

RACINE="$(cd "$(dirname "$0")" && pwd)"
PORT_MOTEUR="${SHYCLONE_PORT:-5000}"
PORT_UI="${SHYCLONE_UI_PORT:-5173}"
MOTEUR_PID=""
UI_PID=""

liberer_port() {
  local port=$1
  local pids
  pids=$(lsof -ti ":$port" 2>/dev/null) || return 0
  if [ -n "$pids" ]; then
    echo "[ShyClone] port $port occupé — libération"
    kill $pids 2>/dev/null
    sleep 1
  fi
}

ARRET_FAIT=0
arreter() {
  [ "$ARRET_FAIT" -eq 1 ] && return
  ARRET_FAIT=1
  echo ""
  echo "[ShyClone] arrêt…"
  # Les processus sont tués par groupe : npx lance vite dans un enfant qui
  # survivrait à un kill sur le seul PID de npx.
  for pid in "$MOTEUR_PID" "$UI_PID"; do
    [ -n "$pid" ] && kill -- "-$pid" 2>/dev/null
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
  done
  wait 2>/dev/null
  echo "[ShyClone] arrêté."
}
trap arreter EXIT INT TERM

cd "$RACINE"

if [ ! -d node_modules ]; then
  echo "[ShyClone] dépendances npm manquantes — npm install"
  npm install || exit 1
fi

liberer_port "$PORT_MOTEUR"
liberer_port "$PORT_UI"

echo "[ShyClone] démarrage du moteur…"
set -m
python3 src/server.py &
MOTEUR_PID=$!
set +m

pret=0
for _ in $(seq 1 24); do
  if curl -sf "http://127.0.0.1:$PORT_MOTEUR/api/health" > /dev/null 2>&1; then
    pret=1
    break
  fi
  # Inutile d'attendre si le moteur est déjà mort (dépendance Python absente).
  kill -0 "$MOTEUR_PID" 2>/dev/null || break
  sleep 0.5
done

if [ "$pret" -ne 1 ]; then
  echo "[ShyClone] le moteur n'a pas démarré."
  echo "           vérifiez les dépendances : pip3 install -r requirements.txt"
  exit 1
fi
echo "[ShyClone] moteur prêt sur le port $PORT_MOTEUR"

set -m
npx vite --port "$PORT_UI" &
UI_PID=$!
set +m

echo ""
echo "  ShyClone 1.0"
echo "  Interface : http://localhost:$PORT_UI"
echo "  Moteur    : http://127.0.0.1:$PORT_MOTEUR"
echo "  Ctrl+C pour tout arrêter."
echo ""

# On rend la main dès que l'un des deux s'arrête, pour ne pas laisser
# l'autre tourner dans le vide. `wait -n` n'existe pas en bash 3.2 (macOS).
if [ "${BASH_VERSINFO[0]:-3}" -ge 4 ]; then
  wait -n "$MOTEUR_PID" "$UI_PID"
else
  while kill -0 "$MOTEUR_PID" 2>/dev/null && kill -0 "$UI_PID" 2>/dev/null; do
    sleep 1
  done
fi
