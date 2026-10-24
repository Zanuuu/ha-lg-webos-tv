"""Phase 1, étape 1 : appairage et identification du téléviseur."""

import asyncio
import json

from common import KEY_DB, make_client


async def main() -> None:
    client = await make_client()
    print(f"Appairage réussi, clé conservée dans {KEY_DB}")

    software = await client.get_software_info()
    print("--- software_info")
    print(json.dumps(software, indent=2, ensure_ascii=False))

    system = await client.get_system_info()
    print("--- system_info")
    print(json.dumps(system, indent=2, ensure_ascii=False))

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
