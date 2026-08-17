import { useEffect, useRef, useState } from 'react'

const DELAI_ENVOI_MS = 300

export default function Curseur({ entree, valeur, onEcrire }) {
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

  return (
    <div className="controle-curseur">
      <input
        type="range"
        min={bornes.min}
        max={bornes.max}
        step={bornes.pas || 1}
        value={local}
        onChange={(e) => changer(e.target.value)}
      />
      <span className="valeur-curseur">{local}</span>
    </div>
  )
}
