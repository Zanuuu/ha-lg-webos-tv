import LigneReglage from './LigneReglage.jsx'

export default function PanneauMenu({ chemin, reglages, onEcrire, onEntrer, onRevenir }) {
  const noeud = chemin[chemin.length - 1]

  return (
    <section className="panneau-menu">
      <FilAriane chemin={chemin} onRevenir={onRevenir} />
      <div className="liste-reglages">
        {(noeud.enfants || []).map((enfant) => (
          <LigneReglage
            key={enfant.id}
            entree={enfant}
            reglages={reglages}
            onEcrire={onEcrire}
            onEntrer={onEntrer}
          />
        ))}
      </div>
    </section>
  )
}

function FilAriane({ chemin, onRevenir }) {
  return (
    <div className="fil-ariane">
      {chemin.map((noeud, i) => (
        <span key={noeud.id}>
          {i > 0 && <span className="separateur-ariane">›</span>}
          {i === chemin.length - 1 ? (
            <span className="miette-courante">{noeud.libelle}</span>
          ) : (
            <button type="button" className="miette" onClick={() => onRevenir(i)}>
              {noeud.libelle}
            </button>
          )}
        </span>
      ))}
    </div>
  )
}
