"""Santé de l'installation de la luminosité adaptative : statistiques
journalières, mesure de la rétroaction de l'écran et diagnostics
(docs/etude-luminosite-adaptative.md, § 3.4, 3.9 et 4.5, lot 3).

Logique seule, sans Home Assistant : les instants (secondes, flottants) et
le jour local (« AAAA-MM-JJ ») sont fournis par l'appelant, ce qui la rend
testable par séries synthétiques.

Un diagnostic est structuré (identifiant, niveau, chiffres, proposition
d'options) : les textes, en français, vivent dans le panneau. Les seuils
sont des points de départ de l'étude, à confirmer à l'essai réel.
"""

import math
import statistics
from collections import deque
from dataclasses import asdict, dataclass, field, fields
from datetime import date, timedelta

from .const import (CONF_EMPLACEMENT, CONF_HYSTERESIS_DESCENTE,
                    CONF_HYSTERESIS_MONTEE, CONF_LISSAGE_DESCENTE,
                    CONF_LUMINOSITE_MIN, CONF_LUX_MAX, CONF_LUX_MIN)
from .signal_lux import PLATEFORMES_SUR_VARIATION, Constantes

CONSERVATION_JOURS = 30
FENETRE_JOURS = 7

# Histogramme des intervalles entre deux rapports du capteur (secondes).
BORNES_INTERVALLES = (2, 5, 10, 30, 60, 120, 300, 600, 1800)
# Histogramme du lux : une tranche sous 1 lx (0 compris), puis 10 tranches
# par décade jusqu'à 200 000 lx. La tranche i ≥ 1 couvre
# [10^((i−1)/10) ; 10^(i/10)[ : un centile tombe à ±12 % près.
TRANCHES_PAR_DECADE = 10
NB_TRANCHES_LUX = 1 + math.ceil(TRANCHES_PAR_DECADE * math.log10(200_000))
# Événements gardés par jour : de quoi calculer une médiane, sans gonfler la
# base.
MAX_EVENEMENTS_TV = 20
MAX_REPONSES_RAMPES = 50
AMBIANCES = ("sombre", "intermediaire", "claire")

# --------------------------------------------------------------- seuils
# Capteur trop lent : intervalle médian entre deux rapports, téléviseur
# allumé.
LENT_INTERVALLE_S = 300
LENT_MIN_INTERVALLES = 20
# Capteur trop grossier : plus petit pas vu sous 20 lx, rapporté au lux
# sombre habituel, mais pas sous « Pièce sombre » : la courbe y est plate et
# un pas n'y change rien.
SOMBRE_LUX = 20
GROSSIER_PAS_RELATIF = 0.20
GROSSIER_MIN_RAPPORTS = 20
# « Pièce sombre » proposée : là où un pas ne fait plus que 20 %.
GROSSIER_FACTEUR = 1 / GROSSIER_PAS_RELATIF
# Plafond : même maximum répété, et le temps passé près du maximum l'est à
# la valeur exacte (un capteur qui plafonne ne fluctue plus).
PLAFOND_MIN_RAPPORTS = 10
PLAFOND_MIN_JOURS = 2
PLAFOND_ZONE = 0.8
PLAFOND_PART = 0.80
PLAFOND_MIN_TEMPS_S = 600
# Plancher : 0 lx la plupart du temps, téléviseur allumé.
PLANCHER_PART = 0.5
PLANCHER_MIN_ALLUME_S = 3 * 3600
# Courbe calée de travers : temps actif à une borne.
COURBE_PART = 0.80
COURBE_MIN_ACTIF_S = 10 * 3600
COURBE_CENTILE = 0.90
COURBE_ETENDUE_MIN = 1.5  # P90 / P10
# Allers-retours : 3 inversions de sens en 10 min font un épisode.
ALLERS_RETOURS_FENETRE_S = 600
ALLERS_RETOURS_INVERSIONS = 3
ALLERS_RETOURS_EPISODES = 3
# Rétroaction de l'écran, allumage et extinction (§ 3.4, option 1). Le
# délai entre l'écran et la connexion websocket est inconnu (reconnexion
# jusqu'à 30 s) : la valeur « avant » est prise une minute plus tôt.
RETRO_MARGE_AVANT_S = 60
RETRO_FENETRE_APRES_S = (30, 150)
RETRO_ETEINT_MIN_S = 180
RETRO_LUX_SOMBRE_MAX = 50
RETRO_MIN_EVENEMENTS = 5
RETRO_PART = 0.30
RETRO_DELTA_MIN_LX = 1
# Réponse aux rampes (option 2) : capteur rapide seulement, variation en
# fraction du lux pour 10 points de luminosité.
RAMPE_DELTA_MIN = 8
RAMPE_FENETRE_S = 20
RAMPE_MIN_REPONSES = 5
RAMPE_R10 = 0.05
# Rapports bruts gardés pour la rétroaction (fenêtres de quelques minutes).
RETRO_MEMOIRE_S = 600
# Pauses fréquentes : en moyenne une reprise en main par jour.
PAUSES_MIN = 7
# Écritures refusées.
REFUS_MIN = 3
REFUS_PART = 0.10
# Allers-retours : réglages proposés.
HYSTERESIS_EN_PLUS = 10  # points de pourcentage
LISSAGE_DESCENTE_MIN_S = 15


