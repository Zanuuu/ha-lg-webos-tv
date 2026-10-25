"""Signal du capteur de lumière ambiante : filtrage, hystérésis, confirmation
des sauts, gel après nos écritures, cadence des mesures et profils de
capteur (docs/etude-luminosite-adaptative.md, § 3.1 et 3.2, lots 1 et 2).

Logique seule, sans Home Assistant : les instants (secondes, flottants) sont
fournis par l'appelant, ce qui la rend testable par séries horodatées.

Le filtre travaille sur ln(lux), l'échelle de la courbe. Il est défini en
temps et non en nombre de mesures : les capteurs domotiques publient aussi
bien chaque seconde que toutes les cinq minutes, ou seulement sur variation.
"""

import math
import statistics
from collections import deque
from dataclasses import dataclass, replace

from .const import (CONF_CONFIRMATION_SAUT, CONF_GEL_ECRITURE,
                    CONF_HYSTERESIS_DESCENTE, CONF_HYSTERESIS_MONTEE,
                    CONF_LISSAGE_DESCENTE, CONF_LISSAGE_MONTEE)

# Au-delà d'un facteur 4 par rapport au lux filtré, une mesure isolée
# (passage devant le capteur, reflet) attend d'être confirmée.
FACTEUR_SAUT = 4
LN_SAUT = math.log(FACTEUR_SAUT)
# Réévaluation tant que le filtre n'a pas rejoint la dernière mesure : un
# capteur qui ne publie que sur variation ne relancera pas le calcul.
REEVALUATION_S = 1.0
# Filtre considéré comme arrivé à 1 % de la mesure.
LN_CONVERGENCE = math.log(1.01)


@dataclass(frozen=True)
class Constantes:
    lissage_montee_s: float
    lissage_descente_s: float
    hysteresis_montee: float  # fraction : 0,10 pour +10 %
    hysteresis_descente: float  # fraction : 0,20 pour −20 %
    confirmation_saut_s: float  # 0 : sauts pris sans confirmation
    gel_s: float


# Points de départ de l'étude (§ 3.1, 3.2, 4.4), à confirmer à l'essai.
_RAPIDE = Constantes(5, 15, 0.10, 0.20, 8, 5)
PROFILS = {
    "rapide": _RAPIDE,
    "periodique": _RAPIDE,
    # Mesures rares : ne pas les retarder davantage.
    "sur_variation": replace(_RAPIDE, lissage_montee_s=0, lissage_descente_s=5),
    # Une mesure toutes les cinq minutes ou plus : la filtrer ou la
    # confirmer ajouterait un retard sans rien rejeter.
    "lent": replace(_RAPIDE, lissage_montee_s=0, lissage_descente_s=0,
                    confirmation_saut_s=0),
    "inconnu": _RAPIDE,
}
# Placement D (au point de vue, face à l'écran) : l'écran éclaire le
# capteur, dont la réponse à nos écritures demande plus de temps.
GEL_EMPLACEMENT_D_S = 20

PLATEFORMES_SUR_VARIATION = ("zha", "mqtt", "hue", "deconz")
PLATEFORMES_LENTES = ("zwave_js",)
INTERVALLE_RAPIDE_S = 10
INTERVALLE_LENT_S = 300

# Option avancée → (champ de Constantes, facteur de conversion).
CHAMPS_OPTIONS = {
    CONF_LISSAGE_MONTEE: ("lissage_montee_s", 1),
    CONF_LISSAGE_DESCENTE: ("lissage_descente_s", 1),
    CONF_HYSTERESIS_MONTEE: ("hysteresis_montee", 0.01),
    CONF_HYSTERESIS_DESCENTE: ("hysteresis_descente", 0.01),
    CONF_CONFIRMATION_SAUT: ("confirmation_saut_s", 1),
    CONF_GEL_ECRITURE: ("gel_s", 1),
}


def profil(plateforme: str | None, intervalle_s: float | None) -> str:
    """Profil du capteur : l'intervalle observé, une fois connu, l'emporte
    sur la plateforme (un Zigbee réglé à 1 s est un capteur rapide)."""
    if intervalle_s is not None:
        if intervalle_s < INTERVALLE_RAPIDE_S:
            return "rapide"
        if intervalle_s > INTERVALLE_LENT_S:
            return "lent"
    if plateforme in PLATEFORMES_SUR_VARIATION:
        return "sur_variation"
    if intervalle_s is not None:
        return "periodique"
    if plateforme in PLATEFORMES_LENTES:
        return "lent"
    return "inconnu"


