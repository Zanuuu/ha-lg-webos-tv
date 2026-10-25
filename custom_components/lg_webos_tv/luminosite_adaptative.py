"""Luminosité adaptative : règle la luminosité des pixels OLED d'après un
capteur de lumière ambiante, sur une échelle logarithmique proche de la
perception de l'œil.

Remplace le blueprint de la 2.0.0, qui ne pouvait ni suivre la reprise en
main réglage par réglage (il lisait le dernier événement « manuel », toutes
clés confondues), ni voir les réglages faits depuis Home Assistant (le
téléviseur les attribue tous à notre client). Ici :

- tout changement de la luminosité OLED qui ne vient pas de cette fonction
  met la fonction en pause : télécommande ou autre application (origine
  notifiée par le téléviseur), entité, panneau, preset ou retour arrière
  (origine enregistrée dans l'historique). La pause dure le délai choisi,
  ou jusqu'au prochain allumage du téléviseur ou au bouton « Reprendre » ;
- la luminosité est propre à l'entrée et au mode d'image (dimensions du
  descripteur `backlight`, inventaire-api.json) : toute valeur rappelée par
  le téléviseur après un changement de mode ou d'entrée relance
  l'application ;
- le lux est filtré, avec hystérésis, confirmation des sauts et gel après
  nos écritures (signal_lux.py) ; un capteur figé ou une fonction native du
  téléviseur qui règle déjà la luminosité (économie d'énergie, mode Éco)
  arrêtent les écritures et ouvrent une Réparation ;
- une transition se fait en rampe (rampe.py) : petits pas cadencés, chacun
  confirmé par le téléviseur avant le suivant, qui suivent la cible lissée
  jusqu'à son arrivée. Une seule entrée d'historique par rampe (départ →
  arrivée) ; mesures mises de côté pendant la rampe et le gel qui suit ;
- la santé de l'installation (sante.py) se mesure au fil de l'eau :
  agrégats journaliers enregistrés en SQLite (statistiques.py), réponse du
  capteur à l'allumage, à l'extinction et aux rampes, diagnostics pour le
  panneau ;
- une pause se lève aussi quand l'éclairage change nettement, et une
  correction gardée assez longtemps est enregistrée (corrections.py) : de
  quoi proposer des retouches de la courbe, que l'utilisateur applique ou
  non (reprise.py).
"""

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import (Event, EventStateChangedData,
                                EventStateReportedData, HomeAssistant, State,
                                callback)
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (async_track_point_in_utc_time,
                                         async_track_state_change_event,
                                         async_track_state_report_event,
                                         async_track_time_interval)
from homeassistant.util import dt as dt_util

from .const import (CONF_ANCRAGES, CONF_CAPTEUR_LUX, CONF_CONFIRMATION_SAUT,
                    CONF_ECART_MINIMAL, CONF_EMPLACEMENT, CONF_GEL_ECRITURE,
                    CONF_HYSTERESIS_DESCENTE, CONF_HYSTERESIS_MONTEE,
                    CONF_LISSAGE_DESCENTE, CONF_LISSAGE_MONTEE,
                    CONF_LUMINOSITE_MAX, CONF_LUMINOSITE_MIN, CONF_LUX_MAX,
                    CONF_LUX_MIN, CONF_MODES_EXCLUS, CONF_PAUSE_MIN,
                    CONF_POINT_INTERMEDIAIRE, CONF_RAMPE_DEBIT,
                    CONF_RAMPE_PAS, CONF_REPRISE_SUR_CHANGEMENT, DOMAIN,
                    ECART_MINIMAL_DEFAUT, EMPLACEMENTS, MODES_HDR,
                    OPTIONS_AVANCEES, OPTIONS_LUMINOSITE_DEFAUT)
from . import courbe
from .courbe import calculer_cible, valider_point_intermediaire
from .entite import descriptions
from .rampe import Rampe, parametres
from .reprise import (Correction, SuiviCorrection, a_ecarter, bornes_reprise,
                      changement_net, ecart, plage, suggestions)
from .sante import (CONSERVATION_JOURS, RAMPE_DELTA_MIN, Accumulateur,
                    Contexte, Inversions, Retroaction, StatsJour, ambiance,
                    evaluer, fenetre, resume, resume_jour)
from .signal_lux import REEVALUATION_S, Cadence, SignalLux, constantes, profil

log = logging.getLogger(__name__)

ID_OLED = "image.parametres-avances.luminosite.luminosite-pixels-oled"
ID_MODE = "image.mode-selection"
ID_ECONOMIE = "general.economie-energie.fonction-economie-energie"
CATEGORIE, CLE = "picture", "backlight"
CLE_ECONOMIE = "energySaving"
# Valeurs de « Fonction Économie d'énergie » qui règlent elles-mêmes la
# luminosité (Auto : d'après le capteur du téléviseur). `screen_off`
# (Écran désactivé) n'en est pas une : il n'y a plus d'image à régler.
ECONOMIE_EN_CONFLIT = ("auto", "min", "med", "max")
MODE_ECO = "eco"
ORIGINE = "luminosite_adaptative"

# Notifications du téléviseur qui valent reprise en main.
ORIGINES_EXTERIEURES = ("manuel", "autre_application")
# Reprises en main qui deviennent des corrections, matière des suggestions :
# les réglages isolés. Ni preset ni retour arrière (une valeur posée en lot
# n'a pas été choisie pour l'éclairage du moment).
ORIGINES_CORRECTION = (*ORIGINES_EXTERIEURES, "home_assistant", "panneau")
# Écritures en lot : la fonction attend qu'elles retombent, sinon elle
# pourrait s'intercaler entre deux écritures d'un preset et écraser la
# luminosité qu'il vient de poser.
ORIGINES_LOT = ("preset", "annulation")
# Un changement de mode ou d'entrée fait rappeler au téléviseur une rafale
# de valeurs (origine « cascade ») : une seule application, une fois la
# rafale retombée.
DELAI_APPLICATION_S = 1.0
DELAI_APRES_LOT_S = 3.0

# Journal de la fonction pour le panneau : en mémoire, perdu au redémarrage
# (diagnostic ; l'historique SQLite garde les écritures).
TAILLE_JOURNAL = 50
# Pause demandée depuis le panneau, sans réglage de la luminosité.
PAUSE_MANUELLE = "pause_manuelle"
VERIFICATION_CAPTEUR = timedelta(minutes=1)
# Statistiques de santé : au plus cinq minutes perdues sur un arrêt brutal.
ENREGISTREMENT_STATS = timedelta(minutes=5)

# Réparations (Paramètres → Réparations) : seulement les cas qui bloquent la
# fonction (docs/etude-luminosite-adaptative.md, arbitrage A6).
PROBLEME_CONFLIT = "conflit_economie_energie"
PROBLEME_FIGE = "capteur_fige"

# Bornes des options numériques, communes au formulaire des options et au
# panneau. Le téléviseur n'accepte que des entiers pour la luminosité.
# Options avancées en secondes et en pourcentage ; rampe en points et en
# points par seconde.
BORNES = {CONF_LUX_MIN: (1, 1000), CONF_LUX_MAX: (2, 100000),
          CONF_LUMINOSITE_MIN: (0, 100), CONF_LUMINOSITE_MAX: (0, 100),
          CONF_ECART_MINIMAL: (1, 20), CONF_PAUSE_MIN: (5, 720),
          CONF_LISSAGE_MONTEE: (0, 120), CONF_LISSAGE_DESCENTE: (0, 300),
          CONF_HYSTERESIS_MONTEE: (0, 100), CONF_HYSTERESIS_DESCENTE: (0, 90),
          CONF_CONFIRMATION_SAUT: (0, 60), CONF_GEL_ECRITURE: (0, 120),
          CONF_RAMPE_PAS: (1, 10), CONF_RAMPE_DEBIT: (1, 20)}
ENTIERS = (CONF_LUMINOSITE_MIN, CONF_LUMINOSITE_MAX, CONF_PAUSE_MIN, *OPTIONS_AVANCEES)

# Par ordre de priorité (voir LuminositeAdaptative.etat).
ETATS = ["desactivee", "televiseur_deconnecte", "consultation", "mise_en_route", "pause",
         "mode_exclu", "conflit_economie_energie", "capteur_indisponible",
         "capteur_fige", "active"]

