import { useEffect, useRef, useState } from 'react'

const DELAI_ENVOI_MS = 300

export default function Curseur({ entree, valeur, ecriture = true, onEcrire }) {
  const bornes = entree.bornes || { min: 0, max: 100, pas: 1 }
  const [local, setLocal] = useState(valeur)
  const minuteur = useRef(null)

  useEffect(() => {
    setLocal(valeur)
  }, [valeur])

  if (valeur === undefined) return <span className="valeur-en-attente">…</span>

  function changer(v) {
    const nombre = Number(v)
    setLocal(nombre)
    clearTimeout(minuteur.current)
    minuteur.current = setTimeout(() => onEcrire(nombre), DELAI_ENVOI_MS)
  }

  // Alimente le remplissage de la piste (WebKit n'a pas d'équivalent à ::-moz-range-progress).
  const etendue = bornes.max - bornes.min
  const remplissage = etendue > 0 ? ((local - bornes.min) / etendue) * 100 : 0

  return (
    <div className="controle-curseur" style={{ '--remplissage': `${remplissage}%` }}>
      <input
        type="range"
        min={bornes.min}
        max={bornes.max}
        step={bornes.pas || 1}
        value={local}
        aria-label={entree.libelle}
        disabled={!ecriture}
        onChange={(e) => changer(e.target.value)}
      />
      <span className="valeur-curseur" aria-hidden="true">{local}</span>
    </div>
  )
}
