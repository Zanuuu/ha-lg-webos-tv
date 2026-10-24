"""Entités de réglage dérivées de l'arbre des menus.

Chaque réglage pilotable de l'arbre devient une entité dont le type suit le
contrôle du menu ; seuls les réglages dont la correspondance API est
entièrement connue (bornes d'un curseur, valeur API de chaque choix) sont
exposés : rien n'est deviné. L'état est toujours celui notifié ou relu par le
téléviseur, jamais une valeur supposée après une commande.
"""

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from . import arbre
from .const import DOMAIN

# Réglages d'usage courant, activés dès l'installation ; tous les autres sont
# créés désactivés (à activer au besoin depuis la page de l'appareil).
ACTIVES_PAR_DEFAUT = {
    "image.mode-selection",
    "image.parametres-avances.luminosite.luminosite-pixels-oled",
    "image.parametres-avances.luminosite.ajuster-le-contraste",
    "image.parametres-avances.luminosite.niveau-noir",
    "image.parametres-avances.couleur.profondeur-couleur",
    "image.parametres-avances.luminosite.protection-yeux",
    "image.parametres-avances.luminosite.luminosite-maximale",
    "image.parametres-avances.luminosite.mappage-tons-dynamiques",
    "image.parametres-avances.reduire-lumiere-bleue",
    "image.parametres-avances.clarte.trumotion",
    "general.economie-energie.fonction-economie-energie",
}

EXCLUES = {
    # Mode magasin : bascule le téléviseur en démonstration, sans usage
    # domestique à automatiser.
    "assistance.mode-domicile-magasin",
    # Lecture seule à correspondance douteuse ou valeur composite
    # (docs/incidents-ecriture.md § 2 et 3) : un capteur induirait en erreur.
    "image.parametres-avances.luminosite.plage-video",
    "image.parametres-avances.couleur.balance-blancs.luminosite-signal-max",
    "general.systeme.langue.langue-du-menu",
}

# Libellés qui ne disent rien hors de leur écran de menu : préfixés, comme les
# libellés répétés, par le libellé du menu parent.
CONTEXTE_PARENT = {
    "image.parametres-avances.couleur.balance-blancs.methode",
    "image.parametres-avances.couleur.balance-blancs.point",
    "image.parametres-avances.couleur.ajuster.selectionner-couleur",
}


@dataclass(frozen=True)
class DescriptionReglage:
    entree_id: str
    plateforme: str  # "number" | "select" | "switch" | "sensor"
    nom: str
    categorie: str
    cle: str
    actif_par_defaut: bool
    mode_dependant: bool
    bornes: dict | None = None
    # Libellé du menu → valeur API, dans l'ordre du menu.
    choix: dict[str, Any] = field(default_factory=dict)

    @property
    def categorie_entite(self) -> EntityCategory | None:
        return None if self.actif_par_defaut else EntityCategory.CONFIG

    def libelle_de(self, valeur: Any) -> str | None:
        for libelle, valeur_api in self.choix.items():
            if str(valeur_api) == str(valeur):
                return libelle
        return None


def _plateforme(entree: dict) -> str | None:
    api = entree.get("api") or {}
    controle = entree.get("controle")
    if api.get("acces") == "lecture_seule":
        return "sensor"
    if not arbre._est_pilotable_api(api):
        return None
    if controle == "curseur":
        return "number" if entree.get("bornes") else None
    if controle == "liste":
        choix = entree.get("choix") or []
        if choix and all("valeur_api" in c for c in choix):
            return "select"
        return None
    if controle == "interrupteur":
        return "switch"
    # action, texte, sous-menu : pas d'équivalent d'entité fidèle.
    return None


