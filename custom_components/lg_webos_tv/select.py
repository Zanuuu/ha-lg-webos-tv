"""Listes de choix du menu (mode d'image, TruMotion…)."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entite import EntiteReglage, descriptions


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(ReglageListe(entry, d) for d in descriptions()
                       if d.plateforme == "select")


class ReglageListe(EntiteReglage, SelectEntity):
    def __init__(self, entry, description) -> None:
        super().__init__(entry, description)
        self._attr_options = list(description.choix)

    @property
    def current_option(self) -> str | None:
        return self.description_reglage.libelle_de(self.valeur)

    async def async_select_option(self, option: str) -> None:
        await self._ecrire(self.description_reglage.choix[option])