# ----------------------------------------------------------- histogrammes
def tranche_lux(lux: float) -> int:
    if lux < 1:
        return 0
    return min(1 + int(TRANCHES_PAR_DECADE * math.log10(lux)), NB_TRANCHES_LUX - 1)


def _bornes_tranche(i: int) -> tuple[float, float]:
    if i == 0:
        return 0.0, 1.0
    return 10 ** ((i - 1) / TRANCHES_PAR_DECADE), 10 ** (i / TRANCHES_PAR_DECADE)


def centile_lux(histogramme: list[float], q: float) -> float | None:
    """Centile d'un histogramme de temps par tranche de lux, interpolé sur le
    logarithme dans la tranche."""
    total = sum(histogramme)
    if total <= 0:
        return None
    cible, cumul = q * total, 0.0
    for i, temps in enumerate(histogramme):
        if temps > 0 and cumul + temps >= cible:
            bas, haut = _bornes_tranche(i)
            fraction = (cible - cumul) / temps
            if i == 0:
                return bas + fraction * (haut - bas)
            return bas * (haut / bas) ** fraction
        cumul += temps
    return _bornes_tranche(len(histogramme) - 1)[1]


def part_au_dessus(histogramme: list[float], seuil: float) -> float | None:
    """Part du temps passé à `seuil` lx ou plus, la tranche du seuil coupée
    en proportion de son logarithme."""
    total = sum(histogramme)
    if total <= 0:
        return None
    dessus = 0.0
    for i, temps in enumerate(histogramme):
        bas, haut = _bornes_tranche(i)
        if bas >= seuil:
            dessus += temps
        elif haut > seuil:
            if i == 0:
                dessus += temps * (haut - seuil) / (haut - bas)
            else:
                dessus += temps * math.log(haut / seuil) / math.log(haut / bas)
    return dessus / total


def mediane_intervalles(histogramme: list[int], sommes: list[float]) -> float | None:
    """Intervalle médian : moyenne des intervalles de la tranche médiane
    (exacte pour un capteur régulier, quelle que soit la largeur de la
    tranche)."""
    total = sum(histogramme)
    if total <= 0:
        return None
    cumul = 0
    for nombre, somme in zip(histogramme, sommes):
        if nombre > 0 and cumul + nombre >= total / 2:
            return somme / nombre
        cumul += nombre
    return None


def tranche_intervalle(secondes: float) -> int:
    return next((i for i, borne in enumerate(BORNES_INTERVALLES) if secondes < borne),
                len(BORNES_INTERVALLES))


def ambiance(lux: float, lux_min: float, lux_max: float) -> str:
    """Tiers de la plage logarithmique de la courbe."""
    t = (math.log(max(lux, 1)) - math.log(lux_min)) / (math.log(lux_max) - math.log(lux_min))
    return AMBIANCES[0] if t < 1 / 3 else AMBIANCES[1] if t < 2 / 3 else AMBIANCES[2]


def arrondi(valeur: float) -> float | int:
    """Deux chiffres significatifs : une proposition se lit et se retient."""
    resultat = float(f"{valeur:.2g}")
    return int(resultat) if resultat >= 10 else resultat


# ------------------------------------------------------------ agrégats
def _zeros_intervalles() -> list[int]:
    return [0] * (len(BORNES_INTERVALLES) + 1)


def _zeros_lux() -> list[float]:
    return [0.0] * NB_TRANCHES_LUX


def _zeros_reprises() -> dict[str, list[float]]:
    return {nom: [0, 0] for nom in AMBIANCES}


