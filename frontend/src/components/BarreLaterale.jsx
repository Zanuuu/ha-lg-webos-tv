const VUES_SERVICE = [
  { id: 'presets', libelle: 'Presets' },
  { id: 'historique', libelle: 'Historique' },
]

export default function BarreLaterale({ sections, vue, sectionActiveId, onChoisirSection, onChoisirVue }) {
  function bouton(id, libelle, actif, onClick) {
    return (
      <button
        key={id}
        type="button"
        className={`section-nav${actif ? ' section-nav-active' : ''}`}
        aria-current={actif ? 'page' : undefined}
        onClick={onClick}
      >
        {libelle}
      </button>
    )
  }

  return (
    <nav className="barre-laterale" aria-label="Sections">
      {sections.map((section) =>
        bouton(section.id, section.libelle, vue === 'menu' && section.id === sectionActiveId,
          () => onChoisirSection(section)))}
      <hr className="separateur-nav" />
      {VUES_SERVICE.map(({ id, libelle }) =>
        bouton(id, libelle, vue === id, () => onChoisirVue(id)))}
    </nav>
  )
}
