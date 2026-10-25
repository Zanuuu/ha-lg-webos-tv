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
  arrivée) ; mesures mises de côté pendant la rampe et le gel qui suit.
"""

import logging
import math
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import (Event, EventStateChangedData,
                                EventStateReportedData, HomeAssistant, State,
                                callback)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (async_track_point_in_utc_time,
                                         async_track_state_change_event,
                                         async_track_state_report_event,
                                         async_track_time_interval)
from homeassistant.util import dt as dt_util

from .const import (CONF_CAPTEUR_LUX, CONF_CONFIRMATION_SAUT,
                    CONF_ECART_MINIMAL, CONF_EMPLACEMENT, CONF_GEL_ECRITURE,
                    CONF_HYSTERESIS_DESCENTE, CONF_HYSTERESIS_MONTEE,
                    CONF_LISSAGE_DESCENTE, CONF_LISSAGE_MONTEE,
                    CONF_LUMINOSITE_MAX, CONF_LUMINOSITE_MIN, CONF_LUX_MAX,
                    CONF_LUX_MIN, CONF_MODES_EXCLUS, CONF_PAUSE_MIN,
                    CONF_RAMPE_DEBIT, CONF_RAMPE_PAS, DOMAIN,
                    ECART_MINIMAL_DEFAUT, EMPLACEMENTS, MODES_HDR,
                    OPTIONS_AVANCEES, OPTIONS_LUMINOSITE_DEFAUT)
from .entite import descriptions
from .rampe import Rampe, parametres
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
ETATS = ["desactivee", "televiseur_deconnecte", "consultation", "pause",
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
    options = {cle: valeur for cle, valeur in options.items()
               if not (cle in OPTIONS_AVANCEES and valeur is None)}
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
    exclus = options.get(CONF_MODES_EXCLUS)
    if not isinstance(exclus, list) or not set(exclus) <= set(modes):
        erreurs[CONF_MODES_EXCLUS] = "mode_inconnu"
    if options.get(CONF_EMPLACEMENT, "inconnu") not in EMPLACEMENTS:
        erreurs[CONF_EMPLACEMENT] = "emplacement_inconnu"
    if erreurs:
        return options, erreurs
    # Les sélecteurs numériques rendent des flottants.
    return {**options, **{cle: int(options[cle]) for cle in ENTIERS if cle in options}}, {}


def calculer_cible(lux: float, options: dict) -> int:
    """Interpolation sur le logarithme du lux, bornée aux extrêmes."""
    lux_min, lux_max = options[CONF_LUX_MIN], options[CONF_LUX_MAX]
    t = (math.log(max(lux, 1)) - math.log(lux_min)) / (math.log(lux_max) - math.log(lux_min))
    t = min(max(t, 0), 1)
    bas, haut = options[CONF_LUMINOSITE_MIN], options[CONF_LUMINOSITE_MAX]
    # Arrondi « commercial » (0,5 vers le haut), comme Jinja dans le
    # blueprint, plutôt que l'arrondi au pair de round().
    return int(math.floor(bas + t * (haut - bas) + 0.5))


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

        # Signal du capteur : repart de zéro à chaque changement de capteur.
        self._plateforme: str | None = None
        self.profil = "inconnu"
        self._cadence = Cadence()
        self._signal = SignalLux(self._constantes())
        # Réparations ouvertes : cause du conflit, capteur figé.
        self._conflit_signale: str | None = None
        self._fige_signale = False
        self._cible_signalee: int | None = None

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
        etat = self.hass.states.get(self.capteur)
        if (lux := _lire_lux(etat)) is not None:
            self._cadence.noter(etat.last_reported_timestamp)
            self._signal.mesurer(_horloge(), lux)

    def arreter(self) -> None:
        for desabonner in self._desabonnements:
            desabonner()
        self._desabonnements.clear()
        for ne_plus_suivre in self._ne_plus_suivre_capteur:
            ne_plus_suivre()
        self._ne_plus_suivre_capteur = []
        self._annuler_planification()
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

    def _prevenir(self) -> None:
        self._cible_signalee = self.cible
        self._synchroniser_reparations()
        for ecouteur in list(self._ecouteurs):
            ecouteur()
        self._prevenir_details()

    def _prevenir_details(self) -> None:
        for ecouteur in list(self._ecouteurs_details):
            ecouteur()

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

    def reprendre(self, raison: str = "bouton") -> None:
        self._lever_pause(raison)
        self._signal.oublier_reference()
        self._lancer()
        self._prevenir()

    def mettre_en_pause(self, minutes: int) -> None:
        """Pause demandée depuis le panneau (le temps d'un film), sans
        toucher à la luminosité."""
        self._pause(dt_util.utcnow() + timedelta(minutes=minutes), PAUSE_MANUELLE)
        self._prevenir()

    def reconfigurer(self, options: dict) -> None:
        """Options modifiées depuis le panneau, appliquées sans recharger
        l'intégration (qui couperait la connexion au téléviseur). Une pause
        en cours est conservée."""
        self.options = {**OPTIONS_LUMINOSITE_DEFAUT, **options}
        if options[CONF_CAPTEUR_LUX] != self.capteur:
            self.capteur = options[CONF_CAPTEUR_LUX]
            self._suivre_capteur()
        else:
            self._actualiser_profil()
        self._signal.oublier_reference()
        self._planifier(DELAI_APPLICATION_S)
        self._prevenir()

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
            self._cadence.noter(instant)
            self._signal.mesurer(_horloge(), lux)
            self._actualiser_profil()
            for evenement in self._signal.evenements():
                self._noter(evenement)
            if fige:
                self._signal.oublier_reference()
        # Débit et non rebond : une rafale de mesures ne repousse pas
        # l'évaluation (un capteur à 0,5 s l'aurait repoussée sans fin).
        if self._annuler_application is None:
            self._planifier(DELAI_APPLICATION_S)
        self._prevenir()

    @callback
    def _verifier_capteur(self, _instant) -> None:
        if (self.active and self._tv.etat_connexion == "connecte"
                and self.fige != self._fige_signale):
            self._prevenir()

    async def _sur_evenement(self, evenement: dict) -> None:
        if evenement["type"] == "connexion":
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
                self._reprise_en_main(self._tv.mode_image, origine)
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
            self._reprise_en_main(ecriture["mode_image"], ecriture["origine"])
        elif ecriture["origine"] in ORIGINES_LOT:
            self._reappliquer(DELAI_APRES_LOT_S, ecriture["origine"])

    # ----------------------------------------------------------------- pause
    def _reprise_en_main(self, mode: str | None, origine: str) -> None:
        # La luminosité d'un mode laissé de côté ne dit rien de celle des
        # autres modes.
        if not self.active or self.mode_exclu(mode):
            return
        self._pause(dt_util.utcnow() + timedelta(minutes=self.options[CONF_PAUSE_MIN]), origine)
        self._prevenir()

    def _pause(self, fin: datetime, origine: str) -> None:
        cause = {"origine": origine, "horodatage": dt_util.utcnow().isoformat()}
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

    def _lever_pause(self, raison: str | None = None) -> None:
        """`raison` : délai, bouton ou rallumage, notée au journal ; aucune
        quand l'interrupteur change (son changement est déjà noté)."""
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
            self._annuler_fin_pause = None
        if self.fin_pause is not None and raison is not None:
            self._noter("reprise", raison=raison)
        self.fin_pause = None
        self.cause_pause = None
        self._eteint_pendant_pause = False

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
        if self.etat != "active":
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
        elif fin == "non_confirmee":
            self._noter("erreur", cible=transition.demandee, raison=self.derniere_erreur)
        if fin != "arret":
            # Évaluation après le gel : mesure mise de côté, filtre qui
            # avance encore, ou valeur changée par le téléviseur.
            self._planifier(max(self._signal.fin_gel - instant, 0.1))
            self._prevenir()

    async def _historiser_rampe(self, transition: _Transition) -> None:
        """Une seule entrée pour la rampe, celle du premier pas, complétée de
        la nouvelle valeur du dernier : le retour arrière restaure le
        départ."""
        await self._historique.completer(transition.premier["id_historique"],
                                         transition.dernier["nouvelle"])

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
