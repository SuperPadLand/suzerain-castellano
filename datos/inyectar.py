#!/usr/bin/env python3
"""Mete la traducción de traduccion/ en el juego.

Uso:
  herramientas/venv/bin/python herramientas/inyectar.py            # aplica la traducción
  herramientas/venv/bin/python herramientas/inyectar.py --restaurar # deja el juego en inglés

Qué parchea:
  - Diálogos: traduccion/<parte>.json + fuente_<parte>.json (una conversación cada uno),
    en database_assets_all_*.bundle.
  - Entidades: traduccion/entidades_<grupo>.json + fuente_entidades_<grupo>.json
    (fichas, línea temporal, HUD...), en el bundle de entitytextassets. Cada JSON está dos veces
    en el bundle (TextAsset y cadena del MonoBehaviour «Entity Text Assets»): se cambian las dos.
  - Cargos y nombres visibles de los personajes: traduccion/actores.json + fuente_actores.json,
    en la lista de actores de la misma base de datos.
  - Variables de texto que se insertan en las frases: traduccion/variables.json.
  - Llamadas Lua de los diálogos que escriben texto visible (UpdateCharacterTitle…):
    traduccion/scripts.json (llamada inglesa exacta -> llamada en castellano).
  - Menús: traduccion/interfaz.json (texto inglés exacto -> castellano), en los TextMeshPro
    (m_text) y en las claves locaId de las escenas mainmenu, sordland y rizia.

Si una actualización cambia el inglés de un texto, ese texto no se toca y se avisa.
"""
import argparse, glob, hashlib, json, os, re, shutil, sys
import UnityPy

PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# El parche que se comparte (herramientas/empaquetar.py) usa este mismo script con otras rutas:
# SUZERAIN_TRAD (carpeta de JSON), SUZERAIN_JUEGO (instalación), SUZERAIN_COPIAS (originales y estado)
# y SUZERAIN_SOLO_BASE=1 para no tocar la escena de Rizia (el DLC).
TRAD = os.environ.get("SUZERAIN_TRAD", os.path.join(PROYECTO, "traduccion"))
JUEGO = os.environ.get("SUZERAIN_JUEGO", os.path.expanduser("~/.local/share/Steam/steamapps/common/Suzerain"))
AA = os.path.join(JUEGO, "Suzerain_Data/StreamingAssets/aa/StandaloneWindows64")
COPIAS = os.environ.get("SUZERAIN_COPIAS")
ORIGINALES = os.path.join(COPIAS, "originales") if COPIAS else os.path.join(PROYECTO, "originales")
ESTADO = os.path.join(COPIAS, "estado.json") if COPIAS else os.path.join(PROYECTO, "estado.json")
SOLO_BASE = os.environ.get("SUZERAIN_SOLO_BASE") == "1"
CAMPOS = {"T": "en", "M": "Menu Text en"}
AVISOS = []
# Textos de entidades que el código del juego usa como claves: si se traducen, algo deja de funcionar.
# Los nombres demográficos de las fichas del mapa («Others», «Sordish», «Bludish»...) bloquean el
# arranque del Turno 1 (no sale la personalización y el mapa se queda sin botones).
PROHIBIDOS = re.compile(r"^MapTokenData\|[^|]+\|DemographicsProperties\.(EthnicityDatas|ReligionDatas)\.\d+\.Name$")


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def cargar(ruta):
    return json.load(open(ruta, encoding="utf-8"))


def un_bundle(patron):
    rutas = glob.glob(os.path.join(AA, patron))
    if len(rutas) != 1:
        sys.exit(f"Esperaba un {patron} y hay {len(rutas)}")
    return rutas[0]


def origen_limpio(ruta_juego, estado):
    """Copia en inglés del bundle: la del juego si está sin tocar, o la guardada en originales/."""
    nombre = os.path.basename(ruta_juego)
    os.makedirs(ORIGINALES, exist_ok=True)
    guardado = os.path.join(ORIGINALES, nombre)
    if estado.get(nombre) == sha256(ruta_juego):
        if not os.path.exists(guardado):
            sys.exit(f"El juego tiene nuestra traducción pero falta el original {guardado}")
        return guardado
    if not os.path.exists(guardado) or sha256(guardado) != sha256(ruta_juego):
        shutil.copy2(ruta_juego, guardado)
        print(f"Guardado original: {nombre}")
    return guardado


# ---------- Diálogos ----------

def campo(entrada, titulo):
    for f in entrada["fields"]:
        if f["title"] == titulo:
            return f
    return None


