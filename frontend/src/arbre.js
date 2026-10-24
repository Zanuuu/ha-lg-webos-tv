export function indexerParId(arbre) {
  const index = new Map()
  function visiter(entree) {
    index.set(entree.id, entree)
    for (const enfant of entree.enfants || []) visiter(enfant)
  }
  for (const section of arbre?.sections || []) visiter(section)
  return index
}

export function estPilotable(api) {
  return Boolean(api && api.acces === 'lecture_ecriture' && api.cle && !api.cle.includes('<'))
}

export function estLisible(api) {
  return Boolean(
    api &&
      (api.acces === 'lecture_ecriture' || api.acces === 'lecture_seule') &&
      api.cle &&
      !api.cle.includes('<'),
  )
}

export function valeurDe(reglages, api) {
  if (!estLisible(api)) return undefined
  return reglages?.[api.categorie]?.[api.cle]
}

export function libelleChoix(entree, valeurApi) {
  const choix = (entree.choix || []).find((c) => c.valeur_api === valeurApi)
  return choix ? choix.libelle : undefined
}