@dataclass
class StatsJour:
    """Agrégats d'un jour, pour un capteur. Sérialisés en JSON : un champ
    ajouté plus tard prend sa valeur par défaut à la relecture."""

    jour: str
    allume_s: float = 0  # téléviseur connecté
    actif_s: float = 0  # fonction dans l'état « active »
    rapports: int = 0  # rapports du capteur, téléviseur allumé
    intervalles: list[int] = field(default_factory=_zeros_intervalles)
    intervalles_s: list[float] = field(default_factory=_zeros_intervalles)  # sommes
    lux_actif: list[float] = field(default_factory=_zeros_lux)  # lux filtré
    lux_allume: list[float] = field(default_factory=_zeros_lux)  # lux brut
    sombre_rapports: int = 0  # rapports dans ]0 ; 20[ lx
    sombre_pas_min: float | None = None
    sous_10_rapports: int = 0
    sous_10_entiers: int = 0
    vmax: float | None = None
    vmax_rapports: int = 0
    vmax_s: float = 0  # temps à vmax exactement, téléviseur allumé
    zero_s: float = 0  # temps à 0 lx, téléviseur allumé
    transitions: int = 0
    pas_confirmes: int = 0
    non_confirmees: int = 0
    inversions: int = 0
    allers_retours: int = 0
    # Ambiance → [nombre, somme des corrections (valeur posée − cible)].
    reprises: dict[str, list[float]] = field(default_factory=_zeros_reprises)
    pauses_manuelles: int = 0
    tv: list[list] = field(default_factory=list)  # [sens, avant, après]
    rampes: list[float] = field(default_factory=list)  # r10

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, donnees: dict) -> "StatsJour":
        stats = cls(jour=donnees["jour"])
        for champ in fields(cls):
            if champ.name in donnees and champ.name != "jour":
                valeur = donnees[champ.name]
                defaut = getattr(stats, champ.name)
                # Histogramme d'une autre taille (version future) : ignoré.
                if isinstance(defaut, list) and champ.name in (
                        "intervalles", "intervalles_s", "lux_actif", "lux_allume"
                ) and len(valeur) != len(defaut):
                    continue
                if champ.name == "reprises":
                    valeur = {**_zeros_reprises(), **valeur}
                setattr(stats, champ.name, valeur)
        return stats

    def fusionner(self, autre: "StatsJour") -> None:
        """Ajoute les agrégats d'`autre` (même jour) : jour relu en base au
        démarrage et jour commencé depuis."""
        for nom in ("allume_s", "actif_s", "rapports", "sombre_rapports", "sous_10_rapports",
                    "sous_10_entiers", "zero_s", "transitions", "pas_confirmes",
                    "non_confirmees", "inversions", "allers_retours", "pauses_manuelles"):
            setattr(self, nom, getattr(self, nom) + getattr(autre, nom))
        for nom in ("intervalles", "intervalles_s", "lux_actif", "lux_allume"):
            setattr(self, nom, [a + b for a, b in zip(getattr(self, nom), getattr(autre, nom))])
        pas = [p for p in (self.sombre_pas_min, autre.sombre_pas_min) if p is not None]
        self.sombre_pas_min = min(pas) if pas else None
        if autre.vmax is not None:
            if self.vmax is None or autre.vmax > self.vmax:
                self.vmax, self.vmax_rapports, self.vmax_s = (
                    autre.vmax, autre.vmax_rapports, autre.vmax_s)
            elif autre.vmax == self.vmax:
                self.vmax_rapports += autre.vmax_rapports
                self.vmax_s += autre.vmax_s
        for nom in AMBIANCES:
            self.reprises[nom] = [a + b for a, b in zip(self.reprises[nom], autre.reprises[nom])]
        self.tv = (autre.tv + self.tv)[-MAX_EVENEMENTS_TV:]
        self.rampes = (autre.rampes + self.rampes)[-MAX_REPONSES_RAMPES:]


