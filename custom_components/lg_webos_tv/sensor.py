"""Capteurs : réglages en lecture seule du menu, voie d'écriture (diagnostic)."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entite import EntiteReglage, EntiteTeleviseur, descriptions


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([
        *(ReglageLectureSeule(entry, d) for d in descriptions()
          if d.plateforme == "sensor"),
        VoieEcriture(entry),
    ])


class ReglageLectureSeule(EntiteReglage, SensorEntity):
    def __init__(self, entry, description) -> None:
        super().__init__(entry, description)
        if description.choix:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(description.choix)

    @property
    def native_value(self) -> str | None:
        valeur = self.valeur
        if valeur is None:
            return None
        if self.description_reglage.choix:
            return self.description_reglage.libelle_de(valeur)
        return str(valeur)


class VoieEcriture(EntiteTeleviseur, SensorEntity):
    """Voie par laquelle le téléviseur accepte nos écritures : setSystemSettings
    direct (ssap), pont createAlert (alerte), ou aucune (consultation)."""

    _attr_translation_key = "voie_ecriture"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ssap", "alerte", "aucune"]

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "voie_ecriture"

    @property
    def available(self) -> bool:
        return self._tv.etat_connexion == "connecte"

    @property
    def native_value(self) -> str | None:
        if self._tv.ecriture_possible is None:
            return None
        return self._tv.voie_ecriture or "aucune"
