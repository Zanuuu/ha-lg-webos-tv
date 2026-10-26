"""Soirée de la luminosité adaptative (docs/etude-luminosite-adaptative.md,
§ 3.6.4, R15) : état horaire, et non lumineux, pendant lequel la luminosité
est baissée d'une fraction et, en option, « Réduire la lumière bleue » est
activé.

Fondé sur le consensus de Brown et al. (2022) : limiter la lumière reçue à
l'œil le soir, d'abord en baissant la luminosité des écrans ; réduire leur
bleu n'en retire qu'une partie. Aucun bénéfice pour le sommeil n'est promis.

Logique seule, sans Home Assistant : l'orchestrateur lit l'entité source et
l'horloge, ce module décide.

- Source heure : une plage quotidienne [début, fin[, qui peut passer minuit.
  L'heure de début vient de l'option, ou d'une entité `input_datetime` (son
  heure, la date ignorée).
- Source interrupteur (`binary_sensor`, `schedule`) : la Soirée commence au
  passage à `on` et finit au passage à `off` ou à l'heure de fin qui suit,
  la première des deux.
- « Terminer la soirée » la finit jusqu'à la fin de la plage en cours : un
  redémarrage de Home Assistant, ou l'entité remise à `on`, ne la relance
  pas avant.
- L'extinction du téléviseur ne la termine pas (arbitrage du 25/10/2026) :
  rallumé dans la plage, il retrouve la Soirée.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from .const import (CONF_SOIREE, CONF_SOIREE_DEBUT, CONF_SOIREE_ENTITE,
                    CONF_SOIREE_FIN, CONF_SOIREE_LUMIERE_BLEUE)

# Domaines des entités qui peuvent faire commencer la Soirée.
DOMAINE_HEURE = "input_datetime"
DOMAINES_INTERRUPTEUR = ("binary_sensor", "schedule")
DOMAINES_SOURCE = (DOMAINE_HEURE, *DOMAINES_INTERRUPTEUR)
REDUCTION_MAX = 50
LUMIERE_BLEUE_ACTIVE = "on"


def lire_heure(texte: Any) -> time | None:
    """« HH:MM » ou « HH:MM:SS » (sélecteur d'heure de Home Assistant)."""
    if not isinstance(texte, str):
        return None
    try:
        return time.fromisoformat(texte)
    except ValueError:
        return None


def ecrire_heure(heure: time) -> str:
    return heure.strftime("%H:%M")


def normaliser_heure(texte: Any) -> str | None:
    heure = lire_heure(texte)
    return None if heure is None else ecrire_heure(heure)


def _a(jour, heure: time, zone) -> datetime:
    return datetime.combine(jour, heure, tzinfo=zone)


def prochaine(maintenant: datetime, heure: time) -> datetime:
    """Prochain passage à `heure`, strictement après `maintenant`."""
    instant = _a(maintenant.date(), heure, maintenant.tzinfo)
    return instant if instant > maintenant else instant + timedelta(days=1)


def occurrence(maintenant: datetime, debut: time, fin: time) -> tuple[datetime, datetime] | None:
    """Plage [début, fin[ qui contient `maintenant` (heure locale), commencée
    aujourd'hui ou hier, ou None. Début et fin égaux : aucune plage."""
    if debut == fin:
        return None
    for jours in (0, -1):
        depart = _a(maintenant.date() + timedelta(days=jours), debut, maintenant.tzinfo)
        arrivee = _a(depart.date(), fin, maintenant.tzinfo)
        if arrivee <= depart:
            arrivee += timedelta(days=1)
        if depart <= maintenant < arrivee:
            return depart, arrivee
    return None


@dataclass(frozen=True)
class Source:
    """Ce que l'orchestrateur a lu de la source. `debut` : heure de début
    (option ou `input_datetime`), None si l'entité n'en donne pas.
    `allumee` et `depuis` : état d'un interrupteur (None : indisponible) et
    instant de son dernier changement."""

    debut: time | None = None
    interrupteur: bool = False
    allumee: bool | None = None
    depuis: datetime | None = None


@dataclass(frozen=True)
class EtatSoiree:
    active: bool
    fin: datetime | None = None
    # Terminée à la main : jusqu'à quand.
    terminee_jusqua: datetime | None = None
    # Prochaine réévaluation sans événement (début, fin), ou None.
    echeance: datetime | None = None


class SuiviSoiree:
    def __init__(self, terminee_jusqua: datetime | None = None) -> None:
        self.terminee_jusqua = terminee_jusqua

    def _plage(self, maintenant: datetime, source: Source,
               fin: time) -> tuple[tuple[datetime, datetime] | None, datetime | None]:
        """Plage en cours et prochain début connu à l'avance."""
        if source.interrupteur:
            if not source.allumee or source.depuis is None:
                return None, None
            arrivee = prochaine(source.depuis, fin)
            return ((source.depuis, arrivee) if maintenant < arrivee else None), None
        if source.debut is None:
            return None, None
        plage = occurrence(maintenant, source.debut, fin)
        return plage, (None if source.debut == fin else prochaine(maintenant, source.debut))

    def evaluer(self, maintenant: datetime, source: Source, fin: time) -> EtatSoiree:
        if self.terminee_jusqua is not None and maintenant >= self.terminee_jusqua:
            self.terminee_jusqua = None
        plage, prochain_debut = self._plage(maintenant, source, fin)
        if self.terminee_jusqua is not None:
            # Une plage qui finit après la Soirée terminée (entité remise à
            # `on` le lendemain soir) n'est plus la même.
            if plage is None or plage[1] <= self.terminee_jusqua:
                return EtatSoiree(False, terminee_jusqua=self.terminee_jusqua,
                                  echeance=self.terminee_jusqua)
            self.terminee_jusqua = None
        if plage is not None:
            return EtatSoiree(True, fin=plage[1], echeance=plage[1])
        return EtatSoiree(False, echeance=prochain_debut)

    def terminer(self, etat: EtatSoiree) -> None:
        if etat.active:
            self.terminee_jusqua = etat.fin

    def oublier(self) -> None:
        """Soirée désactivée ou source changée : plus rien de terminé."""
        self.terminee_jusqua = None


# ------------------------------------------------------------ lumière bleue
@dataclass
class PiloteLumiereBleue:
    """« Réduire la lumière bleue » (`eyeComfortMode`) : réglage global, sans
    garde de mode. Valeur de base relue sur le téléviseur au moment de
    l'activer, restaurée à la fin de la Soirée ou à l'entrée d'un mode laissé
    de côté. Un réglage de l'utilisateur pendant la Soirée est une reprise en
    main de ce réglage seul : il n'est plus touché jusqu'à la fin, ni
    restauré."""

    base: str | None = None
    # Activée par nous, écriture confirmée : à restaurer.
    posee: bool = False
    reprise: bool = False

    def voulue(self, soiree: bool, option: bool, mode_exclu: bool,
               actuelle: str | None) -> str | None:
        """Valeur à écrire maintenant, ou None. `actuelle` : valeur notifiée
        ou relue par le téléviseur (None : inconnue, rien n'est écrit)."""
        if actuelle is None or self.reprise:
            return None
        if soiree and option and not mode_exclu:
            return LUMIERE_BLEUE_ACTIVE if actuelle != LUMIERE_BLEUE_ACTIVE else None
        if self.posee and actuelle == LUMIERE_BLEUE_ACTIVE and self.base is not None:
            return self.base
        return None

    def avant_ecriture(self, valeur: str, actuelle: str) -> None:
        if valeur == LUMIERE_BLEUE_ACTIVE and not self.posee:
            self.base = actuelle

    def confirmee(self, valeur: str) -> None:
        if valeur == LUMIERE_BLEUE_ACTIVE:
            self.posee = True
        else:
            self.posee, self.base = False, None

    def reprendre_en_main(self, soiree: bool) -> bool:
        """Changement venu d'ailleurs. Renvoie vrai si c'est une reprise en
        main (Soirée en cours, ou valeur posée par nous pas encore
        restaurée)."""
        if not (soiree or self.posee):
            return False
        if soiree:
            self.reprise = True
        # Le choix de l'utilisateur reste : plus rien à restaurer.
        self.posee, self.base = False, None
        return True

    def fin_soiree(self) -> None:
        self.reprise = False

    def en_dict(self) -> dict:
        return {"base": self.base, "posee": self.posee, "reprise": self.reprise}

    @classmethod
    def depuis_dict(cls, donnees: dict | None) -> "PiloteLumiereBleue":
        donnees = donnees or {}
        return cls(base=donnees.get("base"), posee=bool(donnees.get("posee")),
                   reprise=bool(donnees.get("reprise")))


# --------------------------------------------------------------- options
def valider(options: dict) -> tuple[dict, dict[str, str]]:
    """Options de la Soirée normalisées (heures en « HH:MM ») et erreurs, en
    clés de traduction du formulaire. Absentes, elles prennent leur valeur
    par défaut ; la réduction est bornée par luminosite_adaptative.BORNES."""
    options, erreurs = dict(options), {}
    for cle in (CONF_SOIREE, CONF_SOIREE_LUMIERE_BLEUE):
        if cle in options and not isinstance(options[cle], bool):
            erreurs[cle] = "hors_bornes"
    for cle in (CONF_SOIREE_DEBUT, CONF_SOIREE_FIN):
        if cle in options:
            if (heure := normaliser_heure(options[cle])) is None:
                erreurs[cle] = "heure_invalide"
            else:
                options[cle] = heure
    if (CONF_SOIREE_DEBUT not in erreurs and CONF_SOIREE_FIN not in erreurs
            and CONF_SOIREE_ENTITE not in options
            and options.get(CONF_SOIREE_DEBUT) is not None
            and options.get(CONF_SOIREE_DEBUT) == options.get(CONF_SOIREE_FIN)):
        erreurs[CONF_SOIREE_FIN] = "soiree_debut_egal_fin"
    entite = options.get(CONF_SOIREE_ENTITE)
    if entite is not None and (not isinstance(entite, str)
                               or entite.split(".")[0] not in DOMAINES_SOURCE):
        erreurs[CONF_SOIREE_ENTITE] = "soiree_entite_invalide"
    return options, erreurs
