"""Phase 2, passe 3 : extraction des libellés/descriptions/choix français de
l'app Réglages du firmware 33.31.68.

Sources (copies dans data/firmware/, hors git) :
- settings-main.js : bundle Enact minifié de com.palm.app.settings ;
- settings-strings-fr.json : dictionnaire de traduction EN -> FR (ilib).

Méthode (analyse textuelle ciblée, pas d'AST) :
1. Les listes `keys:[…]` du bundle donnent l'ensemble des clés API que l'app
   manipule réellement.
2. Pour chaque clé connue, les sites d'appel `xx("cle")` sont fenêtrés ; les
   chaînes anglaises de la fenêtre qui existent dans le dictionnaire de
   traduction sont récoltées : les courtes sont des titres candidats, les
   longues des descriptions candidates. Les objets `{key:"…",value:"…"}`
   (traductions à variantes) sont résolus.
3. Les fabriques `case"nom":return{valeurApi:Up(...)…}` donnent les tables
   valeur API -> libellé de choix.

Sortie : data/firmware-menus.json, à dépouiller par croiser_firmware.py.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "data" / "firmware" / "settings-main.js"
STRINGS = ROOT / "data" / "firmware" / "settings-strings-fr.json"
CANDIDATES = Path(__file__).parent / "candidats.json"
OUTPUT = ROOT / "data" / "firmware-menus.json"

WINDOW = 900

s = BUNDLE.read_text(encoding="utf-8", errors="replace")
tr = json.loads(STRINGS.read_text())


def fr(en: str) -> str | None:
    return tr.get(en)


# --- 1. Clés API manipulées par l'app (listes keys:[...]) -------------------
app_keys: set[str] = set()
for m in re.finditer(r'keys:\[((?:"[A-Za-z0-9_]+",?)+)\]', s):
    app_keys.update(re.findall(r'"([A-Za-z0-9_]+)"', m.group(1)))

# Variante avec catégorie explicite : category:"picture"…keys:[…] (ordre
# variable, on cherche les deux champs dans une même fenêtre d'objet).
app_keys_par_categorie: dict[str, set[str]] = {}
for m in re.finditer(r'category:"([a-zA-Z]*)"[^{}]{0,200}?keys:\[((?:"[A-Za-z0-9_]+",?)+)\]', s):
    cat, keys = m.group(1), re.findall(r'"([A-Za-z0-9_]+)"', m.group(2))
    app_keys_par_categorie.setdefault(cat, set()).update(keys)
for m in re.finditer(r'keys:\[((?:"[A-Za-z0-9_]+",?)+)\][^{}]{0,200}?category:"([a-zA-Z]*)"', s):
    keys, cat = re.findall(r'"([A-Za-z0-9_]+)"', m.group(1)), m.group(2)
    app_keys_par_categorie.setdefault(cat, set()).update(keys)

candidates = json.loads(CANDIDATES.read_text())
known_keys = app_keys | {k for keys in candidates.values() for k in keys}

# --- 2. Tables valeur API -> libellé (fabriques case"nom":return{...}) ------
# Deux formes de libellé : Xx("EN") et Xx({key:"cle",value:"EN"}).
PAIR = re.compile(
    r'([A-Za-z0-9_]+):[A-Za-z_$]{1,4}\((?:"((?:[^"\\]|\\.)*)"'
    r'|\{key:"([^"]+)",value:"((?:[^"\\]|\\.)*)"\})\)'
)
display_names: dict[str, dict] = {}
for m in re.finditer(r'case"([A-Za-z0-9_]+)":return\{', s):
    nom = m.group(1)
    debut = m.end() - 1
    # Fin du bloc : accolade fermante appariée (objets plats, un niveau suffit
    # sauf objets imbriqués rares -> on équilibre les accolades).
    profondeur, i = 0, debut
    while i < len(s):
        if s[i] == "{":
            profondeur += 1
        elif s[i] == "}":
            profondeur -= 1
            if profondeur == 0:
                break
        i += 1
    bloc = s[debut:i + 1]
    table = {}
    for valeur, en, cle_tr, en_variante in PAIR.findall(bloc):
        # Dans une table de choix le contexte est sûr : une chaîne absente du
        # dictionnaire est une traduction identité (ex. « FILMMAKER MODE »).
        if en:
            libelle_en = en
            libelle_fr = fr(en) or en
        else:
            libelle_en = en_variante
            libelle_fr = fr(cle_tr) or fr(en_variante) or en_variante
        table[valeur] = {"en": libelle_en, "fr": libelle_fr}
    if table:
        # Certains noms de fabrique apparaissent deux fois (libellés + ids de
        # vidéos en langue des signes) : on garde la table la plus traduite.
        if nom not in display_names or len(table) > len(display_names[nom]):
            display_names[nom] = table

# --- 3. Fenêtres autour des sites d'appel par clé ---------------------------
STR_CALL = re.compile(r'[A-Za-z_$]{1,4}\("((?:[^"\\]|\\.)*)"\)')
VAR_CALL = re.compile(r'[A-Za-z_$]{1,4}\(\{key:"([^"]+)",value:"((?:[^"\\]|\\.)*)"\}\)')
COND_CALL = re.compile(
    r'[A-Za-z_$]{1,4}\([A-Za-z_$][A-Za-z0-9_$.]*\?"((?:[^"\\]|\\.)*)":"((?:[^"\\]|\\.)*)"\)'
)
DN_CALL = re.compile(r'[A-Za-z_$]{1,4}\("([A-Za-z0-9_]+)"\)')

resultat: dict[str, dict] = {}
for cle in sorted(known_keys):
    infos = {"titres": [], "descriptions": [], "display_names": []}
    for m in re.finditer(r'\("' + re.escape(cle) + r'"\)', s):
        fenetre = s[m.end():m.end() + WINDOW]
        # Chaînes conditionnelles (variantes selon modèle) d'abord : elles
        # seraient sinon partiellement capturées par STR_CALL.
        for a, b in COND_CALL.findall(fenetre):
            for en in (a, b):
                t = fr(en)
                if t:
                    cible = infos["descriptions"] if len(en) > 45 else infos["titres"]
                    item = {"en": en, "fr": t, "variante": True}
                    if item not in cible:
                        cible.append(item)
        for en in STR_CALL.findall(fenetre):
            t = fr(en)
            if t is None:
                if en in display_names and en not in infos["display_names"]:
                    infos["display_names"].append(en)
                continue
            cible = infos["descriptions"] if len(en) > 45 else infos["titres"]
            item = {"en": en, "fr": t}
            if item not in cible:
                cible.append(item)
        for cle_tr, en in VAR_CALL.findall(fenetre):
            t = fr(cle_tr) or fr(en)
            if t is None:
                continue
            cible = infos["descriptions"] if len(en) > 45 else infos["titres"]
            item = {"en": en, "fr": t, "cle_traduction": cle_tr}
            if item not in cible:
                cible.append(item)
    if infos["titres"] or infos["descriptions"] or infos["display_names"]:
        resultat[cle] = infos

sortie = {
    "cles_app": sorted(app_keys),
    "cles_app_par_categorie": {c: sorted(k) for c, k in sorted(app_keys_par_categorie.items())},
    "reglages": resultat,
    "tables_choix": display_names,
}
OUTPUT.write_text(json.dumps(sortie, indent=1, ensure_ascii=False) + "\n")
print(f"{len(app_keys)} clés manipulées par l'app, {len(resultat)} clés documentées, "
      f"{len(display_names)} tables de choix -> {OUTPUT}")
