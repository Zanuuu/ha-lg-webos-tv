"""Interrupteurs du menu, et celui de la luminosité adaptative."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import (ExtraStoredData,
                                                 RestoredExtraData, RestoreEntity)
from homeassistant.util import dt as dt_util

from .entite import EntiteReglage, EntiteTeleviseur, descriptions


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entites = [ReglageInterrupteur(entry, d) for d in descriptions()
               if d.plateforme == "switch"]
    if entry.runtime_data.luminosite_adaptative is not None:
        entites.append(LuminositeAdaptativeActive(entry))
    async_add_entities(entites)


class ReglageInterrupteur(EntiteReglage, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        # "on"/"off" pour la plupart des clés, booléen natif pour quelques-unes
        # (arbre.CLES_BOOLEENNES_NATIVES).
        valeur = self.valeur
        if valeur is None:
            return None
        return valeur is True or valeur == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        # arbre.preparer_ecriture convertit en "on"/"off" quand la clé l'attend.
        await self._ecrire(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._ecrire(False)


class LuminositeAdaptativeActive(EntiteTeleviseur, SwitchEntity, RestoreEntity):
    """Active la luminosité adaptative. Conserve aussi la fin et la cause
    d'une pause en cours : un redémarrage de Home Assistant n'écrase pas un
    réglage manuel."""

    _attr_translation_key = "luminosite_adaptative"

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative"
        self._fonction = entry.runtime_data.luminosite_adaptative

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        derniere = await self.async_get_last_state()
        extra = await self.async_get_last_extra_data()
        extra = extra.as_dict() if extra else {}
        fin_pause = extra.get("fin_pause")
        self._fonction.restaurer(
            derniere is None or derniere.state != "off",
            dt_util.parse_datetime(fin_pause) if fin_pause else None,
            extra.get("cause_pause"))
        self.async_on_remove(self._fonction.ecouter(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return self._fonction.active

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        fin_pause = self._fonction.fin_pause
        return RestoredExtraData(
            {"fin_pause": fin_pause.isoformat() if fin_pause else None,
             "cause_pause": self._fonction.cause_pause})

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._fonction.activer(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._fonction.activer(False)
