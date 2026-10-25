import { EMPLACEMENTS } from '../luminosite.js'

// Pièce vue de dessus : téléviseur contre le mur du haut, canapé en bas,
// fenêtre à gauche, extérieur à droite. Formes simples, sans dessin LG.
// Repère : (x, y) du marqueur, et flèche éventuelle (sens de la mesure).
const MARQUEURS = [
  { cle: 'a', x: 82, y: 40, fleche: 'bas' },
  { cle: 'a', x: 198, y: 40, fleche: 'bas' },
  { cle: 'b', x: 140, y: 27 },
  { cle: 'c', x: 140, y: 105, plafond: true },
  { cle: 'd', x: 118, y: 172, fleche: 'haut' },
  { cle: 'e', x: 162, y: 172, plafond: true },
  { cle: 'f', x: 42, y: 145 },
  { cle: 'g', x: 292, y: 120 },
]

function Fleche({ x, y, sens }) {
  const dy = sens === 'bas' ? 1 : -1
  const pointe = y + dy * 26
  return (
    <path
      className="fleche-schema"
      d={`M ${x} ${y + dy * 13} L ${x} ${pointe} M ${x - 4} ${pointe - dy * 5} L ${x} ${pointe} L ${x + 4} ${pointe - dy * 5}`}
    />
  )
}

export default function SchemaEmplacement({ choisi, onChoisir, desactive }) {
  return (
    <figure className="schema-emplacement">
      <svg viewBox="0 0 320 236" role="img"
        aria-label="Emplacements possibles du capteur, pièce vue de dessus">
        <rect className="piece-schema" x="20" y="16" width="240" height="204" rx="4" />
        <line className="fenetre-schema" x1="20" y1="122" x2="20" y2="170" />
        <text className="legende-schema" x="28" y="118">fenêtre</text>
        <rect className="tv-schema" x="100" y="33" width="80" height="6" rx="1" />
        <text className="legende-schema" x="140" y="54" textAnchor="middle">téléviseur</text>
        <rect className="canape-schema" x="92" y="190" width="96" height="20" rx="5" />
        <text className="legende-schema" x="140" y="204" textAnchor="middle">canapé</text>
        <text className="legende-schema" x="292" y="150" textAnchor="middle">extérieur</text>
        {MARQUEURS.map((m, i) => {
          const actif = m.cle === choisi
          const deconseille = EMPLACEMENTS[m.cle].avertissement
          return (
            <g
              key={`${m.cle}-${i}`}
              className={`marqueur-schema${actif ? ' marqueur-choisi' : ''}${deconseille ? ' marqueur-deconseille' : ''}`}
              onClick={desactive ? undefined : () => onChoisir(m.cle)}
            >
              <title>{EMPLACEMENTS[m.cle].libelle}</title>
              {m.fleche && <Fleche x={m.x} y={m.y} sens={m.fleche} />}
              {m.plafond && <circle className="plafond-schema" cx={m.x} cy={m.y} r="15" />}
              <circle cx={m.x} cy={m.y} r="10" />
              <text x={m.x} y={m.y + 4} textAnchor="middle">{m.cle.toUpperCase()}</text>
            </g>
          )
        })}
      </svg>
      <figcaption className="texte-attenue">
        Flèche : sens de la mesure. Cercle pointillé : capteur tourné vers le plafond.
      </figcaption>
    </figure>
  )
}
