import { useRef } from 'react'
import { BORNES, calculerCible } from '../luminosite.js'

// Repère du graphique (unités du viewBox) : marges pour les graduations.
const LARGEUR = 640
const HAUTEUR = 300
// Bas et gauche : graduations, agrandies sur téléphone (App.css).
const MARGE = { haut: 20, droite: 20, bas: 48, gauche: 56 }
const X0 = MARGE.gauche
const X1 = LARGEUR - MARGE.droite
const Y0 = HAUTEUR - MARGE.bas
const Y1 = MARGE.haut
const GRADUATIONS_LUMINOSITE = [0, 25, 50, 75, 100]

const borner = (v, bas, haut) => Math.min(Math.max(v, bas), haut)

function formaterLux(lux) {
  return `${lux.toLocaleString('fr-FR')} lx`
}

// La courbe de la fonction est une droite sur le logarithme du lux : axe des
// lux logarithmique, du lux 1 à la décade qui contient le plus grand des
// repères (pièce lumineuse, mesure actuelle), avec de la marge.
function domaineLux(options, lux) {
  const plusGrand = Math.max(options.lux_max, lux ?? 0) * 1.5
  return 10 ** Math.max(3, Math.ceil(Math.log10(plusGrand)))
}

export default function CourbeLuminosite({ options, lux, desactive, onChanger }) {
  const svgRef = useRef(null)
  const luxFin = domaineLux(options, lux)
  const xDeLux = (l) => X0 + (Math.log10(borner(l, 1, luxFin)) / Math.log10(luxFin)) * (X1 - X0)
  const luxDeX = (x) => 10 ** (((borner(x, X0, X1) - X0) / (X1 - X0)) * Math.log10(luxFin))
  const yDeLum = (v) => Y0 - (v / 100) * (Y0 - Y1)
  const lumDeY = (y) => ((Y0 - borner(y, Y1, Y0)) / (Y0 - Y1)) * 100

  const decades = []
  for (let l = 1; l <= luxFin; l *= 10) decades.push(l)

  const bas = { x: xDeLux(options.lux_min), y: yDeLum(options.luminosite_min) }
  const haut = { x: xDeLux(options.lux_max), y: yDeLum(options.luminosite_max) }
  const trace = `M ${X0} ${bas.y} L ${bas.x} ${bas.y} L ${haut.x} ${haut.y} L ${X1} ${haut.y}`

  const cible = lux !== null && lux !== undefined ? calculerCible(lux, options) : null
  const maintenant = cible !== null ? { x: xDeLux(Math.max(lux, 1)), y: yDeLum(cible) } : null

  // Chaque poignée reste de son côté de l'autre : pièce sombre sous pièce
  // lumineuse, luminosité minimale sous la maximale.
  function deplacer(poignee, luxVoulu, lumVoulue) {
    if (poignee === 'bas') {
      onChanger({
        lux_min: borner(Math.round(luxVoulu), BORNES.lux_min[0],
          Math.min(BORNES.lux_min[1], options.lux_max - 1)),
        luminosite_min: borner(Math.round(lumVoulue), 0, options.luminosite_max),
      })
    } else {
      onChanger({
        lux_max: borner(Math.round(luxVoulu), Math.max(BORNES.lux_max[0], options.lux_min + 1),
          BORNES.lux_max[1]),
        luminosite_max: borner(Math.round(lumVoulue), options.luminosite_min, 100),
      })
    }
  }

  function pointSvg(e) {
    const point = svgRef.current.createSVGPoint()
    point.x = e.clientX
    point.y = e.clientY
    return point.matrixTransform(svgRef.current.getScreenCTM().inverse())
  }

  function commencerGlisser(e) {
    if (desactive) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    e.currentTarget.focus()
  }

  function glisser(poignee) {
    return (e) => {
      if (desactive || !e.currentTarget.hasPointerCapture(e.pointerId)) return
      const { x, y } = pointSvg(e)
      deplacer(poignee, luxDeX(x), lumDeY(y))
    }
  }

  // Flèches gauche / droite : lux par pas de 10 % (au moins 1) ; haut / bas :
  // luminosité par pas de 1.
  function touche(poignee) {
    return (e) => {
      const lux0 = poignee === 'bas' ? options.lux_min : options.lux_max
      const lum0 = poignee === 'bas' ? options.luminosite_min : options.luminosite_max
      const pas = Math.max(1, Math.round(lux0 * 0.1))
      const deplacements = {
        ArrowLeft: [lux0 - pas, lum0],
        ArrowRight: [lux0 + pas, lum0],
        ArrowDown: [lux0, lum0 - 1],
        ArrowUp: [lux0, lum0 + 1],
      }
      if (desactive || !(e.key in deplacements)) return
      e.preventDefault()
      deplacer(poignee, ...deplacements[e.key])
    }
  }

  function poignee(id, point, libelle, luxP, lumP) {
    return (
      <g
        className="poignee-courbe"
        role="slider"
        tabIndex={desactive ? -1 : 0}
        aria-label={libelle}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={lumP}
        aria-valuetext={`${formaterLux(luxP)}, luminosité ${lumP}`}
        aria-disabled={desactive || undefined}
        onPointerDown={commencerGlisser}
        onPointerMove={glisser(id)}
        onKeyDown={touche(id)}
      >
        {/* Cible tactile élargie, invisible. */}
        <circle cx={point.x} cy={point.y} r="22" className="zone-poignee" />
        <circle cx={point.x} cy={point.y} r="8" className="disque-poignee" />
      </g>
    )
  }

  return (
    <figure className="courbe-luminosite">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${LARGEUR} ${HAUTEUR}`}
        role="group"
        aria-label="Courbe de la luminosité selon la lumière ambiante"
      >
        {GRADUATIONS_LUMINOSITE.map((v) => (
          <g key={`y${v}`}>
            <line x1={X0} x2={X1} y1={yDeLum(v)} y2={yDeLum(v)} className="grille-courbe" />
            <text x={X0 - 8} y={yDeLum(v)} className="graduation-courbe" textAnchor="end"
              dominantBaseline="middle">
              {v}
            </text>
          </g>
        ))}
        {decades.map((l, i) => (
          <g key={`x${l}`}>
            <line x1={xDeLux(l)} x2={xDeLux(l)} y1={Y1} y2={Y0} className="grille-courbe" />
            {/* Extrêmes alignés vers l'intérieur : la première graduation ne
                touche pas le « 0 » de l'axe vertical, la dernière ne sort pas. */}
            <text x={xDeLux(l)} y={Y0 + 22} className="graduation-courbe"
              textAnchor={i === 0 ? 'start' : i === decades.length - 1 ? 'end' : 'middle'}>
              {formaterLux(l)}
            </text>
          </g>
        ))}
        <path d={trace} className="trace-courbe" />
        {maintenant && (
          <g className="point-maintenant">
            <line x1={maintenant.x} x2={maintenant.x} y1={Y0} y2={maintenant.y} />
            <circle cx={maintenant.x} cy={maintenant.y} r="6" />
          </g>
        )}
        {poignee('bas', bas, 'Pièce sombre et luminosité minimale', options.lux_min,
          options.luminosite_min)}
        {poignee('haut', haut, 'Pièce lumineuse et luminosité maximale', options.lux_max,
          options.luminosite_max)}
      </svg>
      <figcaption className="texte-attenue">
        {maintenant
          ? `Maintenant : ${formaterLux(Math.round(lux * 10) / 10)} → luminosité ${cible}`
          : 'Mesure du capteur indisponible'}
        {' · '}faites glisser les deux points, ou utilisez les flèches du clavier.
      </figcaption>
    </figure>
  )
}
