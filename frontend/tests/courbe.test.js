// Copie JavaScript de la courbe alignée sur l'intégration : mêmes vecteurs
// que tests/test_courbe.py.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { calculerCible, validerOptions } from '../src/luminosite.js'

const vecteurs = JSON.parse(readFileSync(new URL('../../tests/vecteurs_courbe.json', import.meta.url)))

for (const cas of vecteurs.cibles) {
  test(`cible : ${cas.nom}`, () => {
    assert.equal(calculerCible(cas.lux, cas.options), cas.cible)
  })
}

for (const cas of vecteurs.validation) {
  test(`validation : ${cas.nom}`, () => {
    assert.deepEqual(Object.keys(validerOptions(cas.options)).sort(), cas.erreurs)
  })
}