@lru_cache(maxsize=1)
def descriptions() -> tuple[DescriptionReglage, ...]:
    entrees = arbre.par_id()
    parents: dict[str, dict] = {}

    def visiter(entree: dict) -> None:
        for enfant in entree.get("enfants", []):
            parents[enfant["id"]] = entree
            visiter(enfant)

    for section in arbre.charger()["sections"]:
        visiter(section)

    retenues = []
    for entree in entrees.values():
        if entree["id"] in EXCLUES:
            continue
        plateforme = _plateforme(entree)
        if plateforme:
            retenues.append((entree, plateforme))

    # Libellés génériques répétés (« Activer la fonction », « Mode
    # Sélection ») : préfixés par le libellé du menu parent.
    occurrences = Counter(e["libelle"] for e, _ in retenues)
    resultat = []
    for entree, plateforme in retenues:
        nom = entree["libelle"]
        if occurrences[nom] > 1 or entree["id"] in CONTEXTE_PARENT:
            nom = f"{parents[entree['id']]['libelle']} — {nom}"
        api = entree["api"]
        resultat.append(DescriptionReglage(
            entree_id=entree["id"], plateforme=plateforme, nom=nom,
            categorie=api["categorie"], cle=api["cle"],
            actif_par_defaut=entree["id"] in ACTIVES_PAR_DEFAUT,
            mode_dependant=arbre.mode_dependant(api["categorie"], api["cle"]),
            bornes=entree.get("bornes"),
            choix={c["libelle"]: c["valeur_api"]
                   for c in entree.get("choix") or [] if "valeur_api" in c},
        ))
    return tuple(resultat)


def info_appareil(entry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="LG Electronics",
        model="webOS TV",
    )


class EntiteTeleviseur(Entity):
    """Base : appareil commun, mise à jour poussée par le téléviseur."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry) -> None:
        self._entry = entry
        self._donnees = entry.runtime_data
        self._attr_device_info = info_appareil(entry)

    @property
    def _tv(self):
        return self._donnees.televiseur

    async def async_added_to_hass(self) -> None:
        self._tv.abonner(self._sur_evenement)
        self.async_on_remove(lambda: self._tv.desabonner(self._sur_evenement))

    def _concerne(self, evenement: dict) -> bool:
        return evenement["type"] in ("connexion", "ecriture")

    async def _sur_evenement(self, evenement: dict) -> None:
        if self._concerne(evenement):
            self.async_write_ha_state()


class EntiteReglage(EntiteTeleviseur):
    """Un réglage de l'arbre des menus."""

    def __init__(self, entry, description: DescriptionReglage) -> None:
        super().__init__(entry)
        self.description_reglage = description
        self._attr_unique_id = description.entree_id
        self._attr_name = description.nom
        self._attr_entity_registry_enabled_default = description.actif_par_defaut
        self._attr_entity_category = description.categorie_entite

    @property
    def valeur(self) -> Any:
        d = self.description_reglage
        return self._tv.etat.get(d.categorie, {}).get(d.cle)

    @property
    def available(self) -> bool:
        return self._tv.etat_connexion == "connecte"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        # Les réglages d'image valent pour le mode d'image actif seulement :
        # l'interface doit toujours dire lequel.
        if self.description_reglage.mode_dependant:
            return {"mode_image": self._tv.mode_image}
        return None

    def _concerne(self, evenement: dict) -> bool:
        if evenement["type"] != "changement":
            return super()._concerne(evenement)
        d = self.description_reglage
        if evenement["categorie"] != d.categorie:
            return False
        reglages = evenement["reglages"]
        return d.cle in reglages or (d.mode_dependant and "pictureMode" in reglages)

    async def _ecrire(self, valeur: Any) -> None:
        try:
            resultat = await self._donnees.ecritures.demander(
                self.description_reglage.entree_id, valeur)
        except arbre.ValeurInvalide as exc:
            raise ServiceValidationError(f"{self.name} : {exc}") from exc
        if not resultat["ok"]:
            # L'état affiché reste celui du téléviseur : on le republie pour
            # que l'interface quitte la valeur demandée.
            self.async_write_ha_state()
            raise HomeAssistantError(f"{self.name} : {resultat['raison']}")