class Accumulateur:
    """Remplit les agrégats du jour au fil des rapports du capteur, des
    changements d'état et des minutes."""

    def __init__(self, stats: StatsJour) -> None:
        self.stats = stats
        self._etat: tuple | None = None  # (t, allumé, actif, lux filtré, lux brut)
        self._rapport: tuple[float, float, bool] | None = None  # (t, lux, allumé)

    def echantillon(self, t: float, jour: str, allume: bool, actif: bool,
                    lux_filtre: float | None, lux_brut: float | None) -> StatsJour | None:
        """État courant. Le temps écoulé depuis l'échantillon précédent est
        attribué à l'état d'alors, et au jour de cet échantillon (à une
        minute près autour de minuit). Rend l'agrégat du jour fini, s'il
        vient de se terminer."""
        if self._etat is not None:
            t0, allume0, actif0, filtre0, brut0 = self._etat
            duree = max(t - t0, 0)
            s = self.stats
            if allume0:
                s.allume_s += duree
                if brut0 is not None:
                    s.lux_allume[tranche_lux(brut0)] += duree
                    if brut0 == 0:
                        s.zero_s += duree
                    if brut0 == s.vmax:
                        s.vmax_s += duree
            if actif0 and filtre0 is not None:
                s.actif_s += duree
                s.lux_actif[tranche_lux(filtre0)] += duree
        termine = None
        if jour != self.stats.jour:
            termine, self.stats = self.stats, StatsJour(jour)
        self._etat = (t, allume, actif, lux_filtre, lux_brut)
        return termine

    def rapport(self, t: float, lux: float, allume: bool) -> None:
        s = self.stats
        if s.vmax is None or lux > s.vmax:
            s.vmax, s.vmax_rapports, s.vmax_s = lux, 1, 0
        elif lux == s.vmax:
            s.vmax_rapports += 1
        if 0 < lux < SOMBRE_LUX:
            s.sombre_rapports += 1
            if self._rapport is not None and 0 < self._rapport[1] < SOMBRE_LUX:
                pas = abs(lux - self._rapport[1])
                if pas > 0 and (s.sombre_pas_min is None or pas < s.sombre_pas_min):
                    s.sombre_pas_min = pas
        if 0 < lux < 10:
            s.sous_10_rapports += 1
            s.sous_10_entiers += lux == int(lux)
        if allume:
            s.rapports += 1
            if self._rapport is not None and self._rapport[2]:
                intervalle = t - self._rapport[0]
                s.intervalles[tranche_intervalle(intervalle)] += 1
                s.intervalles_s[tranche_intervalle(intervalle)] += intervalle
        self._rapport = (t, lux, allume)

    def transition(self, pas_confirmes: int, inversion: bool, episode: bool) -> None:
        self.stats.transitions += 1
        self.stats.pas_confirmes += pas_confirmes
        self.stats.inversions += inversion
        self.stats.allers_retours += episode

    def non_confirmee(self) -> None:
        self.stats.non_confirmees += 1

    def reprise(self, nom_ambiance: str, correction: float) -> None:
        self.stats.reprises[nom_ambiance][0] += 1
        self.stats.reprises[nom_ambiance][1] += correction

    def corriger_reprise(self, nom_ambiance: str, ecart: float) -> None:
        """Valeur changée encore pendant la même pause (plusieurs appuis sur
        la télécommande) : seule compte la dernière."""
        self.stats.reprises[nom_ambiance][1] += ecart

    def pause_manuelle(self) -> None:
        self.stats.pauses_manuelles += 1

    def evenement_tv(self, evenement: list) -> None:
        self.stats.tv = [*self.stats.tv, evenement][-MAX_EVENEMENTS_TV:]

    def reponse_rampe(self, r10: float) -> None:
        self.stats.rampes = [*self.stats.rampes, r10][-MAX_REPONSES_RAMPES:]


