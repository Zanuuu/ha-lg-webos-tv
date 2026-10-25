// Santé de l'installation : textes des diagnostics calculés par
// l'intégration (sante.py). Les chiffres et propositions viennent tels quels
// de l'intégration : aucun calcul n'est refait ici.

import { texteRapportSecours } from './luminosite.js'

export const NIVEAUX_ACTIFS = ['bloquant', 'avertissement', 'info']

export const AMBIANCES = {
  sombre: 'pièce sombre',
  intermediaire: 'lumière intermédiaire',
  claire: 'pièce claire',
}

export function duree(secondes) {
  if (secondes < 90) return `${Math.round(secondes)} s`
  if (secondes < 5400) return `${Math.round(secondes / 60)} min`
  return `${Math.round(secondes / 3600)} h`
}

export function heures(secondes) {
  const h = secondes / 3600
  return `${h.toLocaleString('fr-FR', { maximumFractionDigits: h < 10 ? 1 : 0 })} h`
}

const nombre = (valeur) => valeur.toLocaleString('fr-FR')
const lux = (valeur) => `${nombre(valeur)} lx`
const pourcent = (fraction) => `${Math.round(fraction * 100)} %`
export const signe = (valeur) => (valeur > 0 ? `+${nombre(valeur)}` : nombre(valeur))

// Conseil de réglage du capteur selon son intégration (étude, § 4.1).
function conseilCadence(plateforme) {
  if (plateforme === 'esphome') {
    return 'Dans ESPHome, une mesure toutes les 2 à 5 s suffit (update_interval: 5s) ; inutile '
      + 'de filtrer dans ESPHome, la fonction lisse elle-même.'
  }
  if (plateforme === 'zwave_js') {
    return 'Les capteurs Z-Wave ne signalent souvent un changement qu\'au-delà d\'un seuil élevé : '
      + 'abaissez le seuil et l\'intervalle de rapport dans les paramètres de l\'appareil '
      + '(l\'autonomie de la pile baissera).'
  }
  return 'Réglez la fréquence de mesure du capteur au plus court : une mesure toutes les 5 à 30 s '
    + 'suffit.'
}

// Texte d'un contrôle passé (✓) ou en observation, sur une ligne.
export function texteControle(d) {
  const v = d.valeurs
  if (d.niveau === 'attente') {
    const [acquis, requis] = v.progression
    switch (d.id) {
      case 'capteur_lent':
        return `Fréquence des mesures : ${acquis} intervalles observés sur ${requis}, téléviseur allumé.`
      case 'capteur_grossier':
        return `Résolution en pièce sombre : ${acquis} mesures sous 20 lx sur ${requis}.`
      case 'plancher':
        return `Mesure dans le noir : ${nombre(acquis)} h de téléviseur allumé sur ${requis} h.`
      case 'courbe':
        return `Calage de la courbe : ${nombre(acquis)} h de fonctionnement sur ${requis} h.`
      case 'secours':
        return `Capteur de secours : rapport avec le principal en apprentissage, ${acquis} `
          + `mesures communes sur ${requis}.`
      case 'retroaction':
        return `Effet de l'écran sur le capteur : ${acquis} allumage${acquis > 1 ? 's' : ''} ou `
          + `extinction${acquis > 1 ? 's' : ''} mesuré${acquis > 1 ? 's' : ''} sur ${requis} `
          + '(téléviseur éteint au moins 3 min, pièce sombre, mesure dans les 2 min).'
      default:
        return `${d.id} : ${acquis} sur ${requis}`
    }
  }
  switch (d.id) {
    case 'conflit':
      return 'Aucune fonction du téléviseur ne règle la luminosité en même temps.'
    case 'capteur_lent':
      return `Capteur : une mesure toutes les ${duree(v.intervalle_s)}, téléviseur allumé.`
    case 'capteur_grossier':
      return `Résolution : pas de ${nombre(v.pas)} lx en pièce sombre, assez fin.`
    case 'plafond':
      return `Plage : jusqu'à ${lux(v.vmax)} mesurés, sans plafond.`
    case 'plancher':
      return v.part === 0
        ? 'Mesure dans le noir : le capteur ne tombe jamais à 0 lx, téléviseur allumé.'
        : `Mesure dans le noir : 0 lx seulement ${pourcent(v.part)} du temps, téléviseur allumé.`
    case 'courbe':
      return `Courbe : lumière habituelle de ${lux(v.lux_p10)} à ${lux(v.lux_p90)}, bien couverte.`
    case 'allers_retours':
      return `Stabilité : pas d'allers-retours répétés (${v.inversions} changements de sens en 7 jours).`
    case 'retroaction':
      return v.mesure_tv
        ? `Effet de l'écran sur le capteur : négligeable (≈ ${lux(v.delta_lx)}, ${v.evenements} événements).`
        : `Effet de l'écran sur le capteur : négligeable après ${v.rampes} transitions.`
    case 'ecritures_refusees':
      return v.non_confirmees === 0
        ? 'Écritures : toutes confirmées par le téléviseur.'
        : `Écritures : ${v.non_confirmees} non confirmées sur ${v.tentatives}.`
    case 'pauses_frequentes':
      return `Reprises en main : ${v.reprises} en 7 jours.`
    case 'pieces_differentes':
      return `Capteur et téléviseur dans la même pièce (${v.televiseur}).`
    case 'secours':
      return `Capteur de secours : prêt à prendre le relais. ${texteRapportSecours(v)}`
    default:
      return d.id
  }
}

