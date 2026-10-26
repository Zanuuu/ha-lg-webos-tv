"""Un bouton par preset : application depuis une automatisation, une scène
ou un tableau de bord. Les boutons suivent la liste des presets. Plus le
bouton de reprise de la luminosité adaptative, et celui qui termine sa
Soirée."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import restauration
from .const import DOMAIN
from .entite import EntiteTeleviseur

PREFIXE = "preset_"


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    presets = entry.runtime_data.presets
    boutons: dict[str, BoutonPreset] = {}
    registre = er.async_get(hass)

    async def synchroniser() -> None:
        noms = {p["nom"] for p in await presets.lister()}
        nouveaux = [BoutonPreset(entry, nom) for nom in sorted(noms - boutons.keys())]
        boutons.update({b.nom: b for b in nouveaux})
        async_add_entities(nouveaux)
        # Presets supprimés, y compris pendant que Home Assistant était arrêté.
        for inscrite in er.async_entries_for_config_entry(registre, entry.entry_id):
            if inscrite.domain == "button" and inscrite.unique_id.startswith(PREFIXE) \
                    and inscrite.unique_id.removeprefix(PREFIXE) not in noms:
                boutons.pop(inscrite.unique_id.removeprefix(PREFIXE), None)
                registre.async_remove(inscrite.entity_id)

    @callback
    def presets_modifies() -> None:
        entry.async_create_task(hass, synchroniser())

    await synchroniser()
    entry.async_on_unload(presets.ecouter(presets_modifies))
    if entry.runtime_data.luminosite_adaptative is not None:
        async_add_entities([ReprendreLuminositeAdaptative(entry), TerminerSoiree(entry)])


class BoutonPreset(EntiteTeleviseur, ButtonEntity):
    _attr_translation_key = "appliquer_preset"

    def __init__(self, entry, nom: str) -> None:
        super().__init__(entry)
        self.nom = nom
        self._attr_unique_id = f"{PREFIXE}{nom}"
        self._attr_translation_placeholders = {"nom": nom}

    @property
    def available(self) -> bool:
        return self._tv.etat_connexion == "connecte"

    async def async_press(self) -> None:
        d = self._donnees
        resultat = await restauration.appliquer_preset(
            d.televiseur, d.historique, d.presets, self.nom)
        if resultat["echecs"]:
            details = "; ".join(f"{e['cle']} ({e['raison']})" for e in resultat["echecs"][:5])
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="preset_partiel",
                translation_placeholders={
                    "nom": self.nom, "appliques": str(len(resultat["appliques"])),
                    "echecs": str(len(resultat["echecs"])), "details": details})


class ReprendreLuminositeAdaptative(EntiteTeleviseur, ButtonEntity):
    """Lève la pause après un réglage manuel et réapplique tout de suite."""

    _attr_translation_key = "luminosite_adaptative_reprendre"

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_reprendre"
        self._fonction = entry.runtime_data.luminosite_adaptative

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._fonction.ecouter(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._fonction.active

    async def async_press(self) -> None:
        self._fonction.reprendre()


class TerminerSoiree(EntiteTeleviseur, ButtonEntity):
    """Termine la Soirée en cours jusqu'à la fin de sa plage : luminosité
    normale, lumière bleue rétablie. « Reprendre » n'y touche pas."""

    _attr_translation_key = "luminosite_adaptative_terminer_soiree"

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "luminosite_adaptative_terminer_soiree"
        self._fonction = entry.runtime_data.luminosite_adaptative
        self._disponible: bool | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._fonction.ecouter(self._sur_changement))

    def _sur_changement(self) -> None:
        if self.available != self._disponible:
            self.async_write_ha_state()

    def async_write_ha_state(self) -> None:
        self._disponible = self.available
        super().async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._fonction.soiree_active

    async def async_press(self) -> None:
        self._fonction.terminer_soiree("home_assistant")
