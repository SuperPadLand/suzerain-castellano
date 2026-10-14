#!/usr/bin/env bash
# Suzerain en castellano 1.0 — instalador para Linux.
# Uso: bash instalar.sh            (busca el juego en Steam)
#      bash instalar.sh "/ruta/a/steamapps/common/Suzerain"
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATOS="$AQUI/datos"
COPIAS="${XDG_DATA_HOME:-$HOME/.local/share}/suzerain-castellano"
VENV="$COPIAS/venv"
UNITYPY="UnityPy==1.25.4"
AA="Suzerain_Data/StreamingAssets/aa/StandaloneWindows64"

fallo() { echo; echo "ERROR: $*" >&2; exit 1; }

echo "=== Suzerain en castellano 1.0 ==="
echo

# 1. Dónde está el juego
buscar_juego() {
    local raiz lib
    for raiz in "$HOME/.local/share/Steam" "$HOME/.steam/steam" "$HOME/.steam/root" \
                "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam" \
                "$HOME/snap/steam/common/.local/share/Steam"; do
        [ -d "$raiz/steamapps" ] || continue
        if [ -d "$raiz/steamapps/common/Suzerain/$AA" ]; then echo "$raiz/steamapps/common/Suzerain"; return 0; fi
        [ -f "$raiz/steamapps/libraryfolders.vdf" ] || continue
        while IFS= read -r lib; do
            if [ -d "$lib/steamapps/common/Suzerain/$AA" ]; then echo "$lib/steamapps/common/Suzerain"; return 0; fi
        done < <(sed -n 's/^[[:space:]]*"path"[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$raiz/steamapps/libraryfolders.vdf")
    done
    return 1
}
if [ $# -ge 1 ]; then
    JUEGO="${1%/}"
else
    JUEGO="$(buscar_juego)" || fallo "No encuentro Suzerain en las bibliotecas de Steam.
Pásame la carpeta del juego, por ejemplo:
  bash instalar.sh \"/media/disco/SteamLibrary/steamapps/common/Suzerain\""
fi
[ -d "$JUEGO/$AA" ] || fallo "En «$JUEGO» no está la carpeta $AA. ¿Es la carpeta de Suzerain?"
echo "Juego: $JUEGO"

# 2. El juego tiene que estar cerrado
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
    fallo "Suzerain está abierto. Ciérralo y vuelve a ejecutar el instalador."
fi

# 3. Python y UnityPy (la primera vez se descargan unos 30 MB)
command -v python3 >/dev/null 2>&1 || fallo "Hace falta Python 3 (paquete python3 de tu distribución)."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || fallo "Hace falta Python 3.8 o más nuevo."
mkdir -p "$COPIAS"
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import UnityPy' >/dev/null 2>&1; then
    echo "Preparando las herramientas (solo la primera vez, necesita internet)..."
    rm -rf "$VENV"
    python3 -m venv "$VENV" || fallo "No se pudo crear el entorno de Python.
En Debian, Ubuntu o Mint instala el paquete python3-venv:  sudo apt install python3-venv"
    "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check "$UNITYPY" \
        || fallo "No se pudo descargar UnityPy. Comprueba la conexión a internet."
fi

# 4. ¿Es la versión para la que se hizo la traducción?
if [ ! -f "$COPIAS/estado.json" ]; then
    distintos=0
    while read -r suma nombre; do
        case "$nombre" in database_*|defaultlocalgroup_*|*mainmenu*|*sordland*) ;; *) continue;; esac
        f="$JUEGO/$AA/$nombre"
        if [ ! -f "$f" ] || [ "$(sha256sum "$f" | cut -d' ' -f1)" != "$suma" ]; then distintos=$((distintos + 1)); fi
    done < "$DATOS/SHA256SUMS"
    if [ "$distintos" -gt 0 ]; then
        echo
        echo "AVISO: tus archivos del juego no son los de la versión 3.1.0 para la que se hizo esta"
        echo "traducción (puede que el juego se haya actualizado o que tengas otro mod puesto)."
        echo "Se traducirá todo lo que siga igual; lo que haya cambiado se quedará en inglés."
    fi
fi

# 5. Traducir
echo
echo "Traduciendo (tarda uno o dos minutos)..."
REGISTRO="$COPIAS/ultimo-registro.txt"
SUZERAIN_TRAD="$DATOS/traduccion" SUZERAIN_JUEGO="$JUEGO" SUZERAIN_COPIAS="$COPIAS" SUZERAIN_SOLO_BASE=1 \
    "$VENV/bin/python" "$DATOS/inyectar.py" > "$REGISTRO" 2>&1 || { cat "$REGISTRO"; fallo "La traducción no se ha podido aplicar (registro en $REGISTRO)."; }
grep -v '^AVISO:' "$REGISTRO" || true
avisos=$(grep -c '^AVISO:' "$REGISTRO" || true)
echo
if [ "$avisos" -gt 0 ]; then
    echo "Hecho, con $avisos textos que se han quedado en inglés porque no coinciden con esta versión."
    echo "Detalle en: $REGISTRO"
    if [ "$avisos" -gt 500 ]; then
        echo "Son muchos: si tienes otro mod puesto, verifica los archivos de Suzerain en Steam"
        echo "(Propiedades > Archivos instalados > Verificar integridad) y vuelve a instalar."
    fi
else
    echo "Hecho. Suzerain ya está en castellano."
fi
echo "Si Steam actualiza el juego y vuelve el inglés, ejecuta otra vez este instalador."
