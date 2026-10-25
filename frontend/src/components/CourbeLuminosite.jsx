import { useRef } from 'react'
import { arrondirLux, BORNES, calculerCible, pointsCourbe } from '../luminosite.js'

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

// La courbe de la fonction est faite de segments sur le logarithme du lux :
// axe des lux logarithmique, du lux 1 à la décade qui contient le plus grand des
// repères (pièce lumineuse, mesure actuelle), avec de la marge.
function domaineLux(options, lux) {
  const plusGrand = Math.max(options.lux_max, lux ?? 0) * 1.5
  return 10 ** Math.max(3, Math.ceil(Math.log10(plusGrand)))
}

function libelleCorrection(c) {
  const date = new Date(c.horodatage).toLocaleString('fr-FR', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const ecart = c.ecart > 0 ? `+${c.ecart}` : `${c.ecart}`
  return `Correction du ${date} : luminosité ${c.valeur} à ${formaterLux(c.lux)} `
    + `(courbe ${ecart})${c.ecartee ? ', écartée des suggestions' : ''}`
}

// `ancrages` : points d'ancrage de la mise en route, affichés en losanges ;
// `corrections` : réglages manuels retenus, en points ; `apercu` : options
// d'une courbe suggérée, tracée en pointillé. Sans `onChanger`, la courbe est
// un aperçu, sans poignées.
export default function CourbeLuminosite({ options, lux, ancrages = [], corrections = [],
  apercu = null, desactive, onChanger }) {
  const svgRef = useRef(null)
  const luxFin = domaineLux(options, lux)
  const xDeLux = (l) => X0 + (Math.log10(borner(l, 1, luxFin)) / Math.log10(luxFin)) * (X1 - X0)
  const luxDeX = (x) => 10 ** (((borner(x, X0, X1) - X0) / (X1 - X0)) * Math.log10(luxFin))
  const yDeLum = (v) => Y0 - (v / 100) * (Y0 - Y1)
  const lumDeY = (y) => ((Y0 - borner(y, Y1, Y0)) / (Y0 - Y1)) * 100

  const decades = []
  for (let l = 1; l <= luxFin; l *= 10) decades.push(l)

  // Plate au-delà des extrémités, jusqu'aux bords du graphique.
  function tracer(opts) {
    const pts = pointsCourbe(opts).map(([l, v]) => ({ x: xDeLux(l), y: yDeLum(v) }))
    return `M ${X0} ${pts[0].y} ${pts.map((p) => `L ${p.x} ${p.y}`).join(' ')} `
      + `L ${X1} ${pts[pts.length - 1].y}`
  }
  const points = pointsCourbe(options).map(([l, v]) => ({ x: xDeLux(l), y: yDeLum(v) }))
  const premier = points[0]
  const dernier = points[points.length - 1]
  const trace = tracer(options)

  const cible = lux !== null && lux !== undefined ? calculerCible(lux, options) : null
  const maintenant = cible !== null ? { x: xDeLux(Math.max(lux, 1)), y: yDeLum(cible) } : null
  const milieu = options.point_intermediaire

  // Chaque poignée reste entre ses voisines, en lux (au moins un dixième
  // d'écart) comme en luminosité : la courbe reste monotone.
  function deplacer(poignee, luxVoulu, lumVoulue) {
    const voisins = pointsCourbe(options)
    if (poignee === 'bas') {
      const [luxSuivant, lumSuivante] = voisins[1]
      onChanger({
        lux_min: borner(arrondirLux(luxVoulu), BORNES.lux_min[0],
          Math.min(BORNES.lux_min[1], arrondirLux(luxSuivant - 0.1))),
        luminosite_min: borner(Math.round(lumVoulue), 0, lumSuivante),
      })
    } else if (poignee === 'milieu') {
      onChanger({
        point_intermediaire: [
          borner(arrondirLux(luxVoulu), arrondirLux(options.lux_min + 0.1),
            arrondirLux(options.lux_max - 0.1)),
          borner(Math.round(lumVoulue), options.luminosite_min, options.luminosite_max),
        ],
      })
    } else {
      const [luxPrecedent, lumPrecedente] = voisins[voisins.length - 2]
      onChanger({
        lux_max: borner(arrondirLux(luxVoulu),
          Math.max(BORNES.lux_max[0], arrondirLux(luxPrecedent + 0.1)), BORNES.lux_max[1]),
        luminosite_max: borner(Math.round(lumVoulue), lumPrecedente, 100),
      })
    }
  }

  // Posé sur la courbe, au milieu des extrémités en ln(lux) : la luminosité
  // calculée ne change pas tant qu'on ne le déplace pas.
  function ajouterMilieu() {
    const luxMilieu = arrondirLux(Math.sqrt(options.lux_min * options.lux_max))
    onChanger({ point_intermediaire: [luxMilieu, calculerCible(luxMilieu, options)] })
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

  // Flèches gauche / droite : lux par pas de 10 % (au moins 0,1) ; haut / bas :
  // luminosité par pas de 1.
  function touche(poignee) {
    return (e) => {
      const [lux0, lum0] = {
        bas: [options.lux_min, options.luminosite_min],
        milieu: milieu,
        haut: [options.lux_max, options.luminosite_max],
      }[poignee]
      const pas = Math.max(0.1, arrondirLux(lux0 * 0.1))
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
        {apercu && <path d={tracer(apercu)} className="trace-apercu" />}
        {corrections.map((c) => (
          <circle key={c.id} cx={xDeLux(Math.max(c.lux, 1))} cy={yDeLum(c.valeur)} r="5"
            className={`correction-courbe${c.ecartee ? ' correction-ecartee' : ''}`}>
            <title>{libelleCorrection(c)}</title>
          </circle>
        ))}
        {ancrages.map((a) => (
          <rect key={a.horodatage} className="ancre-courbe" x={xDeLux(a.lux) - 6}
            y={yDeLum(a.luminosite) - 6} width="12" height="12"
            transform={`rotate(45 ${xDeLux(a.lux)} ${yDeLum(a.luminosite)})`}>
            <title>{`Point d'ancrage : ${formaterLux(a.lux)}, luminosité ${a.luminosite}`}</title>
          </rect>
        ))}
        {maintenant && (
          <g className="point-maintenant">
            <line x1={maintenant.x} x2={maintenant.x} y1={Y0} y2={maintenant.y} />
            <circle cx={maintenant.x} cy={maintenant.y} r="6" />
          </g>
        )}
        {onChanger && (
          <>
            {poignee('bas', premier, 'Pièce sombre et luminosité minimale', options.lux_min,
              options.luminosite_min)}
            {milieu && poignee('milieu', points[1], 'Point intermédiaire', milieu[0], milieu[1])}
            {poignee('haut', dernier, 'Pièce lumineuse et luminosité maximale', options.lux_max,
              options.luminosite_max)}
          </>
        )}
      </svg>
      <figcaption className="texte-attenue">
        {maintenant
          ? `Maintenant : ${formaterLux(Math.round(lux * 10) / 10)} → luminosité ${cible}`
          : 'Mesure du capteur indisponible'}
        {onChanger
          ? ` · faites glisser les ${milieu ? 'trois' : 'deux'} points, ou utilisez les flèches `
            + 'du clavier.'
          : '.'}
        {ancrages.length > 0 && ' Losanges : vos points d\'ancrage.'}
        {corrections.length > 0 && ' Points : vos corrections retenues.'}
        {apercu && ' Pointillé : la courbe suggérée.'}
      </figcaption>
      {onChanger && (
        <div className="actions-courbe">
          {milieu ? (
            <button type="button" className="bouton-secondaire" disabled={desactive}
              onClick={() => onChanger({ point_intermediaire: null })}>
              Retirer le point intermédiaire
            </button>
          ) : (
            <button type="button" className="bouton-secondaire" disabled={desactive}
              onClick={ajouterMilieu}>
              Ajouter un point intermédiaire
            </button>
          )}
        </div>
      )}
    </figure>
  )
}
