"""Corrections de la luminosité adaptative en SQLite : par capteur, purge,
oubli, mise à l'écart."""

import time

from custom_components.lg_webos_tv.corrections import CorrectionsLuminosite
from custom_components.lg_webos_tv.reprise import CORRECTIONS_MAX, Correction

JOUR = 86400


def correction(horodatage, lux=2.0):
    return Correction(horodatage=horodatage, lux=lux, valeur=48, cible=40,
                      mode_image="vivid", origine="manuel")


async def test_ajout_et_lecture_par_capteur(tmp_path):
    base = CorrectionsLuminosite(tmp_path / "historique.sqlite")
    id_ = await base.ajouter("sensor.a", correction(2))
    await base.ajouter("sensor.a", correction(1, lux=300))
    await base.ajouter("sensor.b", correction(3))
    lues = await base.charger("sensor.a")
    assert [c.horodatage for c in lues] == [1, 2]
    assert lues[1] == Correction(horodatage=2, lux=2.0, valeur=48, cible=40,
                                 mode_image="vivid", origine="manuel", id=id_)
    assert len(await base.charger("sensor.b")) == 1


async def test_oubli_et_mise_a_l_ecart(tmp_path):
    base = CorrectionsLuminosite(tmp_path / "historique.sqlite")
    ids = [await base.ajouter("sensor.a", correction(t)) for t in range(3)]
    assert await base.oublier(ids[0])
    assert not await base.oublier(ids[0])
    await base.ecarter(ids[1:2])
    assert [(c.id, c.ecartee) for c in await base.charger("sensor.a")] == [
        (ids[1], True), (ids[2], False)]


async def test_purge_apres_un_an(tmp_path):
    base = CorrectionsLuminosite(tmp_path / "historique.sqlite")
    maintenant = time.time()
    await base.ajouter("sensor.a", correction(maintenant - 366 * JOUR))
    await base.ajouter("sensor.a", correction(maintenant - 364 * JOUR))
    assert await base.purger(maintenant) == 1
    assert len(await base.charger("sensor.a")) == 1


async def test_purge_au_dela_de_500_tous_capteurs_confondus(tmp_path):
    base = CorrectionsLuminosite(tmp_path / "historique.sqlite")
    maintenant = time.time()
    for i in range(CORRECTIONS_MAX + 5):
        await base.ajouter("sensor.a" if i % 2 else "sensor.b", correction(maintenant - i))
    assert await base.purger(maintenant) == 5
    restantes = await base.charger("sensor.a") + await base.charger("sensor.b")
    assert len(restantes) == CORRECTIONS_MAX
    # Les plus anciennes sont parties.
    assert min(c.horodatage for c in restantes) == maintenant - (CORRECTIONS_MAX - 1)


async def test_meme_fichier_que_l_historique(tmp_path):
    from custom_components.lg_webos_tv.historique import Historique
    from custom_components.lg_webos_tv.statistiques import StatsLuminosite

    chemin = tmp_path / "historique.sqlite"
    Historique(chemin)
    StatsLuminosite(chemin)
    base = CorrectionsLuminosite(chemin)
    await base.ajouter("sensor.a", correction(1))
    assert len(await base.charger("sensor.a")) == 1


async def test_decalage_enregistre(tmp_path):
    base = CorrectionsLuminosite(tmp_path / "historique.sqlite")
    await base.ajouter("sensor.a", Correction(horodatage=1, lux=2.0, valeur=38, cible=30,
                                              mode_image="vivid", origine="manuel",
                                              decalage=-10))
    [lue] = await base.charger("sensor.a")
    assert lue.decalage == -10


async def test_base_2_9_0_sans_colonne_decalage(tmp_path):
    """Base créée par la 2.9.0 : la colonne est ajoutée, les corrections
    existantes valent pour un décalage nul."""
    import sqlite3
    chemin = tmp_path / "historique.sqlite"
    with sqlite3.connect(chemin) as co:
        co.executescript("""
            CREATE TABLE corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT, horodatage REAL NOT NULL,
                capteur TEXT NOT NULL, lux REAL NOT NULL, valeur INTEGER NOT NULL,
                cible INTEGER NOT NULL, mode_image TEXT, origine TEXT,
                ecartee INTEGER NOT NULL DEFAULT 0);
            INSERT INTO corrections (horodatage, capteur, lux, valeur, cible, mode_image, origine)
                VALUES (1, 'sensor.a', 2.0, 48, 40, 'vivid', 'manuel');
        """)
    base = CorrectionsLuminosite(chemin)
    [lue] = await base.charger("sensor.a")
    assert (lue.valeur, lue.decalage) == (48, 0)
    await base.ajouter("sensor.a", correction(2))
    assert len(await base.charger("sensor.a")) == 2
    # Une seconde ouverture ne réessaie pas d'ajouter la colonne.
    CorrectionsLuminosite(chemin)
