#!/usr/bin/env bash
# Suzerain en castellano 1.0 — vuelve a dejar el juego en inglés.
# Uso: bash desinstalar.sh   (o con la carpeta del juego, igual que instalar.sh)
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COPIAS="${XDG_DATA_HOME:-$HOME/.local/share}/suzerain-castellano"
VENV="$COPIAS/venv"
AA="Suzerain_Data/StreamingAssets/aa/StandaloneWindows64"

fallo() { echo; echo "ERROR: $*" >&2; exit 1; }

if [ ! -f "$COPIAS/estado.json" ] || [ ! -x "$VENV/bin/python" ]; then
    fallo "No encuentro las copias de los archivos originales en $COPIAS.
Para volver al inglés, verifica los archivos en Steam:
Suzerain > Propiedades > Archivos instalados > Verificar integridad de los archivos."
fi
if [ $# -ge 1 ]; then
    JUEGO="${1%/}"
else
    # la misma búsqueda que el instalador
    source <(sed -n '/^buscar_juego() {/,/^}/p' "$AQUI/instalar.sh")
    JUEGO="$(buscar_juego)" || fallo "No encuentro Suzerain. Pásame la carpeta del juego como en instalar.sh."
fi
[ -d "$JUEGO/$AA" ] || fallo "En «$JUEGO» no está la carpeta $AA."
juego_abierto() {
    # ¿hay un Suzerain.exe en marcha desde esta misma carpeta? (Proton lo lanza con la ruta de Linux)
    local real pid arg
    real="$(realpath -m "$JUEGO")"
    for pid in $(pgrep -f 'Suzerain\.exe' || true); do
        [ -r "/proc/$pid/cmdline" ] || continue
        while IFS= read -r -d '' arg; do
            case "$arg" in
                */Suzerain.exe) [ "$(realpath -m "${arg%/Suzerain.exe}")" = "$real" ] && return 0 ;;
            esac
        done < "/proc/$pid/cmdline"
    done
    return 1
}
if juego_abierto; then
    fallo "Suzerain está abierto. Ciérralo y vuelve a ejecutar el desinstalador."
fi
SUZERAIN_TRAD="$AQUI/datos/traduccion" SUZERAIN_JUEGO="$JUEGO" SUZERAIN_COPIAS="$COPIAS" SUZERAIN_SOLO_BASE=1 \
    "$VENV/bin/python" "$AQUI/datos/inyectar.py" --restaurar
rm -f "$COPIAS/estado.json"
echo
echo "Hecho. Suzerain vuelve a estar en inglés."
echo "Si quieres borrar también las copias y las herramientas: rm -rf \"$COPIAS\""
