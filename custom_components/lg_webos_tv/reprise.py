"""Reprise en main de la luminosité adaptative : levée de la pause quand
l'éclairage change nettement, corrections retenues et suggestions de courbe
(docs/etude-luminosite-adaptative.md, § 3.8, R7 et R8, lot 5).

Logique seule, sans Home Assistant : les instants (secondes, flottants) sont
fournis par l'appelant.

- **Levée de la pause** : une correction valait pour l'éclairage du moment ;
  quand il a doublé ou diminué de moitié depuis, la fonction reprend. Les
  lux sont ramenés dans la plage de la courbe : au-delà de ses extrémités,
  elle est plate, et reprendre réécrirait la valeur que l'utilisateur vient
  d'écarter.
- **Corrections** : une valeur gardée 10 minutes, sans autre réglage, sous
  un lux stable, est enregistrée (lux, valeur, cible de la courbe, mode).
- **Suggestions** : quand au moins 3 corrections d'une même demi-décade de
  lux s'écartent de la courbe dans le même sens d'au moins 5 points
  (médiane), une courbe modifiée est proposée ; jamais appliquée sans
  l'accord de l'utilisateur. L'écart est mesuré à la courbe actuelle : une
  fois la suggestion appliquée, ses corrections tombent près de zéro et
  elle disparaît d'elle-même.
"""

import math
import statistics
from dataclasses import dataclass, field

from .const import (CLES_COURBE, CONF_ANCRAGES, CONF_LUMINOSITE_MAX,
                    CONF_LUMINOSITE_MIN, CONF_LUX_MAX, CONF_LUX_MIN,
                    CONF_POINT_INTERMEDIAIRE)
from .courbe import LUX_PLANCHER, _encadrer, _valeur, calculer_cible, points
from .sante import ambiance
from .signal_lux import LN_CONVERGENCE

# Levée de la pause : lux filtré doublé ou diminué de moitié depuis la
# reprise en main (Android oublie la correction de la même façon).
FACTEUR_REPRISE = 2
# Correction retenue : valeur gardée ce temps-là, lux filtré resté dans ce
# rapport (la moitié du facteur de reprise, en logarithme).
CORRECTION_DUREE_S = 600
LUX_STABLE = 1.5
# Le lux n'est jugé qu'une fois le lissage arrivé (quatre constantes de
# temps) : une reprise en main pendant une transition ne doit pas compter la
# fin de celle-ci comme un éclairage instable. Au plus la moitié de
# l'observation.
STABILISATION_CONSTANTES = 4
# Suggestions (seuils de l'étude, à revoir après l'essai réel).
CORRECTIONS_MIN = 3
ECART_MIN = 5
# Seules les plus récentes d'une plage comptent : une préférence qui change
# se voit sans attendre que les nouvelles corrections dépassent en nombre
# toutes les anciennes.
CORRECTIONS_PAR_PLAGE = 10
# Conservation en base (corrections.py).
CONSERVATION_JOURS = 365
CORRECTIONS_MAX = 500
# Position dans un segment (en ln(lux)) au-delà de laquelle le point le plus
# proche ne suffit plus : sur une courbe à 2 points, on y ajoute le point
# intermédiaire plutôt que de tordre toute la courbe.
TIERS = 1 / 3


# ------------------------------------------------------------ levée (R7)
def _dans_la_courbe(lux: float, options: dict) -> float:
    return min(max(lux, options[CONF_LUX_MIN]), options[CONF_LUX_MAX])


def _sens(lux: float, lux_reference: float, options: dict) -> int:
    # À 1 % près, la précision du filtre arrivé : il ne fait qu'approcher la
    # nouvelle mesure, et un éclairage qui double tout juste ne lèverait
    # jamais la pause.
    ln = math.log(_dans_la_courbe(lux, options) / _dans_la_courbe(lux_reference, options))
    seuil = math.log(FACTEUR_REPRISE) - LN_CONVERGENCE
    return 1 if ln >= seuil else -1 if ln <= -seuil else 0


