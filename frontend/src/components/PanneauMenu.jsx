import LigneReglage from './LigneReglage.jsx'

export default function PanneauMenu({
  chemin, reglages, lectureSeule, horsLigne, luminosite, entreeRevelee, titreRef, onEcrire,
  onReprendre, onDetailsLuminosite, onEntrer, onRevenir,
}) {
  const noeud = chemin[chemin.length - 1]
  const parent = chemin.length > 1 ? chemin[chemin.length - 2] : null

  return (
    <section className="panneau-menu" aria-labelledby="titre-noeud">
      {/* À la racine d'une section, le fil ne ferait que répéter le titre. */}
      {parent && <FilAriane chemin={chemin} onRevenir={onRevenir} />}
      <div className="entete-noeud">
        {parent && (
          <button
            type="button"
            className="bouton-retour"
            aria-label={`Revenir à ${parent.libelle}`}
            title="Revenir (Échap)"
            onClick={() => onRevenir(chemin.length - 2)}
          >
            ‹
          </button>
        )}
        <h2 id="titre-noeud" className="titre-noeud" ref={titreRef} tabIndex={-1}>
          {noeud.libelle}
        </h2>
      </div>
      <div className="liste-reglages">
        {(noeud.enfants || []).map((enfant) => (
          <LigneReglage
            key={enfant.id}
            entree={enfant}
            reglages={reglages}
            lectureSeule={lectureSeule}
            horsLigne={horsLigne}
            luminosite={luminosite}
            revelee={enfant.id === entreeRevelee}
            onEcrire={onEcrire}
            onReprendre={onReprendre}
            onDetailsLuminosite={onDetailsLuminosite}
            onEntrer={onEntrer}
          />
        ))}
      </div>
    </section>
  )
}

function FilAriane({ chemin, onRevenir }) {
  return (
    <nav className="fil-ariane" aria-label="Fil d'Ariane">
      {chemin.map((noeud, i) => (
        <span key={noeud.id}>
          {i > 0 && <span className="separateur-ariane" aria-hidden="true">›</span>}
          {i === chemin.length - 1 ? (
            <span className="miette-courante" aria-current="location">{noeud.libelle}</span>
          ) : (
            <button type="button" className="miette" onClick={() => onRevenir(i)}>
              {noeud.libelle}
            </button>
          )}
        </span>
      ))}
    </nav>
  )
}
