export default function BarreLaterale({ sections, sectionActiveId, onChoisir }) {
  return (
    <nav className="barre-laterale">
      {sections.map((section) => (
        <button
          key={section.id}
          type="button"
          className={`section-nav${section.id === sectionActiveId ? ' section-nav-active' : ''}`}
          onClick={() => onChoisir(section)}
        >
          {section.libelle}
        </button>
      ))}
    </nav>
  )
}