def changement_net(lux_filtre: float, lux_retenu: float, lux_reference: float,
                   options: dict) -> bool:
    """L'éclairage a-t-il nettement changé depuis la reprise en main ? Le lux
    filtré et la dernière mesure retenue doivent l'un et l'autre avoir
    franchi le facteur, dans le même sens : ni une ombre passagère (le
    filtre ne l'a pas suivie) ni la fin d'une transition en cours à la
    reprise (la mesure retenue n'a pas bougé) ne lèvent la pause. La
    référence est la mesure retenue au moment de la reprise en main, celle
    vers laquelle allait le filtre."""
    sens = _sens(lux_filtre, lux_reference, options)
    return sens != 0 and _sens(lux_retenu, lux_reference, options) == sens


def bornes_reprise(lux_reference: float, options: dict) -> tuple[float | None, float | None]:
    """Lux sous lequel et au-delà duquel la pause se lève ; None quand la
    partie plate de la courbe rend la limite inaccessible."""
    reference = _dans_la_courbe(lux_reference, options)
    bas, haut = reference / FACTEUR_REPRISE, reference * FACTEUR_REPRISE
    return (bas if bas >= options[CONF_LUX_MIN] else None,
            haut if haut <= options[CONF_LUX_MAX] else None)


# ------------------------------------------------------- corrections (R8)
@dataclass
class Correction:
    horodatage: float
    lux: float  # lux filtré pendant la correction
    valeur: int  # luminosité gardée
    cible: int  # cible de la courbe à ce moment (affichage)
    mode_image: str | None
    origine: str
    id: int | None = None
    # Écartée des suggestions par « Ignorer » ; reste affichée.
    ecartee: bool = False


@dataclass
class SuiviCorrection:
    """Reprise en main en cours d'observation. Un nouveau réglage la
    remplace (les 10 minutes repartent)."""

    debut: float
    valeur: int
    mode_image: str | None
    origine: str
    # Plus grande constante de temps du lissage du lux filtré.
    lissage_s: float = 0
    lux_min: float | None = None
    lux_max: float | None = None

    @property
    def echeance(self) -> float:
        return self.debut + CORRECTION_DUREE_S

    @property
    def debut_mesures(self) -> float:
        return self.debut + min(STABILISATION_CONSTANTES * self.lissage_s,
                                CORRECTION_DUREE_S / 2)

    def mesurer(self, t: float, lux: float | None) -> None:
        if lux is None or t < self.debut_mesures:
            return
        # Plancher : un capteur qui oscille entre 0 et 1 lx dans le noir reste
        # stable.
        lux = max(lux, LUX_PLANCHER)
        self.lux_min = lux if self.lux_min is None else min(self.lux_min, lux)
        self.lux_max = lux if self.lux_max is None else max(self.lux_max, lux)

    @property
    def lux(self) -> float | None:
        if self.lux_min is None:
            return None
        return math.sqrt(self.lux_min * self.lux_max)

    def verdict(self, t: float, valeur: int | None, mode_image: str | None,
                connecte: bool, en_pause: bool) -> str | None:
        """Raison d'écarter la correction, ou None si elle est retenue."""
        # Une minuterie posée à l'échéance peut partir un peu avant.
        if t < self.echeance - 1:
            return "trop_tot"
        if not connecte:
            return "deconnecte"
        if not en_pause:
            return "pause_levee"
        if mode_image != self.mode_image:
            return "mode"
        if valeur != self.valeur:
            return "valeur_changee"
        if self.lux is None:
            return "lux_inconnu"
        if self.lux_max / self.lux_min > LUX_STABLE:
            return "lux_instable"
        return None

    def correction(self, t: float, options: dict) -> Correction:
        return Correction(horodatage=t, lux=round(self.lux, 1), valeur=self.valeur,
                          cible=calculer_cible(self.lux, options),
                          mode_image=self.mode_image, origine=self.origine)