def constantes(options: dict, nom_profil: str, emplacement: str | None) -> Constantes:
    """Constantes du profil, gel allongé pour l'emplacement D, puis options
    avancées saisies par l'utilisateur, qui priment. La courbe n'en dépend
    jamais."""
    resultat = PROFILS[nom_profil]
    if emplacement == "d":
        resultat = replace(resultat, gel_s=GEL_EMPLACEMENT_D_S)
    saisies = {champ: options[cle] * facteur
               for cle, (champ, facteur) in CHAMPS_OPTIONS.items()
               if options.get(cle) is not None}
    return replace(resultat, **saisies)


class SignalLux:
    """Lux filtré et décision d'appliquer.

    Filtre exponentiel du premier ordre sur ln(lux), l'entrée étant
    maintenue entre deux mesures : y(t) = x + (y0 − x)·exp(−(t − t0)/τ), avec
    τ de montée si x > y, de descente sinon. La forme exacte rend le résultat
    indépendant du pas de réévaluation, et les pas irréguliers ne posent
    aucun problème.
    """

    def __init__(self, constantes_: Constantes) -> None:
        self.constantes = constantes_
        self._x: float | None = None  # entrée maintenue, ln(lux)
        self._y0 = 0.0
        self._t0 = 0.0
        self._saut: tuple[float, float] | None = None  # (ln, instant)
        self._fin_gel = -math.inf
        self._differee: float | None = None
        self._reference: float | None = None  # lux de la dernière application
        self._evenements: list[str] = []

    # ------------------------------------------------------------- filtre
    def _y(self, t: float) -> float | None:
        if self._x is None:
            return None
        tau = (self.constantes.lissage_montee_s if self._x > self._y0
               else self.constantes.lissage_descente_s)
        if tau <= 0:
            return self._x
        return self._x + (self._y0 - self._x) * math.exp(-max(t - self._t0, 0) / tau)

    def _fixer_entree(self, t: float, ln: float) -> None:
        y = self._y(t)
        self._y0 = ln if y is None else y
        self._t0 = t
        self._x = ln

    def _recevoir(self, t: float, ln: float) -> None:
        if self._x is None:
            self._fixer_entree(t, ln)
            return
        ecart = ln - self._y(t)
        if self._saut is not None:
            ancien = self._saut[0] - self._y(t)
            if abs(ecart) > LN_SAUT and (ecart > 0) == (ancien > 0):
                self._saut = None
                self._fixer_entree(t, ln)
                return
            self._saut = None
            self._evenements.append("saut_ecarte")
        if abs(ecart) > LN_SAUT and self.constantes.confirmation_saut_s > 0:
            self._saut = (ln, t)
            return
        self._fixer_entree(t, ln)

    def _avancer(self, t: float) -> None:
        """Échéances passées, dans l'ordre : confirmation d'un saut par le
        délai, mesure différée par le gel."""
        while True:
            echeances = []
            if self._saut is not None:
                echeances.append((self._saut[1] + self.constantes.confirmation_saut_s, "saut"))
            if self._differee is not None:
                echeances.append((self._fin_gel, "gel"))
            echeances = [e for e in echeances if e[0] <= t]
            if not echeances:
                return
            instant, nature = min(echeances)
            if nature == "saut":
                ln, _ = self._saut
                self._saut = None
                self._fixer_entree(instant, ln)
            else:
                ln, self._differee = self._differee, None
                self._recevoir(instant, ln)

    # ---------------------------------------------------------- commandes
    def mesurer(self, t: float, lux: float) -> None:
        self._avancer(t)
        ln = math.log(max(lux, 1))
        if self.gele(t):
            # Seule la plus récente compte : à la fin du gel, c'est la
            # valeur stabilisée.
            self._differee = ln
            return
        self._recevoir(t, ln)

    def oublier(self) -> None:
        """Capteur indisponible : la mesure suivante repart de zéro, et la
        luminosité sera recalculée sans condition d'hystérésis."""
        self._x = None
        self._saut = None
        self._differee = None
        self._reference = None

    def suspendre(self, t: float) -> None:
        """Rampe en cours : mesures mises de côté jusqu'à `geler`, appelé à
        sa fin. L'écran change pendant toute la rampe."""
        self._avancer(t)
        self._fin_gel = math.inf

    def geler(self, t: float) -> None:
        """Après nos écritures (fin d'une rampe) : le capteur peut voir
        l'écran changer, avec son propre délai de mesure."""
        self._avancer(t)
        self._fin_gel = t + self.constantes.gel_s

    def gele(self, t: float) -> bool:
        return t < self._fin_gel

    @property
    def fin_gel(self) -> float:
        return self._fin_gel

    def evenements(self) -> list[str]:
        """Événements à noter au journal depuis le dernier appel."""
        evenements, self._evenements = self._evenements, []
        return evenements

    # ------------------------------------------------------------ lecture
    def lux_filtre(self, t: float) -> float | None:
        self._avancer(t)
        y = self._y(t)
        return None if y is None else math.exp(y)

    def lux_vise(self, t: float) -> float | None:
        """Lux vers lequel le filtre avance : la dernière mesure retenue."""
        self._avancer(t)
        return None if self._x is None else math.exp(self._x)

    def converge(self, t: float) -> bool:
        y = self._y(t)
        return y is None or abs(y - self._x) <= LN_CONVERGENCE

    def hors_bande(self, t: float) -> bool:
        """Faut-il recalculer la luminosité ? Oui sans référence, ou si le
        lux filtré sort de [référence × (1 − descente) ; référence ×
        (1 + montée)] : hystérésis relative, donc en logarithme, avec une
        mémoire du sens que la zone morte sur la sortie n'a pas."""
        lux = self.lux_filtre(t)
        if lux is None:
            return False
        if self._reference is None:
            return True
        return (lux > self._reference * (1 + self.constantes.hysteresis_montee)
                or lux < self._reference * (1 - self.constantes.hysteresis_descente))

    def noter_reference(self, lux: float) -> None:
        self._reference = lux

    def oublier_reference(self) -> None:
        self._reference = None

    def prochaine_echeance(self, t: float) -> float | None:
        """Prochain instant où la décision peut changer sans nouvelle mesure :
        confirmation d'un saut, fin du gel avec une mesure différée, ou
        réévaluation tant que le filtre avance (pas avant la fin du gel)."""
        self._avancer(t)
        echeances = []
        if self._saut is not None:
            echeances.append(self._saut[1] + self.constantes.confirmation_saut_s)
        if self._differee is not None:
            echeances.append(self._fin_gel)
        if not self.converge(t):
            echeances.append(max(t + REEVALUATION_S, self._fin_gel))
        return min(echeances) if echeances else None