def aplicar_dialogos(env):
    obj = next(o for o in env.objects if o.type.name == "MonoBehaviour")
    bd = obj.read_typetree()
    por_titulo = {campo(c, "Title")["value"]: c for c in bd["conversations"] if campo(c, "Title")}
    por_id = {c["id"]: c for c in bd["conversations"]}
    total = 0
    for ruta in sorted(glob.glob(os.path.join(TRAD, "*.json"))):
        nombre = os.path.basename(ruta)
        if nombre.startswith(("fuente_", "entidades_")) or nombre in ("interfaz.json", "actores.json", "variables.json", "scripts.json"):
            continue
        tr = cargar(ruta)
        f = cargar(os.path.join(TRAD, "fuente_" + nombre))
        fuente = {str(e["id"]): e for e in (f["entradas"] if isinstance(f, dict) else f)}
        conv = por_id.get(tr["_id"]) if "_id" in tr else por_titulo.get(tr["_conversacion"])
        if conv is None:
            AVISOS.append(f"no existe la conversación {tr['_conversacion']}")
            continue
        entradas = {str(e["id"]): e for e in conv["dialogueEntries"]}
        for eid, textos in tr.items():
            if eid.startswith("_"):
                continue
            entrada = entradas.get(eid)
            for clave, es in textos.items():
                f = campo(entrada, CAMPOS[clave]) if entrada else None
                ingles = fuente[eid]["text" if clave == "T" else "menu"]
                if f is None or f["value"] != ingles:
                    AVISOS.append(f"{tr['_conversacion']} #{eid} {CAMPOS[clave]}: el inglés ha cambiado")
                    continue
                f["value"] = es
                total += 1
    total += aplicar_actores(bd)
    total += aplicar_variables(bd)
    total += aplicar_scripts(bd)
    obj.save_typetree(bd)
    return total


def aplicar_actores(bd):
    """Cargo (CharacterTitle) y nombre visible (CharacterName) de los actores; se buscan por Name."""
    tr = {k: v for k, v in cargar(os.path.join(TRAD, "actores.json")).items() if not k.startswith("_")}
    fuente = cargar(os.path.join(TRAD, "fuente_actores.json"))
    actores = {campo(a, "Name")["value"]: a for a in bd["actors"]}
    total = 0
    for clave, es in tr.items():
        nombre, titulo = clave.split("|")
        f = campo(actores[nombre], titulo) if nombre in actores else None
        if f is None or f["value"] != fuente.get(clave):
            AVISOS.append(f"actor {clave}: el inglés ha cambiado o ya no existe")
            continue
        f["value"] = es
        total += 1
    return total


def aplicar_variables(bd):
    """Valores iniciales de las variables de texto que se insertan en las frases ({BaseGameText.X})."""
    tr = {k: v for k, v in cargar(os.path.join(TRAD, "variables.json")).items() if not k.startswith("_")}
    total = 0
    for v in bd["variables"]:
        nombre = campo(v, "Name")["value"]
        if nombre not in tr:
            continue
        f = campo(v, "Initial Value")
        ingles, es = tr[nombre]
        if f["value"] != ingles:
            AVISOS.append(f"variable {nombre}: el inglés ha cambiado")
            continue
        f["value"] = es
        total += 1
    return total


def aplicar_scripts(bd):
    """Cambia llamadas Lua exactas en los userScript de los diálogos (cargos que cambian en partida...)."""
    tr = {k: v for k, v in cargar(os.path.join(TRAD, "scripts.json")).items() if not k.startswith("_")}
    usados, total = set(), 0
    for conv in bd["conversations"]:
        for e in conv["dialogueEntries"]:
            s = e.get("userScript") or ""
            nuevo = s
            for en, es in tr.items():
                if en in nuevo:
                    nuevo = nuevo.replace(en, es)
                    usados.add(en)
                    total += 1
            if nuevo != s:
                e["userScript"] = nuevo
    for en in tr:
        if en not in usados:
            AVISOS.append(f"script {en}: ya no aparece en ningún diálogo")
    return total


# ---------- Entidades ----------

def poner(nodo, ruta, ingles, es):
    for paso in ruta[:-1]:
        nodo = nodo[paso]
    if nodo[ruta[-1]] != ingles:
        return False
    nodo[ruta[-1]] = es
    return True


