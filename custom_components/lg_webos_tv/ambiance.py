"""Ambiance de la pièce : sombre, intermédiaire ou claire, d'après le lux
filtré (docs/etude-luminosite-adaptative.md, § 3.6.4, R14a, lot 6).

Logique seule, sans Home Assistant : les instants (secondes, flottants) sont
fournis par l'appelant.

Les seuils sont les tiers de la plage de la courbe en ln(lux) : ils suivent
ses retouches (ancrage, suggestion), sauf si l'utilisateur les fige dans les
options. L'entité « Ambiance » sert aux automatisations : une ambiance ne
change qu'au-delà d'une hystérésis autour du seuil franchi, et une fois la
nouvelle tenue dix minutes, pour qu'une lampe allumée un instant ne
bascule pas un réglage du téléviseur.
"""

import math

from .const import (CONF_AMBIANCE_CLAIRE, CONF_AMBIANCE_SOMBRE, CONF_LUX_MAX,
                    CONF_LUX_MIN)

AMBIANCES = ("sombre", "intermediaire", "claire")
# Franchir un seuil demande de le dépasser de ce facteur (dans un sens comme
# dans l'autre) : un lux qui fluctue autour du seuil ne fait pas osciller
# l'ambiance.
HYSTERESIS = 1.25
DUREE_MIN_S = 600


def seuils_courbe(options: dict) -> tuple[float, float]:
    """Tiers de la plage logarithmique de la courbe."""
    bas, haut = math.log(options[CONF_LUX_MIN]), math.log(options[CONF_LUX_MAX])
    return math.exp(bas + (haut - bas) / 3), math.exp(bas + 2 * (haut - bas) / 3)


def seuils(options: dict) -> tuple[float, float]:
    """Seuils sombre → intermédiaire et intermédiaire → claire : ceux figés
    par l'utilisateur, sinon les tiers de la courbe."""
    sombre, claire = seuils_courbe(options)
    return (options.get(CONF_AMBIANCE_SOMBRE) or sombre,
            options.get(CONF_AMBIANCE_CLAIRE) or claire)


def nommer(lux: float, limites: tuple[float, float]) -> str:
    """Ambiance d'un lux, sans hystérésis (statistiques, suggestions)."""
    return AMBIANCES[0] if lux < limites[0] else AMBIANCES[1] if lux < limites[1] else AMBIANCES[2]


class SuiviAmbiance:
    """Ambiance publiée : la première tout de suite, les suivantes après
    l'hystérésis et la durée minimale."""

    def __init__(self) -> None:
        self.valeur: str | None = None
        self.depuis: float | None = None
        self._candidate: str | None = None
        self._candidate_depuis: float | None = None

    def restaurer(self, valeur: str, depuis: float | None) -> None:
        """Ambiance d'avant un redémarrage : elle remplace celle que la
        première mesure vient de donner (l'entité n'a encore rien publié) et
        tient jusqu'à ce que la mesure en justifie une autre, sans
        changement d'état parasite pour les automatisations."""
        if valeur in AMBIANCES:
            self.valeur, self.depuis = valeur, depuis
            self._candidate = self._candidate_depuis = None

    def _visee(self, lux: float, limites: tuple[float, float]) -> str:
        if self.valeur is None:
            return nommer(lux, limites)
        i = j = AMBIANCES.index(self.valeur)
        while j < len(limites) and lux >= limites[j] * HYSTERESIS:
            j += 1
        if j == i:
            while j > 0 and lux < limites[j - 1] / HYSTERESIS:
                j -= 1
        return AMBIANCES[j]

    @property
    def echeance(self) -> float | None:
        """Instant où la candidate sera publiée si elle tient."""
        if self._candidate is None:
            return None
        return self._candidate_depuis + DUREE_MIN_S

    def mesurer(self, t: float, lux: float, limites: tuple[float, float]) -> bool:
        """Lux filtré du moment ; vrai si l'ambiance publiée change."""
        visee = self._visee(lux, limites)
        if self.valeur is None:
            self.valeur, self.depuis = visee, t
            return True
        if visee == self.valeur:
            self._candidate = self._candidate_depuis = None
            return False
        if visee != self._candidate:
            self._candidate, self._candidate_depuis = visee, t
        # Une minuterie posée à l'échéance peut partir un peu avant.
        if t >= self.echeance - 1:
            self.valeur, self.depuis = visee, t
            self._candidate = self._candidate_depuis = None
            return True
        return False
