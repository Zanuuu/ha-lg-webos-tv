"""File d'écriture coalescente."""

import asyncio

import pytest

from custom_components.lg_webos_tv.ecritures import FileEcritures


class EcritureLente:
    def __init__(self):
        self.appels = []
        self.liberer = asyncio.Event()

    async def __call__(self, entree_id, valeur):
        self.appels.append((entree_id, valeur))
        await self.liberer.wait()
        return {"ok": True, "entree_id": entree_id, "nouvelle": valeur}


async def test_derniere_valeur_gagnante_pendant_une_ecriture():
    ecrire = EcritureLente()
    file = FileEcritures(ecrire)
    premiere = asyncio.create_task(file.demander("a", 1))
    await asyncio.sleep(0)
    # Pendant l'écriture de 1, deux demandes pour la même entrée : seule la
    # dernière sera envoyée.
    deuxieme = asyncio.create_task(file.demander("a", 2))
    troisieme = asyncio.create_task(file.demander("a", 3))
    await asyncio.sleep(0)
    ecrire.liberer.set()
    resultats = await asyncio.gather(premiere, deuxieme, troisieme)
    assert ecrire.appels == [("a", 1), ("a", 3)]
    assert [r["nouvelle"] for r in resultats] == [1, 3, 3]


async def test_entrees_differentes_dans_l_ordre():
    ecrire = EcritureLente()
    ecrire.liberer.set()
    file = FileEcritures(ecrire)
    await asyncio.gather(file.demander("a", 1), file.demander("b", 2), file.demander("a", 3))
    assert ecrire.appels == [("a", 3), ("b", 2)]


async def test_erreur_transmise_et_file_continue():
    async def ecrire(entree_id, valeur):
        if entree_id == "mauvaise":
            raise ValueError("invalide")
        return {"ok": True}

    file = FileEcritures(ecrire)
    with pytest.raises(ValueError):
        await file.demander("mauvaise", 1)
    assert await file.demander("bonne", 1) == {"ok": True}


async def test_arreter_annule_les_demandes():
    ecrire = EcritureLente()
    file = FileEcritures(ecrire)
    demande = asyncio.create_task(file.demander("a", 1))
    await asyncio.sleep(0)
    await file.arreter()
    with pytest.raises(asyncio.CancelledError):
        await demande
