"""Phase 1, étape 2 : inventaire complet des réglages lisibles sur NOTRE G5.

Pour chaque catégorie et chaque clé candidate (candidats.json) :
- getSystemSettings   -> la clé est-elle lisible, et sa valeur actuelle ;
- getSystemSettingDesc -> son descripteur (type, bornes, choix, dimensions).

Les clés rejetées sont retirées par lots grâce à l'errorText qui les nomme.
Résultat : backend/app/inventaire-api.json (versionné, base de la phase 2).
"""

import asyncio
import json
import re
from pathlib import Path

from bscpylgtv.exceptions import PyLGTVCmdError, PyLGTVServiceNotFoundError

from common import make_client

CANDIDATES_FILE = Path(__file__).parent / "candidats.json"
OUTPUT_FILE = Path(__file__).resolve().parents[2] / "custom_components" / "lg_webos_tv" / "inventaire-api.json"
BATCH_SIZE = 20
REQUEST_TIMEOUT = 15

REJECTED_RE = [
    re.compile(r"\(\s*(.*?)\s*\)\s*$"),          # "… ( k1, k2 )"
    re.compile(r"key\(?s?\)?\s*:\s*(.*?)\s*$"),  # "… the key(s): k1, k2"
]


def parse_rejected(error_text: str) -> list[str]:
    for regex in REJECTED_RE:
        match = regex.search(error_text)
        if match:
            keys = [k.strip() for k in match.group(1).split(",")]
            return [k for k in keys if k]
    return []


async def probe(client, uri: str, category: str, keys: list[str]) -> tuple[dict, list[str], list[str]]:
    """Sonde un lot de clés ; renvoie (payload accepté, clés retenues, rejets)."""
    keys = list(keys)
    rejected_all: list[str] = []
    while keys:
        payload = {"category": category, "keys": keys}
        try:
            res = await asyncio.wait_for(
                client.request(uri, payload=payload), REQUEST_TIMEOUT
            )
            return res, keys, rejected_all
        except PyLGTVCmdError as exc:
            error_text = exc.args[0].get("payload", {}).get("errorText", "") if exc.args else ""
            rejected = [k for k in parse_rejected(error_text) if k in keys]
            if not rejected:
                # Erreur non analysable : repli clé par clé.
                if len(keys) == 1:
                    rejected_all.append(keys[0])
                    return {}, [], rejected_all
                mid = len(keys) // 2
                left = await probe(client, uri, category, keys[:mid])
                right = await probe(client, uri, category, keys[mid:])
                merged: dict = {}
                for part in (left[0], right[0]):
                    for key, value in part.items():
                        if isinstance(value, dict) and isinstance(merged.get(key), dict):
                            merged[key].update(value)
                        elif isinstance(value, list) and isinstance(merged.get(key), list):
                            merged[key].extend(value)
                        else:
                            merged[key] = value
                return merged, left[1] + right[1], rejected_all + left[2] + right[2]
            keys = [k for k in keys if k not in rejected]
            rejected_all.extend(rejected)
    return {}, [], rejected_all


async def main() -> None:
    candidates: dict[str, list[str]] = json.loads(CANDIDATES_FILE.read_text())
    client = await make_client()

    inventory: dict = {"categories": {}}
    try:
        software = await client.get_software_info()
    except PyLGTVCmdError:
        # Depuis webOS 11, READ_UPDATE_INFO est SECURE : refusé au manifeste
        # non signé. La version est alors relevée à la main (EPK, menu TV).
        software = {}
    inventory["firmware"] = {
        "product_name": software.get("product_name"),
        "major_ver": software.get("major_ver"),
        "minor_ver": software.get("minor_ver"),
    }
    current = await client.request(
        "settings/getSystemSettings",
        {"category": "picture", "keys": ["pictureMode"]},
    )
    inventory["contexte"] = {"pictureMode": current.get("settings", {}).get("pictureMode")}
    print(f"Firmware {software.get('major_ver')}.{software.get('minor_ver')}, "
          f"mode d'image actif : {inventory['contexte']['pictureMode']}")

    for category, keys in sorted(candidates.items()):
        entry = {"lisibles": {}, "descripteurs": {}, "rejetees_lecture": [],
                 "rejetees_desc": [], "erreurs": []}
        inventory["categories"][category] = entry

        for start in range(0, len(keys), BATCH_SIZE):
            batch = keys[start:start + BATCH_SIZE]
            try:
                res, accepted, rejected = await probe(
                    client, "settings/getSystemSettings", category, batch
                )
                entry["lisibles"].update(res.get("settings", {}))
                entry["rejetees_lecture"].extend(rejected)
            except (PyLGTVServiceNotFoundError, asyncio.TimeoutError) as exc:
                entry["erreurs"].append(f"lecture {batch}: {type(exc).__name__} {exc}")
                continue

        readable = sorted(entry["lisibles"].keys())
        for start in range(0, len(readable), BATCH_SIZE):
            batch = readable[start:start + BATCH_SIZE]
            try:
                res, accepted, rejected = await probe(
                    client, "settings/getSystemSettingDesc", category, batch
                )
                for item in res.get("results", []):
                    entry["descripteurs"][item.get("key")] = item
                entry["rejetees_desc"].extend(rejected)
            except (PyLGTVServiceNotFoundError, asyncio.TimeoutError) as exc:
                entry["erreurs"].append(f"desc {batch}: {type(exc).__name__} {exc}")
                continue

        print(f"{category or '\"\"'}: {len(entry['lisibles'])}/{len(keys)} lisibles, "
              f"{len(entry['descripteurs'])} descripteurs, "
              f"{len(entry['erreurs'])} erreurs")

    await client.disconnect()

    OUTPUT_FILE.write_text(json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Inventaire écrit dans {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