# (plateforme, unique_id) des entités de la fonction : retirées du registre
# quand le capteur est effacé des options.
ENTITES = (("switch", "luminosite_adaptative"),
           ("sensor", "luminosite_adaptative_etat"),
           ("button", "luminosite_adaptative_reprendre"))


def modes_proposes() -> list[str]:
    """Modes que l'utilisateur peut laisser de côté : ceux du menu (arbre),
    puis l'option groupée HDR / Dolby Vision. Lit l'arbre : hors boucle
    d'événements au premier appel."""
    mode = next(d for d in descriptions() if d.entree_id == ID_MODE)
    return [*mode.choix.values(), MODES_HDR]


def valider_options(options: dict, modes: list[str]) -> tuple[dict, dict[str, str]]:
    """Options normalisées (entiers là où le téléviseur les attend, options
    avancées vides retirées) et erreurs par option, en clés de traduction du
    formulaire."""
    erreurs = {}
    # Vides : option avancée qui suit le profil, courbe sans point
    # intermédiaire.
    options = {cle: valeur for cle, valeur in options.items()
               if not ((cle in OPTIONS_AVANCEES or cle == CONF_POINT_INTERMEDIAIRE)
                       and valeur is None)}
    for cle, (bas, haut) in BORNES.items():
        valeur = options.get(cle)
        if cle in OPTIONS_AVANCEES and valeur is None:
            continue
        if (isinstance(valeur, bool) or not isinstance(valeur, int | float)
                or not bas <= valeur <= haut):
            erreurs[cle] = "hors_bornes"
    if not erreurs:
        if options[CONF_LUX_MAX] <= options[CONF_LUX_MIN]:
            erreurs[CONF_LUX_MAX] = "lux_max_trop_bas"
        if options[CONF_LUMINOSITE_MAX] < options[CONF_LUMINOSITE_MIN]:
            erreurs[CONF_LUMINOSITE_MAX] = "luminosite_max_trop_basse"
    if not erreurs and CONF_POINT_INTERMEDIAIRE in options:
        point, erreur = valider_point_intermediaire(options)
        if erreur is not None:
            erreurs[CONF_POINT_INTERMEDIAIRE] = erreur
        else:
            options[CONF_POINT_INTERMEDIAIRE] = point
    if not isinstance(options.get(CONF_ANCRAGES, []), list):
        erreurs[CONF_ANCRAGES] = "hors_bornes"
    exclus = options.get(CONF_MODES_EXCLUS)
    if not isinstance(exclus, list) or not set(exclus) <= set(modes):
        erreurs[CONF_MODES_EXCLUS] = "mode_inconnu"
    if options.get(CONF_EMPLACEMENT, "inconnu") not in EMPLACEMENTS:
        erreurs[CONF_EMPLACEMENT] = "emplacement_inconnu"
    if not isinstance(options.get(CONF_REPRISE_SUR_CHANGEMENT, True), bool):
        erreurs[CONF_REPRISE_SUR_CHANGEMENT] = "hors_bornes"
    if erreurs:
        return options, erreurs
    # Les sélecteurs numériques rendent des flottants.
    return {**options, **{cle: int(options[cle]) for cle in ENTIERS if cle in options}}, {}


def zone_entite(hass: HomeAssistant, entity_id: str) -> str | None:
    """Pièce d'une entité, sinon celle de son appareil (registres de Home
    Assistant)."""
    if (entite := er.async_get(hass).async_get(entity_id)) is None:
        return None
    if entite.area_id is not None or entite.device_id is None:
        return entite.area_id
    appareil = dr.async_get(hass).async_get(entite.device_id)
    return appareil.area_id if appareil is not None else None


def zone_televiseur(hass: HomeAssistant) -> str | None:
    if not (entrees := hass.config_entries.async_entries(DOMAIN)):
        return None
    tv = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entrees[0].entry_id),
                                                           entrees[0].entry_id)
    return tv.area_id if tv is not None else None


def nom_zone(hass: HomeAssistant, zone_id: str | None) -> str | None:
    zone = ar.async_get(hass).async_get_area(zone_id) if zone_id is not None else None
    return zone.name if zone is not None else None


class AncrageImpossible(Exception):
    """Point d'ancrage refusé ; le message est un code pour le panneau."""


class SuggestionInconnue(Exception):
    """Plage sans suggestion (déjà appliquée, ou corrections oubliées entre-
    temps)."""


class CorrectionInconnue(Exception):
    pass


@callback
def retirer_entites(hass: HomeAssistant) -> None:
    registre = er.async_get(hass)
    for plateforme, unique_id in ENTITES:
        if entity_id := registre.async_get_entity_id(plateforme, DOMAIN, unique_id):
            registre.async_remove(entity_id)


def _lire_lux(etat: State | None) -> float | None:
    try:
        return float(etat.state) if etat is not None else None
    except ValueError:
        return None


def _horloge() -> float:
    """Instant en secondes pour le signal (signal_lux ignore Home Assistant)."""
    return dt_util.utcnow().timestamp()


def _jour_local() -> str:
    """Jour des statistiques : celui de l'utilisateur, pas l'UTC."""
    return dt_util.as_local(dt_util.utcnow()).date().isoformat()


def _premier_jour_conserve() -> str:
    return (date.fromisoformat(_jour_local())
            - timedelta(days=CONSERVATION_JOURS - 1)).isoformat()


@dataclass
class _Transition:
    """Rampe en cours et ce qu'il faut pour l'historiser à sa fin."""

    rampe: Rampe
    mode: str | None  # mode d'image de départ : garde de chaque pas
    premier: dict | None = None  # résultat du premier pas confirmé
    dernier: dict | None = None  # résultat du dernier pas confirmé
    demandee: int | None = None  # valeur du dernier pas envoyé
    annuler_minuterie: Callable[[], None] | None = None
    tache: Any = None


