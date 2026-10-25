import { useMemo } from 'react'
import { rechercher, requeteSuffisante } from '../recherche.js'
import LigneReglage from './LigneReglage.jsx'

export default function VueRecherche({
  entrees, requete, reglages, lectureSeule, horsLigne, luminosite, onEcrire, onReprendre,
  onDetailsLuminosite, onOuvrir,
}) {
  const resultats = useMemo(() => rechercher(entrees, requete), [entrees, requete])
  const suffisante = requeteSuffisante(requete)

  let annonce = 'Saisissez au moins 2 caractères.'
  if (suffisante) {
    annonce = resultats.length === 0
      ? `Aucun réglage ne correspond à « ${requete.trim()} ».`
      : `${resultats.length} réglage${resultats.length > 1 ? 's' : ''} trouvé${resultats.length > 1 ? 's' : ''}`
  }

  return (
    <section className="panneau-menu" aria-labelledby="titre-recherche">
      <h2 id="titre-recherche" className="titre-noeud">Recherche</h2>
      <p className="texte-attenue resultats-recherche" role="status">{annonce}</p>
      <div className="liste-reglages">
        {resultats.map(({ entree, chemin }) => (
          <div key={entree.id} className="resultat-recherche">
            <button
              type="button"
              className="chemin-resultat"
              title="Ouvrir dans le menu"
              onClick={() => onOuvrir(chemin, entree.id)}
            >
              {chemin.map((n) => n.libelle).join(' › ')}
            </button>
            <LigneReglage
              entree={entree}
              reglages={reglages}
              lectureSeule={lectureSeule}
              horsLigne={horsLigne}
              luminosite={luminosite}
              onEcrire={onEcrire}
              onReprendre={onReprendre}
              onDetailsLuminosite={onDetailsLuminosite}
              onEntrer={(sousMenu) => onOuvrir([...chemin, sousMenu])}
            />
          </div>
        ))}
      </div>
    </section>
  )
}
