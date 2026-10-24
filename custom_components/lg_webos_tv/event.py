"""Événement « réglage modifié sur le téléviseur » : signale les changements
qui ne viennent pas de cette intégration (télécommande, réglages rapides, ou
une autre application). Sert aux automatisations qui doivent céder la main à
un réglage manuel, comme le blueprint de luminosité ambiante."""

from functools import partial
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .entite import EntiteTeleviseur, descriptions

# Un glissement du curseur des réglages rapides produit ≈ 25 notifications
# en 0,5 s (docs/rapport-api.md, phase 7) : un seul événement par réglage,
# émis une fois la rafale retombée, avec la valeur finale.
DELAI_REGROUPEMENT_S = 0.7


async def async_setup_entry(hass: HomeAssistant, entry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([ReglageModifieSurTeleviseur(entry)])


class ReglageModifieSurTeleviseur(EntiteTeleviseur, EventEntity):
    _attr_translation_key = "reglage_modifie"
    # manuel : télécommande ou réglages rapides ; autre_application : un
    # autre client de l'API du téléviseur.
    _attr_event_types = ["manuel", "autre_application"]

    def __init__(self, entry) -> None:
        super().__init__(entry)
        self._attr_unique_id = "reglage_modifie"
        self._par_cle = {(d.categorie, d.cle): d for d in descriptions()}
        self._en_attente: dict[tuple[str, str], tuple[str, Any]] = {}

    async def async_will_remove_from_hass(self) -> None:
        for _, annuler in self._en_attente.values():
            annuler()
        self._en_attente.clear()

    async def _sur_evenement(self, evenement: dict) -> None:
        if evenement["type"] == "changement" \
                and evenement["origine"] in self._attr_event_types:
            for cle in evenement["reglages"]:
                cle_tv = (evenement["categorie"], cle)
                if cle_tv in self._en_attente:
                    self._en_attente[cle_tv][1]()
                annuler = async_call_later(
                    self.hass, DELAI_REGROUPEMENT_S, partial(self._emettre, cle_tv))
                self._en_attente[cle_tv] = (evenement["origine"], annuler)
        else:
            await super()._sur_evenement(evenement)

    @callback
    def _emettre(self, cle_tv: tuple[str, str], _maintenant) -> None:
        origine, _ = self._en_attente.pop(cle_tv)
        categorie, cle = cle_tv
        valeur = self._tv.etat.get(categorie, {}).get(cle)
        description = self._par_cle.get(cle_tv)
        attributs = {"categorie": categorie, "cle": cle, "valeur": valeur,
                     "mode_image": self._tv.mode_image}
        if description is not None:
            attributs |= {"entree_id": description.entree_id,
                          "libelle": description.nom}
            if description.choix:
                attributs["valeur_libelle"] = description.libelle_de(valeur)
        self._trigger_event(origine, attributs)
        self.async_write_ha_state()