def plage(lux: float) -> int:
    """Demi-décade de lux : 0 pour 1 à 3,2 lx, 1 pour 3,2 à 10 lx, etc."""
    return math.floor(2 * math.log10(max(lux, LUX_PLANCHER)))


def bornes_plage(indice: int) -> tuple[float, float]:
    return 10 ** (indice / 2), 10 ** ((indice + 1) / 2)


def ecart(correction: Correction, options: dict) -> int:
    """Écart à la courbe actuelle (et non à celle du moment)."""
    return correction.valeur - calculer_cible(correction.lux, options)


# ------------------------------------------------------------ suggestions
@dataclass
class Suggestion:
    plage: int
    lux: float  # lux médian (géométrique) des corrections
    ecart: float  # écart médian à la courbe actuelle
    ambiance: str
    corrections: list[int]  # identifiants des corrections prises en compte
    options: dict  # courbe proposée, sans les points d'ancrage
    # Points déplacés : "min", "intermediaire", "max" ; point intermédiaire
    # ajouté ; voisins poussés pour garder la courbe monotone ; cible
    # seulement approchée (luminosité bornée à 0–100).
    points: list[str]
    ajout: bool = False
    pousses: bool = False
    approche: bool = False
    cible: int = 0  # luminosité de la courbe proposée au lux médian
    nombre: int = field(init=False)

    def __post_init__(self) -> None:
        self.nombre = len(self.corrections)


def _arrondir(valeur: float) -> int:
    return int(math.floor(valeur + 0.5))


def _lux_saisissable(lux: float) -> float:
    """Lux d'un point ajouté, à la précision des options (au dixième sous
    100 lx), au plus près."""
    choix = min(_encadrer(lux), key=lambda v: abs(math.log(v / lux)))
    return int(choix) if float(choix).is_integer() else choix


def _viser(options: dict, lux: float, visee: int) -> tuple[dict, dict]:
    """Courbe modifiée pour passer par (lux, visee) en déplaçant le moins de
    points possible, verticalement ; renvoie les options et ce qui a bougé."""
    pts = points(options)
    xs = [math.log(lx) for lx, _ in pts]
    vs = [float(v) for _, v in pts]
    luxs = [lx for lx, _ in pts]
    x = math.log(lux)
    ajout = False
    if x <= xs[0]:
        bouges = [0]
        vs[0] = visee
    elif x >= xs[-1]:
        bouges = [len(vs) - 1]
        vs[-1] = visee
    else:
        j = next(k for k in range(len(xs) - 1) if xs[k] < x <= xs[k + 1])
        t = (x - xs[j]) / (xs[j + 1] - xs[j])
        decalage = visee - (vs[j] + t * (vs[j + 1] - vs[j]))
        if TIERS <= t <= 1 - TIERS and len(pts) == 2:
            bouges = [1]
            ajout = True
            xs.insert(1, x)
            vs.insert(1, visee)
            luxs.insert(1, _lux_saisissable(lux))
        elif TIERS <= t <= 1 - TIERS:
            # Pas de quatrième point : le segment monte ou descend d'un bloc
            # (le point le plus proche seul bougerait de deux fois l'écart).
            bouges = [j, j + 1]
            vs[j] += decalage
            vs[j + 1] += decalage
        else:
            # Le point le plus proche monte ou descend juste assez pour que
            # la courbe passe par le point visé (au plus 1,5 fois l'écart).
            i, autre, poids = (j, j + 1, 1 - t) if t < 0.5 else (j + 1, j, t)
            bouges = [i]
            vs[i] += decalage / poids
            # Il dépasserait l'autre point du segment : la cible est hors de
            # sa portée, le segment devient un plateau à la valeur visée.
            if (vs[i] - vs[autre]) * (i - autre) < 0:
                vs[i] = visee
    approche = any(not 0 <= vs[k] <= 100 for k in bouges)
    for k in bouges:
        vs[k] = min(max(vs[k], 0), 100)
    # Voisins poussés : la courbe reste monotone et passe encore par le point.
    avant = list(vs)
    for k in range(max(bouges) + 1, len(vs)):
        vs[k] = max(vs[k], vs[k - 1])
    for k in range(min(bouges) - 1, -1, -1):
        vs[k] = min(vs[k], vs[k + 1])
    pousses = vs != avant
    valeurs = [_arrondir(v) for v in vs]

    resultat = {cle: valeur for cle, valeur in options.items() if cle != CONF_ANCRAGES}
    resultat.update({CONF_LUX_MIN: luxs[0], CONF_LUMINOSITE_MIN: valeurs[0],
                     CONF_LUX_MAX: luxs[-1], CONF_LUMINOSITE_MAX: valeurs[-1]})
    resultat.pop(CONF_POINT_INTERMEDIAIRE, None)
    if len(luxs) == 3:
        resultat[CONF_POINT_INTERMEDIAIRE] = [luxs[1], valeurs[1]]
    noms = ["min", *(["intermediaire"] if len(vs) == 3 else []), "max"]
    cible = calculer_cible(lux, resultat)
    return resultat, {"points": [noms[k] for k in bouges], "ajout": ajout, "pousses": pousses,
                      "approche": approche or cible != visee, "cible": cible}


