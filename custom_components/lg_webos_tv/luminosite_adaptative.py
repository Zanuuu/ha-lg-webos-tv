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
  l'application.
"""

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import (Event, EventStateChangedData, HomeAssistant,
                                callback)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (async_track_point_in_utc_time,
                                         async_track_state_change_event)
from homeassistant.util import dt as dt_util

from .const import (CONF_CAPTEUR_LUX, CONF_ECART_MINIMAL, CONF_LUMINOSITE_MAX,
                    CONF_LUMINOSITE_MIN, CONF_LUX_MAX, CONF_LUX_MIN,
                    CONF_MODES_EXCLUS, CONF_PAUSE_MIN, DOMAIN, MODES_HDR,
                    OPTIONS_LUMINOSITE_DEFAUT)
from .entite import descriptions

log = logging.getLogger(__name__)

ID_OLED = "image.parametres-avances.luminosite.luminosite-pixels-oled"
ID_MODE = "image.mode-selection"
CATEGORIE, CLE = "picture", "backlight"
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

# Par ordre de priorité (voir LuminositeAdaptative.etat).
ETATS = ["desactivee", "televiseur_deconnecte", "consultation", "pause",
         "mode_exclu", "capteur_indisponible", "active"]

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
        # Le téléviseur a été vu injoignable pendant la pause : sa prochaine
        # connexion est un rallumage, qui lève la pause. Un simple
        # redémarrage de Home Assistant (connexion sans déconnexion vue) la
        # conserve.
        self._eteint_pendant_pause = False

        self._ecouteurs: list[Callable[[], None]] = []
        self._desabonnements: list[Callable[[], None]] = []
        self._annuler_application: Callable[[], None] | None = None
        self._echeance: datetime | None = None
        self._annuler_fin_pause: Callable[[], None] | None = None
        self._tache = None

    # ---------------------------------------------------------------- cycle
    def demarrer(self) -> None:
        self._tv.abonner(self._sur_evenement)
        self._desabonnements += [
            lambda: self._tv.desabonner(self._sur_evenement),
            self._historique.ecouter(self._sur_ecriture),
            async_track_state_change_event(self.hass, [self.capteur], self._sur_lux),
        ]

    def arreter(self) -> None:
        for desabonner in self._desabonnements:
            desabonner()
        self._desabonnements.clear()
        self._annuler_planification()
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
            self._annuler_fin_pause = None
        if self._tache is not None:
            self._tache.cancel()

    def ecouter(self, ecouteur: Callable[[], None]) -> Callable[[], None]:
        """Abonne une entité aux changements d'état de la fonction."""
        self._ecouteurs.append(ecouteur)
        return lambda: self._ecouteurs.remove(ecouteur)

    def _prevenir(self) -> None:
        for ecouteur in list(self._ecouteurs):
            ecouteur()

    # ----------------------------------------------------------------- état
    @property
    def lux(self) -> float | None:
        etat = self.hass.states.get(self.capteur)
        try:
            return float(etat.state) if etat is not None else None
        except ValueError:
            return None

    @property
    def cible(self) -> int | None:
        lux = self.lux
        return None if lux is None else calculer_cible(lux, self.options)

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
        if self.lux is None:
            return "capteur_indisponible"
        return "active"

    # ------------------------------------------------------------ commandes
    def restaurer(self, active: bool, fin_pause: datetime | None) -> None:
        self.active = active
        if active and fin_pause is not None and fin_pause > dt_util.utcnow():
            self._mettre_en_pause_jusqua(fin_pause)
        self._prevenir()

    def activer(self, active: bool) -> None:
        self.active = active
        self._lever_pause()
        if active:
            self._lancer()
        else:
            self._annuler_planification()
        self._prevenir()

    def reprendre(self) -> None:
        self._lever_pause()
        self._lancer()
        self._prevenir()

    # ---------------------------------------------------------- déclencheurs
    @callback
    def _sur_lux(self, _evenement: Event[EventStateChangedData]) -> None:
        self._planifier(DELAI_APPLICATION_S)
        self._prevenir()

    async def _sur_evenement(self, evenement: dict) -> None:
        if evenement["type"] == "connexion":
            if evenement["etat"] == "connecte":
                if self._eteint_pendant_pause:
                    self._lever_pause()
                self._planifier(DELAI_APPLICATION_S)
            elif evenement["etat"] == "deconnecte" and self.fin_pause is not None:
                self._eteint_pendant_pause = True
            self._prevenir()
        elif evenement["type"] == "ecriture":
            if evenement["possible"]:
                self._planifier(DELAI_APPLICATION_S)
            self._prevenir()
        elif evenement["type"] == "changement" and evenement["categorie"] == CATEGORIE:
            reglages, origine = evenement["reglages"], evenement["origine"]
            if CLE in reglages and origine in ORIGINES_EXTERIEURES:
                self._reprise_en_main(self._tv.mode_image)
            elif origine != "application" and (CLE in reglages or "pictureMode" in reglages):
                self._planifier(DELAI_APPLICATION_S)
            if "pictureMode" in reglages:
                self._prevenir()

    @callback
    def _sur_ecriture(self, ecriture: dict) -> None:
        if ecriture["origine"] == ORIGINE:
            return
        if (ecriture["categorie"], ecriture["cle"]) == (CATEGORIE, CLE):
            self._reprise_en_main(ecriture["mode_image"])
        elif ecriture["origine"] in ORIGINES_LOT:
            self._planifier(DELAI_APRES_LOT_S)

    # ----------------------------------------------------------------- pause
    def _reprise_en_main(self, mode: str | None) -> None:
        # La luminosité d'un mode laissé de côté ne dit rien de celle des
        # autres modes.
        if not self.active or self.mode_exclu(mode):
            return
        fin = dt_util.utcnow() + timedelta(minutes=self.options[CONF_PAUSE_MIN])
        self._mettre_en_pause_jusqua(fin)
        self._prevenir()

    def _mettre_en_pause_jusqua(self, fin: datetime) -> None:
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
        self._annuler_planification()
        self.fin_pause = fin
        self._eteint_pendant_pause = False
        self._annuler_fin_pause = async_track_point_in_utc_time(
            self.hass, self._sur_fin_de_pause, fin)

    @callback
    def _sur_fin_de_pause(self, _maintenant) -> None:
        self._annuler_fin_pause = None
        self.reprendre()

    def _lever_pause(self) -> None:
        if self._annuler_fin_pause is not None:
            self._annuler_fin_pause()
            self._annuler_fin_pause = None
        self.fin_pause = None
        self._eteint_pendant_pause = False

    # ----------------------------------------------------------- application
    def _planifier(self, delai_s: float) -> None:
        """Application différée ; une échéance déjà plus lointaine est
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
        self._tache = self.hass.async_create_background_task(
            self._appliquer(), f"{DOMAIN} luminosité adaptative")

    async def _appliquer(self) -> None:
        if self.etat != "active":
            return
        cible = self.cible
        try:
            actuelle = float(self._tv.etat.get(CATEGORIE, {}).get(CLE))
        except (TypeError, ValueError):
            actuelle = None
        if actuelle is not None and abs(cible - actuelle) < self.options[CONF_ECART_MINIMAL]:
            return
        try:
            # Garde de mode : si le mode change entre le calcul et
            # l'écriture, celle-ci est refusée et la cascade du nouveau mode
            # relance le calcul.
            resultat = await self._ecritures.demander(
                ID_OLED, cible, ORIGINE, mode_attendu=self._tv.mode_image)
        except Exception as exc:  # noqa: BLE001 — exposé dans l'état
            self.derniere_erreur = str(exc)
        else:
            self.derniere_erreur = None if resultat["ok"] else resultat["raison"]
        if self.derniere_erreur:
            log.info("Luminosité adaptative : écriture de %s impossible : %s",
                     cible, self.derniere_erreur)
        self._prevenir()

    def resume(self) -> dict[str, Any]:
        """État transmis au panneau. Sans le lux : il change à chaque mesure
        du capteur, et le panneau n'est prévenu que si le résumé change."""
        return {
            "etat": self.etat,
            "entree_id": ID_OLED,
            "cible": self.cible,
            "fin_pause": self.fin_pause.isoformat() if self.fin_pause else None,
        }

    def attributs(self) -> dict[str, Any]:
        return {
            "lux": self.lux,
            "cible": self.cible,
            "fin_pause": self.fin_pause.isoformat() if self.fin_pause else None,
            "mode_image": self._tv.mode_image,
            "derniere_erreur": self.derniere_erreur,
        }