# ------------------------------------------------------------ rétroaction
class Retroaction:
    """Réponse du capteur à l'écran : allumage et extinction du téléviseur,
    fins de rampe. Les événements se résolvent une fois leur fenêtre de
    mesure passée (`resoudre`)."""

    def __init__(self) -> None:
        self._rapports: deque[tuple[float, float]] = deque()
        self._allume: bool | None = None
        self._depuis: float | None = None  # dernier changement d'état vu
        self._en_attente: list[dict] = []

    def rapport(self, t: float, lux: float) -> None:
        self._rapports.append((t, lux))
        # Garde le dernier rapport antérieur à la mémoire : la valeur
        # maintenue d'un capteur qui ne publie que sur variation.
        while len(self._rapports) >= 2 and self._rapports[1][0] <= t - RETRO_MEMOIRE_S:
            self._rapports.popleft()

    def _maintenue(self, t: float) -> float | None:
        valeur = None
        for instant, lux in self._rapports:
            if instant > t:
                break
            valeur = lux
        return valeur

    def _mediane(self, debut: float, fin: float) -> float | None:
        valeurs = [lux for instant, lux in self._rapports if debut <= instant <= fin]
        return statistics.median(valeurs) if valeurs else None

    def televiseur(self, t: float, allume: bool) -> None:
        precedent, depuis = self._allume, self._depuis
        if precedent == allume:
            return
        self._allume, self._depuis = allume, t
        if precedent is None:
            # Premier état connu (démarrage de Home Assistant) : rien à
            # comparer.
            return
        # Toute fenêtre en cours est faussée par le changement d'état.
        self._en_attente = [e for e in self._en_attente if e["fin"] < t]
        if not allume:
            sens = "extinction"
        elif t - depuis >= RETRO_ETEINT_MIN_S:
            sens = "allumage"
        else:
            # Coupure brève (réseau, redémarrage du téléviseur) : l'écran
            # n'est peut-être jamais resté éteint.
            return
        avant = self._maintenue(t - RETRO_MARGE_AVANT_S)
        if avant is not None:
            self._en_attente.append({"nature": "tv", "sens": sens, "t": t, "avant": avant,
                                     "fin": t + RETRO_FENETRE_APRES_S[1]})

    def rampe(self, t_fin: float, lux_avant: float, delta: int, gel_s: float) -> None:
        """Fin d'une rampe arrivée : `lux_avant`, l'ambiance mesurée avant
        qu'elle ne change l'écran ; `delta`, son amplitude en points."""
        debut = t_fin + gel_s
        self._en_attente.append({"nature": "rampe", "debut": debut, "fin": debut + RAMPE_FENETRE_S,
                                 "avant": lux_avant, "delta": delta})

    def perturbation(self, t: float) -> None:
        """Rampe, reprise en main : la fenêtre d'une fin de rampe en cours
        ne mesure plus la seule réponse de l'écran."""
        self._en_attente = [e for e in self._en_attente
                            if e["nature"] != "rampe" or e["fin"] < t]

    def resoudre(self, t: float) -> list[tuple[str, object]]:
        """Événements dont la fenêtre est passée : ("tv", [sens, avant,
        après]) ou ("rampe", r10). Sans rapport dans la fenêtre (capteur
        trop lent), sans conclusion."""
        resultats, restants = [], []
        for e in self._en_attente:
            if e["fin"] > t:
                restants.append(e)
                continue
            if e["nature"] == "tv":
                apres = self._mediane(e["t"] + RETRO_FENETRE_APRES_S[0], e["fin"])
                if apres is not None:
                    resultats.append(("tv", [e["sens"], e["avant"], apres]))
            else:
                apres = self._mediane(e["debut"], e["fin"])
                if apres is not None and e["avant"] > 0:
                    variation = (apres - e["avant"]) / e["avant"]
                    r10 = variation * 10 / abs(e["delta"]) * math.copysign(1, e["delta"])
                    resultats.append(("rampe", round(r10, 4)))
        self._en_attente = restants
        return resultats


class Inversions:
    """Changements de sens des transitions ; un épisode d'allers-retours
    quand 3 inversions tombent dans 10 min."""

    def __init__(self) -> None:
        self._sens: int | None = None
        self._instants: deque[float] = deque()

    def transition(self, t: float, sens: int) -> tuple[bool, bool]:
        """(inversion, épisode)."""
        inversion = self._sens is not None and sens != self._sens
        self._sens = sens
        if not inversion:
            return False, False
        self._instants.append(t)
        while self._instants and self._instants[0] < t - ALLERS_RETOURS_FENETRE_S:
            self._instants.popleft()
        if len(self._instants) >= ALLERS_RETOURS_INVERSIONS:
            self._instants.clear()
            return True, True
        return True, False


# ------------------------------------------------------------ diagnostics
@dataclass
class Contexte:
    options: dict
    constantes: Constantes
    profil: str
    plateforme: str | None = None
    conflit: str | None = None
    fige: bool = False
    ecriture_possible: bool | None = None
    piece_capteur: str | None = None
    piece_televiseur: str | None = None


@dataclass
class Diagnostic:
    id: str
    # ok, info, avertissement, bloquant, attente (pas encore assez de
    # données : `valeurs["progression"]` = [acquis, requis]).
    niveau: str
    valeurs: dict = field(default_factory=dict)
    # Options à appliquer d'un clic (commande `configurer`).
    proposition: dict | None = None


def fenetre(jours: list[StatsJour], aujourdhui: str,
            nb_jours: int = FENETRE_JOURS) -> list[StatsJour]:
    debut = (date.fromisoformat(aujourdhui) - timedelta(days=nb_jours - 1)).isoformat()
    return sorted((j for j in jours if debut <= j.jour <= aujourdhui), key=lambda j: j.jour)


def _somme(jours: list[StatsJour], nom: str) -> list[float]:
    return [sum(valeurs) for valeurs in zip(*(getattr(j, nom) for j in jours))] if jours else []


def _total(jours: list[StatsJour], nom: str) -> float:
    return sum(getattr(j, nom) for j in jours)


def _attente(id_: str, acquis: float, requis: float, **valeurs) -> Diagnostic:
    return Diagnostic(id_, "attente", {"progression": [round(acquis, 1), requis], **valeurs})