// Diagnostic actif : { titre, pourquoi, action, libelleProposition }.
// `suggestions` : nombre de suggestions de courbe en attente.
export function texteDiagnostic(d, options, suggestions = 0) {
  const v = d.valeurs
  switch (d.id) {
    case 'capteur_fige':
      if (v.relais) {
        return {
          titre: 'Capteur principal figé : le secours a pris le relais',
          pourquoi: 'Aucune mesure du capteur principal depuis bien plus longtemps que '
            + 'd\'habitude, alors que le téléviseur est allumé. La luminosité suit le capteur de '
            + 'secours, converti avec leur rapport habituel ; souvent moins bien placé, il ne '
            + 'devrait servir que le temps de la réparation.',
          action: 'Pile vide, ou appareil injoignable (réseau Zigbee, Wi-Fi) ? Le principal '
            + 'reprendra la main dès sa prochaine mesure. Voir aussi Paramètres › Réparations.',
        }
      }
      return {
        titre: 'Capteur figé',
        pourquoi: 'Aucune mesure du capteur depuis bien plus longtemps que d\'habitude, alors que '
          + 'le téléviseur est allumé. La luminosité actuelle est conservée jusqu\'à la prochaine '
          + 'mesure.',
        action: 'Pile vide, ou appareil injoignable (réseau Zigbee, Wi-Fi) ? Voir aussi '
          + 'Paramètres › Réparations.',
      }
    case 'capteur_lent':
      return v.sur_variation
        ? {
          titre: 'Capteur peu bavard',
          pourquoi: `Votre capteur n'a donné qu'une mesure toutes les ${duree(v.intervalle_s)} en `
            + 'moyenne. Il ne publie peut-être que quand la lumière change : dans une pièce '
            + 'stable, c\'est normal.',
          action: 'Vérifiez qu\'il réagit en quelques secondes quand vous allumez une lampe ; '
            + 'sinon, réglez sa période de détection au plus court.',
        }
        : {
          titre: 'Capteur trop lent',
          pourquoi: `Votre capteur donne une mesure toutes les ${duree(v.intervalle_s)} en moyenne : `
            + 'la luminosité suit l\'éclairage avec ce retard.',
          action: conseilCadence(v.plateforme),
        }
    case 'capteur_grossier':
      return {
        titre: 'Capteur trop grossier en pièce sombre',
        pourquoi: `${v.entiers
          ? 'Sous 10 lx, votre capteur ne mesure que des valeurs entières'
          : `Votre capteur avance par pas de ${lux(v.pas)}`} : vers ${lux(v.reference)}, un pas `
          + `fait ${pourcent(v.pas_relatif)} de la mesure, et la luminosité avance par sauts dans `
          + 'le noir.',
        action: d.proposition
          ? `Relever « Pièce sombre » à ${lux(d.proposition.lux_min)} : en dessous, la luminosité `
            + 'reste au minimum, et chaque pas du capteur compte moins.'
          : 'Un capteur plus sensible en faible lumière fera mieux.',
        libelleProposition: 'Appliquer',
      }
    case 'plafond':
      return {
        titre: 'Le capteur plafonne',
        pourquoi: `Votre capteur s'arrête à ${lux(v.vmax)} (${v.rapports} mesures à cette valeur `
          + `exacte). ${v.sous_lux_max
            ? `C'est en deçà de « Pièce lumineuse » (${lux(options.lux_max)}) : la luminosité `
              + 'n\'atteint jamais son maximum.'
            : `C'est au-delà de « Pièce lumineuse » (${lux(options.lux_max)}) : sans effet sur `
              + 'la luminosité.'}`,
        action: v.sous_lux_max
          ? 'Abaissez « Pièce lumineuse » sous cette valeur, ou choisissez un capteur à plus '
            + 'grande plage.'
          : null,
      }
    case 'plancher':
      return {
        titre: 'Le capteur affiche 0 dans le noir',
        pourquoi: `Votre capteur affiche 0 lx ${pourcent(v.part)} du temps quand le téléviseur est `
          + 'allumé : il ne distingue pas le noir d\'une pièce faiblement éclairée. La fonction '
          + 'traite 0 comme « Pièce sombre ».',
        action: 'Si vous regardez souvent dans une faible lumière, un capteur plus sensible fera '
          + 'mieux.',
      }
    case 'courbe':
      return v.borne === 'haute'
        ? {
          titre: 'Courbe calée trop bas',
          pourquoi: `Depuis 7 jours, la luminosité reste au maximum ${pourcent(v.part_haute)} du `
            + 'temps : la pièce est plus claire que prévu par la courbe (« Pièce lumineuse » : '
            + `${lux(options.lux_max)}).`,
          action: d.proposition
            ? `Régler « Pièce lumineuse » à ${lux(d.proposition.lux_max)} (90 % du temps en `
              + 'dessous) : la luminosité suivra de nouveau la lumière de la pièce.'
            : 'La lumière de la pièce varie trop peu pour proposer une valeur.',
          libelleProposition: 'Appliquer',
        }
        : {
          titre: 'Luminosité au minimum presque tout le temps',
          pourquoi: `La luminosité reste au minimum (${v.luminosite_min}) ${pourcent(v.part_basse)} `
            + `du temps : la pièce est plus sombre que « Pièce sombre » (${lux(options.lux_min)}).`,
          action: 'Si ce minimum vous convient dans le noir, rien à faire. Si l\'image vous paraît '
            + 'trop sombre, relevez « Luminosité minimale ».',
        }
    case 'allers_retours':
      return {
        titre: 'La luminosité fait des allers-retours',
        pourquoi: `${v.episodes} fois en 7 jours, la luminosité a changé de sens 3 fois en `
          + '10 minutes : mesure instable (reflet, passage devant le capteur, lampe qui '
          + 'clignote), ou lampes allumées et éteintes à la main.',
        action: d.proposition
          ? `Seuils à ${d.proposition.hysteresis_montee} % à la hausse et `
            + `${d.proposition.hysteresis_descente} % à la baisse, lissage à la baisse de `
            + `${d.proposition.lissage_descente_s} s : la luminosité réagira un peu moins vite.`
          : null,
        libelleProposition: 'Appliquer',
      }
    case 'retroaction': {
      const mesures = []
      if (v.vue_tv) {
        mesures.push(`environ ${lux(v.delta_lx)} de sa mesure viennent du téléviseur `
          + `(${pourcent(v.part)} en pièce sombre, médiane de ${v.evenements} allumages et `
          + 'extinctions)')
      }
      if (v.vue_rampes) {
        mesures.push(`après une transition, la mesure varie de ${pourcent(v.r10)} pour 10 points `
          + `de luminosité (${v.rampes} transitions)`)
      }
      if (mesures.length > 0) {
        const texte = mesures.join(' ; ')
        return {
          titre: 'Votre capteur voit l\'écran',
          pourquoi: `${texte.charAt(0).toUpperCase()}${texte.slice(1)}. La luminosité suit alors `
            + 'les scènes claires et sombres.',
          action: 'Placez le capteur à côté de l\'écran, tourné vers la pièce (emplacement A).',
          lienEmplacement: true,
        }
      }
      if (d.niveau === 'info') {
        return {
          titre: 'Pas d\'effet de l\'écran mesuré',
          pourquoi: 'Vous avez indiqué l\'emplacement D (face à l\'écran), mais les mesures ne '
            + 'montrent pas d\'effet de l\'écran sur le capteur.',
          action: 'Vérifiez l\'emplacement choisi.',
          lienEmplacement: true,
        }
      }
      return {
        titre: 'Capteur déclaré face à l\'écran',
        pourquoi: 'Vous avez indiqué l\'emplacement D : l\'écran éclaire le capteur, et la '
          + 'luminosité suivrait les scènes. La fonction attend 20 s après chaque changement. '
          + `Les mesures automatiques le confirmeront (${v.evenements} événements sur 5).`,
        action: 'Si possible, placez le capteur à côté de l\'écran, tourné vers la pièce '
          + '(emplacement A).',
        lienEmplacement: true,
      }
    }
    case 'ecritures_refusees':
      return {
        titre: 'Le téléviseur n\'applique pas toujours les changements',
        pourquoi: `${v.non_confirmees} écritures sur ${v.tentatives} n'ont pas été confirmées par `
          + 'le téléviseur en 7 jours.',
        action: v.ecriture_possible === false
          ? 'L\'écriture est impossible en ce moment (mode consultation) : voir Paramètres › '
            + 'Réparations.'
          : 'Voyez la dernière erreur et le journal ; si cela persiste, redémarrez le téléviseur.',
      }
    case 'pauses_frequentes':
      return {
        titre: 'Corrections fréquentes',
        pourquoi: `Vous avez corrigé la luminosité ${v.reprises} fois en 7 jours, surtout en `
          + `${AMBIANCES[v.ambiance] || v.ambiance} (${signe(v.correction_moyenne)} en moyenne).`,
        action: suggestions > 0
          ? 'Vos corrections dessinent déjà une retouche de la courbe : voyez la suggestion, '
            + 'sous la courbe, et appliquez-la si elle vous convient.'
          : 'Chaque correction gardée 10 minutes est retenue ; dès 3 dans le même sens pour un '
            + 'même éclairage, une suggestion de courbe apparaît sous la courbe.',
        lienSuggestion: suggestions > 0,
      }
    case 'secours':
      return texteSecours(v)
    case 'pieces_differentes':
      return {
        titre: 'Capteur dans une autre pièce',
        pourquoi: `Ce capteur est rangé dans « ${v.capteur} », le téléviseur dans `
          + `« ${v.televiseur} » (pièces de Home Assistant).`,
        action: 'Si le capteur est bien près du téléviseur, rangez-le dans la même pièce ; sinon, '
          + 'choisissez un capteur de la pièce du téléviseur.',
      }
    default:
      return { titre: d.id, pourquoi: JSON.stringify(v), action: null }
  }
}

// Capteur de secours (diagnostic `secours`) : en relais, ou qui ne pourrait
// pas le prendre.
function texteSecours(v) {
  if (v.actif) {
    return {
      titre: 'Le capteur de secours a pris le relais',
      pourquoi: 'Le capteur principal ne donne plus de mesure utilisable : la luminosité suit '
        + `le secours, converti avec leur rapport habituel. ${texteRapportSecours(v) ?? ''}`,
      action: 'Le principal reprendra la main dès qu\'il mesurera de nouveau.',
    }
  }
  if (!v.disponible || v.fige) {
    return {
      titre: v.disponible ? 'Capteur de secours figé' : 'Capteur de secours indisponible',
      pourquoi: 'Il ne pourrait pas prendre le relais si le capteur principal tombait en panne.',
      action: 'Pile vide, ou appareil injoignable (réseau Zigbee, Wi-Fi) ?',
    }
  }
  return {
    titre: v.etat === 'incoherent' ? 'Capteurs incohérents' : 'Rapport entre les capteurs instable',
    pourquoi: texteRapportSecours(v),
    action: 'Choisissez un secours placé comme le principal, dans la même pièce et à '
      + 'l\'abri du jour direct, ou retirez-le.',
  }
}
