"""Capteur de secours de la luminosité adaptative : facteur relatif entre
les deux capteurs et choix du capteur qui sert
(docs/etude-luminosite-adaptative.md, § 3.5, R12, lot 6).

Logique seule, sans Home Assistant : les instants (secondes, flottants) sont
fournis par l'appelant.

Deux capteurs placés différemment ne mesurent pas le même lux : sur une
courbe en ln(lux), un facteur multiplicatif équivaut à un décalage de la
courbe (§ 3.2). Le secours ne prend donc le relais qu'une fois ce facteur
appris, quand les deux publient (médiane de ln(l1/l2), robuste aux
transitions où l'un a du retard), et seulement si le rapport est stable :
un capteur extérieur ou près d'une fenêtre, dont le rapport à la pièce
change avec l'heure, est écarté par la mesure plutôt que par une
déclaration. Seuils de départ, à confirmer par l'essai P6.
"""

import math
import statistics
from collections import deque

# Un échantillon par minute au plus : les capteurs rapides ne doivent pas
# peser plus que les lents.
ECHANTILLON_S = 60
ECHANTILLONS_MAX = 1000
ECHANTILLONS_MIN = 30
# Sous 2 lx, le pas d'un capteur (souvent 1 lx) et le plancher à 0 rendent
# le rapport sans signification.
LUX_MIN_RAPPORT = 2
# Dispersion robuste de ln(l1/l2) (écart interquartile / 1,349, un écart-type
# pour une loi normale) au-delà de laquelle le rapport est jugé instable : le
# secours se tromperait couramment de plus de 50 %.
DISPERSION_MAX = math.log(1.5)
IQR_ECART_TYPE = 1.349
# Incohérence : l'un à 0 quand l'autre dépasse 20 lx (§ 3.5).
ZERO_AUTRE_LX = 20
ZEROS_MIN = 5


class RapportCapteurs:
    """Échantillons (instant, lux principal, lux secours) pris quand les deux
    capteurs publient et que la lumière est stable."""

    def __init__(self, echantillons: list | None = None) -> None:
        self._echantillons: deque[tuple[float, float, float]] = deque(
            (tuple(e) for e in echantillons or []), maxlen=ECHANTILLONS_MAX)

    def noter(self, t: float, principal: float, secours: float) -> bool:
        """Échantillon retenu ou non (cadence)."""
        if self._echantillons and t - self._echantillons[-1][0] < ECHANTILLON_S - 1:
            return False
        self._echantillons.append((round(t), round(principal, 2), round(secours, 2)))
        return True

    def _ln(self) -> list[float]:
        return [math.log(p / s) for _, p, s in self._echantillons
                if p >= LUX_MIN_RAPPORT and s >= LUX_MIN_RAPPORT]

    @property
    def nombre(self) -> int:
        return len(self._ln())

    @property
    def facteur(self) -> float | None:
        """Lux du principal ≈ facteur × lux du secours."""
        ln = self._ln()
        return math.exp(statistics.median(ln)) if len(ln) >= ECHANTILLONS_MIN else None

    @property
    def dispersion(self) -> float | None:
        ln = self._ln()
        if len(ln) < ECHANTILLONS_MIN:
            return None
        q1, _, q3 = statistics.quantiles(ln, n=4)
        return (q3 - q1) / IQR_ECART_TYPE

    def zeros(self) -> dict[str, int]:
        """Échantillons où l'un était à 0 quand l'autre dépassait 20 lx."""
        return {
            "principal": sum(1 for _, p, s in self._echantillons if p < 1 and s > ZERO_AUTRE_LX),
            "secours": sum(1 for _, p, s in self._echantillons if s < 1 and p > ZERO_AUTRE_LX),
        }

    @property
    def etat(self) -> str:
        """apprentissage, stable, instable ou incoherent."""
        if max(self.zeros().values()) >= ZEROS_MIN:
            return "incoherent"
        dispersion = self.dispersion
        if dispersion is None:
            return "apprentissage"
        return "instable" if dispersion > DISPERSION_MAX else "stable"

    @property
    def utilisable(self) -> bool:
        return self.etat == "stable"

    def resume(self) -> dict:
        facteur, dispersion = self.facteur, self.dispersion
        return {
            "etat": self.etat,
            "facteur": None if facteur is None else round(facteur, 3),
            "echantillons": self.nombre,
            "requis": ECHANTILLONS_MIN,
            # En facteur : 1,2 = le rapport varie couramment de ±20 %.
            "dispersion": None if dispersion is None else round(math.exp(dispersion), 2),
            "zeros": self.zeros(),
        }

    def en_liste(self) -> list[list[float]]:
        return [list(e) for e in self._echantillons]


def choisir(principal_ok: bool, secours_ok: bool, utilisable: bool) -> str | None:
    """Capteur qui sert : le principal dès qu'il répond, le secours s'il
    répond et que son facteur est sûr, sinon aucun (luminosité gardée)."""
    if principal_ok:
        return "principal"
    if secours_ok and utilisable:
        return "secours"
    return None