class Cadence:
    """Intervalle habituel entre deux rapports du capteur (valeur changée ou
    non : `last_reported` de Home Assistant), pour le profil et la
    détection d'un capteur figé."""

    TAILLE = 20
    MINIMUM = 5
    SILENCE_MIN_S = 2 * 3600
    FACTEUR_SILENCE = 3

    def __init__(self) -> None:
        self._instants: deque[float] = deque(maxlen=self.TAILLE + 1)

    def noter(self, t: float) -> None:
        if not self._instants or t > self._instants[-1]:
            self._instants.append(t)

    @property
    def dernier(self) -> float | None:
        return self._instants[-1] if self._instants else None

    def intervalle(self) -> float | None:
        instants = list(self._instants)
        intervalles = [b - a for a, b in zip(instants, instants[1:])]
        if len(intervalles) < self.MINIMUM:
            return None
        return statistics.median(intervalles)

    def silence_max(self) -> float | None:
        """Silence au-delà duquel le capteur est tenu pour figé. Inconnu
        tant que l'intervalle habituel ne l'est pas : un capteur qui ne
        publie que sur variation peut se taire longtemps dans une pièce
        stable."""
        intervalle = self.intervalle()
        if intervalle is None:
            return None
        return max(self.FACTEUR_SILENCE * intervalle, self.SILENCE_MIN_S)

    def fige(self, t: float) -> bool:
        silence = self.silence_max()
        return silence is not None and t - self.dernier > silence
