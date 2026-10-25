"""Diagnostics téléchargeables depuis la page de l'intégration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_CAPTEUR_LUX, CONF_CAPTEUR_SECOURS, CONF_CLE_CLIENT
from .entite import descriptions

A_MASQUER = {CONF_HOST, CONF_CLE_CLIENT}


def _luminosite_adaptative(fonction) -> dict[str, Any] | None:
    """État, réglages et santé de la fonction, sans donnée personnelle : ni
    l'identifiant du capteur (souvent le nom de la pièce), ni les noms de
    pièce."""
    if fonction is None:
        return None
    sante = fonction.sante()
    diagnostics = []
    for diagnostic in sante["diagnostics"]:
        if diagnostic["id"] == "pieces_differentes":
            diagnostic = {**diagnostic,
                          "valeurs": {"differentes": diagnostic["niveau"] != "ok"}}
        diagnostics.append(diagnostic)
    details = fonction.details()
    suggestions = fonction.suggestions()
    return {
        "etat": details["etat"],
        "options": {cle: valeur for cle, valeur in fonction.options.items()
                    if cle not in (CONF_CAPTEUR_LUX, CONF_CAPTEUR_SECOURS)},
        "decalage": details["decalage"],
        "capteur_actif": details["capteur_actif"],
        "ambiance": details["ambiance"],
        "seuils_ambiance": details["seuils_ambiance"],
        # Rapport appris et état du secours, sans son identifiant.
        "secours": (None if details["secours"] is None
                    else {cle: valeur for cle, valeur in details["secours"].items()
                          if cle not in ("lux", "derniere_mesure")}),
        "profil": details["profil"],
        "constantes": details["constantes"],
        "parametres_rampe": details["parametres_rampe"],
        "statistiques": sante["resume"],
        "jours": sante["jours"],
        "diagnostics": diagnostics,
        # Nombres seulement : les corrections portent l'heure des réglages.
        "corrections": len(suggestions["corrections"]),
        "suggestions": len(suggestions["suggestions"]),
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    tv = entry.runtime_data.televiseur
    return {
        "entree": async_redact_data(dict(entry.data), A_MASQUER),
        "connexion": tv.etat_connexion,
        "voie_ecriture": tv.voie_ecriture,
        "ecriture_possible": tv.ecriture_possible,
        "mode_image": tv.mode_image,
        "reglages": tv.etat,
        "entites": {
            plateforme: sum(1 for d in descriptions() if d.plateforme == plateforme)
            for plateforme in ("number", "select", "switch", "sensor")
        },
        "luminosite_adaptative": _luminosite_adaptative(entry.runtime_data.luminosite_adaptative),
    }
