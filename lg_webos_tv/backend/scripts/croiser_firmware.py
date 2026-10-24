"""Phase 2, passe 3 : application à menu-tree des corrections issues du
firmware 33.31.68 (data/firmware-menus.json, produit par analyser_firmware.py).

La table CORRECTIONS est curée à la main : chaque entrée cite sa source
(table de choix ou fenêtre de hook du bundle). Opérations possibles :
- "choix"        : remplace la liste de choix (libellés + valeurs officiels) ;
- "choix_maj"    : complète des choix existants (valeur_api, libellé corrigé) ;
- "description"  : remplace la description par le texte d'aide de l'écran
                   Réglages (le guide TV, lui, a son propre texte) ;
- "notes"        : notes à ajouter (préfixées [firmware]) ;
- "resoudre"     : points a_verifier tranchés, à retirer ;
- "a_verifier"   : points à ajouter.

Chaque entrée touchée reçoit source.firmware = "33.31.68". Le script écrit
aussi le rapport docs/ecarts-firmware.md. Idempotent.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MENU = ROOT / "custom_components" / "lg_webos_tv" / "menu_tree"
# Rapports de développement : dossier docs/ à la racine du dépôt.
RAPPORT = ROOT / "docs" / "ecarts-firmware.md"
FIRMWARE = "33.31.68"

C = {
    # ---------------- Image
    "image.mode-selection": {
        "resoudre": ["libelle"],
        "choix_maj": {
            "Economie d'énergie automatique": {"libelle": "Éco", "valeur_api": "eco"},
            "Accueil cinéma": {"valeur_api": "hdrCinemaBright"},
        },
        "notes": [
            "Titre d'écran confirmé : « Mode Sélection » (Select Mode). L'entrée est désignée « Mode Image » (Picture Mode) dans les textes.",
            "Écart guide→firmware : le mode eco s'affiche « Éco », pas « Economie d'énergie automatique ».",
            "« Accueil cinéma » (hdrCinemaBright) et les variantes hdr*/dolbyHdr* n'apparaissent qu'en signal HDR/Dolby Vision.",
            "« Basique » (guide) est absent de la table pictureMode du firmware : probablement une variante d'autres modèles ; à confirmer.",
            "Le firmware connaît aussi photo (Photo) et hdrEffect (Effet HDR), non listés par le guide.",
        ],
        "ecart": "Libellé du mode eco : « Éco » (firmware) vs « Economie d'énergie automatique » (guide) ; « Basique » introuvable dans le firmware.",
    },
    "image.parametres-avances.luminosite.contraste-dynamique-automatique": {
        "resoudre": ["controle", "choix"],
        "description": "Optimisez les paramètres de contraste en fonction de la luminosité de l'image.",
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé", "valeur_api": "high"},
        ],
    },
    "image.parametres-avances.luminosite.mappage-tons-dynamiques": {
        "resoudre": ["controle", "choix", "visibilite"],
        "description": "Ajustez le contraste en temps réel lorsque vous regardez une vidéo HDR.",
        "notes": [
            "L'API accepte aussi la valeur HGIG (exposée dans l'Optimiseur de jeu).",
        ],
    },
    "image.parametres-avances.luminosite.amplificateur-expression": {
        "resoudre": ["controle", "choix"],
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Détails", "valeur_api": "detail"},
            {"libelle": "Luminosité", "valeur_api": "highlight"},
        ],
        "notes": [
            "Clé interne expressionEnhancer, non accessible par l'API publique.",
        ],
    },
    "image.parametres-avances.luminosite.luminosite-maximale": {
        "resoudre": ["controle", "choix"],
        "description": "Ajustez la luminosité pour obtenir une luminosité maximale de l'écran.",
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Activé", "valeur_api": "high"},
        ],
        "a_verifier": ["libelle"],
        "notes": [
            "Le descripteur du téléviseur n'expose que off/high ; le firmware connaît aussi low/medium (Faible/Moyen) sur d'autres modèles.",
            "Le titre est « Luminosité dynamique » (Dynamic Brightness) sur une variante de modèles, « Luminosité maximale » sinon : à trancher sur photo.",
        ],
        "ecart": "Titre à variante : Luminosité maximale / Luminosité dynamique.",
    },
    "image.parametres-avances.luminosite.gamma": {
        "resoudre": ["choix"],
        "choix": [
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé1", "valeur_api": "high1"},
            {"libelle": "Élevé2", "valeur_api": "high2"},
        ],
        "notes": [
            "Table gamma_adv du firmware. Le téléviseur documente aussi mediumHavingLevel ; la note BT.1886 du guide correspond probablement à un libellé contextuel des modes expert : à confirmer sur photo.",
        ],
    },
    "image.parametres-avances.luminosite.plage-video": {
        "resoudre": ["controle", "choix"],
        "choix": [
            {"libelle": "Auto", "valeur_api": "auto"},
            {"libelle": "Limité(e)", "valeur_api": "low"},
            {"libelle": "Plein écran", "valeur_api": "high"},
        ],
        "notes": [
            "Le firmware utilise aussi les alias limited/full pour certains contextes.",
        ],
    },
    "image.parametres-avances.luminosite.led-local-dimming": {
        "resoudre": ["choix"],
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé", "valeur_api": "high"},
        ],
    },
    "image.parametres-avances.couleur.gamme-couleurs": {
        "resoudre": ["choix"],
        "description": "Développez la plage de couleurs pouvant être affichée.",
        "choix": [
            {"libelle": "Détection auto", "valeur_api": "auto"},
            {"libelle": "Originale", "valeur_api": "native"},
            {"libelle": "Dynamique", "valeur_api": "dynamic"},
            {"libelle": "Étendu", "valeur_api": "extended"},
            {"libelle": "Large", "valeur_api": "wide"},
        ],
        "ecart": "Choix du firmware : Détection auto/Originale/Dynamique/Étendu/Large — le guide listait Adobe RGB et Cinéma, absents du firmware 33.31.68.",
    },
    "image.parametres-avances.couleur.balance-blancs.temperature-couleur": {
        "notes": [
            "Hors modes expert, le firmware propose une liste Froid/Moyen/Chaud1-3 (cool/medium/warm1-3) ; en mode expert c'est un curseur -50..+50 (valeur relevée : -40).",
        ],
    },
    "image.parametres-avances.couleur.balance-blancs.methode": {
        "notes": [
            "Le firmware connaît aussi « IRE à 20 points » (valeur 20) sur certains modèles.",
        ],
    },
    "image.parametres-avances.clarte.resolution-elevee": {
        "resoudre": ["controle", "choix"],
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé", "valeur_api": "high"},
        ],
    },
    "image.parametres-avances.clarte.reduction-bruit": {
        "resoudre": ["controle", "choix"],
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé", "valeur_api": "high"},
            {"libelle": "Auto", "valeur_api": "auto"},
        ],
    },
    "image.parametres-avances.clarte.reduction-bruit-mpeg": {
        "resoudre": ["controle", "choix"],
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé", "valeur_api": "high"},
            {"libelle": "Auto", "valeur_api": "auto"},
        ],
    },
    "image.parametres-avances.clarte.degrades-fluides": {
        "resoudre": ["controle", "choix"],
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Faible", "valeur_api": "low"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Élevé", "valeur_api": "high"},
        ],
    },
    "image.parametres-avances.clarte.trumotion": {
        "resoudre": ["choix"],
        "description": "Optimisez la qualité de l'image pour ne rien rater des scènes d'action.",
        "choix": [
            {"libelle": "Désactivé", "valeur_api": "off"},
            {"libelle": "Mouvement cinématographique", "valeur_api": "cinemaClear"},
            {"libelle": "Naturel", "valeur_api": "natural"},
            {"libelle": "Mouvement fluide", "valeur_api": "smooth"},
            {"libelle": "Éclatant", "valeur_api": "clear"},
            {"libelle": "Sélection de l'utilisateur", "valeur_api": "user"},
        ],
        "notes": [
            "« Éclatant » (clear) n'existe que sur certains modèles/entrées ; visibilité à confirmer.",
        ],
    },
    # ---------------- Son
    "son.mode-selection": {
        "resoudre": ["choix"],
        "choix": [
            {"libelle": "Son personnalisé", "valeur_api": "personalized"},
            {"libelle": "Son AI Pro", "valeur_api": "aiSoundPlus"},
            {"libelle": "Standard", "valeur_api": "standard"},
            {"libelle": "Cinéma", "valeur_api": "movie"},
            {"libelle": "Voix nette", "valeur_api": "news"},
            {"libelle": "Sport", "valeur_api": "sports"},
            {"libelle": "Musique", "valeur_api": "music"},
            {"libelle": "Optimiseur de jeu", "valeur_api": "game"},
        ],
        "notes": [
            "Sur ce modèle le mode AI s'affiche « Son AI Pro » (aiSoundPlus) ; « Son AI » (aiSound) est la variante des modèles sans Pro. Voix nette = news.",
        ],
        "ecart": "Libellés simples confirmés : « Son AI Pro » et « Voix nette » (le guide écrivait « Son AI/Son AI Pro » et « Voix nette/Voix nette Pro »).",
    },
    "son.sortie-son.haut-parleur-tv": {
        "notes": ["Valeur soundOutput : tv_speaker (« Haut-parleur TV »)."],
    },
    "son.sortie-son.haut-parleur-sans-fil": {
        "resoudre": ["choix"],
        "choix_maj": {
            "Périphérique Bluetooth": {"valeur_api": "bt_soundbar"},
            "Haut-parleurs WiSA": {"valeur_api": "wisa_speaker"},
            "Périphérique mobile": {"valeur_api": "mobile_phone"},
        },
        "notes": ["LG WOWCAST n'a pas de valeur soundOutput identifiée dans le firmware (géré à part) ; à vérifier."],
    },
    "son.sortie-son.haut-parleur-filaire": {
        "resoudre": ["choix"],
        "choix_maj": {
            "Périphérique de sortie optique": {"valeur_api": "external_optical"},
            "Périphérique HDMI(ARC)": {"valeur_api": "external_arc"},
        },
        "notes": ["« Périphérique de sortie audio » = lineout, « Casque avec fil » = headphone (deux valeurs soundOutput distinctes)."],
    },
    "son.sortie-son.haut-parleurs-externes-et-tv": {
        "resoudre": ["choix"],
        "choix_maj": {
            "Périphérique Bluetooth + Haut-parleur TV": {"valeur_api": "tv_speaker_bluetooth"},
            "Périphérique de sortie optique + Haut-parleur TV": {"valeur_api": "tv_external_speaker"},
            "Périphérique HDMI(ARC) + Haut-parleur du téléviseur": {"valeur_api": "tv_speaker_external_arc"},
            "Casque avec fil + Haut-parleur TV": {"valeur_api": "tv_speaker_headphone"},
        },
    },
    "son.parametres-avances.sortie-audio-numerique": {
        "resoudre": ["choix"],
        "choix_maj": {
            "PCM": {"valeur_api": "pcm"},
            "Auto": {"valeur_api": "auto"},
            "Interconnexion": {"valeur_api": "passThrough"},
        },
    },
    "son.parametres-avances.amelioration-dialogue-ac4": {
        "resoudre": ["controle"],
        "notes": ["Clé interne ac4DialogueEnhancer (on/off), non accessible par l'API publique."],
    },
    # ---------------- Général
    "general.economie-energie.fonction-economie-energie": {
        "resoudre": [],
        "notes": ["Table firmware complète : auto/off/min/med/max (+ screen_off porté par l'entrée Écran désactivé)."],
    },
    "general.economie-energie.ecran-desactive": {
        "notes": ["Correspond à la valeur screen_off de picture.energySaving (libellé firmware : « Écran désactivé »)."],
    },
    "general.economie-energie.luminosite-minimale": {
        "notes": ["Clé interne energySavingAutoMin, non accessible par l'API publique."],
    },
    "general.maintenance-oled.parametres-image-maintenance": {
        "choix_maj": {
            "Désactivé": {"valeur_api": "off"},
            "Mode Confort": {"valeur_api": "comfortCare"},
            "Mode Salle de spectacle": {"valeur_api": "cinemaCare"},
            "Mode Enfants": {"valeur_api": "kidsCare"},
        },
        "notes": ["Clé interne oledCareMode, non accessible par l'API publique."],
    },
    "general.systeme.parametres-supplementaires.options-de-pointeur.vitesse-de-suivi": {
        "resoudre": ["choix"],
        "choix": [
            {"libelle": "Très lent", "valeur_api": "verySlow"},
            {"libelle": "Faible", "valeur_api": "slow"},
            {"libelle": "Moyen", "valeur_api": "medium"},
            {"libelle": "Rapide", "valeur_api": "fast"},
            {"libelle": "Très rapide", "valeur_api": "veryFast"},
        ],
        "notes": ["Clé interne (catégorie non publique) ; valeurs de la table slowToFast du firmware."],
    },
    "general.systeme.parametres-supplementaires.options-de-pointeur.taille-du-pointeur": {
        "resoudre": ["choix"],
        "choix": [
            {"libelle": "Petite taille", "valeur_api": "small"},
            {"libelle": "Taille moyenne", "valeur_api": "medium"},
            {"libelle": "Grande taille", "valeur_api": "large"},
        ],
    },
    # ---------------- Interrupteurs « Activer la fonction » (libellé officiel
    # confirmé : « Enable the function » -> « Activer la fonction »)
    "general.accessibilite.guide-audio.activer-la-fonction": {
        "resoudre": ["libelle", "description"],
    },
    "general.accessibilite.augmenter-temps-pression.activer-la-fonction": {
        "resoudre": ["libelle", "description"],
    },
    "general.accessibilite.agrandir-langue-signes.activer-la-fonction": {
        "resoudre": ["libelle", "description"],
    },
    "general.toujours-pret.activer-la-fonction": {
        "resoudre": ["libelle", "description"],
    },
    "general.systeme.securite.activer-la-fonction": {
        "resoudre": ["libelle", "description"],
    },
    "general.peripheriques-externes.tv-allume-mobile.activer-via-wifi": {
        "resoudre": ["libelle", "description"],
    },
    "general.peripheriques-externes.tv-allume-mobile.activer-via-bluetooth": {
        "resoudre": ["libelle", "description"],
    },
    # ---------------- Résolutions complémentaires
    "general.peripheriques-externes.parametres-hdmi.hdmi-deep-color": {
        "resoudre": ["choix"],
        "choix_maj": {
            "4K": {"valeur_api": "on"},
            "Désactivé": {"valeur_api": "off"},
        },
    },
    "image.parametres-avances.couleur.ajuster.selectionner-couleur": {
        "resoudre": ["choix"],
    },
    "image.parametres-avances.clarte.cinema-originel": {
        "resoudre": ["controle"],
    },
    "image.parametres-avances.luminosite.protection-yeux": {
        "resoudre": ["controle"],
    },
    "general.systeme.parametres-supplementaires.parametres-ecran-veille.duree": {
        "resoudre": ["choix"],
        "choix": [
            {"libelle": "5 min", "valeur_api": "5"},
            {"libelle": "10 min", "valeur_api": "10"},
            {"libelle": "15 min", "valeur_api": "15"},
            {"libelle": "30 min", "valeur_api": "30"},
            {"libelle": "1 h", "valeur_api": "60"},
            {"libelle": "2 h", "valeur_api": "120"},
        ],
        "notes": ["Table screenOffTime du firmware ; clé non accessible par l'API publique."],
    },
}


# Verdicts de la vérification visuelle sur le téléviseur (utilisateur,
# 17/08/2026) : appliqués avec source.photo au lieu de source.firmware.
V = {
    "image.mode-selection": {
        "supprimer_choix": ["Basique"],
        "resoudre": ["choix"],
        "notes": ["Vérifié sur TV : pas de mode « Basique », le mode « Standard » existe."],
    },
    "image.parametres-avances.luminosite.luminosite-maximale": {
        "resoudre": ["libelle"],
        "notes": ["Vérifié sur TV : le titre est bien « Luminosité maximale »."],
    },
    "image.parametres-avances.luminosite.gamma": {
        "choix": [
            {"libelle": "2.2"},
            {"libelle": "BT.1886"},
        ],
        "a_verifier": ["choix"],
        "notes": [
            "Vérifié sur TV : libellés numériques (« 2.2 » et « BT.1886 » constatés), pas Faible/Moyen/Élevé1/Élevé2 (table gamma_adv). Liste complète (1.9 ? 2.4 ?) et correspondance avec les valeurs API low/medium/high1/high2 à établir en phase 3 par écriture puis lecture du libellé affiché.",
        ],
    },
    "image.parametres-avances.couleur.balance-blancs.temperature-couleur": {
        "resoudre": ["controle"],
        "notes": ["Vérifié sur TV : curseur (mode expert actif)."],
    },
}

VERIF_VISUELLE = "validation visuelle utilisateur 2026-08-17"


def iter_entrees(entree):
    yield entree
    for enfant in entree.get("enfants", []):
        yield from iter_entrees(enfant)


def appliquer(entree: dict, corr: dict, rapport: list[str]) -> None:
    eid = entree["id"]
    if "supprimer_choix" in corr:
        avant = len(entree.get("choix", []))
        entree["choix"] = [c for c in entree.get("choix", [])
                           if c["libelle"] not in corr["supprimer_choix"]]
        if len(entree["choix"]) != avant:
            rapport.append(f"- `{eid}` : choix supprimé(s) : {', '.join(corr['supprimer_choix'])}.")
    if "description" in corr:
        if entree.get("description") != corr["description"]:
            rapport.append(f"- `{eid}` : description remplacée par le texte de l'écran Réglages.")
        entree["description"] = corr["description"]
    if "choix" in corr:
        entree["choix"] = corr["choix"]
        rapport.append(f"- `{eid}` : liste de choix posée depuis le firmware ({len(corr['choix'])} choix).")
    if "choix_maj" in corr:
        index = {c["libelle"]: c for c in entree.get("choix", [])}
        for libelle, maj in corr["choix_maj"].items():
            if libelle not in index:
                rapport.append(f"- `{eid}` : AVERTISSEMENT, choix « {libelle} » introuvable.")
                continue
            cible = index[libelle]
            if "libelle" in maj and maj["libelle"] != libelle:
                rapport.append(f"- `{eid}` : choix « {libelle} » renommé « {maj['libelle']} » (firmware).")
                cible["libelle"] = maj["libelle"]
            if "valeur_api" in maj:
                cible["valeur_api"] = maj["valeur_api"]
    for note in corr.get("notes", []):
        notes = entree.setdefault("notes", [])
        note_pref = f"[firmware] {note}"
        if note_pref not in notes:
            notes.append(note_pref)
    if corr.get("resoudre"):
        restants = [x for x in entree.get("a_verifier", []) if x not in corr["resoudre"]]
        if restants:
            entree["a_verifier"] = restants
        else:
            entree.pop("a_verifier", None)
    for point in corr.get("a_verifier", []):
        entree.setdefault("a_verifier", [])
        if point not in entree["a_verifier"]:
            entree["a_verifier"].append(point)


def main() -> None:
    rapport: list[str] = []
    rapport_visuel: list[str] = []
    ecarts: list[str] = []
    appliques = set()

    for path in sorted(MENU.rglob("*.json")):
        if path.name in ("schema.json", "index.json"):
            continue
        data = json.loads(path.read_text())
        modifie = False
        for entree in iter_entrees(data):
            corr = C.get(entree.get("id", ""))
            if corr:
                appliquer(entree, corr, rapport)
                entree.setdefault("source", {})["firmware"] = FIRMWARE
                appliques.add(entree["id"])
                if "ecart" in corr:
                    ecarts.append(f"- `{entree['id']}` : {corr['ecart']}")
                modifie = True
            verif = V.get(entree.get("id", ""))
            if verif:
                appliquer(entree, verif, rapport_visuel)
                entree.setdefault("source", {})["photo"] = VERIF_VISUELLE
                appliques.add(entree["id"])
                modifie = True
        if modifie:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    manquants = sorted((set(C) | set(V)) - appliques)
    for m in manquants:
        rapport.append(f"- AVERTISSEMENT : correction sans entrée : `{m}`")

    contenu = [
        "# Écarts et corrections issus du firmware 33.31.68",
        "",
        "Croisement de l'arbre des menus (transcrit depuis le guide webOS 25)",
        "avec l'app Réglages du firmware installé (`com.palm.app.settings` :",
        "bundle `main.js` + traductions françaises `strings.json`).",
        "Généré par `backend/scripts/croiser_firmware.py`.",
        "",
        "## Écarts notables guide → firmware",
        "",
        *(ecarts or ["Aucun."]),
        "",
        "## Corrections appliquées",
        "",
        *rapport,
        "",
        "## Vérification visuelle sur le téléviseur (utilisateur, 17/08/2026)",
        "",
        "- Pas de mode d'image « Basique » ; « Standard » présent.",
        "- Titre confirmé : « Luminosité maximale » (pas « Luminosité dynamique »).",
        "- Gamma : libellés numériques (« 2.2 », « BT.1886 » constatés) — correspondance API à établir en phase 3.",
        "- Température de couleur : curseur (mode expert).",
        "- Ordre confirmé : Image, Son, Général, Assistance ; sous Général : Accessibilité, Toujours prêt, Service d'AI, Optimiseur de jeu, Maintenance OLED, Précautions d'utilisation, Chaînes, Réseau, Périphériques externes, Système, Économie d'énergie.",
        "",
        *rapport_visuel,
        "",
        "## Constats d'API",
        "",
        "- Les clés supplémentaires vues dans l'app (dimensionInfo.*, "
        "expressionEnhancer, oledCareMode, energySavingAutoMin, "
        "ac4DialogueEnhancer, pointerSpeed/Size, screenOffTime…) sont toutes "
        "refusées par l'API publique `getSystemSettings` (testé le 17/08/2026) : "
        "l'app passe par le bus Luna privilégié. L'inventaire de la phase 1 "
        "reste la référence de ce qui est pilotable.",
    ]
    RAPPORT.write_text("\n".join(contenu) + "\n")
    print(f"{len(appliques)}/{len(C)} corrections appliquées, rapport -> {RAPPORT}")


if __name__ == "__main__":
    main()
