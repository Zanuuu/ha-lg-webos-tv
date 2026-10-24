"""Capteurs binaires de diagnostic : connexion au téléviseur, écriture possible."""

from homeassistant.components.binary_sensor import (BinarySensorDeviceClass,
                                                    BinarySensorEntity)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entite import EntiteTeleviseur


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([Connexion(entry), EcritureImpossible(entry)])


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