def _lent(jours, ctx: Contexte) -> Diagnostic:
    histogramme = _somme(jours, "intervalles")
    nombre = sum(histogramme)
    if nombre < LENT_MIN_INTERVALLES:
        return _attente("capteur_lent", nombre, LENT_MIN_INTERVALLES)
    intervalle = mediane_intervalles(histogramme, _somme(jours, "intervalles_s"))
    valeurs = {"intervalle_s": round(intervalle), "plateforme": ctx.plateforme}
    if intervalle <= LENT_INTERVALLE_S:
        return Diagnostic("capteur_lent", "ok", valeurs)
    # Un capteur qui ne publie que sur variation se tait dans une pièce
    # stable : un long intervalle n'y prouve pas la lenteur.
    sur_variation = ctx.plateforme in PLATEFORMES_SUR_VARIATION
    return Diagnostic("capteur_lent", "info" if sur_variation else "avertissement",
                      {**valeurs, "sur_variation": sur_variation})


def _grossier(jours, ctx: Contexte) -> Diagnostic:
    rapports = _total(jours, "sombre_rapports")
    pas = [j.sombre_pas_min for j in jours if j.sombre_pas_min is not None]
    # Lux sombre habituel : médiane du temps passé sous 20 lx, téléviseur
    # allumé.
    sombre = _somme(jours, "lux_allume")[:tranche_lux(SOMBRE_LUX)]
    mediane = centile_lux(sombre, 0.5) if sombre else None
    if rapports < GROSSIER_MIN_RAPPORTS or not pas or mediane is None:
        return _attente("capteur_grossier", rapports, GROSSIER_MIN_RAPPORTS)
    pas_min = min(pas)
    lux_min = ctx.options[CONF_LUX_MIN]
    reference = max(mediane, lux_min)
    sous_10 = _total(jours, "sous_10_rapports")
    valeurs = {"pas": pas_min, "lux_sombre": round(mediane, 1), "reference": round(reference, 1),
               "pas_relatif": round(pas_min / reference, 3),
               "entiers": sous_10 > 0 and _total(jours, "sous_10_entiers") == sous_10}
    if pas_min / reference <= GROSSIER_PAS_RELATIF:
        return Diagnostic("capteur_grossier", "ok", valeurs)
    proposition = None
    propose = arrondi(GROSSIER_FACTEUR * pas_min)
    if lux_min < propose < ctx.options[CONF_LUX_MAX] and 1 <= propose <= 1000:
        proposition = {CONF_LUX_MIN: propose}
    return Diagnostic("capteur_grossier", "avertissement", valeurs, proposition)


def _plafond(jours, ctx: Contexte) -> Diagnostic | None:
    maxima = [j.vmax for j in jours if j.vmax is not None]
    if not maxima:
        return None
    vmax = max(maxima)
    a_vmax = [j for j in jours if j.vmax == vmax]
    rapports = sum(j.vmax_rapports for j in a_vmax)
    temps_vmax = sum(j.vmax_s for j in a_vmax)
    allume = _somme(jours, "lux_allume")
    part_zone = part_au_dessus(allume, PLAFOND_ZONE * vmax) if vmax > 0 else None
    temps_zone = (part_zone or 0) * sum(allume)
    valeurs = {"vmax": vmax, "rapports": rapports, "jours": len(a_vmax)}
    if (vmax <= 0 or rapports < PLAFOND_MIN_RAPPORTS or len(a_vmax) < PLAFOND_MIN_JOURS
            or temps_zone < PLAFOND_MIN_TEMPS_S or temps_vmax < PLAFOND_PART * temps_zone):
        return Diagnostic("plafond", "ok", valeurs)
    # Au-delà de « Pièce lumineuse », la luminosité est déjà au maximum :
    # le plafond n'y change rien.
    gene = vmax <= ctx.options[CONF_LUX_MAX]
    return Diagnostic("plafond", "avertissement" if gene else "info",
                      {**valeurs, "sous_lux_max": gene})


def _plancher(jours, ctx: Contexte) -> Diagnostic:
    allume = _total(jours, "allume_s")
    if allume < PLANCHER_MIN_ALLUME_S:
        return _attente("plancher", allume / 3600, PLANCHER_MIN_ALLUME_S / 3600)
    part = _total(jours, "zero_s") / allume
    return Diagnostic("plancher", "info" if part >= PLANCHER_PART else "ok",
                      {"part": round(part, 3)})


