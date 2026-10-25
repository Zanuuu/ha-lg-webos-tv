"""API websocket du panneau, calquée sur l'API REST de l'ancienne app :
même découpage, mêmes réponses, pour que le frontend ne change que sa couche
d'accès (frontend/src/api.js). Réservée aux administrateurs, comme le
panneau."""

from collections.abc import Callable
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from homeassistant.util import dt as dt_util

from . import arbre, restauration
from .const import (CONF_CAPTEUR_LUX, CONF_CAPTEUR_SECOURS,
                    CONF_POINT_INTERMEDIAIRE, DECALAGE_MAX, DECALAGE_MIN,
                    DOMAIN, OPTIONS_AMBIANCE, OPTIONS_AVANCEES,
                    OPTIONS_LUMINOSITE_DEFAUT)
from .courbe import conserver_ancrages
from .luminosite_adaptative import (AncrageImpossible, CorrectionInconnue,
                                    SuggestionInconnue, modes_proposes,
                                    nom_zone, valider_options, zone_entite,
                                    zone_televiseur)
from .signal_lux import profil
from .presets import PresetExistant, PresetInconnu, capturer_snapshot

# Textes des erreurs de validation des options (mêmes clés que le formulaire).
ERREURS_OPTIONS = {
    "hors_bornes": "valeur hors des limites autorisées",
    "lux_max_trop_bas": "doit dépasser la valeur « Pièce sombre »",
    "luminosite_max_trop_basse": "doit être au moins égale à la luminosité minimale",
    "mode_inconnu": "mode d'image inconnu",
    "emplacement_inconnu": "emplacement inconnu",
    "capteur_inconnu": "capteur introuvable",
    "point_intermediaire_hors_courbe":
        "doit tomber entre les deux extrémités de la courbe, en lux et en luminosité",
    "secours_identique": "doit être différent du capteur principal",
    "ambiance_seuils_croises": "le seuil de la pièce claire doit dépasser celui de la pièce sombre",
}

# Refus du point d'ancrage (luminosite_adaptative.AncrageImpossible).
ERREURS_ANCRAGE = {
    "deconnecte": "le téléviseur n'est pas connecté",
    "mode_exclu": "le mode d'image actuel est laissé de côté : passez dans un autre mode",
    "indisponible": "mesure du capteur ou luminosité du téléviseur inconnue",
}
# Capteurs qui ont publié depuis moins d'une heure : proposés juste après
# ceux de la pièce du téléviseur.
RECENT_S = 3600


def _donnees(hass: HomeAssistant, connection, msg) -> Any | None:
    entrees = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entrees:
        connection.send_error(msg["id"], "non_chargee",
                              "L'intégration LG webOS TV n'est pas chargée")
        return None
    return entrees[0].runtime_data


def _commande(schema: dict, gestionnaire: Callable) -> Callable:
    """Commande asynchrone, réservée aux administrateurs, qui reçoit les
    données de l'entrée chargée."""

    @websocket_api.websocket_command(schema)
    @websocket_api.require_admin
    @websocket_api.async_response
    async def commande(hass: HomeAssistant, connection, msg) -> None:
        donnees = _donnees(hass, connection, msg)
        if donnees is not None:
            await gestionnaire(hass, connection, msg, donnees)

    return commande


def _echec_ecriture(connection, msg, resultat: dict) -> bool:
    """Envoie l'erreur d'une écriture échouée ; renvoie True si envoyée."""
    if resultat["ok"]:
        return False
    raison = resultat.get("raison", "")
    if raison == "téléviseur injoignable":
        code = "injoignable"
    elif raison == restauration.RAISON_ECRITURE_IMPOSSIBLE:
        code = "ecriture_impossible"
    else:
        code = "refusee"
    connection.send_error(msg["id"], code, raison)
    return True


async def _arbre(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], arbre.charger())


def _luminosite(donnees) -> dict | None:
    fonction = donnees.luminosite_adaptative
    return fonction.resume() if fonction is not None else None


