"""Curseurs du menu (luminosité, contraste…), et le décalage de la
luminosité adaptative."""

from homeassistant.components.number import (NumberEntity, NumberMode,
                                             RestoreNumber)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DECALAGE_MAX, DECALAGE_MIN
from .entite import EntiteReglage, EntiteTeleviseur, descriptions


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entites = [ReglageCurseur(entry, d) for d in descriptions() if d.plateforme == "number"]
    if entry.runtime_data.luminosite_adaptative is not None:
        entites.append(DecalageLuminositeAdaptative(entry))
    async_add_entities(entites)


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


class DecalageLuminositeAdaptative(EntiteTeleviseur, RestoreNumber):
    """Décalage ajouté à la cible de la courbe, que les automatisations de
    l'utilisateur règlent selon l'heure, la présence ou l'application
    (docs/etude-luminosite-adaptative.md, § 3.7, R11). Conservé au
    redémarrage ; le changer ne met jamais la fonction en pause."""

    _attr_translation_key = "luminosite_adaptative_decalage"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = DECALAGE_MIN
    _attr_native_max_value = DECALAGE_MAX
    _attr_native_step = 1

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_decalage"
        self._fonction = entry.runtime_data.luminosite_adaptative
        self._ecrite: int | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (derniere := await self.async_get_last_number_data()) is not None:
            self._fonction.restaurer_decalage(derniere.native_value)
        self.async_on_remove(self._fonction.ecouter(self._sur_changement))

    def _sur_changement(self) -> None:
        # La fonction prévient à chaque mesure : n'écrire que si la valeur
        # a changé (panneau, autre automatisation).
        if self._fonction.decalage != self._ecrite:
            self.async_write_ha_state()

    def async_write_ha_state(self) -> None:
        self._ecrite = self._fonction.decalage
        super().async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._fonction.decalage

    async def async_set_native_value(self, value: float) -> None:
        self._fonction.regler_decalage(value, "home_assistant")