def _courbe(jours, ctx: Contexte) -> Diagnostic:
    actif = _total(jours, "actif_s")
    if actif < COURBE_MIN_ACTIF_S:
        return _attente("courbe", actif / 3600, COURBE_MIN_ACTIF_S / 3600)
    histogramme = _somme(jours, "lux_actif")
    lux_min, lux_max = ctx.options[CONF_LUX_MIN], ctx.options[CONF_LUX_MAX]
    # Calculé avec les options actuelles : une correction appliquée se voit
    # aussitôt.
    haute = part_au_dessus(histogramme, lux_max)
    basse = 1 - part_au_dessus(histogramme, lux_min)
    valeurs = {"part_haute": round(haute, 3), "part_basse": round(basse, 3),
               "lux_p10": arrondi(centile_lux(histogramme, 0.10)),
               "lux_p90": arrondi(centile_lux(histogramme, COURBE_CENTILE))}
    if haute > COURBE_PART:
        propose = valeurs["lux_p90"]
        # Pas pour une lumière constante (étendue sous une tranche et demie) :
        # elle resterait au sommet de la courbe quelle que soit la valeur.
        etendue = centile_lux(histogramme, COURBE_CENTILE) / centile_lux(histogramme, 0.10)
        proposition = ({CONF_LUX_MAX: propose}
                       if lux_max < propose <= 100_000 and etendue >= COURBE_ETENDUE_MIN
                       else None)
        return Diagnostic("courbe", "avertissement", {**valeurs, "borne": "haute"}, proposition)
    if basse > COURBE_PART:
        # Deux lectures possibles (pièce plus sombre que prévu, ou minimum
        # qui convient la nuit) : information seule, sans proposition.
        return Diagnostic("courbe", "info", {**valeurs, "borne": "basse",
                                             "luminosite_min": ctx.options[CONF_LUMINOSITE_MIN]})
    return Diagnostic("courbe", "ok", valeurs)


def _allers_retours(jours, ctx: Contexte) -> Diagnostic:
    episodes = _total(jours, "allers_retours")
    valeurs = {"episodes": episodes, "inversions": _total(jours, "inversions")}
    if episodes < ALLERS_RETOURS_EPISODES:
        return Diagnostic("allers_retours", "ok", valeurs)
    c = ctx.constantes
    proposition = {
        CONF_HYSTERESIS_MONTEE: min(round(c.hysteresis_montee * 100) + HYSTERESIS_EN_PLUS, 100),
        CONF_HYSTERESIS_DESCENTE: min(round(c.hysteresis_descente * 100) + HYSTERESIS_EN_PLUS, 90),
        CONF_LISSAGE_DESCENTE: min(max(round(c.lissage_descente_s * 2), LISSAGE_DESCENTE_MIN_S),
                                   300),
    }
    return Diagnostic("allers_retours", "avertissement", valeurs, proposition)


def mesure_retroaction(jours: list[StatsJour]) -> dict:
    """Contribution de l'écran d'après les allumages et extinctions en pièce
    sombre (médianes), et réponse aux rampes."""
    deltas, parts = [], []
    for sens, avant, apres in (e for j in jours for e in j.tv):
        allume, eteint = (avant, apres) if sens == "extinction" else (apres, avant)
        if eteint > RETRO_LUX_SOMBRE_MAX:
            continue
        deltas.append(allume - eteint)
        parts.append((allume - eteint) / allume if allume > 0 else 0.0)
    rampes = [r for j in jours for r in j.rampes]
    return {
        "evenements": len(deltas),
        "delta_lx": round(statistics.median(deltas), 1) if deltas else None,
        "part": round(statistics.median(parts), 3) if parts else None,
        "rampes": len(rampes),
        "r10": round(statistics.median(rampes), 3) if rampes else None,
    }


def _retroaction(jours, ctx: Contexte) -> Diagnostic:
    mesure = mesure_retroaction(jours)
    declare_d = ctx.options.get(CONF_EMPLACEMENT) == "d"
    par_tv = mesure["evenements"] >= RETRO_MIN_EVENEMENTS
    par_rampes = mesure["rampes"] >= RAMPE_MIN_REPONSES
    vue_tv = par_tv and mesure["part"] > RETRO_PART and mesure["delta_lx"] >= RETRO_DELTA_MIN_LX
    vue_rampes = par_rampes and mesure["r10"] >= RAMPE_R10
    valeurs = {**mesure, "emplacement_d": declare_d, "mesure_tv": par_tv,
               "mesure_rampes": par_rampes, "vue_tv": vue_tv, "vue_rampes": vue_rampes}
    if vue_tv or vue_rampes:
        return Diagnostic("retroaction", "avertissement", valeurs)
    if declare_d:
        # Déclaré face à l'écran : averti d'office, sauf si les mesures
        # disent le contraire.
        return Diagnostic("retroaction", "info" if par_tv or par_rampes else "avertissement",
                          valeurs)
    if par_tv or par_rampes:
        return Diagnostic("retroaction", "ok", valeurs)
    return _attente("retroaction", mesure["evenements"], RETRO_MIN_EVENEMENTS, **valeurs)