def _instantane(donnees) -> dict:
    return {**donnees.televiseur.instantane(),
            "luminosite_adaptative": _luminosite(donnees)}


async def _reglages(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], _instantane(donnees))


async def _ecrire(hass, connection, msg, donnees) -> None:
    try:
        resultat = await donnees.ecritures.demander(msg["entree_id"], msg["valeur"], "panneau")
    except arbre.EntreeInconnue:
        connection.send_error(msg["id"], "introuvable", f"Entrée inconnue : {msg['entree_id']}")
        return
    except arbre.EntreeNonPilotable:
        connection.send_error(msg["id"], "invalide",
                              f"Entrée non pilotable par l'API : {msg['entree_id']}")
        return
    except arbre.ValeurInvalide as exc:
        connection.send_error(msg["id"], "invalide", f"Valeur invalide : {exc}")
        return
    if not _echec_ecriture(connection, msg, resultat):
        connection.send_result(msg["id"], resultat)


async def _historique(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], await donnees.historique.lister(msg["limite"]))


async def _annuler(hass, connection, msg, donnees) -> None:
    resultat = await restauration.annuler_ecriture(
        donnees.televiseur, donnees.historique, msg["ecriture_id"])
    if not resultat["ok"] and resultat.get("raison") == "entrée d'historique introuvable":
        connection.send_error(msg["id"], "introuvable", resultat["raison"])
        return
    connection.send_result(msg["id"], resultat)


async def _revenir(hass, connection, msg, donnees) -> None:
    resultats = await restauration.revenir_a(
        donnees.televiseur, donnees.historique, msg["horodatage"])
    connection.send_result(msg["id"], {"resultats": resultats})


async def _presets(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], await donnees.presets.lister())


async def _preset(hass, connection, msg, donnees) -> None:
    preset = await donnees.presets.recuperer(msg["nom"])
    if preset is None:
        connection.send_error(msg["id"], "introuvable", f"Preset inconnu : {msg['nom']}")
        return
    connection.send_result(msg["id"], preset)


async def _creer_preset(hass, connection, msg, donnees) -> None:
    tv = donnees.televiseur
    snapshot = capturer_snapshot(tv.etat, tv.mode_image, msg.get("entrees"))
    if not snapshot:
        connection.send_error(
            msg["id"], "invalide",
            "Aucun réglage pilotable à capturer (sélection vide, ou valeurs pas "
            "encore lues depuis le téléviseur)")
        return
    try:
        connection.send_result(msg["id"], await donnees.presets.sauvegarder(msg["nom"], snapshot))
    except PresetExistant:
        connection.send_error(msg["id"], "existe_deja",
                              f"Un preset nommé « {msg['nom']} » existe déjà")


async def _importer_preset(hass, connection, msg, donnees) -> None:
    try:
        connection.send_result(msg["id"], await donnees.presets.sauvegarder(
            msg["nom"], msg["entrees"], remplacer=msg["remplacer"]))
    except PresetExistant:
        connection.send_error(
            msg["id"], "existe_deja",
            f"Un preset nommé « {msg['nom']} » existe déjà (utilisez remplacer)")


async def _supprimer_preset(hass, connection, msg, donnees) -> None:
    if not await donnees.presets.supprimer(msg["nom"]):
        connection.send_error(msg["id"], "introuvable", f"Preset inconnu : {msg['nom']}")
        return
    connection.send_result(msg["id"], {"supprime": msg["nom"]})


async def _appliquer_preset(hass, connection, msg, donnees) -> None:
    try:
        connection.send_result(msg["id"], await restauration.appliquer_preset(
            donnees.televiseur, donnees.historique, donnees.presets, msg["nom"]))
    except PresetInconnu:
        connection.send_error(msg["id"], "introuvable", f"Preset inconnu : {msg['nom']}")


