"""Courbe de la luminosité adaptative : luminosité voulue selon le lux, et
calage sur la préférence de l'utilisateur (docs/etude-luminosite-adaptative.md,
§ 3.1, 4.6, lot 4).

Logique seule, sans Home Assistant. La courbe passe par deux points
(pièce sombre, pièce lumineuse) et un point intermédiaire facultatif ; elle
est linéaire par morceaux sur ln(lux), plate au-delà des extrémités, et
monotone (plateaux permis). Le panneau en a une copie
(frontend/src/luminosite.js), alignée par tests/vecteurs_courbe.json.

Point d'ancrage : « la luminosité qui me convient ici » décale la courbe en
ln(lux), forme et pente conservées ; un deuxième point dans une ambiance
nettement différente cale aussi la pente (transformation affine de ln(lux)).
Seuls les lux bougent : les luminosités de la courbe ne changent que pour
s'étendre jusqu'à une valeur d'ancrage hors des bornes.
"""

import itertools
import math

from .const import (CLES_COURBE, CONF_ANCRAGES, CONF_LUMINOSITE_MAX,
                    CONF_LUMINOSITE_MIN, CONF_LUX_MAX, CONF_LUX_MIN,
                    CONF_POINT_INTERMEDIAIRE, OPTIONS_LUMINOSITE_DEFAUT)

# Le lux est compté à partir de 1 (ln(1) = 0) : un capteur qui affiche 0
# dans le noir ne fait pas diverger le logarithme.
LUX_PLANCHER = 1
# Bornes des options lux_max et lux_min (luminosite_adaptative.BORNES).
LUX_PLAFOND = 100000
LUX_MIN_PLAFOND = 1000
# Deux ancrages ne calent la pente que s'ils sont pris dans des ambiances
# nettement différentes : plus proches, le second remplace le premier (une
# pente tirée de deux lux voisins amplifierait le moindre écart).
FACTEUR_DEUX_POINTS = 4
ANCRAGES_MAX = 2


def points(options: dict) -> list[tuple[float, float]]:
    """(lux, luminosité) de la courbe, du plus sombre au plus lumineux."""
    resultat = [(options[CONF_LUX_MIN], options[CONF_LUMINOSITE_MIN])]
    if (point := options.get(CONF_POINT_INTERMEDIAIRE)) is not None:
        resultat.append((point[0], point[1]))
    resultat.append((options[CONF_LUX_MAX], options[CONF_LUMINOSITE_MAX]))
    return resultat


def _valeur(x: float, courbe: list[tuple[float, float]]) -> float:
    """Luminosité en x = ln(lux), courbe donnée en (ln(lux), luminosité)."""
    if x <= courbe[0][0]:
        return courbe[0][1]
    for (x0, v0), (x1, v1) in zip(courbe, courbe[1:], strict=False):
        if x <= x1:
            return v0 + (x - x0) / (x1 - x0) * (v1 - v0)
    return courbe[-1][1]


def _en_ln(options: dict) -> list[tuple[float, float]]:
    return [(math.log(lux), valeur) for lux, valeur in points(options)]


def calculer_cible(lux: float, options: dict, decalage: float = 0,
                   reduction: float = 0) -> int:
    """Interpolation par morceaux sur le logarithme du lux, bornée aux
    extrémités, plus le décalage pilotable (entité « Décalage »), le tout
    borné à 0–100 : le décalage peut dépasser les luminosités de la courbe.
    `reduction` (Soirée, en %) s'applique ensuite, à la valeur bornée : la
    baisse vaut pour ce que le téléviseur aurait affiché."""
    valeur = _valeur(math.log(max(lux, LUX_PLANCHER)), _en_ln(options)) + decalage
    if reduction:
        valeur = min(max(valeur, 0), 100) * (1 - reduction / 100)
    # Arrondi « commercial » (0,5 vers le haut), comme Jinja dans l'ancien
    # blueprint, plutôt que l'arrondi au pair de round().
    return min(max(int(math.floor(valeur + 0.5)), 0), 100)


def _nombre(valeur) -> bool:
    return not isinstance(valeur, bool) and isinstance(valeur, int | float)


def valider_point_intermediaire(options: dict) -> tuple[list | None, str | None]:
    """Point intermédiaire normalisé (luminosité entière) et code d'erreur.
    Il doit tomber strictement entre les deux extrémités en lux, et entre
    leurs luminosités (courbe monotone ; un plateau est permis)."""
    point = options.get(CONF_POINT_INTERMEDIAIRE)
    if point is None:
        return None, None
    if (not isinstance(point, list | tuple) or len(point) != 2
            or not all(_nombre(v) for v in point)
            or not LUX_PLANCHER <= point[0] <= LUX_PLAFOND or not 0 <= point[1] <= 100):
        return point, "hors_bornes"
    lux, luminosite = point
    if not (options[CONF_LUX_MIN] < lux < options[CONF_LUX_MAX]
            and options[CONF_LUMINOSITE_MIN] <= luminosite <= options[CONF_LUMINOSITE_MAX]):
        return point, "point_intermediaire_hors_courbe"
    return [lux, int(luminosite)], None


