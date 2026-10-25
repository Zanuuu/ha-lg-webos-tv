import { useEffect, useId, useRef } from 'react'

// Dialogue modal natif : focus piégé, Échap et arrière-plan inerte fournis
// par le navigateur. Monté à la demande par le parent, ouvert au montage.
export default function Confirmation({
  titre, children, libelleAction, danger = false, occupe = false, onConfirmer, onAnnuler,
}) {
  const ref = useRef(null)
  const idTitre = useId()

  useEffect(() => {
    const dialogue = ref.current
    if (!dialogue.open) dialogue.showModal()
    return () => dialogue.close()
  }, [])

  return (
    <dialog
      ref={ref}
      className="confirmation"
      aria-labelledby={idTitre}
      onCancel={(e) => {
        // Échap : c'est le parent qui démonte le dialogue.
        e.preventDefault()
        if (!occupe) onAnnuler()
      }}
    >
      <h3 id={idTitre}>{titre}</h3>
      <div className="confirmation-corps">{children}</div>
      <div className="confirmation-actions">
        <button type="button" className="bouton-secondaire" onClick={onAnnuler} disabled={occupe}>
          Annuler
        </button>
        <button
          type="button"
          className={danger ? 'bouton-danger-plein' : 'bouton-principal'}
          onClick={onConfirmer}
          disabled={occupe}
        >
          {occupe ? 'En cours…' : libelleAction}
        </button>
      </div>
    </dialog>
  )
}
