"""Rampe de la luminosité : passage de la valeur du téléviseur à la cible par
petits pas cadencés, au lieu d'un saut (docs/etude-luminosite-adaptative.md,
§ 3.1 Rampes, lot 2).

Logique seule, sans Home Assistant ni téléviseur : les instants (secondes,
flottants) sont fournis par l'appelant, qui écrit chaque pas et ne confirme
que la valeur relue sur le téléviseur.

La rampe suit une cible qui peut bouger (lux filtré qui avance, options
changées) : chaque pas vise la cible du moment, et le sens s'inverse si elle
repasse de l'autre côté.
"""

import math
from dataclasses import dataclass

from .const import CONF_RAMPE_DEBIT, CONF_RAMPE_PAS

# Point de départ de l'étude (§ 3.1, 4.4) : 4 points par seconde, 40 → 100
# en 15 s. À confirmer à l'essai (P4 : pas visibles, débit soutenu).
PAS_DEFAUT = 1
DEBIT_DEFAUT = 4
# Un pas lent (latence du téléviseur) est rattrapé au pas suivant, sans
# dépasser ce multiple du pas : un saut visible serait pire qu'un retard.
RATTRAPAGE_MAX = 2


@dataclass(frozen=True)
class Parametres:
    pas: int  # points par pas
    debit: float  # points par seconde

    @property
    def intervalle_s(self) -> float:
        return self.pas / self.debit


def parametres(options: dict) -> Parametres:
    pas, debit = options.get(CONF_RAMPE_PAS), options.get(CONF_RAMPE_DEBIT)
    return Parametres(pas=PAS_DEFAUT if pas is None else pas,
                      debit=DEBIT_DEFAUT if debit is None else debit)


class Rampe:
    """Une transition, de la valeur du téléviseur au départ jusqu'à
    l'arrivée. `valeur` n'avance qu'avec les valeurs confirmées par le
    téléviseur, jamais avec celles demandées."""

    def __init__(self, parametres_: Parametres, depart: int | None, t: float) -> None:
        self.parametres = parametres_
        self.depart = depart
        self.valeur = depart
        self.debut = t
        self.pas_confirmes = 0
        self.interruption: str | None = None
        self._dernier_envoi: float | None = None
        self._reste = 0.0

    def prochain_pas(self, t: float, cible: int) -> tuple[float, int] | None:
        """(instant, valeur) du prochain pas vers `cible`, ou None si le
        téléviseur y est déjà. Valeur actuelle inconnue : un seul pas,
        directement à la cible."""
        if self.valeur == cible:
            return None
        if self.valeur is None:
            return t, cible
        p = self.parametres
        if self._dernier_envoi is None:
            instant, amplitude = t, p.pas
        else:
            instant = max(t, self._dernier_envoi + p.intervalle_s)
            # Marge sur le flottant : 4 × 0,25 doit donner 1.
            permis = math.floor(self._credit(instant) + 1e-6)
            amplitude = min(max(p.pas, permis), RATTRAPAGE_MAX * p.pas)
        ecart = cible - self.valeur
        return instant, self.valeur + int(math.copysign(min(amplitude, abs(ecart)), ecart))

    def _credit(self, t: float) -> float:
        """Points permis par le débit depuis le dernier envoi, reste du pas
        précédent compris : une latence de 0,4 s pour 0,25 s d'intervalle
        donne des pas de 1 et 2 points, et non 1 point toutes les 0,4 s."""
        return self._reste + self.parametres.debit * (t - self._dernier_envoi)

    def envoyer(self, t: float, valeur: int) -> None:
        if self._dernier_envoi is not None and self.valeur is not None:
            # Borné à un pas : une attente sur la cible n'accumule rien.
            self._reste = min(max(self._credit(t) - abs(valeur - self.valeur), 0),
                              self.parametres.pas)
        self._dernier_envoi = t

    def confirmer(self, valeur: int) -> None:
        self.valeur = valeur
        self.pas_confirmes += 1

    def interrompre(self, raison: str) -> None:
        """La première raison compte : c'est elle qui a arrêté la rampe."""
        if self.interruption is None:
            self.interruption = raison

    def arrivee(self, cible: int | None, cible_finale: int | None) -> bool:
        """Arrivée seulement quand le filtre lui-même est arrivé, au point
        près : sinon la cible bougera encore et la transition continue dans
        la même rampe."""
        return self.valeur is not None and self.valeur == cible == cible_finale

    def duree(self, t: float) -> float:
        return t - self.debut
