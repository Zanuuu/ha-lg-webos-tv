"""Phase 2, passe 1 : extraction fidèle du chapitre 6 « Paramètres » du guide
webOS 25 français vers un JSON brut (data/guide-chapitre6.json).

Rien n'est reformulé : libellés, descriptions et notes sont le texte exact du
guide. Les images de navigation sont remplacées par leur attribut alt entre
crochets quand elles portent du sens (« Tous les paramètres », « suivant »).
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "guide-webos25-fre.html"
DST = ROOT / "data" / "guide-chapitre6.json"


def texte(node: Tag, *, skip: set[str] = frozenset()) -> str:
    """Texte d'un nœud, images remplacées par leur alt, sans les sous-listes."""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            if child.name in skip:
                continue
            if child.name == "img":
                alt = child.get("alt", "")
                if alt and alt != "suivant":
                    parts.append(f"[{alt}]")
                elif alt == "suivant":
                    parts.append("→")
            elif child.name == "br":
                parts.append("\n")
            else:
                parts.append(texte(child, skip=skip))
    text = "".join(parts)
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r" *\n *", "\n", text).strip()


def chemin_depuis_seq(seq: Tag) -> list[str]:
    """Chemin de menu : libellés en <strong> du <li> qui contient l'icône
    « Tous les paramètres » (c'est la ligne « Entrez le chemin suivant »)."""
    for li in seq.find_all("li", recursive=False):
        if li.find("img", alt="Tous les paramètres"):
            return [s.get_text(strip=True) for s in li.find_all("strong")]
    return []


def parse_settings_list(ul: Tag) -> list[dict]:
    reglages = []
    for li in ul.find_all("li", recursive=False):
        notes_ul = li.find("ul", class_="text-body-note", recursive=False)
        sous_ul = [u for u in li.find_all("ul", class_="settings-list", recursive=False)]
        libelle_p = li.find("p", recursive=False)
        libelle = libelle_p.get_text(strip=True) if libelle_p else ""
        corps = texte(li, skip={"ul", "p"})
        item = {"libelle": libelle, "description": corps}
        options_ul = li.find("ul", class_="list-note", recursive=False)
        if options_ul:
            options, options_notes = [], []
            for opt_li in options_ul.find_all("li", recursive=False):
                opt_texte = texte(opt_li, skip={"ul"})
                premier = opt_li.find(["strong"])
                # Une option est de la forme « <strong>Libellé</strong>: description ».
                if premier and ":" in opt_texte and opt_texte.index(":") < 60:
                    opt_libelle, _, opt_desc = opt_texte.partition(":")
                    options.append({"libelle": opt_libelle.strip(),
                                    "description": opt_desc.strip()})
                else:
                    options_notes.append(opt_texte)
            if options:
                item["options"] = options
            if options_notes:
                item.setdefault("notes_options", []).extend(options_notes)
        if notes_ul:
            item["notes"] = [texte(n) for n in notes_ul.find_all("li", recursive=False)]
        if sous_ul:
            item["sous_reglages"] = [r for u in sous_ul for r in parse_settings_list(u)]
        reglages.append(item)
    return reglages


def main() -> None:
    html = SRC.read_text()

    # Découpage linéaire par position des titres pour éviter toute duplication
    # due à l'imbrication HTML : chaque sous-section = texte entre son titre
    # et le titre suivant. Chapitre 6 : de l'ancre 5109 à l'ancre 11115.
    headings = [
        (m.start(), m.group(2), m.group(3))
        for m in re.finditer(r'<h([2-4]) id="(\d+)">([^<]*)</h\1>', html)
    ]
    starts = [i for i, (_, ancre, _) in enumerate(headings) if ancre == "5109"]
    ends = [i for i, (_, ancre, _) in enumerate(headings) if ancre == "11115"]
    if not starts or not ends:
        raise SystemExit("ancres du chapitre 6 introuvables")

    sections = []
    for idx in range(starts[0], ends[0]):
        pos, ancre, titre_brut = headings[idx]
        fin = headings[idx + 1][0] if idx + 1 < len(headings) else len(html)
        num_match = re.match(r"(6(?:\.\d+)*)\.\s+(.*)", titre_brut.strip())
        if not num_match:
            continue
        fragment = BeautifulSoup(html[pos:fin], "lxml")
        current = {
            "num": num_match.group(1),
            "titre": num_match.group(2),
            "ancre": ancre,
            "chemins": [],
            "intro": "",
            "etapes": [],
            "notes": [],
            "reglages": [],
        }
        sections.append(current)

        for seq in fragment.find_all("ol", class_="seq-list"):
            chemin = chemin_depuis_seq(seq)
            if chemin:
                current["chemins"].append(chemin)
        for ul in fragment.find_all("ul", class_="settings-list"):
            if ul.find_parent("ul", class_="settings-list"):
                continue  # traité récursivement
            current["reglages"].extend(parse_settings_list(ul))
        for div in fragment.find_all("div", class_="text-body"):
            intro = texte(div, skip={"ol", "ul", "table"})
            if intro:
                current["intro"] = intro
            break
        # Étapes des séquences hors ligne de chemin (souvent la description
        # de l'action ou des choix Activé/Désactivé).
        for seq in fragment.find_all("ol", class_="seq-list"):
            for li in seq.find_all("li", recursive=False):
                if li.find("img", alt="Tous les paramètres") or li.find("img", alt="Paramètres"):
                    continue
                t = texte(li, skip={"ul"})
                if t and not t.startswith("Appuyez sur"):
                    current["etapes"].append(t)
        # Notes de niveau section (hors settings-list) : conditions,
        # limitations.
        for note_ul in fragment.find_all("ul", class_="text-body-note"):
            if note_ul.find_parent("ul", class_="settings-list"):
                continue
            for li in note_ul.find_all("li", recursive=False):
                current["notes"].append(texte(li))

    DST.write_text(json.dumps(sections, indent=1, ensure_ascii=False) + "\n")
    n_reglages = sum(len(s["reglages"]) for s in sections)
    print(f"{len(sections)} sous-sections, {n_reglages} réglages -> {DST}")


if __name__ == "__main__":
    asyncio = None  # pas d'accès TV ici
    main()