def conserver_ancrages(anciennes: dict, nouvelles: dict) -> dict:
    """Options enregistrées : les ancrages suivent tant que la courbe n'a pas
    été retouchée ; sinon ils sont oubliés (ils ne la décrivent plus)."""
    resultat = {cle: valeur for cle, valeur in nouvelles.items() if cle != CONF_ANCRAGES}
    ancrages = anciennes.get(CONF_ANCRAGES)

    def courbe(options: dict) -> list:
        # Options d'avant la première saisie : valeurs par défaut implicites.
        options = {**OPTIONS_LUMINOSITE_DEFAUT, **options}
        return [list(v) if isinstance(v, list | tuple) else v
                for v in (options.get(cle) for cle in CLES_COURBE)]

    if ancrages and courbe(anciennes) == courbe(resultat):
        resultat[CONF_ANCRAGES] = ancrages
    return resultat


# ------------------------------------------------------------------ ancrage
def _antecedent(valeur: float, courbe: list[tuple[float, float]], x: float,
                cote: str = "proche") -> float:
    """Abscisse ln(lux) où la courbe vaut `valeur` (comprise entre ses
    luminosités extrêmes). Sur un plateau, ou à une extrémité, l'antécédent
    est un intervalle : on y prend le point le plus proche de `x` (aucun
    déplacement si l'utilisateur est déjà dans la partie plate), ou son
    bord droit (`cote="haut"`) ou gauche (`cote="bas"`)."""
    intervalles = []
    if valeur == courbe[0][1]:
        intervalles.append((-math.inf, courbe[0][0]))
    for (x0, v0), (x1, v1) in zip(courbe, courbe[1:], strict=False):
        if v0 == v1 == valeur:
            intervalles.append((x0, x1))
        elif min(v0, v1) <= valeur <= max(v0, v1) and v0 != v1:
            xv = x0 + (valeur - v0) / (v1 - v0) * (x1 - x0)
            intervalles.append((xv, xv))
    if valeur == courbe[-1][1]:
        intervalles.append((courbe[-1][0], math.inf))
    # Courbe monotone : les intervalles se touchent, un seul en tout.
    bas, haut = min(i[0] for i in intervalles), max(i[1] for i in intervalles)
    if cote == "haut":
        return haut
    if cote == "bas":
        return bas
    return min(max(x, bas), haut)


def _etendre(options: dict, valeurs: list[int]) -> tuple[dict, str | None]:
    """Bornes de luminosité élargies jusqu'aux valeurs d'ancrage."""
    options = dict(options)
    etendue = None
    if min(valeurs) < options[CONF_LUMINOSITE_MIN]:
        options[CONF_LUMINOSITE_MIN] = min(valeurs)
        etendue = "min"
    if max(valeurs) > options[CONF_LUMINOSITE_MAX]:
        options[CONF_LUMINOSITE_MAX] = max(valeurs)
        etendue = "max" if etendue is None else "min_max"
    return options, etendue


def _couper(courbe: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], bool]:
    """Partie de la courbe hors d'atteinte (sous 1 lx, au-delà du plafond)
    remplacée par sa valeur à la limite : pour tout lux mesurable, la
    luminosité est exactement celle de la courbe décalée."""
    x_bas, x_haut = math.log(LUX_PLANCHER), math.log(LUX_PLAFOND)
    coupee = False
    if courbe[0][0] < x_bas:
        courbe = [(x_bas, _valeur(x_bas, courbe))] + [p for p in courbe if p[0] > x_bas]
        coupee = True
    if courbe[-1][0] > x_haut:
        courbe = [p for p in courbe if p[0] < x_haut] + [(x_haut, _valeur(x_haut, courbe))]
        coupee = True
    return courbe, coupee


def _encadrer(lux: float) -> set[float]:
    """Valeurs saisissables qui encadrent `lux` : au dixième sous 100 lx
    (à 3 lx, l'unité déplacerait la courbe de deux points de luminosité),
    à l'unité au-delà, entre 1 lx et le plafond."""
    pas = 0.1 if lux < 100 else 1
    bas = round(math.floor(lux / pas) * pas, 1)
    return {min(max(v, LUX_PLANCHER), LUX_PLAFOND) for v in (bas, round(bas + pas, 1))}


def _arrondir(courbe: list[tuple[float, float]], valeurs: list[int],
              cibles: list[tuple[float, int]]) -> list[float]:
    """Lux de la courbe ramenés à la précision des options : de l'arrondi
    inférieur ou supérieur de chaque point, la combinaison qui s'écarte le
    moins des points d'ancrage."""
    choix = [sorted(_encadrer(math.exp(x))) for x, _ in courbe]

    def ecart(lux: tuple[float, ...]) -> tuple[float, float]:
        en_ln = [(math.log(lx), v) for lx, v in zip(lux, valeurs, strict=True)]
        pire = max((abs(_valeur(math.log(c), en_ln) - v) for c, v in cibles), default=0)
        distance = sum(abs(math.log(lx) - x) for lx, (x, _) in zip(lux, courbe, strict=True))
        return pire, distance

    valides = [lux for lux in itertools.product(*choix)
               if all(a < b for a, b in itertools.pairwise(lux))]
    if not valides:
        return [min(choix_point) for choix_point in choix]
    return [int(lx) if float(lx).is_integer() else lx for lx in min(valides, key=ecart)]


