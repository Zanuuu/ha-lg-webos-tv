// Recherche d'un réglage dans l'arbre du menu, insensible à la casse et aux
// accents (« cinema » trouve « Cinéma »).

const LONGUEUR_MINIMALE = 2
const RESULTATS_MAX = 50

export function normaliser(texte) {
  return (texte || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

// Toutes les entrées sous les sections, avec leur chemin (de la section au
// parent) et les textes normalisés une fois pour toutes.
export function aplatir(arbre) {
  const entrees = []
  function visiter(entree, chemin) {
    entrees.push({
      entree,
      chemin,
      libelle: normaliser(entree.libelle),
      contexte: normaliser([
        entree.libelle,
        ...chemin.map((n) => n.libelle),
        ...(entree.choix || []).map((c) => c.libelle),
      ].join(' ')),
      description: normaliser(entree.description),
    })
    for (const enfant of entree.enfants || []) visiter(enfant, [...chemin, entree])
  }
  for (const section of arbre?.sections || []) {
    for (const enfant of section.enfants || []) visiter(enfant, [section])
  }
  return entrees
}

export function requeteSuffisante(requete) {
  return normaliser(requete).trim().length >= LONGUEUR_MINIMALE
}

// Tous les mots doivent être trouvés. Ordre : libellé, puis libellé avec
// ancêtres et choix (« cinema » trouve Mode d'image), puis description ;
// l'ordre du menu est conservé à rang égal.
export function rechercher(entrees, requete) {
  if (!requeteSuffisante(requete)) return []
  const mots = normaliser(requete).split(/\s+/).filter(Boolean)
  const contient = (texte) => mots.every((mot) => texte.includes(mot))
  const rangs = [[], [], []]
  for (const e of entrees) {
    if (contient(e.libelle)) rangs[0].push(e)
    else if (contient(e.contexte)) rangs[1].push(e)
    else if (contient(`${e.contexte} ${e.description}`)) rangs[2].push(e)
  }
  return rangs.flat().slice(0, RESULTATS_MAX)
}