class LuminositeAdaptative:
    def __init__(self, hass: HomeAssistant, donnees, options: dict) -> None:
        self.hass = hass
        self._tv = donnees.televiseur
        self._historique = donnees.historique
        self._ecritures = donnees.ecritures
        self.options = {**OPTIONS_LUMINOSITE_DEFAUT, **options}
        self.capteur: str = options[CONF_CAPTEUR_LUX]
        self._modes_menu = set(modes_proposes()) - {MODES_HDR}

        # Restaurés par l'interrupteur (RestoreEntity) à son ajout.
        self.active = False
        self.fin_pause: datetime | None = None
        self.derniere_erreur: str | None = None
        # Origine et heure de la reprise en main qui a mis la fonction en
        # pause : la question qu'on se pose devant une pause.
        self.cause_pause: dict[str, str] | None = None
        self.journal: deque[dict] = deque(maxlen=TAILLE_JOURNAL)
        self._ecouteurs_journal: list[Callable[[dict], None]] = []
        self._transition: _Transition | None = None
        # Le téléviseur a été vu injoignable pendant la pause : sa prochaine
        # connexion est un rallumage, qui lève la pause. Un simple
        # redémarrage de Home Assistant (connexion sans déconnexion vue) la
        # conserve.
        self._eteint_pendant_pause = False
        # Assistants de mise en route ouverts (onglets du panneau) : la
        # fonction n'écrit pas tant qu'il en reste un.
        self._mises_en_route = 0

        # Signal du capteur : repart de zéro à chaque changement de capteur.
        self._plateforme: str | None = None
        self.profil = "inconnu"
        self._cadence = Cadence()
        self._signal = SignalLux(self._constantes())
        # Réparations ouvertes : cause du conflit, capteur figé.
        self._conflit_signale: str | None = None
        self._fige_signale = False
        self._cible_signalee: int | None = None

        # Santé de l'installation : agrégats du jour en cours, jours passés
        # relus en base pour ce capteur, rétroaction et allers-retours en
        # mémoire. Repart à chaque changement de capteur.
        self._statistiques = donnees.statistiques
        self._jours: dict[str, StatsJour] = {}
        self._accumulateur = Accumulateur(StatsJour(_jour_local()))
        self._retroaction = Retroaction()
        self._inversions = Inversions()
        # Rien n'est enregistré avant la relecture : on écraserait le jour
        # déjà en base.
        self._stats_chargees = False
        self._a_enregistrer: set[str] = set()
        # Reprise en main de la pause en cours (jour, ambiance, valeur) :
        # plusieurs appuis sur la télécommande font une seule correction.
        self._reprise_en_cours: tuple[str, str, float] | None = None
        self._sante: dict | None = None
        self._ecouteurs_sante: list[Callable[[], None]] = []
        self._tache_stats = None

        # Corrections du capteur (relues en base) et suggestions qu'elles
        # appellent ; reprise en main en observation pendant 10 minutes.
        self._base_corrections = donnees.corrections
        self._corrections: list[Correction] = []
        self._corrections_chargees = False
        self._suivi: SuiviCorrection | None = None
        self._annuler_suivi: Callable[[], None] | None = None
        self._suggestions: dict | None = None
        self._ecouteurs_suggestions: list[Callable[[], None]] = []

        self._ecouteurs: list[Callable[[], None]] = []
        # Seulement le détail (page du panneau) : prévenus à chaque pas d'une
        # rampe, sans réécrire l'état des entités.
        self._ecouteurs_details: list[Callable[[], None]] = []
        self._desabonnements: list[Callable[[], None]] = []
        self._annuler_application: Callable[[], None] | None = None
        self._echeance: datetime | None = None
        self._annuler_fin_pause: Callable[[], None] | None = None
        self._ne_plus_suivre_capteur: list[Callable[[], None]] = []
        self._tache = None

    # ---------------------------------------------------------------- cycle
    def demarrer(self) -> None:
        self._tv.abonner(self._sur_evenement)
        self._desabonnements += [
            lambda: self._tv.desabonner(self._sur_evenement),
            self._historique.ecouter(self._sur_ecriture),
            async_track_time_interval(self.hass, self._verifier_capteur,
                                      VERIFICATION_CAPTEUR),
            async_track_time_interval(self.hass, self._enregistrer_periodiquement,
                                      ENREGISTREMENT_STATS),
            self.hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, self._sur_arret_hass),
        ]
        self._suivre_capteur()

    def _suivre_capteur(self) -> None:
        for ne_plus_suivre in self._ne_plus_suivre_capteur:
            ne_plus_suivre()
        # Rapports du capteur, valeur changée ou non : la cadence (profil,
        # capteur figé) se mesure sur les seconds aussi.
        self._ne_plus_suivre_capteur = [
            async_track_state_change_event(self.hass, [self.capteur], self._sur_lux),
            async_track_state_report_event(self.hass, [self.capteur], self._sur_rapport),
        ]
        entite = er.async_get(self.hass).async_get(self.capteur)
        self._plateforme = entite.platform if entite is not None else None
        self._cadence = Cadence()
        self._signal = SignalLux(self._constantes())
        self._actualiser_profil()
        self._reinitialiser_sante()
        self._reinitialiser_corrections()
        etat = self.hass.states.get(self.capteur)
        if (lux := _lire_lux(etat)) is not None:
            self._cadence.noter(etat.last_reported_timestamp)
            self._signal.mesurer(_horloge(), lux)
            # Valeur maintenue, pas un nouveau rapport : la rétroaction
            # seulement.
            self._retroaction.rapport(_horloge(), lux)

    def arreter(self) -> None:
        for desabonner in self._desabonnements:
            desabonner()
        self._desabonnements.clear()
        for ne_plus_suivre in self._ne_plus_suivre_capteur:
            ne_plus_suivre()
        self._ne_plus_suivre_capteur = []
        self._annuler_planification()
        self._abandonner_correction()
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
            self._annuler_fin_pause = None
        if self._tache is not None:
            self._tache.cancel()
        if self._transition is not None:
            # Les pas déjà faits restent historisés.
            if self._transition.tache is not None:
                self._transition.tache.cancel()
            self._finir_rampe("arret")
        ir.async_delete_issue(self.hass, DOMAIN, PROBLEME_CONFLIT)
        ir.async_delete_issue(self.hass, DOMAIN, PROBLEME_FIGE)

    def ecouter(self, ecouteur: Callable[[], None]) -> Callable[[], None]:
        """Abonne une entité aux changements d'état de la fonction."""
        self._ecouteurs.append(ecouteur)
        return lambda: self._ecouteurs.remove(ecouteur)

    def ecouter_details(self, ecouteur: Callable[[], None]) -> Callable[[], None]:
        """Abonne la page du panneau aux changements du détail seul
        (progression d'une rampe)."""
        self._ecouteurs_details.append(ecouteur)
        return lambda: self._ecouteurs_details.remove(ecouteur)

    def ecouter_sante(self, ecouteur: Callable[[], None]) -> Callable[[], None]:
        """Abonne la page du panneau aux changements de la santé de
        l'installation."""
        self._ecouteurs_sante.append(ecouteur)
        return lambda: self._ecouteurs_sante.remove(ecouteur)

    def _prevenir(self) -> None:
        self._echantillonner()
        self._cible_signalee = self.cible
        self._synchroniser_reparations()
        for ecouteur in list(self._ecouteurs):
            ecouteur()
        self._prevenir_details()

    def _prevenir_details(self) -> None:
        for ecouteur in list(self._ecouteurs_details):
            ecouteur()

    def ecouter_suggestions(self, ecouteur: Callable[[], None]) -> Callable[[], None]:
        """Abonne la page du panneau aux corrections et aux suggestions."""
        self._ecouteurs_suggestions.append(ecouteur)
        return lambda: self._ecouteurs_suggestions.remove(ecouteur)

    def ecouter_journal(self, ecouteur: Callable[[dict], None]) -> Callable[[], None]:
        """Abonne le panneau aux nouveaux événements du journal."""
        self._ecouteurs_journal.append(ecouteur)
        return lambda: self._ecouteurs_journal.remove(ecouteur)

    def _noter(self, type_: str, **details) -> None:
        evenement = {"horodatage": dt_util.utcnow().isoformat(), "type": type_, **details}
        self.journal.append(evenement)
        for ecouteur in list(self._ecouteurs_journal):
            ecouteur(evenement)

    # --------------------------------------------------------------- signal
    def _constantes(self):
        return constantes(self.options, self.profil, self.options[CONF_EMPLACEMENT])

    def _actualiser_profil(self) -> None:
        self.profil = profil(self._plateforme, self._cadence.intervalle())
        self._signal.constantes = self._constantes()

    @property
    def lux(self) -> float | None:
        """Dernière mesure brute du capteur."""
        return _lire_lux(self.hass.states.get(self.capteur))

    @property
    def lux_filtre(self) -> float | None:
        if self.lux is None:
            return None
        return self._signal.lux_filtre(_horloge())

    def _lux_retenu(self) -> float | None:
        """Dernière mesure retenue par le signal (sauts confirmés)."""
        if self.lux is None:
            return None
        return self._signal.lux_vise(_horloge())

    @property
    def cible(self) -> int | None:
        lux = self.lux_filtre
        return None if lux is None else calculer_cible(lux, self.options)

    @property
    def rampe(self) -> Rampe | None:
        return self._transition.rampe if self._transition is not None else None

    @property
    def cible_finale(self) -> int | None:
        """Cible une fois le filtre arrivé sur la dernière mesure retenue."""
        if self.lux is None:
            return None
        lux = self._signal.lux_vise(_horloge())
        return None if lux is None else calculer_cible(lux, self.options)

    @property
    def ecart_minimal(self) -> int:
        ecart = self.options.get(CONF_ECART_MINIMAL)
        return ECART_MINIMAL_DEFAUT if ecart is None else ecart

    def _actuelle(self) -> float | None:
        """Luminosité notifiée ou relue par le téléviseur."""
        try:
            return float(self._tv.etat.get(CATEGORIE, {}).get(CLE))
        except (TypeError, ValueError):
            return None

    # ----------------------------------------------------------------- état
    def mode_exclu(self, mode: str | None) -> bool:
        exclus = self.options[CONF_MODES_EXCLUS]
        if mode in self._modes_menu:
            return mode in exclus
        if mode is not None and mode.startswith(("hdr", "dolbyHdr")):
            return MODES_HDR in exclus
        # Mode inconnu du menu (ex. creator) : l'utilisateur n'a pas pu le
        # choisir dans les options, on n'y touche pas.
        return True

    @property
    def conflit(self) -> str | None:
        """Fonction du téléviseur qui règle déjà la luminosité d'après son
        propre capteur : deux régulations se contrarieraient. Seulement si
        la fonction agirait dans le mode actif."""
        mode = self._tv.mode_image
        if self.mode_exclu(mode):
            return None
        if self._tv.etat.get(CATEGORIE, {}).get(CLE_ECONOMIE) in ECONOMIE_EN_CONFLIT:
            return "economie_energie"
        if mode == MODE_ECO:
            return "mode_eco"
        return None

    @property
    def economie_energie(self) -> str | None:
        return self._tv.etat.get(CATEGORIE, {}).get(CLE_ECONOMIE)

    @property
    def fige(self) -> bool:
        return self._cadence.fige(_horloge())

    @property
    def etat(self) -> str:
        if not self.active:
            return "desactivee"
        if self._tv.etat_connexion != "connecte":
            return "televiseur_deconnecte"
        if self._tv.ecriture_possible is False:
            return "consultation"
        if self._mises_en_route:
            return "mise_en_route"
        if self.fin_pause is not None:
            return "pause"
        if self.mode_exclu(self._tv.mode_image):
            return "mode_exclu"
        if self.conflit is not None:
            return "conflit_economie_energie"
        if self.lux is None:
            return "capteur_indisponible"
        if self.fige:
            return "capteur_fige"
        return "active"

    def _synchroniser_reparations(self) -> None:
        """Réparations alignées sur l'état : le conflit compte même pendant
        une pause (il reviendra à sa levée), le capteur figé seulement
        téléviseur allumé."""
        connecte = self.active and self._tv.etat_connexion == "connecte"
        conflit = self.conflit if connecte else None
        if conflit != self._conflit_signale:
            self._conflit_signale = conflit
            if conflit is None:
                ir.async_delete_issue(self.hass, DOMAIN, PROBLEME_CONFLIT)
            else:
                self._noter("conflit", cause=conflit)
                ir.async_create_issue(
                    self.hass, DOMAIN, PROBLEME_CONFLIT,
                    is_fixable=conflit == "economie_energie",
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=(PROBLEME_CONFLIT if conflit == "economie_energie"
                                     else "conflit_mode_eco"))
            self._actualiser_sante()
        fige = connecte and self.fige
        if fige != self._fige_signale:
            self._fige_signale = fige
            if not fige:
                ir.async_delete_issue(self.hass, DOMAIN, PROBLEME_FIGE)
            else:
                self._noter("capteur_fige")
                etat = self.hass.states.get(self.capteur)
                ir.async_create_issue(
                    self.hass, DOMAIN, PROBLEME_FIGE, is_fixable=False,
                    severity=ir.IssueSeverity.WARNING, translation_key=PROBLEME_FIGE,
                    translation_placeholders={
                        "capteur": etat.name if etat is not None else self.capteur,
                        "depuis": dt_util.as_local(dt_util.utc_from_timestamp(
                            self._cadence.dernier)).strftime("%d/%m %H:%M"),
                    })
            self._actualiser_sante()

    # ------------------------------------------------------------ commandes
    def restaurer(self, active: bool, fin_pause: datetime | None,
                  cause_pause: dict | None = None) -> None:
        self.active = active
        if active and fin_pause is not None and fin_pause > dt_util.utcnow():
            self._mettre_en_pause_jusqua(fin_pause, cause_pause)
        self._prevenir()

    def activer(self, active: bool) -> None:
        if active != self.active:
            self._noter("activation" if active else "desactivation")
        self.active = active
        self._lever_pause()
        if active:
            self._signal.oublier_reference()
            self._lancer()
        else:
            self._annuler_planification()
        self._prevenir()

    def reprendre(self, raison: str = "bouton", **details) -> None:
        self._lever_pause(raison, **details)
        self._signal.oublier_reference()
        self._lancer()
        self._prevenir()

    def mettre_en_pause(self, minutes: int) -> None:
        """Pause demandée depuis le panneau (le temps d'un film), sans
        toucher à la luminosité."""
        self._pause(dt_util.utcnow() + timedelta(minutes=minutes), PAUSE_MANUELLE)
        self._accumulateur.pause_manuelle()
        self._reprise_en_cours = None
        self._prevenir()
        self._actualiser_sante()

    def reconfigurer(self, options: dict) -> None:
        """Options modifiées depuis le panneau, appliquées sans recharger
        l'intégration (qui couperait la connexion au téléviseur). Une pause
        en cours est conservée."""
        self.options = {**OPTIONS_LUMINOSITE_DEFAUT, **options}
        if options[CONF_CAPTEUR_LUX] != self.capteur:
            # Les statistiques de l'ancien capteur, avant de repartir de
            # celles du nouveau.
            if (a_ecrire := self._a_ecrire()) is not None:
                self.hass.async_create_task(self._statistiques.enregistrer(*a_ecrire))
            self.capteur = options[CONF_CAPTEUR_LUX]
            self._suivre_capteur()
        else:
            self._actualiser_profil()
        self._signal.oublier_reference()
        self._planifier(DELAI_APPLICATION_S)
        self._prevenir()
        self._actualiser_sante()
        self._actualiser_suggestions()

    def commencer_mise_en_route(self) -> None:
        """Assistant de mise en route ouvert dans le panneau : la fonction
        n'écrit plus, et la luminosité réglée pendant ce temps (curseur de
        l'assistant, télécommande) ne la met pas en pause."""
        self._mises_en_route += 1
        if self._mises_en_route > 1:
            return
        # Le point d'ancrage va recaler la courbe : la correction en cours
        # ne la décrirait plus.
        self._abandonner_correction("mise_en_route")
        if self.rampe is not None:
            self.rampe.interrompre("mise_en_route")
        self._annuler_planification()
        self._noter("mise_en_route")
        self._prevenir()

    def terminer_mise_en_route(self) -> None:
        """Assistant fermé (terminé, abandonné ou connexion perdue) : la
        fonction reprend, sans condition d'hystérésis. Une pause d'avant
        l'assistant est conservée."""
        self._mises_en_route = max(self._mises_en_route - 1, 0)
        # Fonction arrêtée entre-temps (rechargement) : rien à relancer.
        if self._mises_en_route or not self._desabonnements:
            return
        self._noter("fin_mise_en_route")
        self._signal.oublier_reference()
        self._planifier(DELAI_APPLICATION_S)
        self._prevenir()

    def ancrer(self) -> tuple[dict, dict]:
        """Point d'ancrage : la courbe est calée pour donner, au lux filtré du
        moment, la luminosité du téléviseur (notifiée ou relue, jamais celle
        demandée). Renvoie les options à enregistrer et le compte rendu."""
        if self._tv.etat_connexion != "connecte":
            raise AncrageImpossible("deconnecte")
        # La luminosité d'un mode calibré ne dit rien de la préférence.
        if self.mode_exclu(self._tv.mode_image):
            raise AncrageImpossible("mode_exclu")
        lux, valeur = self.lux_filtre, self._actuelle()
        if lux is None or valeur is None:
            raise AncrageImpossible("indisponible")
        options, ancrages, compte_rendu = courbe.ancrer(
            self.options, self.options.get(CONF_ANCRAGES), lux, round(valeur),
            dt_util.utcnow().isoformat())
        self._noter("ancrage", lux=round(lux, 1), luminosite=round(valeur),
                    points=compte_rendu["points"])
        return {**options, CONF_ANCRAGES: ancrages}, compte_rendu

    async def desactiver_economie_energie(self, origine: str) -> dict:
        """« Fonction Économie d'énergie » sur Désactivé, sur demande
        explicite de l'utilisateur, par la file d'écriture. L'état suit la
        notification du téléviseur."""
        return await self._ecritures.demander(ID_ECONOMIE, "off", origine)

    # ---------------------------------------------------------- déclencheurs
    @callback
    def _sur_lux(self, evenement: Event[EventStateChangedData]) -> None:
        etat = evenement.data["new_state"]
        self._recevoir(_lire_lux(etat), etat.last_reported_timestamp if etat else None)

    @callback
    def _sur_rapport(self, evenement: Event[EventStateReportedData]) -> None:
        self._recevoir(_lire_lux(evenement.data["new_state"]),
                       evenement.data["last_reported"].timestamp())

    def _recevoir(self, lux: float | None, instant: float | None) -> None:
        if lux is None:
            self._signal.oublier()
        else:
            fige = self._fige_signale
            maintenant = _horloge()
            self._accumulateur.rapport(maintenant, lux, self._tv.etat_connexion == "connecte")
            self._retroaction.rapport(maintenant, lux)
            self._resoudre_retroaction(maintenant)
            self._cadence.noter(instant)
            self._signal.mesurer(_horloge(), lux)
            self._actualiser_profil()
            for evenement in self._signal.evenements():
                self._noter(evenement)
            if fige:
                self._signal.oublier_reference()
            if self._suivi is not None:
                self._suivi.mesurer(maintenant, self.lux_filtre)
            self._verifier_reprise()
        # Débit et non rebond : une rafale de mesures ne repousse pas
        # l'évaluation (un capteur à 0,5 s l'aurait repoussée sans fin).
        if self._annuler_application is None:
            self._planifier(DELAI_APPLICATION_S)
        self._prevenir()

    @callback
    def _verifier_capteur(self, _instant) -> None:
        self._echantillonner()
        # Le filtre avance entre deux mesures d'un capteur qui ne publie que
        # sur variation.
        if self._suivi is not None and self.lux is not None:
            self._suivi.mesurer(_horloge(), self.lux_filtre)
        self._verifier_reprise()
        self._resoudre_retroaction(_horloge())
        self._actualiser_sante()
        if (self.active and self._tv.etat_connexion == "connecte"
                and self.fige != self._fige_signale):
            self._prevenir()

    async def _sur_evenement(self, evenement: dict) -> None:
        if evenement["type"] == "connexion":
            if evenement["etat"] in ("connecte", "deconnecte"):
                self._retroaction.televiseur(_horloge(), evenement["etat"] == "connecte")
            if evenement["etat"] == "connecte":
                if self._eteint_pendant_pause:
                    self._lever_pause("rallumage")
                self._reappliquer(DELAI_APPLICATION_S)
            elif evenement["etat"] == "deconnecte" and self.fin_pause is not None:
                self._eteint_pendant_pause = True
            self._prevenir()
        elif evenement["type"] == "ecriture":
            if evenement["possible"]:
                self._reappliquer(DELAI_APPLICATION_S)
            self._prevenir()
        elif evenement["type"] == "changement" and evenement["categorie"] == CATEGORIE:
            reglages, origine = evenement["reglages"], evenement["origine"]
            if CLE in reglages and origine != "application" and self.rampe is not None:
                # La valeur n'est plus celle que la rampe a confirmée.
                self.rampe.interrompre("reprise_en_main" if origine in ORIGINES_EXTERIEURES
                                       else "changement_exterieur")
            if CLE in reglages and origine in ORIGINES_EXTERIEURES:
                self._reprise_en_main(self._tv.mode_image, origine, reglages[CLE])
            elif origine != "application" and (CLE in reglages or "pictureMode" in reglages):
                self._reappliquer(DELAI_APPLICATION_S)
            elif CLE_ECONOMIE in reglages:
                self._reappliquer(DELAI_APPLICATION_S)
            if "pictureMode" in reglages or CLE_ECONOMIE in reglages:
                self._prevenir()

    @callback
    def _sur_ecriture(self, ecriture: dict) -> None:
        if ecriture["origine"] == ORIGINE:
            return
        if (ecriture["categorie"], ecriture["cle"]) == (CATEGORIE, CLE):
            self._reprise_en_main(ecriture["mode_image"], ecriture["origine"],
                                  ecriture["nouvelle"])
        elif ecriture["origine"] in ORIGINES_LOT:
            self._reappliquer(DELAI_APRES_LOT_S, ecriture["origine"])

    # ----------------------------------------------------------------- pause
    def _reprise_en_main(self, mode: str | None, origine: str, valeur=None) -> None:
        if self._mises_en_route:
            # Curseur de l'assistant ou télécommande : c'est le point
            # d'ancrage qui se cherche, pas une correction de la courbe.
            self._retroaction.perturbation(_horloge())
            return
        # La luminosité d'un mode laissé de côté ne dit rien de celle des
        # autres modes.
        if not self.active or self.mode_exclu(mode):
            return
        self._noter_reprise(valeur)
        self._pause(dt_util.utcnow() + timedelta(minutes=self.options[CONF_PAUSE_MIN]), origine)
        self._observer_correction(mode, origine, valeur)
        self._prevenir()

    def _noter_reprise(self, valeur) -> None:
        """Statistiques : correction = valeur posée par l'utilisateur − cible
        de la fonction, rangée par ambiance (pauses fréquentes ; matière des
        suggestions du lot 5)."""
        self._retroaction.perturbation(_horloge())
        try:
            valeur = float(valeur)
        except (TypeError, ValueError):
            return
        jour = self._accumulateur.stats.jour
        if (self.fin_pause is not None and self._reprise_en_cours is not None
                and self._reprise_en_cours[0] == jour):
            _, nom, precedente = self._reprise_en_cours
            self._accumulateur.corriger_reprise(nom, valeur - precedente)
            self._reprise_en_cours = (jour, nom, valeur)
            return
        cible, lux = self.cible, self.lux_filtre
        if cible is None or lux is None:
            return
        nom = ambiance(lux, self.options[CONF_LUX_MIN], self.options[CONF_LUX_MAX])
        self._accumulateur.reprise(nom, valeur - cible)
        self._reprise_en_cours = (jour, nom, valeur)
        self._actualiser_sante()

    def _pause(self, fin: datetime, origine: str) -> None:
        cause = {"origine": origine, "horodatage": dt_util.utcnow().isoformat()}
        # Éclairage de la reprise en main : la pause se lève s'il change
        # nettement. Mesure retenue, vers laquelle va le filtre : une reprise
        # en main pendant une transition vaut pour l'éclairage d'arrivée.
        # Conservé avec la cause au redémarrage.
        if origine != PAUSE_MANUELLE and (lux := self._lux_retenu()) is not None:
            cause["lux"] = round(lux, 2)
        self._mettre_en_pause_jusqua(fin, cause)
        self._noter("pause", origine=origine, fin=fin.isoformat())

    def _mettre_en_pause_jusqua(self, fin: datetime, cause: dict | None) -> None:
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
        self._annuler_planification()
        self.fin_pause = fin
        self.cause_pause = cause
        self._eteint_pendant_pause = False
        self._annuler_fin_pause = async_track_point_in_utc_time(
            self.hass, self._sur_fin_de_pause, fin)

    @callback
    def _sur_fin_de_pause(self, _maintenant) -> None:
        self._annuler_fin_pause = None
        self.reprendre("delai")

    def _lever_pause(self, raison: str | None = None, **details) -> None:
        """`raison` : délai, bouton, rallumage ou changement d'éclairage,
        notée au journal ; aucune quand l'interrupteur change (son
        changement est déjà noté)."""
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
            self._annuler_fin_pause = None
        if self.fin_pause is not None:
            self._abandonner_correction("pause_levee" if raison is not None else None)
        if self.fin_pause is not None and raison is not None:
            self._noter("reprise", raison=raison, **details)
        self.fin_pause = None
        self.cause_pause = None
        self._eteint_pendant_pause = False
        self._reprise_en_cours = None

    def _reference_reprise(self) -> float | None:
        """Lux de la reprise en main, si la pause peut se lever quand
        l'éclairage change : jamais pour une pause demandée depuis le
        panneau (le temps d'un film, souvent lumière éteinte)."""
        cause = self.cause_pause
        if (self.fin_pause is None or cause is None
                or not self.options[CONF_REPRISE_SUR_CHANGEMENT]
                or cause.get("origine") == PAUSE_MANUELLE):
            return None
        return cause.get("lux")

    def _verifier_reprise(self) -> bool:
        """Lève la pause si le lux filtré a doublé ou diminué de moitié
        depuis la reprise en main (reprise.changement_net)."""
        if self._mises_en_route or (reference := self._reference_reprise()) is None:
            return False
        lux, retenu = self.lux_filtre, self._lux_retenu()
        if lux is None or retenu is None or not changement_net(lux, retenu, reference,
                                                                 self.options):
            return False
        self.reprendre("changement_eclairage", lux_depart=round(reference, 1), lux=round(lux, 1))
        return True

    def _surveiller_pause(self) -> None:
        """Évaluation pendant une pause : levée sur changement d'éclairage,
        sinon nouvelle vérification tant que le filtre avance (un capteur
        qui ne publie que sur variation n'en donnera pas l'occasion)."""
        if self._reference_reprise() is None or self._verifier_reprise():
            return
        instant = _horloge()
        echeance = self._signal.prochaine_echeance(instant)
        if echeance is not None and self._annuler_application is None:
            self._planifier(max(echeance - instant, 0.1))

    def _reprise_lux(self) -> dict | None:
        """Lux sous lequel et au-delà duquel la pause en cours se lèvera."""
        if (reference := self._reference_reprise()) is None:
            return None
        bas, haut = bornes_reprise(reference, self.options)
        return {"bas": None if bas is None else round(bas, 1),
                "haut": None if haut is None else round(haut, 1)}

    # ---------------------------------------------------------- corrections
    def _observer_correction(self, mode: str | None, origine: str, valeur) -> None:
        """Reprise en main : correction candidate, retenue si la valeur est
        gardée 10 minutes sous un lux stable. Un nouveau réglage la remplace
        (les 10 minutes repartent)."""
        self._abandonner_correction(None if origine in ORIGINES_CORRECTION else origine)
        try:
            valeur = round(float(valeur))
        except (TypeError, ValueError):
            return
        if origine not in ORIGINES_CORRECTION:
            return
        constantes = self._signal.constantes
        self._suivi = SuiviCorrection(
            _horloge(), valeur, mode, origine,
            lissage_s=max(constantes.lissage_montee_s, constantes.lissage_descente_s))
        self._suivi.mesurer(_horloge(), self.lux_filtre)
        self._annuler_suivi = async_track_point_in_utc_time(
            self.hass, self._sur_fin_suivi, dt_util.utc_from_timestamp(self._suivi.echeance))

    def _abandonner_correction(self, raison: str | None = None) -> None:
        """Correction candidate abandonnée ; `raison` notée au journal (rien
        quand un nouveau réglage la remplace ou que la fonction s'arrête)."""
        if self._annuler_suivi is not None:
            self._annuler_suivi()
            self._annuler_suivi = None
        if self._suivi is not None and raison is not None:
            self._noter("correction_ecartee", raison=raison, valeur=self._suivi.valeur)
        self._suivi = None

    @callback
    def _sur_fin_suivi(self, _maintenant) -> None:
        self._annuler_suivi = None
        suivi, self._suivi = self._suivi, None
        if suivi is None:
            return
        instant = _horloge()
        if self.lux is not None:
            suivi.mesurer(instant, self.lux_filtre)
        actuelle = self._actuelle()
        raison = suivi.verdict(instant, None if actuelle is None else round(actuelle),
                               self._tv.mode_image, self._tv.etat_connexion == "connecte",
                               self.fin_pause is not None)
        # La page n'affiche plus la correction en observation.
        self._prevenir_details()
        if raison is not None:
            self._noter("correction_ecartee", raison=raison, valeur=suivi.valeur)
            return
        correction = suivi.correction(instant, self.options)
        self._noter("correction", lux=correction.lux, valeur=correction.valeur,
                    cible=correction.cible)
        self.hass.async_create_task(self._enregistrer_correction(self.capteur, correction),
                                    f"{DOMAIN} correction")

    async def _enregistrer_correction(self, capteur: str, correction: Correction) -> None:
        try:
            await self._base_corrections.ajouter(capteur, correction)
            await self._base_corrections.purger()
        except Exception:  # noqa: BLE001 — la fonction marche sans
            log.exception("Luminosité adaptative : correction non enregistrée")
        await self._relire_corrections(capteur)

    def _reinitialiser_corrections(self) -> None:
        """Démarrage ou nouveau capteur : corrections de ce capteur, après
        la purge."""
        self._abandonner_correction()
        self._corrections = []
        self._corrections_chargees = False
        self.hass.async_create_task(self._charger_corrections(self.capteur),
                                    f"{DOMAIN} corrections")

    async def _charger_corrections(self, capteur: str) -> None:
        try:
            await self._base_corrections.purger()
        except Exception:  # noqa: BLE001 — la fonction marche sans
            log.exception("Luminosité adaptative : corrections illisibles")
        await self._relire_corrections(capteur)

    async def _relire_corrections(self, capteur: str) -> None:
        try:
            corrections = await self._base_corrections.charger(capteur)
        except Exception:  # noqa: BLE001 — la fonction marche sans
            log.exception("Luminosité adaptative : corrections illisibles")
            return
        if capteur != self.capteur:
            return
        self._corrections = corrections
        self._corrections_chargees = True
        self._actualiser_suggestions()

    def _calculer_suggestions(self) -> dict[str, Any]:
        return {
            "chargees": self._corrections_chargees,
            "corrections": [{
                "id": c.id, "horodatage": dt_util.utc_from_timestamp(c.horodatage).isoformat(),
                "lux": c.lux, "valeur": c.valeur, "cible": c.cible,
                "ecart": ecart(c, self.options), "mode_image": c.mode_image,
                "origine": c.origine, "ecartee": c.ecartee, "plage": plage(c.lux),
            } for c in self._corrections],
            "suggestions": [asdict(s) for s in suggestions(self._corrections, self.options)],
        }

    def _actualiser_suggestions(self) -> None:
        resultat = self._calculer_suggestions()
        if resultat != self._suggestions:
            self._suggestions = resultat
            for ecouteur in list(self._ecouteurs_suggestions):
                ecouteur()

    def suggestions(self) -> dict[str, Any]:
        """Corrections du capteur (écart à la courbe actuelle) et
        suggestions de courbe."""
        if self._suggestions is None:
            self._suggestions = self._calculer_suggestions()
        return self._suggestions

    def _suggestion(self, indice: int):
        suggestion = next((s for s in suggestions(self._corrections, self.options)
                           if s.plage == indice), None)
        if suggestion is None:
            raise SuggestionInconnue(indice)
        return suggestion

    def appliquer_suggestion(self, indice: int) -> tuple[dict, dict]:
        """Courbe proposée pour cette plage, recalculée ici (jamais celle
        qu'envoie le panneau) ; les points d'ancrage sont oubliés, comme
        après toute retouche de la courbe. Renvoie les options à
        enregistrer et le compte rendu."""
        suggestion = self._suggestion(indice)
        self._noter("suggestion_appliquee", lux=suggestion.lux, ecart=suggestion.ecart,
                    corrections=suggestion.nombre)
        return dict(suggestion.options), {
            "plage": indice, "points": suggestion.points, "ajout": suggestion.ajout,
            "ancrages_oublies": bool(self.options.get(CONF_ANCRAGES)),
            "cible": suggestion.cible}

    async def ignorer_suggestion(self, indice: int) -> None:
        """Corrections de la plage écartées des suggestions, gardées à
        l'affichage : une nouvelle suggestion demandera 3 nouvelles
        corrections."""
        self._suggestion(indice)
        ids = a_ecarter(self._corrections, indice)
        await self._base_corrections.ecarter(ids)
        self._noter("suggestion_ignoree", corrections=len(ids))
        await self._relire_corrections(self.capteur)

    async def oublier_correction(self, id_: int) -> None:
        if not await self._base_corrections.oublier(id_):
            raise CorrectionInconnue(id_)
        await self._relire_corrections(self.capteur)

    # ----------------------------------------------------------- application
    def _reappliquer(self, delai_s: float, raison: str = "changement_exterieur") -> None:
        """La luminosité du téléviseur a pu changer sans que le lux bouge
        (mode, entrée, rallumage, preset) : prochaine évaluation sans
        condition d'hystérésis. Une rampe en cours s'arrête : son départ ne
        vaut plus, ou un lot écrit ses propres réglages."""
        if self.rampe is not None:
            self.rampe.interrompre(raison)
        self._signal.oublier_reference()
        self._planifier(delai_s)

    def _planifier(self, delai_s: float) -> None:
        """Évaluation différée ; une échéance déjà plus lointaine est
        conservée (un lot en cours repousse, un nouveau lux n'avance pas)."""
        echeance = dt_util.utcnow() + timedelta(seconds=delai_s)
        if self._annuler_application is not None and self._echeance >= echeance:
            return
        self._annuler_planification()
        self._echeance = echeance
        self._annuler_application = async_track_point_in_utc_time(
            self.hass, self._sur_echeance, echeance)

    def _annuler_planification(self) -> None:
        if self._annuler_application is not None:
            self._annuler_application()
            self._annuler_application = None

    @callback
    def _sur_echeance(self, _maintenant) -> None:
        self._annuler_application = None
        self._lancer()

    def _lancer(self) -> None:
        self._annuler_planification()
        if self.rampe is not None:
            # La rampe suit déjà la cible ; une évaluation suit sa fin.
            return
        self._tache = self.hass.async_create_background_task(
            self._evaluer(), f"{DOMAIN} luminosité adaptative")

    async def _evaluer(self) -> None:
        etat = self.etat
        if etat == "pause":
            self._surveiller_pause()
            return
        if etat != "active":
            return
        instant = _horloge()
        echeance = None
        if self._signal.hors_bande(instant):
            if self._signal.gele(instant):
                echeance = self._signal.fin_gel
            else:
                self._appliquer()
                if self.rampe is not None:
                    # Elle planifiera l'évaluation suivante à sa fin.
                    return
        # Le filtre avance encore, un saut attend sa confirmation, ou une
        # mesure attend la fin du gel : nouvelle évaluation sans mesure.
        instant = _horloge()
        echeances = [e for e in (echeance, self._signal.prochaine_echeance(instant))
                     if e is not None]
        if echeances and self._annuler_application is None:
            self._planifier(max(min(echeances) - instant, 0.1))
        # Le lux filtré avance entre deux mesures : l'état suit la cible, et
        # une dernière fois filtre arrivé (lux filtré exact).
        if not echeances or self.cible != self._cible_signalee:
            self._prevenir()

    def _appliquer(self) -> None:
        lux = self._signal.lux_filtre(_horloge())
        cible = calculer_cible(lux, self.options)
        actuelle = self._actuelle()
        if actuelle is not None and abs(cible - actuelle) < self.ecart_minimal:
            # Le téléviseur est déjà à la bonne valeur : ce lux devient la
            # référence de l'hystérésis, mais seulement filtre arrivé. En
            # pleine transition, l'avancer laisserait la luminosité s'arrêter
            # en chemin (dernier pas sous l'écart minimal, puis lux final
            # dans la bande).
            if self._signal.converge(_horloge()):
                self._signal.noter_reference(lux)
            return
        self._demarrer_rampe(None if actuelle is None else round(actuelle))

    # --------------------------------------------------------------- rampe
    # Machine à états sur les minuteries de Home Assistant, comme
    # l'évaluation : chaque pas est une tâche courte, l'attente entre deux
    # pas une minuterie. Une tâche qui dormirait toute la rampe retiendrait
    # l'arrêt de Home Assistant.

    def _demarrer_rampe(self, depart: int | None) -> None:
        self._transition = _Transition(
            Rampe(parametres(self.options), depart, _horloge()), self._tv.mode_image)
        self._signal.suspendre(_horloge())
        self._retroaction.perturbation(_horloge())
        self._prevenir()
        self._avancer_rampe()

    def _arret_rampe(self, transition: _Transition) -> str | None:
        """Raison d'arrêter la rampe avant son prochain pas, ou None."""
        etat = self.etat
        if etat == "pause":
            origine = self.cause_pause["origine"] if self.cause_pause else None
            return PAUSE_MANUELLE if origine == PAUSE_MANUELLE else "reprise_en_main"
        # Garde de mode : la luminosité est propre au mode de départ.
        if self._tv.mode_image != transition.mode:
            return "mode"
        if transition.rampe.interruption is not None:
            return transition.rampe.interruption
        if etat != "active":
            return etat
        # Une écriture de l'utilisateur attend son tour : le pas suivant la
        # coalescerait et l'effacerait. Elle sera historisée, puis mettra la
        # fonction en pause.
        if self._ecritures.origine_en_attente(ID_OLED) not in (None, ORIGINE):
            return "reprise_en_main"
        return None

    @callback
    def _avancer_rampe(self, _maintenant=None) -> None:
        """Prochain pas vers la cible du moment : écrit tout de suite, ou à
        son heure ; fin de la rampe à l'arrivée du filtre ou sur un arrêt."""
        transition = self._transition
        if transition is None:
            return
        transition.annuler_minuterie = None
        if (fin := self._arret_rampe(transition)) is not None:
            self._finir_rampe(fin)
            return
        rampe = transition.rampe
        instant = _horloge()
        cible = self.cible
        if cible != self._cible_signalee:
            self._prevenir()
        pas = rampe.prochain_pas(instant, cible)
        if pas is None:
            if rampe.arrivee(cible, self.cible_finale):
                self._finir_rampe("arrivee")
            else:
                # Téléviseur sur la cible, filtre pas encore arrivé : la
                # cible bougera encore.
                self._attendre_rampe(instant + min(rampe.parametres.intervalle_s,
                                                   REEVALUATION_S))
            return
        echeance, valeur = pas
        if echeance > instant:
            # Puis tout revérifier : la cible ou l'état ont pu changer.
            self._attendre_rampe(echeance)
            return
        rampe.envoyer(instant, valeur)
        transition.demandee = valeur
        transition.tache = self.hass.async_create_background_task(
            self._ecrire_pas(transition, valeur), f"{DOMAIN} rampe de luminosité")

    def _attendre_rampe(self, instant: float) -> None:
        self._transition.annuler_minuterie = async_track_point_in_utc_time(
            self.hass, self._avancer_rampe, dt_util.utc_from_timestamp(instant))

    async def _ecrire_pas(self, transition: _Transition, valeur: int) -> None:
        try:
            # Le premier pas est historisé à sa place parmi les autres
            # écritures (retour à un instant donné), les suivants non.
            resultat = await self._ecritures.demander(
                ID_OLED, valeur, ORIGINE, mode_attendu=transition.mode,
                historiser=transition.premier is None)
        except Exception as exc:  # noqa: BLE001 — exposé dans l'état
            resultat = {"ok": False, "raison": str(exc)}
        transition.tache = None
        if self._transition is not transition:
            return
        if not resultat["ok"]:
            # Une reprise en main ou un changement de mode survenus pendant
            # l'écriture l'expliquent mieux qu'un échec.
            fin = self._arret_rampe(transition) or "non_confirmee"
            if fin == "non_confirmee":
                self.derniere_erreur = resultat["raison"]
                log.info("Luminosité adaptative : écriture de %s impossible : %s",
                         valeur, self.derniere_erreur)
            self._finir_rampe(fin)
            return
        self.derniere_erreur = None
        transition.premier = transition.premier or resultat
        transition.dernier = resultat
        # La valeur relue sur le téléviseur, jamais celle demandée.
        transition.rampe.confirmer(round(float(resultat["nouvelle"])))
        self._prevenir_details()
        self._avancer_rampe()

    def _finir_rampe(self, fin: str) -> None:
        transition, self._transition = self._transition, None
        if transition.annuler_minuterie is not None:
            transition.annuler_minuterie()
        instant = _horloge()
        self._signal.geler(instant)
        lux = self._signal.lux_filtre(instant) if self.lux is not None else None
        if fin == "arrivee" and lux is not None:
            self._signal.noter_reference(lux)
        else:
            # Interrompue : prochaine évaluation sans condition
            # d'hystérésis.
            self._signal.oublier_reference()
        rampe = transition.rampe
        if transition.dernier is not None:
            self._noter("application", lux=None if lux is None else round(lux, 1),
                        lux_brut=self.lux, ancienne=rampe.depart, cible=rampe.valeur,
                        pas=rampe.pas_confirmes, duree_s=round(rampe.duree(instant), 1),
                        fin=fin)
            if rampe.pas_confirmes > 1:
                self.hass.async_create_background_task(
                    self._historiser_rampe(transition), f"{DOMAIN} historique de la rampe")
            self._compter_transition(rampe, instant, fin)
        elif fin == "non_confirmee":
            self._noter("erreur", cible=transition.demandee, raison=self.derniere_erreur)
        if fin == "non_confirmee":
            self._accumulateur.non_confirmee()
        if fin != "arret":
            self._actualiser_sante()
            # Évaluation après le gel : mesure mise de côté, filtre qui
            # avance encore, ou valeur changée par le téléviseur.
            self._planifier(max(self._signal.fin_gel - instant, 0.1))
            self._prevenir()

    def _compter_transition(self, rampe: Rampe, instant: float, fin: str) -> None:
        """Statistiques d'une transition faite : sens (allers-retours) et,
        capteur rapide, réponse du capteur à l'écran une fois stabilisé."""
        inversion = episode = False
        if rampe.depart is not None and rampe.valeur != rampe.depart:
            delta = rampe.valeur - rampe.depart
            inversion, episode = self._inversions.transition(instant, 1 if delta > 0 else -1)
            lux_avant = self._signal.lux_vise(instant) if self.lux is not None else None
            if (fin == "arrivee" and self.profil == "rapide" and abs(delta) >= RAMPE_DELTA_MIN
                    and lux_avant is not None):
                self._retroaction.rampe(instant, lux_avant, delta, self._signal.constantes.gel_s)
        self._accumulateur.transition(rampe.pas_confirmes, inversion, episode)
        if episode:
            self._noter("allers_retours")

    async def _historiser_rampe(self, transition: _Transition) -> None:
        """Une seule entrée pour la rampe, celle du premier pas, complétée de
        la nouvelle valeur du dernier : le retour arrière restaure le
        départ."""
        await self._historique.completer(transition.premier["id_historique"],
                                         transition.dernier["nouvelle"])

    # ------------------------------------------------------------- santé
    def _reinitialiser_sante(self) -> None:
        """Démarrage ou nouveau capteur : les statistiques repartent de
        celles enregistrées pour ce capteur."""
        self._jours = {}
        self._accumulateur = Accumulateur(StatsJour(_jour_local()))
        self._retroaction = Retroaction()
        self._inversions = Inversions()
        self._stats_chargees = False
        self._a_enregistrer = set()
        self._reprise_en_cours = None
        self._tache_stats = self.hass.async_create_task(
            self._charger_statistiques(self.capteur), f"{DOMAIN} statistiques")

    async def _charger_statistiques(self, capteur: str) -> None:
        depuis = _premier_jour_conserve()
        try:
            await self._statistiques.purger(depuis)
            lignes = await self._statistiques.charger(capteur, depuis)
        except Exception:  # noqa: BLE001 — la fonction marche sans
            log.exception("Luminosité adaptative : statistiques illisibles")
            lignes = []
        if capteur != self.capteur:
            return
        for donnees in lignes:
            stats = StatsJour.depuis_dict(donnees)
            if stats.jour == self._accumulateur.stats.jour:
                # Jour commencé avant le redémarrage, puis depuis.
                stats.fusionner(self._accumulateur.stats)
                self._accumulateur.stats = stats
            else:
                self._jours.setdefault(stats.jour, stats)
        self._stats_chargees = True
        self._actualiser_sante()

    def _a_ecrire(self) -> tuple[str, list[dict]] | None:
        """(capteur, jours) à enregistrer, figés tout de suite : le capteur
        peut changer pendant l'écriture."""
        if not self._stats_chargees:
            return None
        jours = [self._jours[jour].en_dict() for jour in self._a_enregistrer
                 if jour in self._jours]
        self._a_enregistrer = set()
        return self.capteur, [*jours, self._accumulateur.stats.en_dict()]

    async def enregistrer_statistiques(self) -> None:
        self._echantillonner()
        if (a_ecrire := self._a_ecrire()) is not None:
            await self._statistiques.enregistrer(*a_ecrire)

    @callback
    def _enregistrer_periodiquement(self, _instant) -> None:
        self.hass.async_create_task(self.enregistrer_statistiques(),
                                    f"{DOMAIN} statistiques")

    async def _sur_arret_hass(self, _evenement) -> None:
        await self.enregistrer_statistiques()

    def _echantillonner(self) -> None:
        """Temps passé dans l'état d'avant (allumé, active, lux) ; au
        changement de jour, le jour fini est enregistré."""
        termine = self._accumulateur.echantillon(
            _horloge(), _jour_local(), self._tv.etat_connexion == "connecte",
            self.etat == "active", self.lux_filtre, self.lux)
        if termine is None:
            return
        self._jours[termine.jour] = termine
        self._a_enregistrer.add(termine.jour)
        limite = _premier_jour_conserve()
        for jour in [jour for jour in self._jours if jour < limite]:
            del self._jours[jour]
        self.hass.async_create_task(self.enregistrer_statistiques(), f"{DOMAIN} statistiques")

    def _resoudre_retroaction(self, instant: float) -> None:
        resultats = self._retroaction.resoudre(instant)
        for nature, valeur in resultats:
            if nature == "tv":
                sens, avant, apres = valeur
                self._accumulateur.evenement_tv(valeur)
                # Au journal : de quoi vérifier la mesure à l'essai réel.
                self._noter("retroaction", sens=sens, avant=avant, apres=apres)
            else:
                self._accumulateur.reponse_rampe(valeur)
        if resultats:
            self._actualiser_sante()

    def _pieces(self) -> tuple[str | None, str | None]:
        return (nom_zone(self.hass, zone_entite(self.hass, self.capteur)),
                nom_zone(self.hass, zone_televiseur(self.hass)))

    def _calculer_sante(self) -> dict[str, Any]:
        piece_capteur, piece_televiseur = self._pieces()
        contexte = Contexte(
            options=self.options, constantes=self._signal.constantes, profil=self.profil,
            plateforme=self._plateforme, conflit=self._conflit_signale,
            fige=self._fige_signale, ecriture_possible=self._tv.ecriture_possible,
            piece_capteur=piece_capteur, piece_televiseur=piece_televiseur)
        jours = [*self._jours.values(), self._accumulateur.stats]
        aujourdhui = self._accumulateur.stats.jour
        return {
            "chargees": self._stats_chargees,
            "diagnostics": [asdict(d) for d in evaluer(jours, aujourdhui, contexte)],
            "resume": resume(jours, aujourdhui),
            "jours": [resume_jour(jour) for jour in reversed(fenetre(jours, aujourdhui))],
        }

    def _actualiser_sante(self) -> None:
        sante = self._calculer_sante()
        if sante != self._sante:
            self._sante = sante
            for ecouteur in list(self._ecouteurs_sante):
                ecouteur()

    def sante(self) -> dict[str, Any]:
        """Santé de l'installation : diagnostics, statistiques des 7
        derniers jours et par jour."""
        if self._sante is None:
            self._sante = self._calculer_sante()
        return self._sante

    def _resume_rampe(self) -> dict | None:
        if self.rampe is None:
            return None
        return {"depart": self.rampe.depart,
                "debut": dt_util.utc_from_timestamp(self.rampe.debut).isoformat()}

    def resume(self) -> dict[str, Any]:
        """État transmis au panneau. Sans le lux : il change à chaque mesure
        du capteur, et le panneau n'est prévenu que si le résumé change."""
        return {
            "etat": self.etat,
            "entree_id": ID_OLED,
            "cible": self.cible,
            "fin_pause": self.fin_pause.isoformat() if self.fin_pause else None,
            "cause_pause": self.cause_pause,
            "conflit": self.conflit,
            "rampe": self._resume_rampe(),
            "reprise_lux": self._reprise_lux(),
        }

    def details(self) -> dict[str, Any]:
        """État complet pour la page du panneau, suivi seulement pendant
        qu'elle est ouverte."""
        lux_filtre = self.lux_filtre
        dernier = self._cadence.dernier
        rampe = self._resume_rampe()
        if rampe is not None:
            rampe["pas"] = self.rampe.pas_confirmes
        return {
            **self.resume(),
            "rampe": rampe,
            "lux": self.lux,
            "lux_filtre": None if lux_filtre is None else round(lux_filtre, 1),
            "actuelle": self._actuelle(),
            "mode_image": self._tv.mode_image,
            "mode_exclu": self.mode_exclu(self._tv.mode_image),
            "economie_energie": self.economie_energie,
            "derniere_erreur": self.derniere_erreur,
            "profil": {"nom": self.profil, "plateforme": self._plateforme,
                       "intervalle_s": self._cadence.intervalle()},
            "constantes": asdict(self._signal.constantes),
            # Valeurs effectives des options avancées laissées vides.
            "ecart_minimal": self.ecart_minimal,
            "parametres_rampe": asdict(parametres(self.options)),
            "emplacement": self.options[CONF_EMPLACEMENT],
            "derniere_mesure": (dt_util.utc_from_timestamp(dernier).isoformat()
                                if dernier is not None else None),
            # Correction en observation : valeur et fin des 10 minutes.
            "correction_en_cours": None if self._suivi is None else {
                "valeur": self._suivi.valeur,
                "fin": dt_util.utc_from_timestamp(self._suivi.echeance).isoformat()},
        }

    def attributs(self) -> dict[str, Any]:
        lux_filtre = self.lux_filtre
        return {
            "lux": self.lux,
            "lux_filtre": None if lux_filtre is None else round(lux_filtre, 1),
            "cible": self.cible,
            "fin_pause": self.fin_pause.isoformat() if self.fin_pause else None,
            "cause_pause": self.cause_pause["origine"] if self.cause_pause else None,
            "mode_image": self._tv.mode_image,
            "conflit": self.conflit,
            "rampe": self._resume_rampe(),
            "profil": self.profil,
            "emplacement": self.options[CONF_EMPLACEMENT],
            "derniere_erreur": self.derniere_erreur,
        }