def aplicar_entidades(env):
    tas = {}
    for o in env.objects:
        if o.type.name == "TextAsset":
            d = o.read()
            s = d.m_Script if isinstance(d.m_Script, str) else d.m_Script.decode("utf-8")
            tas[d.m_Name] = (o, d, s, json.loads(s))
    mb_obj = next(o for o in env.objects if o.type.name == "MonoBehaviour")
    mb = mb_obj.read_typetree()
    # Cadena del MonoBehaviour que corresponde a cada TextAsset (son copias idénticas)
    gemelo = {}
    for k, v in mb.items():
        if isinstance(v, str):
            for nombre, (_, _, s, _) in tas.items():
                if v == s:
                    gemelo[nombre] = k
    tocados, total = set(), 0
    for ruta in sorted(glob.glob(os.path.join(TRAD, "entidades_*.json"))):
        nombre = os.path.basename(ruta)
        tr = cargar(ruta)
        fuente = {f"{e['tipo']}|{e['id']}|{'.'.join(map(str, e['ruta']))}": e
                  for e in cargar(os.path.join(TRAD, "fuente_" + nombre))}
        for clave, es in tr.items():
            if "|" not in clave:  # notas como "_nota"
                continue
            if PROHIBIDOS.match(clave):
                AVISOS.append(f"{clave}: no se traduce (el juego lo usa como clave)")
                continue
            if clave.endswith("|+"):  # añadir elementos a una lista (palabras clave del códex)
                tipo, iid, ruta = clave[:-2].split("|")
                items = tas[tipo][3]["items"]
                item = next((i for i in items if (i.get("Id") or i.get("id")) == iid), None)
                if item is None:
                    AVISOS.append(f"{clave}: el elemento ya no existe")
                    continue
                lista = item
                for paso in ruta.split("."):
                    lista = lista[int(paso)] if paso.isdigit() else lista[paso]
                for k in es:
                    if k not in lista:
                        lista.append(k)
                tocados.add(tipo)
                total += 1
                continue
            e = fuente[clave]
            items = tas[e["tipo"]][3]["items"]
            item = next((i for i in items if (i.get("Id") or i.get("id")) == e["id"]), None)
            if item is None or not poner(item, e["ruta"], e["en"], es):
                AVISOS.append(f"{clave}: el inglés ha cambiado o ya no existe")
                continue
            tocados.add(e["tipo"])
            total += 1
    for nombre in tocados:
        o, d, _, j = tas[nombre]
        nuevo = json.dumps(j, ensure_ascii=False, indent=2)
        d.m_Script = nuevo
        d.save()
        if nombre in gemelo:
            mb[gemelo[nombre]] = nuevo
        else:
            AVISOS.append(f"{nombre}: no encontré su copia en el MonoBehaviour")
    mb_obj.save_typetree(mb)
    return total


# ---------- Menús de las escenas ----------

def aplicar_escena(env):
    dic = {k: v for k, v in cargar(os.path.join(TRAD, "interfaz.json")).items() if not k.startswith("_")}
    total = 0
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            t = o.read_typetree()
        except Exception:
            continue
        cambiado = False
        for c in ("m_text", "locaId"):
            v = t.get(c)
            if isinstance(v, str) and v in dic:
                t[c] = dic[v]
                cambiado = True
                total += 1
        if cambiado:
            o.save_typetree(t)
    return total


BUNDLES = [
    ("database_assets_all_*.bundle", aplicar_dialogos),
    ("defaultlocalgroup_assets_assets_database_entitytextassets.asset_*.bundle", aplicar_entidades),
    ("scenes_scenes_assets_scenes_mainmenu.unity_*.bundle", aplicar_escena),
    ("scenes_scenes_assets_scenes_sordland.unity_*.bundle", aplicar_escena),
    ("scenes_scenes_assets_scenes_rizia.unity_*.bundle", aplicar_escena),
]
if SOLO_BASE:
    BUNDLES = [b for b in BUNDLES if "rizia" not in b[0]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restaurar", action="store_true")
    args = ap.parse_args()
    try:
        estado = cargar(ESTADO)
    except FileNotFoundError:
        estado = {}
    for patron, aplicar in BUNDLES:
        ruta = un_bundle(patron)
        nombre = os.path.basename(ruta)
        limpio = origen_limpio(ruta, estado)
        if args.restaurar:
            shutil.copy2(limpio, ruta)
            estado.pop(nombre, None)
            print(f"Restaurado: {nombre}")
            continue
        env = UnityPy.load(limpio)
        total = aplicar(env)
        datos = env.file.save(packer="original")
        with open(ruta + ".tmp", "wb") as f:
            f.write(datos)
        os.replace(ruta + ".tmp", ruta)
        estado[nombre] = sha256(ruta)
        # se guarda en el acto: si un bundle posterior falla, el siguiente arranque no debe tomar
        # este (ya traducido) por un original nuevo (pasó el 14-oct-2026; se arregló verificando en Steam)
        json.dump(estado, open(ESTADO + ".tmp", "w"), indent=1)
        os.replace(ESTADO + ".tmp", ESTADO)
        print(f"{total:6} textos en {nombre}")
    json.dump(estado, open(ESTADO, "w"), indent=1)
    for a in AVISOS:
        print("AVISO:", a)


if __name__ == "__main__":
    main()
