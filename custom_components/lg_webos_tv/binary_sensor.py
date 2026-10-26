"""Capteurs binaires de diagnostic : connexion au téléviseur, écriture
possible ; Soirée de la luminosité adaptative."""

from homeassistant.components.binary_sensor import (BinarySensorDeviceClass,
                                                    BinarySensorEntity)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import (ExtraStoredData,
                                                 RestoredExtraData, RestoreEntity)
from homeassistant.util import dt as dt_util

from .entite import EntiteTeleviseur


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entites = [Connexion(entry), EcritureImpossible(entry)]
    if entry.runtime_data.luminosite_adaptative is not None:
        entites.append(SoireeLuminositeAdaptative(entry))
    async_add_entities(entites)


class Connexion(EntiteTeleviseur, BinarySensorEntity):
    _attr_translation_key = "connexion"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "connexion"

    @property
    def is_on(self) -> bool:
        return self._tv.etat_connexion == "connecte"


class EcritureImpossible(EntiteTeleviseur, BinarySensorEntity):
    """Problème quand le téléviseur n'accorde aucune voie d'écriture (mode
    consultation)."""

    _attr_translation_key = "ecriture_impossible"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "ecriture_impossible"

    @property
    def available(self) -> bool:
        return self._tv.etat_connexion == "connecte" and self._tv.ecriture_possible is not None

    @property
    def is_on(self) -> bool:
        return self._tv.ecriture_possible is False


class SoireeLuminositeAdaptative(EntiteTeleviseur, BinarySensorEntity, RestoreEntity):
    """Soirée en cours (soiree.py) : luminosité baissée et, en option,
    « Réduire la lumière bleue ». Garde au redémarrage une Soirée terminée à
    la main et la lumière bleue posée par la fonction, pour la rétablir même
    si Home Assistant redémarre avant le lendemain."""

    _attr_translation_key = "luminosite_adaptative_soiree"

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_soiree"
        self._fonction = entry.runtime_data.luminosite_adaptative
        self._ecrit: tuple | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None:
            donnees = extra.as_dict()
            terminee = donnees.get("terminee_jusqua")
            self._fonction.restaurer_soiree(
                dt_util.parse_datetime(terminee) if terminee else None,
                donnees.get("lumiere_bleue"))
        self.async_on_remove(self._fonction.ecouter(self._sur_changement))

    def _sur_changement(self) -> None:
        # La fonction prévient à chaque mesure : n'écrire que ce qui change.
        if (self.is_on, self.extra_state_attributes) != self._ecrit:
            self.async_write_ha_state()

    def async_write_ha_state(self) -> None:
        self._ecrit = (self.is_on, self.extra_state_attributes)
        super().async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._fonction.soiree_active

    @property
    def extra_state_attributes(self) -> dict:
        soiree = self._fonction.resume_soiree()
        return {"fin": soiree["fin"], "terminee_jusqua": soiree["terminee_jusqua"],
                "reduction": soiree["reduction"],
                "lumiere_bleue": soiree["lumiere_bleue"]["option"],
                "lumiere_bleue_reprise_en_main": soiree["lumiere_bleue"]["reprise"]}

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return RestoredExtraData(self._fonction.persistance_soiree())