def _courbe(options: dict) -> list:
    return [options.get(cle) for cle in CLES_COURBE]


def _proposer(indice: int, corrections: list[Correction], options: dict) -> Suggestion | None:
    recentes = sorted(corrections, key=lambda c: c.horodatage, reverse=True)
    recentes = recentes[:CORRECTIONS_PAR_PLAGE]
    ecarts = [ecart(c, options) for c in recentes]
    if len(recentes) < CORRECTIONS_MIN:
        return None
    mediane = statistics.median(ecarts)
    if abs(mediane) < ECART_MIN or sum(1 for e in ecarts if e * mediane > 0) < CORRECTIONS_MIN:
        return None
    lux = math.exp(statistics.median(math.log(max(c.lux, LUX_PLANCHER)) for c in recentes))
    actuelle = _valeur(math.log(lux), [(math.log(lx), v) for lx, v in points(options)])
    visee = min(max(_arrondir(actuelle + mediane), 0), 100)
    proposees, compte_rendu = _viser(options, lux, visee)
    if _courbe(proposees) == _courbe(options):
        return None
    return Suggestion(
        plage=indice, lux=round(lux, 1), ecart=mediane,
        ambiance=ambiance(lux, options[CONF_LUX_MIN], options[CONF_LUX_MAX]),
        corrections=[c.id for c in recentes], options=proposees, **compte_rendu)


def suggestions(corrections: list[Correction], options: dict) -> list[Suggestion]:
    """Suggestions par plage de lux, la mieux étayée d'abord. Chacune est
    calculée sur la courbe actuelle : après en avoir appliqué une, les
    autres se recalculent."""
    par_plage: dict[int, list[Correction]] = {}
    for correction in corrections:
        if not correction.ecartee:
            par_plage.setdefault(plage(correction.lux), []).append(correction)
    resultat = [s for indice, liste in sorted(par_plage.items())
                if (s := _proposer(indice, liste, options)) is not None]
    return sorted(resultat, key=lambda s: -s.nombre)


def a_ecarter(corrections: list[Correction], indice: int) -> list[int]:
    """« Ignorer » une suggestion : toutes les corrections de sa plage encore
    prises en compte, les plus anciennes aussi (sans quoi elles en
    formeraient aussitôt une nouvelle)."""
    return [c.id for c in corrections if not c.ecartee and plage(c.lux) == indice]
