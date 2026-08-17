"""Phase 2, passe 3 : test de lecture des clés découvertes dans le firmware
(absentes des candidats de la phase 1)."""

import asyncio
import json

from common import make_client

PROBES = {
    "dimensionInfo": ["_3dStatus", "colorSystem", "dynamicRange", "gameInput", "input"],
    "network": ["wifiConnection", "wiredConnection"],
    "option": ["remoteSetting"],
    "other": ["adaptivePowerDelivery", "autoInputSwitch", "enableLighting", "inputCompatibilityMode"],
    "picture": ["pictureTest", "responseTime"],
    "sound": ["_3dSoundZooming", "ac4DialogueEnhancer", "soundTest"],
    "voiceframework": ["thinQtvTTSBlock"],
    "monitor": ["mapping_monitor_opt"],
}


async def main() -> None:
    client = await make_client()
    for cat, keys in PROBES.items():
        for key in keys:
            try:
                res = await asyncio.wait_for(client.request(
                    "settings/getSystemSettings",
                    {"category": cat, "keys": [key]}), 10)
                print(f"OK  {cat}/{key} = {json.dumps(res.get('settings'), ensure_ascii=False)[:120]}")
            except Exception as exc:
                msg = str(exc)
                print(f"ERR {cat}/{key} : {msg[:110]}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
