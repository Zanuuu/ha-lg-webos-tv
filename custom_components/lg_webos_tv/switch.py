"""Interrupteurs du menu."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entite import EntiteReglage, descriptions


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(ReglageInterrupteur(entry, d) for d in descriptions()
                       if d.plateforme == "switch")


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
