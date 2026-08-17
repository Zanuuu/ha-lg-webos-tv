export default function Interrupteur({ valeur, onEcrire }) {
  if (valeur === undefined) return <span className="valeur-en-attente">…</span>

  const actif = valeur === 'on' || valeur === true

  return (
    <button
      type="button"
      role="switch"
      aria-checked={actif}
      className={`interrupteur${actif ? ' interrupteur-actif' : ''}`}
      onClick={() => onEcrire(!actif)}
    >
      <span className="interrupteur-curseur" />
    </button>
  )
}
