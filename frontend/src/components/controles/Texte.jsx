import { useEffect, useState } from 'react'

export default function Texte({ valeur, ecriture, onEcrire }) {
  const [local, setLocal] = useState(valeur ?? '')

  // Une valeur changée sur la TV (ou ailleurs dans HA) remplace la saisie affichée.
  useEffect(() => {
    setLocal(valeur ?? '')
  }, [valeur])

  if (valeur === undefined) return <span className="valeur-en-attente">…</span>

  if (!ecriture) {
    return <span className="valeur-lecture-seule">{String(valeur)}</span>
  }

  function valider() {
    if (local !== valeur) onEcrire(local)
  }

  return (
    <input
      type="text"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={valider}
      onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
    />
  )
}
