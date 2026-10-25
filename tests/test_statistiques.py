"""Persistance des statistiques journalières de la luminosité adaptative."""

from custom_components.lg_webos_tv.historique import Historique
from custom_components.lg_webos_tv.sante import StatsJour
from custom_components.lg_webos_tv.statistiques import StatsLuminosite

LUX, AUTRE = "sensor.salon_lux", "sensor.bureau_lux"


def jour(nom: str, **valeurs) -> dict:
    return StatsJour(nom, **valeurs).en_dict()


async def test_enregistrer_relire_et_remplacer(tmp_path):
    stats = StatsLuminosite(tmp_path / "historique.sqlite")
    await stats.enregistrer(LUX, [jour("2026-10-24", transitions=3), jour("2026-10-25")])
    await stats.enregistrer(LUX, [jour("2026-10-25", transitions=7)])
    lignes = await stats.charger(LUX, "2026-10-01")
    assert [(ligne["jour"], ligne["transitions"]) for ligne in lignes] == [
        ("2026-10-24", 3), ("2026-10-25", 7)]
    assert StatsJour.depuis_dict(lignes[1]) == StatsJour("2026-10-25", transitions=7)
    assert [ligne["jour"] for ligne in await stats.charger(LUX, "2026-10-25")] == ["2026-10-25"]


async def test_capteurs_separes(tmp_path):
    stats = StatsLuminosite(tmp_path / "historique.sqlite")
    await stats.enregistrer(LUX, [jour("2026-10-25", transitions=1)])
    await stats.enregistrer(AUTRE, [jour("2026-10-25", transitions=2)])
    assert (await stats.charger(AUTRE, "2026-10-01"))[0]["transitions"] == 2
    assert (await stats.charger(LUX, "2026-10-01"))[0]["transitions"] == 1


async def test_purge_au_dela_de_trente_jours(tmp_path):
    stats = StatsLuminosite(tmp_path / "historique.sqlite")
    await stats.enregistrer(LUX, [jour("2026-09-25"), jour("2026-09-26"), jour("2026-10-25")])
    await stats.enregistrer(AUTRE, [jour("2026-09-01")])
    assert await stats.purger("2026-09-26") == 2
    assert [ligne["jour"] for ligne in await stats.charger(LUX, "2000-01-01")] == [
        "2026-09-26", "2026-10-25"]


async def test_meme_fichier_que_l_historique(tmp_path):
    """Une seule base dans <config>/lg_webos_tv/, incluse dans les
    sauvegardes ; les deux tables y cohabitent."""
    chemin = tmp_path / "historique.sqlite"
    historique = Historique(chemin)
    stats = StatsLuminosite(chemin)
    await historique.enregistrer(None, "picture", "backlight", 40, 50, "vivid", "panneau")
    await stats.enregistrer(LUX, [jour("2026-10-25")])
    assert len(await historique.lister()) == 1
    assert len(await stats.charger(LUX, "2026-10-01")) == 1


async def test_rapport_des_capteurs_par_paire(tmp_path):
    stats = StatsLuminosite(tmp_path / "historique.sqlite")
    assert await stats.charger_rapport(LUX, AUTRE) == []
    await stats.enregistrer_rapport(LUX, AUTRE, [[0, 100, 50], [60, 100, 50]])
    await stats.enregistrer_rapport(LUX, AUTRE, [[0, 100, 50], [60, 100, 50], [120, 90, 45]])
    await stats.enregistrer_rapport(AUTRE, LUX, [[0, 50, 100]])
    assert await stats.charger_rapport(LUX, AUTRE) == [[0, 100, 50], [60, 100, 50],
                                                       [120, 90, 45]]
    assert await stats.charger_rapport(AUTRE, LUX) == [[0, 50, 100]]
