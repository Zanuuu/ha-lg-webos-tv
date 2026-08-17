"""Extrait les clés candidates par catégorie depuis available_settings_G5.md
(doc bscpylgtv, G5 firmware 33.21.81) vers candidats.json.

Les clés candidates servent uniquement de liste d'essai : l'inventaire réel
est établi en interrogeant notre téléviseur (explore_05_inventaire.py).
"""

import json
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
DST = Path(__file__).parent / "candidats.json"

text = SRC.read_text()

# Sections "#### `"cat"` category - available settings" suivies d'un bloc json.
pattern = re.compile(
    r'#### `"?([a-zA-Z]*)"?` category - available settings[^\n]*\n```json\n(.*?)\n```',
    re.DOTALL,
)

candidates: dict[str, list[str]] = {}
for match in pattern.finditer(text):
    category = match.group(1)
    try:
        block = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        print(f"Catégorie {category!r} : JSON invalide ({exc}), ignorée", file=sys.stderr)
        continue
    candidates[category] = sorted(block.keys())

# Complément : clés des sections « public API » (get/set), certaines absentes
# des blocs par catégorie (soundMode, onTimerVolume, twinTv…).
public_pattern = re.compile(
    r"#### some of the settings above can (?:also be set|be retrieved)[^\n]*\n```json\n(.*?)\n```",
    re.DOTALL,
)
for match in public_pattern.finditer(text):
    block = json.loads(match.group(1))
    for category, keys in block.items():
        merged = set(candidates.get(category, [])) | set(keys)
        candidates[category] = sorted(merged)

DST.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n")
total = sum(len(v) for v in candidates.values())
print(f"{len(candidates)} catégories, {total} clés candidates -> {DST}")
for category, keys in sorted(candidates.items()):
    print(f"  {category or '\"\"'}: {len(keys)}")
