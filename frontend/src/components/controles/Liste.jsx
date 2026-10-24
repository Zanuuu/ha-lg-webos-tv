import { libelleChoix } from '../../arbre.js'

export default function Liste({ entree, valeur, ecriture, onEcrire }) {
  const choix = (entree.choix || []).filter((c) => c.valeur_api !== undefined)

  if (valeur === undefined) return <span className="valeur-en-attente">…</span>

  if (!ecriture || choix.length === 0) {
    return (
      <span className="valeur-lecture-seule" title="Lecture seule">
        {libelleChoix(entree, valeur) || String(valeur)}
      </span>
    )
  }

  return (
    <select value={valeur} onChange={(e) => onEcrire(e.target.value)}>
      {!choix.some((c) => c.valeur_api === valeur) && (
        <option value={valeur}>{String(valeur)}</option>
      )}
      {choix.map((c) => (
        <option key={c.valeur_api} value={c.valeur_api}>
          {c.libelle}
        </option>
      ))}
    </select>
  )
}
