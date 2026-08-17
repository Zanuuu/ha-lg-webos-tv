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

export function ouvrirCanal(gestionnaires) {
  const protocole = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocole}//${location.host}/api/ws`)
  ws.onmessage = (evt) => gestionnaires.onMessage(JSON.parse(evt.data))
  ws.onopen = () => gestionnaires.onOuverture?.()
  ws.onclose = () => gestionnaires.onFermeture?.()
  ws.onerror = () => ws.close()
  return ws
}
