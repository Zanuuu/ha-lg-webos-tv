"""Phase 1, étape 2a : sonder les formes de requêtes du service settings.

Objectif : savoir si l'API sait énumérer les clés d'une catégorie sans liste
fournie, et si getSystemSettingValues / getSystemSettingDesc sont joignables
en SSAP direct (découverte des plages de valeurs).
"""

import asyncio
import json

from common import make_client

PROBES = [
    ("getSystemSettings picture sans keys", "settings/getSystemSettings", {"category": "picture"}),
    ("getSystemSettings picture keys=[]", "settings/getSystemSettings", {"category": "picture", "keys": []}),
    ("getSystemSettings sans payload", "settings/getSystemSettings", {}),
    ("getSystemSettingValues pictureMode", "settings/getSystemSettingValues", {"key": "pictureMode"}),
    ("getSystemSettingValues category+key", "settings/getSystemSettingValues", {"category": "picture", "key": "contrast"}),
    ("getSystemSettingDesc picture", "settings/getSystemSettingDesc", {"category": "picture"}),
    ("getCurrentSettings", "settings/getCurrentSettings", {"category": "picture"}),
]


async def main() -> None:
    client = await make_client()
    for label, uri, payload in PROBES:
        print(f"=== {label}")
        try:
            res = await client.request(uri, payload=payload)
            out = json.dumps(res, ensure_ascii=False)
            print(out[:2000] + (" …[tronqué]" if len(out) > 2000 else ""))
        except Exception as exc:
            print(f"ÉCHEC {type(exc).__name__}: {exc}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
