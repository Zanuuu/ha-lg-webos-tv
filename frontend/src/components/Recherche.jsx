export default function Recherche({ requete, champRef, onChanger }) {
  function surTouche(e) {
    if (e.key === 'Escape' && requete) {
      // Le champ seul est vidé : Échap ne remonte pas aussi dans le menu.
      e.preventDefault()
      onChanger('')
    }
  }

  return (
    <div className="recherche" role="search">
      <label htmlFor="champ-recherche" className="visuellement-masque">Rechercher un réglage</label>
      <input
        id="champ-recherche"
        ref={champRef}
        type="search"
        placeholder="Rechercher un réglage"
        title="Rechercher un réglage (/)"
        autoComplete="off"
        spellCheck={false}
        value={requete}
        onChange={(e) => onChanger(e.target.value)}
        onKeyDown={surTouche}
      />
    </div>
  )
}
