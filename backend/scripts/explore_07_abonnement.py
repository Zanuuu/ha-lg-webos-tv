"""Phase 1, étape 4 : abonnement aux changements de réglages.

S'abonne à getSystemSettings (subscribe) sur quelques clés picture, puis :
- mode "api" (défaut) : modifie sharpness via l'API et vérifie qu'une
  notification arrive, puis restaure ;
- mode "attente" : écoute passivement pendant N secondes, le temps de faire
  un changement à la télécommande sur le téléviseur.
"""

import asyncio
import json
import sys

from common import make_client

KEYS = ["sharpness", "backlight", "contrast", "brightness", "color",
        "pictureMode", "energySaving"]


async def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    wait_s = int(sys.argv[2]) if len(sys.argv) > 2 else 300

    client = await make_client()
    events: list[dict] = []

    async def on_change(payload: dict) -> None:
        events.append(payload)
        print(f"NOTIFICATION : {json.dumps(payload, ensure_ascii=False)}", flush=True)

    first = await client.subscribe(
        on_change, "settings/getSystemSettings",
        {"category": "picture", "keys": KEYS},
    )
    print(f"Abonnement accepté, état initial : "
          f"{json.dumps(first.get('settings', {}), ensure_ascii=False)}", flush=True)

    if mode == "api":
        original = int(first["settings"]["sharpness"])
        target = original + 1 if original < 50 else original - 1
        print(f"Modification de sharpness {original} -> {target} via l'API…", flush=True)
        await client.request("settings/setSystemSettings",
                             {"category": "picture", "settings": {"sharpness": target}})
        await asyncio.sleep(5)
        print(f"Restauration de sharpness -> {original}…", flush=True)
        await client.request("settings/setSystemSettings",
                             {"category": "picture", "settings": {"sharpness": original}})
        await asyncio.sleep(5)
        print(f"Bilan : {len(events)} notification(s) reçue(s) après 2 écritures.")
    else:
        print(f"Écoute passive pendant {wait_s} s : fais un changement de réglage "
              f"d'image à la télécommande (ex. netteté, ou changer le mode d'image).",
              flush=True)
        await asyncio.sleep(wait_s)
        print(f"Bilan : {len(events)} notification(s) reçue(s) pendant l'attente.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