def _pauses(jours, ctx: Contexte) -> Diagnostic:
    par_ambiance = {nom: [sum(j.reprises[nom][0] for j in jours),
                          sum(j.reprises[nom][1] for j in jours)] for nom in AMBIANCES}
    total = sum(n for n, _ in par_ambiance.values())
    valeurs = {"reprises": total, "pauses_manuelles": _total(jours, "pauses_manuelles")}
    if total < PAUSES_MIN:
        return Diagnostic("pauses_frequentes", "ok", valeurs)
    principale = max(AMBIANCES, key=lambda nom: par_ambiance[nom][0])
    n, somme = par_ambiance[principale]
    return Diagnostic("pauses_frequentes", "info", {
        **valeurs, "ambiance": principale, "reprises_ambiance": n,
        "correction_moyenne": round(somme / n, 1),
        "par_ambiance": {nom: {"reprises": n_, "correction_moyenne":
                               round(s / n_, 1) if n_ else None}
                         for nom, (n_, s) in par_ambiance.items()}})


def _refus(jours, ctx: Contexte) -> Diagnostic:
    refus = _total(jours, "non_confirmees")
    tentatives = _total(jours, "transitions") + refus
    valeurs = {"non_confirmees": refus, "tentatives": tentatives,
               "ecriture_possible": ctx.ecriture_possible}
    if refus >= REFUS_MIN and refus >= REFUS_PART * tentatives:
        return Diagnostic("ecritures_refusees", "avertissement", valeurs)
    return Diagnostic("ecritures_refusees", "ok", valeurs)


def evaluer(jours: list[StatsJour], aujourdhui: str, ctx: Contexte) -> list[Diagnostic]:
    """Diagnostics sur les 7 derniers jours, les cas bloquants d'abord."""
    jours = fenetre(jours, aujourdhui)
    resultat = [
        Diagnostic("conflit", "bloquant" if ctx.conflit else "ok", {"cause": ctx.conflit}),
        Diagnostic("capteur_fige", "bloquant" if ctx.fige else "ok"),
        _retroaction(jours, ctx),
        _courbe(jours, ctx),
        _lent(jours, ctx),
        _grossier(jours, ctx),
        _plafond(jours, ctx),
        _plancher(jours, ctx),
        _allers_retours(jours, ctx),
        _refus(jours, ctx),
        _pauses(jours, ctx),
    ]
    if ctx.piece_capteur is not None and ctx.piece_televiseur is not None:
        differentes = ctx.piece_capteur != ctx.piece_televiseur
        resultat.append(Diagnostic("pieces_differentes", "info" if differentes else "ok",
                                   {"capteur": ctx.piece_capteur,
                                    "televiseur": ctx.piece_televiseur}))
    return [d for d in resultat if d is not None]


def resume(jours: list[StatsJour], aujourdhui: str) -> dict:
    """Statistiques utiles des 7 derniers jours, pour le panneau."""
    jours = fenetre(jours, aujourdhui)
    actif = _somme(jours, "lux_actif")
    pas = [j.sombre_pas_min for j in jours if j.sombre_pas_min is not None]
    return {
        "jours": len(jours),
        "depuis": jours[0].jour if jours else None,
        "allume_s": round(_total(jours, "allume_s")),
        "actif_s": round(_total(jours, "actif_s")),
        "transitions": _total(jours, "transitions"),
        "pas_confirmes": _total(jours, "pas_confirmes"),
        "non_confirmees": _total(jours, "non_confirmees"),
        "reprises": sum(j.reprises[nom][0] for j in jours for nom in AMBIANCES),
        "pauses_manuelles": _total(jours, "pauses_manuelles"),
        "intervalle_s": (round(i) if (i := mediane_intervalles(
            _somme(jours, "intervalles"), _somme(jours, "intervalles_s"))) is not None else None),
        "pas_sombre": min(pas) if pas else None,
        "lux_p10": arrondi(p) if (p := centile_lux(actif, 0.10)) is not None else None,
        "lux_p50": arrondi(p) if (p := centile_lux(actif, 0.50)) is not None else None,
        "lux_p90": arrondi(p) if (p := centile_lux(actif, 0.90)) is not None else None,
    }


def resume_jour(stats: StatsJour) -> dict:
    """Ligne du tableau par jour."""
    return {
        "jour": stats.jour,
        "allume_s": round(stats.allume_s),
        "actif_s": round(stats.actif_s),
        "transitions": stats.transitions,
        "reprises": sum(stats.reprises[nom][0] for nom in AMBIANCES),
        "non_confirmees": stats.non_confirmees,
    }
