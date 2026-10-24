"""Curseurs du menu (luminosité, contraste…)."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entite import EntiteReglage, descriptions


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(ReglageCurseur(entry, d) for d in descriptions()
                       if d.plateforme == "number")


class ReglageCurseur(EntiteReglage, NumberEntity):
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry, description) -> None:
        super().__init__(entry, description)
        bornes = description.bornes
        self._attr_native_min_value = bornes["min"]
        self._attr_native_max_value = bornes["max"]
        self._attr_native_step = bornes.get("pas", 1)

    @property
    def native_value(self) -> float | None:
        try:
            return float(self.valeur)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        # Le téléviseur n'accepte que des entiers pour ces réglages.
        await self._ecrire(int(round(value)))
