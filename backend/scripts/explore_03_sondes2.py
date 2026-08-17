"""Phase 1, étape 2b : formes d'appel de getSystemSettingValues/Desc,
et comportement de getSystemSettings face à une clé inconnue (conditionne
l'inventaire par listes de clés candidates).
"""

import asyncio
import json

from common import make_client

PROBES = [
    ("Values picture/pictureMode", "settings/getSystemSettingValues",
     {"category": "picture", "key": "pictureMode"}),
    ("Values picture/contrast (borne ?)", "settings/getSystemSettingValues",
     {"category": "picture", "key": "backlight"}),
    ("Values option/audioGuidance", "settings/getSystemSettingValues",
     {"category": "option", "key": "audioGuidance"}),
    ("Desc picture keys=[pictureMode]", "settings/getSystemSettingDesc",
     {"category": "picture", "keys": ["pictureMode"]}),
    ("Desc picture keys=[contrast,backlight]", "settings/getSystemSettingDesc",
     {"category": "picture", "keys": ["contrast", "backlight"]}),
    ("getSystemSettings clés de base", "settings/getSystemSettings",
     {"category": "picture", "keys": ["contrast", "backlight", "brightness", "color", "pictureMode"]}),
    ("getSystemSettings avec clé inconnue", "settings/getSystemSettings",
     {"category": "picture", "keys": ["contrast", "cleTotalementInconnue"]}),
]


async def main() -> None:
    client = await make_client()
    for label, uri, payload in PROBES:
        print(f"=== {label}")
        try:
            res = await client.request(uri, payload=payload)
            out = json.dumps(res, ensure_ascii=False)
            print(out[:3000] + (" …[tronqué]" if len(out) > 3000 else ""))
        except Exception as exc:
            print(f"ÉCHEC {type(exc).__name__}: {exc}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
