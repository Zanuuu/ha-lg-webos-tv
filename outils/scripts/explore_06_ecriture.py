"""Phase 1, étape 3 : test d'écriture sur la netteté (sans risque).

Lecture de la valeur actuelle, écriture d'une valeur différente, relecture de
confirmation, restauration de la valeur d'origine, relecture finale.
"""

import asyncio
import json

from common import make_client


async def read_sharpness(client) -> int:
    res = await client.request(
        "settings/getSystemSettings",
        {"category": "picture", "keys": ["sharpness", "pictureMode"]},
    )
    settings = res["settings"]
    print(f"  sharpness={settings['sharpness']} (mode {settings['pictureMode']})")
    return int(settings["sharpness"])


async def write_sharpness(client, value: int) -> dict:
    return await client.request(
        "settings/setSystemSettings",
        {"category": "picture", "settings": {"sharpness": value}},
    )


async def main() -> None:
    client = await make_client()

    print("Valeur d'origine :")
    original = await read_sharpness(client)

    target = original + 1 if original < 50 else original - 1
    print(f"Écriture de {target} :")
    res = await write_sharpness(client, target)
    print(f"  réponse : {json.dumps(res, ensure_ascii=False)}")

    await asyncio.sleep(1)
    print("Relecture :")
    after = await read_sharpness(client)
    print("  -> écriture appliquée" if after == target else "  -> ÉCART !")

    print(f"Restauration de {original} :")
    await write_sharpness(client, original)
    await asyncio.sleep(1)
    print("Relecture finale :")
    final = await read_sharpness(client)
    print("  -> restauré" if final == original else "  -> NON RESTAURÉ !")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
