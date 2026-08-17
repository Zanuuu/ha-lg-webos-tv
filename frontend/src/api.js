export async function recupererArbre() {
  const res = await fetch('/api/arbre')
  return res.json()
}

export async function recupererReglages() {
  const res = await fetch('/api/reglages')
  return res.json()
}

export async function recupererEtat() {
  const res = await fetch('/api/etat')
  return res.json()
}

export async function ecrireReglage(entreeId, valeur) {
  const res = await fetch(`/api/reglages/${encodeURIComponent(entreeId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ valeur }),
  })
  const corps = await res.json()
  if (!res.ok) {
    throw new Error(corps.detail || `Échec de l'écriture (${res.status})`)
  }
  return corps
}

async function jsonOuLeve(res) {
  const corps = await res.json()
  if (!res.ok) throw new Error(corps.detail || `Échec (${res.status})`)
  return corps
}

export async function recupererPresets() {
  return jsonOuLeve(await fetch('/api/presets'))
}

export async function recupererPreset(nom) {
  return jsonOuLeve(await fetch(`/api/presets/${encodeURIComponent(nom)}`))
}

export async function creerPreset(nom) {
  return jsonOuLeve(await fetch('/api/presets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom }),
  }))
}

export async function importerPreset(donnees, remplacer = false) {
  return jsonOuLeve(await fetch('/api/presets/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...donnees, remplacer }),
  }))
}

export async function supprimerPreset(nom) {
  return jsonOuLeve(await fetch(`/api/presets/${encodeURIComponent(nom)}`, { method: 'DELETE' }))
}

export async function appliquerPreset(nom) {
  return jsonOuLeve(await fetch(`/api/presets/${encodeURIComponent(nom)}/appliquer`, { method: 'POST' }))
}

export async function recupererHistorique(limite = 100) {
  const res = await fetch(`/api/historique?limite=${limite}`)
  return res.json()
}

export async function annulerEcriture(id) {
  return jsonOuLeve(await fetch(`/api/historique/${id}/annuler`, { method: 'POST' }))
}

export async function revenirA(horodatage) {
  return jsonOuLeve(await fetch('/api/historique/revenir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ horodatage }),
  }))
}

export function ouvrirCanal(gestionnaires) {
  const protocole = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocole}//${location.host}/api/ws`)
  ws.onmessage = (evt) => gestionnaires.onMessage(JSON.parse(evt.data))
  ws.onopen = () => gestionnaires.onOuverture?.()
  ws.onclose = () => gestionnaires.onFermeture?.()
  ws.onerror = () => ws.close()
  return ws
}