def _vers_options(options: dict, courbe: list[tuple[float, float]],
                  cibles: list[tuple[float, int]]) -> tuple[dict, bool]:
    """Courbe en (ln(lux), luminosité) → options : lux au dixième (à l'unité
    au-delà de 100 lx), ordre strict, luminosités entières. Renvoie aussi si le point n'est plus qu'approché
    (pièce sombre ramenée sous sa borne de formulaire, points confondus)."""
    approche = False
    valeurs = [int(math.floor(v + 0.5)) for _, v in courbe]
    lux = _arrondir(courbe, valeurs, cibles)
    if len(lux) == 3 and not lux[0] < lux[1] < lux[2]:
        # Point intermédiaire confondu avec une extrémité après l'arrondi.
        del lux[1], valeurs[1]
    if lux[0] > LUX_MIN_PLAFOND:
        lux[0] = LUX_MIN_PLAFOND
        approche = True
    if lux[-1] <= lux[0]:
        lux[-1] = round(lux[0] + 1, 1)
        approche = True
    resultat = {**options, CONF_LUX_MIN: lux[0], CONF_LUMINOSITE_MIN: valeurs[0],
                CONF_LUX_MAX: lux[-1], CONF_LUMINOSITE_MAX: valeurs[-1]}
    resultat.pop(CONF_POINT_INTERMEDIAIRE, None)
    if len(lux) == 3 and lux[0] < lux[1] < lux[2]:
        resultat[CONF_POINT_INTERMEDIAIRE] = [lux[1], valeurs[1]]
    return resultat, approche


def _choisir_ancien(ancrages: list[dict], lux: float) -> tuple[dict | None, bool]:
    """Ancrage à combiner avec le nouveau : un ancrage pris dans une ambiance
    voisine est remplacé ; de deux ancrages éloignés, le plus proche cède sa
    place. Renvoie aussi si un ancrage a été remplacé."""
    eloignes = [a for a in ancrages
                if abs(math.log(max(a["lux"], LUX_PLANCHER) / lux)) >= math.log(FACTEUR_DEUX_POINTS)]
    remplace = len(eloignes) < len(ancrages)
    if not eloignes:
        return None, remplace
    ancien = max(eloignes, key=lambda a: abs(math.log(max(a["lux"], LUX_PLANCHER) / lux)))
    return ancien, remplace or len(eloignes) > 1


def ancrer(options: dict, ancrages: list[dict] | None, lux: float, valeur: int,
           horodatage: str) -> tuple[dict, list[dict], dict]:
    """Cale la courbe pour qu'elle donne `valeur` à `lux`, sur un point ou,
    avec un ancrage précédent pris dans une autre ambiance, sur deux.
    Renvoie les options (sans les ancrages), les ancrages à conserver et un
    compte rendu pour le panneau."""
    lux = max(lux, LUX_PLANCHER)
    nouveau = {"lux": round(lux, 1), "luminosite": valeur, "horodatage": horodatage}
    ancien, remplace = _choisir_ancien(list(ancrages or []), lux)
    ancien_oublie = False
    if ancien is not None:
        lux_ancien = max(ancien["lux"], LUX_PLANCHER)
        # Plus de lumière, luminosité au moins égale : sinon la courbe ne
        # pourrait pas passer par les deux points en restant monotone.
        bas, haut = sorted([(lux_ancien, ancien["luminosite"]), (lux, valeur)])
        if haut[1] <= bas[1]:
            ancien, ancien_oublie = None, True

    if ancien is None:
        options, etendue = _etendre(options, [valeur])
        courbe = _en_ln(options)
        x = math.log(lux)
        decalage = x - _antecedent(valeur, courbe, x)
        courbe = [(xp + decalage, v) for xp, v in courbe]
        conserves = [nouveau]
        cibles = [(lux, valeur)]
    else:
        options, etendue = _etendre(options, [bas[1], haut[1]])
        courbe = _en_ln(options)
        x_bas, x_haut = math.log(bas[0]), math.log(haut[0])
        # Bords opposés des plateaux : les deux antécédents restent distincts.
        a_bas = _antecedent(bas[1], courbe, x_bas, "haut")
        a_haut = _antecedent(haut[1], courbe, x_haut, "bas")
        pente = (x_haut - x_bas) / (a_haut - a_bas)
        courbe = [(x_bas + (xp - a_bas) * pente, v) for xp, v in courbe]
        conserves = sorted([ancien, nouveau], key=lambda a: a["lux"])
        cibles = [bas, haut]
    courbe, coupee = _couper(courbe)
    options, approche = _vers_options(options, courbe, cibles)
    options.pop(CONF_ANCRAGES, None)
    return options, conserves, {
        "points": len(conserves),
        "borne_etendue": etendue,
        "coupee": coupee,
        "approche": approche,
        "remplace": remplace,
        "ancien_oublie": ancien_oublie,
        "cible": calculer_cible(lux, options),
    }