def _fonction(connection, msg, donnees):
    if donnees.luminosite_adaptative is None:
        connection.send_error(msg["id"], "non_configuree",
                              "La luminosité adaptative n'est pas configurée")
    return donnees.luminosite_adaptative


async def _reprendre_luminosite(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is not None:
        fonction.reprendre()
        connection.send_result(msg["id"], _luminosite(donnees))


async def _activer_luminosite(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is not None:
        fonction.activer(msg["active"])
        connection.send_result(msg["id"], _luminosite(donnees))


async def _pause_luminosite(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is not None:
        fonction.mettre_en_pause(msg["minutes"])
        connection.send_result(msg["id"], _luminosite(donnees))


def _capteurs_lux(hass: HomeAssistant) -> list[dict]:
    """Capteurs proposés au choix, comme le sélecteur du formulaire des
    options (capteurs de luminosité ambiante) : ceux de la pièce du
    téléviseur d'abord, puis ceux qui ont publié dans l'heure, puis les
    autres. Profil pressenti d'après la plateforme seule (la cadence n'est
    observée qu'une fois le capteur choisi)."""
    registre = er.async_get(hass)
    zone_tv = zone_televiseur(hass)
    maintenant = dt_util.utcnow().timestamp()
    capteurs = []
    for etat in hass.states.async_all("sensor"):
        if etat.attributes.get("device_class") != "illuminance":
            continue
        entite = registre.async_get(etat.entity_id)
        plateforme = entite.platform if entite is not None else None
        if plateforme == DOMAIN:
            # « Lux filtré » de la fonction elle-même.
            continue
        zone = zone_entite(hass, etat.entity_id)
        capteurs.append({
            "entity_id": etat.entity_id, "nom": etat.name, "valeur": etat.state,
            "unite": etat.attributes.get("unit_of_measurement"),
            "piece": nom_zone(hass, zone),
            "meme_piece": zone is not None and zone == zone_tv,
            "age_s": round(maintenant - etat.last_reported_timestamp),
            "plateforme": plateforme,
            "profil": profil(plateforme, None),
        })

    def rang(capteur: dict) -> tuple:
        groupe = 0 if capteur["meme_piece"] else 1 if capteur["age_s"] < RECENT_S else 2
        return groupe, capteur["nom"].casefold()

    return sorted(capteurs, key=rang)


async def _configuration_luminosite(hass, connection, msg, donnees) -> None:
    entree = hass.config_entries.async_loaded_entries(DOMAIN)[0]
    connection.send_result(msg["id"], {
        "options": {**OPTIONS_LUMINOSITE_DEFAUT, CONF_CAPTEUR_LUX: None,
                    CONF_CAPTEUR_SECOURS: None, **entree.options},
        "modes_proposes": await hass.async_add_executor_job(modes_proposes),
        "capteurs": _capteurs_lux(hass),
        "piece_televiseur": nom_zone(hass, zone_televiseur(hass)),
    })


async def _configurer_luminosite(hass, connection, msg, donnees) -> None:
    """Mêmes options que le formulaire. Sans rechargement de l'intégration
    (qui couperait la connexion au téléviseur), sauf pour créer ou retirer
    la fonction : ses entités n'existent que si un capteur est choisi. Une
    option avancée à `null` revient à la valeur du profil du capteur, un
    point intermédiaire à `null` est retiré. Les points d'ancrage sont
    oubliés si la courbe change. Un capteur de secours ou un seuil
    d'ambiance à `null` est retiré."""
    entree = hass.config_entries.async_loaded_entries(DOMAIN)[0]
    connues = {*OPTIONS_LUMINOSITE_DEFAUT, CONF_CAPTEUR_LUX, *OPTIONS_AVANCEES,
               CONF_POINT_INTERMEDIAIRE, CONF_CAPTEUR_SECOURS, *OPTIONS_AMBIANCE}
    saisie = {**OPTIONS_LUMINOSITE_DEFAUT, **entree.options,
              **{cle: valeur for cle, valeur in msg["options"].items() if cle in connues}}
    capteur = saisie.pop(CONF_CAPTEUR_LUX, None) or None
    options, erreurs = valider_options(
        {**saisie, CONF_CAPTEUR_LUX: capteur},
        await hass.async_add_executor_job(modes_proposes))
    options.pop(CONF_CAPTEUR_LUX, None)
    if capteur is not None and hass.states.get(capteur) is None:
        erreurs[CONF_CAPTEUR_LUX] = "capteur_inconnu"
    secours = options.get(CONF_CAPTEUR_SECOURS)
    if secours is not None and hass.states.get(secours) is None:
        erreurs.setdefault(CONF_CAPTEUR_SECOURS, "capteur_inconnu")
    if erreurs:
        connection.send_error(msg["id"], "invalide", "Options invalides : " + " ; ".join(
            f"{cle} : {ERREURS_OPTIONS[code]}" for cle, code in erreurs.items()))
        return
    if capteur is not None:
        options[CONF_CAPTEUR_LUX] = capteur
    options = conserver_ancrages(entree.options, options)
    hass.config_entries.async_update_entry(entree, options=options)

    recharge = (capteur is None) != (donnees.luminosite_adaptative is None)
    if recharge:
        await hass.config_entries.async_reload(entree.entry_id)
    elif donnees.luminosite_adaptative is not None:
        donnees.luminosite_adaptative.reconfigurer(options)
    connection.send_result(msg["id"], {"recharge": recharge})


async def _decalage_luminosite(hass, connection, msg, donnees) -> None:
    """Décalage pilotable réglé depuis le panneau : même effet que l'entité,
    sans pause."""
    if (fonction := _fonction(connection, msg, donnees)) is not None:
        fonction.regler_decalage(msg["valeur"], "panneau")
        connection.send_result(msg["id"], _luminosite(donnees))


async def _desactiver_economie_energie(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    resultat = await fonction.desactiver_economie_energie("panneau")
    if not _echec_ecriture(connection, msg, resultat):
        connection.send_result(msg["id"], resultat)


async def _ancrer_luminosite(hass, connection, msg, donnees) -> None:
    """Point d'ancrage de la mise en route : courbe calée sur la luminosité
    actuelle du téléviseur, enregistrée sans rechargement."""
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    try:
        options, compte_rendu = fonction.ancrer()
    except AncrageImpossible as exc:
        connection.send_error(msg["id"], str(exc), ERREURS_ANCRAGE[str(exc)])
        return
    entree = hass.config_entries.async_loaded_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(entree, options=options)
    fonction.reconfigurer(options)
    connection.send_result(msg["id"], {"options": options, "compte_rendu": compte_rendu})


async def _mise_en_route(hass, connection, msg, donnees) -> None:
    """Assistant de mise en route ouvert : la fonction n'écrit pas et ne se
    met pas en pause tant que l'abonnement dure. Lié à la connexion, il
    prend fin avec elle (onglet fermé, réseau perdu)."""
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    fonction.commencer_mise_en_route()
    connection.subscriptions[msg["id"]] = fonction.terminer_mise_en_route
    connection.send_result(msg["id"])


async def _suggestions_luminosite(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is not None:
        connection.send_result(msg["id"], fonction.suggestions())


def _suggestion_inconnue(connection, msg) -> None:
    connection.send_error(msg["id"], "introuvable",
                          "Aucune suggestion pour cette plage de lux (déjà appliquée ?)")


async def _appliquer_suggestion(hass, connection, msg, donnees) -> None:
    """Courbe proposée, recalculée par la fonction, enregistrée sans
    rechargement ; les points d'ancrage sont oubliés."""
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    try:
        options, compte_rendu = fonction.appliquer_suggestion(msg["plage"])
    except SuggestionInconnue:
        _suggestion_inconnue(connection, msg)
        return
    entree = hass.config_entries.async_loaded_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(entree, options=options)
    fonction.reconfigurer(options)
    connection.send_result(msg["id"], {"options": options, "compte_rendu": compte_rendu})


async def _ignorer_suggestion(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    try:
        await fonction.ignorer_suggestion(msg["plage"])
    except SuggestionInconnue:
        _suggestion_inconnue(connection, msg)
        return
    connection.send_result(msg["id"], fonction.suggestions())


async def _oublier_correction(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    try:
        await fonction.oublier_correction(msg["correction_id"])
    except CorrectionInconnue:
        connection.send_error(msg["id"], "introuvable",
                              f"Correction inconnue : {msg['correction_id']}")
        return
    connection.send_result(msg["id"], fonction.suggestions())


async def _sante_luminosite(hass, connection, msg, donnees) -> None:
    if (fonction := _fonction(connection, msg, donnees)) is not None:
        connection.send_result(msg["id"], fonction.sante())


async def _suivre_luminosite(hass, connection, msg, donnees) -> None:
    """Flux de la page Luminosité adaptative : état complet, lux compris,
    événements du journal, santé de l'installation, corrections et
    suggestions, seulement pendant qu'elle est ouverte."""
    if (fonction := _fonction(connection, msg, donnees)) is None:
        return
    dernier = fonction.details()

    @callback
    def signaler() -> None:
        nonlocal dernier
        details = fonction.details()
        if details != dernier:
            dernier = details
            connection.send_message(websocket_api.event_message(
                msg["id"], {"type": "details", "details": details}))

    @callback
    def noter(evenement: dict) -> None:
        connection.send_message(websocket_api.event_message(
            msg["id"], {"type": "journal", "evenement": evenement}))

    @callback
    def signaler_sante() -> None:
        connection.send_message(websocket_api.event_message(
            msg["id"], {"type": "sante", "sante": fonction.sante()}))

    @callback
    def signaler_suggestions() -> None:
        connection.send_message(websocket_api.event_message(
            msg["id"], {"type": "suggestions", "suggestions": fonction.suggestions()}))

    # Le détail suit aussi chaque pas d'une rampe (valeur du téléviseur).
    ne_plus_ecouter = [fonction.ecouter(signaler), fonction.ecouter_details(signaler),
                       fonction.ecouter_journal(noter), fonction.ecouter_sante(signaler_sante),
                       fonction.ecouter_suggestions(signaler_suggestions)]

    @callback
    def desabonner() -> None:
        for retirer in ne_plus_ecouter:
            retirer()

    connection.subscriptions[msg["id"]] = desabonner
    connection.send_result(msg["id"])
    connection.send_message(websocket_api.event_message(msg["id"], {
        "type": "instantane", "details": dernier, "journal": list(fonction.journal),
        "sante": fonction.sante(), "suggestions": fonction.suggestions()}))


async def _abonner(hass, connection, msg, donnees) -> None:
    """Flux temps réel : instantané initial puis événements du téléviseur."""
    tv = donnees.televiseur

    async def relayer(evenement: dict) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], evenement))

    @callback
    def signaler(type_: str) -> None:
        # Simple signal : le panneau relit la liste par sa commande, avec
        # les libellés et le tri qu'elle applique déjà.
        connection.send_message(websocket_api.event_message(msg["id"], {"type": type_}))

    dernier_resume = _luminosite(donnees)

    @callback
    def signaler_luminosite() -> None:
        # La fonction prévient à chaque mesure du capteur : on ne relaie que
        # les changements visibles dans le panneau.
        nonlocal dernier_resume
        resume = _luminosite(donnees)
        if resume != dernier_resume:
            dernier_resume = resume
            connection.send_message(websocket_api.event_message(
                msg["id"], {"type": "luminosite_adaptative", **resume}))

    tv.abonner(relayer)
    ne_plus_ecouter = [
        donnees.historique.ecouter(lambda _ecriture: signaler("historique")),
        donnees.presets.ecouter(lambda: signaler("presets")),
    ]
    if donnees.luminosite_adaptative is not None:
        ne_plus_ecouter.append(donnees.luminosite_adaptative.ecouter(signaler_luminosite))

    @callback
    def desabonner() -> None:
        tv.desabonner(relayer)
        for retirer in ne_plus_ecouter:
            retirer()

    connection.subscriptions[msg["id"]] = desabonner
    connection.send_result(msg["id"])
    connection.send_message(websocket_api.event_message(
        msg["id"], {"type": "instantane", **_instantane(donnees)}))


def _type(nom: str) -> dict:
    return {vol.Required("type"): f"{DOMAIN}/{nom}"}


COMMANDES = [
    _commande(_type("arbre"), _arbre),
    _commande(_type("reglages"), _reglages),
    _commande({**_type("ecrire"), vol.Required("entree_id"): str,
               vol.Required("valeur"): vol.Any(bool, int, float, str, dict, list)}, _ecrire),
    _commande({**_type("historique"), vol.Optional("limite", default=100): int}, _historique),
    _commande({**_type("historique/annuler"), vol.Required("ecriture_id"): int}, _annuler),
    _commande({**_type("historique/revenir"), vol.Required("horodatage"): vol.Coerce(float)},
              _revenir),
    _commande(_type("presets"), _presets),
    _commande({**_type("presets/obtenir"), vol.Required("nom"): str}, _preset),
    _commande({**_type("presets/creer"), vol.Required("nom"): str,
               vol.Optional("entrees"): vol.Any(None, [str])}, _creer_preset),
    _commande({**_type("presets/importer"), vol.Required("nom"): str,
               vol.Required("entrees"): [dict],
               vol.Optional("remplacer", default=False): bool}, _importer_preset),
    _commande({**_type("presets/supprimer"), vol.Required("nom"): str}, _supprimer_preset),
    _commande({**_type("presets/appliquer"), vol.Required("nom"): str}, _appliquer_preset),
    _commande(_type("luminosite_adaptative/reprendre"), _reprendre_luminosite),
    _commande({**_type("luminosite_adaptative/activer"), vol.Required("active"): bool},
              _activer_luminosite),
    _commande({**_type("luminosite_adaptative/pause"),
               vol.Required("minutes"): vol.All(int, vol.Range(min=1, max=720))},
              _pause_luminosite),
    _commande(_type("luminosite_adaptative/configuration"), _configuration_luminosite),
    _commande({**_type("luminosite_adaptative/decalage"),
               vol.Required("valeur"): vol.All(vol.Coerce(int),
                                               vol.Range(min=DECALAGE_MIN, max=DECALAGE_MAX))},
              _decalage_luminosite),
    _commande({**_type("luminosite_adaptative/configurer"), vol.Required("options"): dict},
              _configurer_luminosite),
    _commande(_type("luminosite_adaptative/desactiver_economie_energie"),
              _desactiver_economie_energie),
    _commande(_type("luminosite_adaptative/sante"), _sante_luminosite),
    _commande(_type("luminosite_adaptative/ancrer"), _ancrer_luminosite),
    _commande(_type("luminosite_adaptative/mise_en_route"), _mise_en_route),
    _commande(_type("luminosite_adaptative/suggestions"), _suggestions_luminosite),
    _commande({**_type("luminosite_adaptative/appliquer_suggestion"),
               vol.Required("plage"): int}, _appliquer_suggestion),
    _commande({**_type("luminosite_adaptative/ignorer_suggestion"),
               vol.Required("plage"): int}, _ignorer_suggestion),
    _commande({**_type("luminosite_adaptative/oublier_correction"),
               vol.Required("correction_id"): int}, _oublier_correction),
    _commande(_type("luminosite_adaptative/suivre"), _suivre_luminosite),
    _commande(_type("abonner"), _abonner),
]


@callback
def async_enregistrer(hass: HomeAssistant) -> None:
    for commande in COMMANDES:
        websocket_api.async_register_command(hass, commande)
