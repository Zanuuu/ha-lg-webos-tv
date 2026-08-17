"""Phase 1, étape 2c : getSystemSettingDesc tolère-t-il clés inconnues et
jokers ? Détermine la stratégie d'inventaire par listes candidates."""

import asyncio
import json

from common import make_client

PROBES = [
    ("Desc avec clé inconnue mélangée", "settings/getSystemSettingDesc",
     {"category": "picture", "keys": ["contrast", "cleTotalementInconnue"]}),
    ("Desc joker *", "settings/getSystemSettingDesc",
     {"category": "picture", "keys": ["*"]}),
    ("Desc catégorie inconnue", "settings/getSystemSettingDesc",
     {"category": "categorieInconnue", "keys": ["contrast"]}),
    ("Desc sans catégorie", "settings/getSystemSettingDesc",
     {"keys": ["audioGuidance"]}),
]


async def main() -> None:
    client = await make_client()
    for label, uri, payload in PROBES:
        print(f"=== {label}")
        try:
            res = await client.request(uri, payload=payload)
            out = json.dumps(res, ensure_ascii=False)
            print(out[:2500] + (" …[tronqué]" if len(out) > 2500 else ""))
        except Exception as exc:
            print(f"ÉCHEC {type(exc).__name__}: {exc}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
