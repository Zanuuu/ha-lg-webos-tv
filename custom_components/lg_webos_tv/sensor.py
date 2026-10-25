"""Capteurs : réglages en lecture seule du menu, voie d'écriture (diagnostic),
état de la luminosité adaptative."""

from homeassistant.components.sensor import (RestoreSensor, SensorDeviceClass,
                                             SensorEntity, SensorStateClass)
from homeassistant.const import LIGHT_LUX, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entite import EntiteReglage, EntiteTeleviseur, descriptions
from .ambiance import AMBIANCES
from .luminosite_adaptative import ETATS, lux_affiche


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entites = [
        *(ReglageLectureSeule(entry, d) for d in descriptions()
          if d.plateforme == "sensor"),
        VoieEcriture(entry),
    ]
    if entry.runtime_data.luminosite_adaptative is not None:
        entites += [EtatLuminositeAdaptative(entry), LuxFiltre(entry),
                    AmbianceLuminosite(entry)]
    async_add_entities(entites)


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


class EtatLuminositeAdaptative(EntiteTeleviseur, SensorEntity):
    """Ce que fait la luminosité adaptative et pourquoi : active, en pause
    après un réglage manuel, mode d'image laissé de côté…"""

    _attr_translation_key = "luminosite_adaptative_etat"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ETATS

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_etat"
        self._fonction = entry.runtime_data.luminosite_adaptative

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._fonction.ecouter(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        return self._fonction.etat

    @property
    def extra_state_attributes(self) -> dict:
        return self._fonction.attributs()


class LuxFiltre(EntiteTeleviseur, SensorEntity):
    """Lux lissé et confirmé de la luminosité adaptative (capteur de secours
    compris, en lux du principal), pour les automatisations : disponible
    téléviseur éteint, fonction en pause ou désactivée."""

    _attr_translation_key = "luminosite_adaptative_lux_filtre"
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_suggested_display_precision = 1

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_lux_filtre"
        self._fonction = entry.runtime_data.luminosite_adaptative
        self._ecrite: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._fonction.ecouter_signal(self._sur_signal))

    def _sur_signal(self) -> None:
        if lux_affiche(self._fonction.lux_filtre) != self._ecrite:
            self.async_write_ha_state()

    def async_write_ha_state(self) -> None:
        self._ecrite = lux_affiche(self._fonction.lux_filtre)
        super().async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._fonction.lux_filtre is not None

    @property
    def native_value(self) -> float | None:
        return lux_affiche(self._fonction.lux_filtre)


class AmbianceLuminosite(EntiteTeleviseur, RestoreSensor):
    """Ambiance de la pièce (sombre, intermédiaire, claire), avec hystérésis
    et 10 minutes avant tout changement (ambiance.py). Restaurée au
    redémarrage : aucun changement d'état parasite pour les
    automatisations."""

    _attr_translation_key = "luminosite_adaptative_ambiance"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(AMBIANCES)

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_ambiance"
        self._fonction = entry.runtime_data.luminosite_adaptative
        self._ecrite: tuple | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (derniere := await self.async_get_last_state()) is not None \
                and derniere.state in AMBIANCES:
            self._fonction.restaurer_ambiance(derniere.state, derniere.last_changed)
        self.async_on_remove(self._fonction.ecouter_signal(self._sur_signal))

    def _sur_signal(self) -> None:
        if (self._fonction.ambiance, self._fonction.seuils_ambiance()) != self._ecrite:
            self.async_write_ha_state()

    def async_write_ha_state(self) -> None:
        self._ecrite = (self._fonction.ambiance, self._fonction.seuils_ambiance())
        super().async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._fonction.ambiance is not None

    @property
    def native_value(self) -> str | None:
        return self._fonction.ambiance

    @property
    def extra_state_attributes(self) -> dict:
        seuils = self._fonction.seuils_ambiance()
        depuis = self._fonction.ambiance_depuis
        return {"depuis": depuis.isoformat() if depuis is not None else None,
                "seuil_sombre": seuils["sombre"], "seuil_claire": seuils["claire"]}
