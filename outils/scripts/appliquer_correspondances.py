"""Phase 2, passe 2 : applique les correspondances menu -> API aux fichiers
menu-tree/*.json.

La table CORRESPONDANCES est la source unique du rapprochement : id d'entrée
-> {categorie, cle, acces, bornes?, valeurs?, note?}. Les bornes viennent des
descripteurs getSystemSettingDesc relevés sur NOTRE téléviseur
(backend/app/inventaire-api.json) ; les énumérations de valeurs API viennent de la
doc communautaire bscpylgtv G5, à confirmer à l'usage (chaque écriture est
suivie d'une relecture).

Toute feuille sans correspondance reçoit acces="aucun" (« À régler sur la
TV »). Le script est idempotent.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "custom_components" / "lg_webos_tv" / "menu_tree"

RW = "lecture_ecriture"
RO = "lecture_seule"

CORRESPONDANCES = {
    # ----- Image
    "image.mode-selection": {
        "categorie": "picture", "cle": "pictureMode", "acces": RW,
        "valeurs": {
            "Image personnalisée": "personalized", "Vif": "vivid",
            "Standard": "normal", "Economie d'énergie automatique": "eco",
            "Cinéma": "cinema", "Sport": "sports", "Optimiseur de jeu": "game",
            "FILMMAKER MODE": "filmMaker",
            "Expert (pièce lumineuse, journée)": "expert1",
            "Expert (pièce sombre, nuit)": "expert2",
        },
        "note": "Modes SDR ; en HDR/Dolby Vision l'API expose hdr*/dolbyHdr*. « Basique » et « Accueil cinéma » restent à rapprocher (probablement modes HDR).",
    },
    "image.parametres-avances.luminosite.luminosite-pixels-oled": {
        "categorie": "picture", "cle": "backlight", "acces": RW,
        "bornes": {"min": 0, "max": 100, "pas": 1},
    },
    "image.parametres-avances.luminosite.ajuster-le-contraste": {
        "categorie": "picture", "cle": "contrast", "acces": RW,
        "bornes": {"min": 0, "max": 100, "pas": 1},
    },
    "image.parametres-avances.luminosite.niveau-noir": {
        "categorie": "picture", "cle": "brightness", "acces": RW,
        "bornes": {"min": 0, "max": 100, "pas": 1},
    },
    "image.parametres-avances.luminosite.contraste-dynamique-automatique": {
        "categorie": "picture", "cle": "dynamicContrast", "acces": RW,
        "note": "Valeurs API documentées : off/low/medium/high ; libellés affichés à relever sur photo.",
    },
    "image.parametres-avances.luminosite.mappage-tons-dynamiques": {
        "categorie": "picture", "cle": "hdrDynamicToneMapping", "acces": RW,
        "valeurs": {"Activé": "on", "Désactivé": "off"},
        "note": "L'API accepte aussi HGIG.",
    },
    "image.parametres-avances.luminosite.luminosite-maximale": {
        "categorie": "picture", "cle": "peakBrightness", "acces": RW,
        "note": "Valeurs API documentées : off/high.",
    },
    "image.parametres-avances.luminosite.gamma": {
        "categorie": "picture", "cle": "gamma", "acces": RW,
        "note": "Valeurs API documentées : low/medium/high1/high2/mediumHavingLevel ; valeur actuelle relevée : high2 (2.2 probable). Libellés affichés à relever sur photo.",
    },
    "image.parametres-avances.luminosite.plage-video": {
        # Écriture testée le 17/08/2026 (choix simple auto/low/high) :
        # refusée, la clé attend l'objet complet par type de signal, pas une
        # valeur simple. RO tant que le bon format n'est pas établi.
        "categorie": "picture", "cle": "blackLevel", "acces": RO,
        "note": "L'API renvoie un objet par type de signal (auto/low/high).",
    },
    "image.parametres-avances.luminosite.protection-yeux": {
        "categorie": "picture", "cle": "motionEyeCare", "acces": RW,
        "note": "Rapprochement présumé (Motion Eye Care) ; à confirmer par test.",
    },
    "image.parametres-avances.reduire-lumiere-bleue": {
        "categorie": "picture", "cle": "eyeComfortMode", "acces": RW,
        "valeurs": {"Activé": "on", "Désactivé": "off"},
    },
    "image.parametres-avances.couleur.profondeur-couleur": {
        "categorie": "picture", "cle": "color", "acces": RW,
        "bornes": {"min": 0, "max": 100, "pas": 1},
    },
    "image.parametres-avances.couleur.teinte": {
        "categorie": "picture", "cle": "tint", "acces": RW,
        "bornes": {"min": -50, "max": 50, "pas": 1},
        "note": "L'écran affiche Rouge 50 … Vert 50 ; l'API code de -50 (rouge) à +50 (vert), sens à confirmer.",
    },
    "image.parametres-avances.couleur.gamme-couleurs": {
        "categorie": "picture", "cle": "colorGamut", "acces": RW,
        "note": "Valeurs API documentées : auto/native/wide/extended/dynamic ; correspondance avec les libellés à confirmer.",
    },
    "image.parametres-avances.couleur.ajuster.selectionner-couleur": {
        "categorie": "picture", "cle": "colorManagementColorSystem", "acces": RW,
        "valeurs": {"Rouge": "red", "Vert": "green", "Bleu": "blue",
                    "Cyan": "cyan", "Magenta": "magenta", "Jaune": "yellow"},
    },
    "image.parametres-avances.couleur.ajuster.saturation-teinte-luminosite": {
        "categorie": "picture", "cle": "colorManagement<Composante><Couleur>", "acces": RW,
        "note": "18 clés API : colorManagement{Saturation,Hue,Luminance}{Red,Green,Blue,Cyan,Magenta,Yellow}, chacune de -30 à +30.",
    },
    "image.parametres-avances.couleur.balance-blancs.temperature-couleur": {
        "categorie": "picture", "cle": "colorTemperature", "acces": RW,
        "bornes": {"min": -50, "max": 50, "pas": 1},
    },
    "image.parametres-avances.couleur.balance-blancs.methode": {
        "categorie": "picture", "cle": "whiteBalanceMethod", "acces": RW,
        "valeurs": {"2 points": "2", "Niveau de signal 10 points (%)": "10",
                    "Niveau de signal 22 points (%)": "22"},
    },
    "image.parametres-avances.couleur.balance-blancs.point": {
        "categorie": "picture", "cle": "whiteBalancePoint", "acces": RW,
        "valeurs": {"Faible": "low", "Élevé": "high"},
    },
    "image.parametres-avances.couleur.balance-blancs.niveau-signal": {
        "categorie": "picture", "cle": "whiteBalanceIre", "acces": RW,
        "note": "Valeurs API documentées : « 2.5 » à « 100 » par pas ; whiteBalanceIre10pt pour la méthode 10 points.",
    },
    "image.parametres-avances.couleur.balance-blancs.luminosite-signal-max": {
        # Écriture testée le 17/08/2026 (valeur relevée, 130) : refusée
        # (« Out of range or interval »). Rapprochement d'origine spéculatif ;
        # RO tant que la clé/plage exacte n'est pas établie.
        "categorie": "picture", "cle": "whiteBalanceLuminance", "acces": RO,
        "note": "Rapprochement présumé ; à confirmer par test.",
    },
    "image.parametres-avances.couleur.balance-blancs.luminosite-signal-selectionne": {
        "categorie": "picture", "cle": "adjustingLuminance", "acces": RW,
        "note": "Tableau de valeurs par point (-50 à +50) ; adjustingLuminance10pt pour la méthode 10 points.",
    },
    "image.parametres-avances.couleur.balance-blancs.rouge-vert-bleu": {
        "categorie": "picture", "cle": "whiteBalance<Couleur>", "acces": RW,
        "note": "Clés API : whiteBalance{Red,Green,Blue} (tableaux par point, -50 à +50) ; en méthode 2 points : whiteBalance{Red,Green,Blue}{Gain,Offset}.",
    },
    "image.parametres-avances.clarte.ajuster-nettete": {
        "categorie": "picture", "cle": "sharpness", "acces": RW,
        "bornes": {"min": 0, "max": 50, "pas": 1},
        "note": "Écriture vérifiée en phase 1 (netteté).",
    },
    "image.parametres-avances.clarte.resolution-elevee": {
        "categorie": "picture", "cle": "superResolution", "acces": RW,
        "note": "Valeurs API documentées : off/low/medium/high.",
    },
    "image.parametres-avances.clarte.reduction-bruit": {
        "categorie": "picture", "cle": "noiseReduction", "acces": RW,
        "note": "Valeurs API documentées : off/low/medium/high/auto.",
    },
    "image.parametres-avances.clarte.reduction-bruit-mpeg": {
        "categorie": "picture", "cle": "mpegNoiseReduction", "acces": RW,
        "note": "Valeurs API documentées : off/low/medium/high/auto.",
    },
    "image.parametres-avances.clarte.degrades-fluides": {
        "categorie": "picture", "cle": "smoothGradation", "acces": RW,
        "note": "Valeurs API documentées : off/low/medium/high.",
    },
    "image.parametres-avances.clarte.cinema-originel": {
        "categorie": "picture", "cle": "realCinema", "acces": RW,
    },
    "image.parametres-avances.clarte.trumotion": {
        "categorie": "picture", "cle": "truMotionMode", "acces": RW,
        "valeurs": {"Désactivé": "off", "Mouvement cinématographique": "cinemaClear",
                    "Naturel": "natural", "Mouvement fluide": "smooth",
                    "Sélection de l'utilisateur": "user"},
    },
    # ----- Son
    "son.mode-selection": {
        "categorie": "sound", "cle": "soundMode", "acces": RO,
        "valeurs": {"Son AI/Son AI Pro": "aiSoundPlus", "Standard": "standard",
                    "Cinéma": "movie", "Sport": "sports", "Musique": "music",
                    "Optimiseur de jeu": "game"},
        "note": "Lisible mais absent de la liste communautaire d'écriture publique : écriture à tester prudemment en phase 3. Voix nette/Son personnalisé restent à rapprocher (news/bassBlast ?).",
    },
    "son.sortie-son": {
        "categorie": "sound", "cle": "soundOutput", "acces": RW,
        "note": "Valeur relevée : external_arc. Valeurs API documentées : tv_speaker, external_optical, external_arc, bt_soundbar, wisa_speaker, mobile_phone, headphone, tv_external_speaker, tv_speaker_bluetooth, etc.",
    },
    "son.parametres-avances.type-installation": {
        "categorie": "sound", "cle": "tvSetupConfiguration", "acces": RW,
        "valeurs": {"Support": "stand", "Installation murale": "wall_mount"},
    },
    "son.parametres-avances.synchroniser-image-son": {
        "categorie": "sound", "cle": "avSync", "acces": RW,
        "note": "Clés liées : avSyncSpdif (curseur 0–60) et avSyncBypassInput (Bypass).",
    },
    "son.parametres-avances.sortie-audio-numerique": {
        "categorie": "sound", "cle": "soundOutputDigital", "acces": RW,
        "valeurs": {"PCM": "pcm", "Auto": "auto", "Interconnexion": "passThrough"},
    },
    "son.parametres-avances.compatibilite-earc": {
        "categorie": "sound", "cle": "eArcSupport", "acces": RW,
    },
    # ----- Général
    "general.accessibilite.guide-audio.activer-la-fonction": {
        "categorie": "option", "cle": "audioGuidance", "acces": RW,
    },
    "general.systeme.securite.activer-la-fonction": {
        "categorie": "lock", "cle": "parentalControl", "acces": RW,
    },
    "general.systeme.securite.verrouillages-programmes-tv": {
        "categorie": "lock", "cle": "parentalGuidance", "acces": RW,
        "note": "Clés liées selon le pays : tvRating*, movieRating, ziggoRaiting. Rapprochement à affiner.",
    },
    "general.systeme.securite.verrouillages-entree": {
        "categorie": "lock", "cle": "inputBlock", "acces": RW,
        "note": "Valeur numérique (masque de bits probable) ; format à établir par test.",
    },
    "general.systeme.securite.verrouillages-application": {
        "categorie": "lock", "cle": "applockPerApp", "acces": RW,
    },
    "general.systeme.heure-et-minuterie.heure-date-fuseau": {
        "categorie": "time", "cle": "timeZone", "acces": RW,
        "note": "Seul le fuseau horaire est exposé par l'API publique ; heure/date non exposées.",
    },
    "general.systeme.parametres-supplementaires.demarrage-rapide-plus": {
        "categorie": "option", "cle": "quickStartMode", "acces": RW,
    },
    "general.systeme.parametres-supplementaires.parametres-accueil.ecran-mise-sous-tension": {
        "categorie": "general", "cle": "homeAutoLaunch", "acces": RW,
        "note": "Rapprochement présumé (lancement auto de l'accueil) ; à confirmer par test.",
    },
    "general.systeme.parametres-supplementaires.parametres-accueil.publicite-accueil": {
        "categorie": "general", "cle": "homePromotion", "acces": RW,
        "note": "Rapprochement présumé ; à confirmer par test.",
    },
    "general.systeme.lieu.pays": {
        # Écriture testée le 17/08/2026, y compris avec la valeur déjà
        # active : déclenche une réinitialisation en cascade de réglages liés
        # à la région (mode d'image, luminosité, sortie audio, guide audio,
        # contrôle parental, économie d'énergie). RO tant qu'aucune méthode
        # sûre n'est identifiée. Détails : docs/incidents-ecriture.md.
        "categorie": "option", "cle": "country", "acces": RO,
        "note": "Valeur relevée : FRA.",
    },
    "general.systeme.lieu.code-postal": {
        "categorie": "option", "cle": "zipcode", "acces": RW,
    },
    "general.systeme.langue.langue-du-menu": {
        "categorie": "", "cle": "localeInfo", "acces": RO,
        "note": "localeInfo est un objet (locales.UI etc.) ; l'écriture publique existe (setSystemSettings catégorie vide) mais reste à tester.",
    },
    "general.peripheriques-externes.parametres-hdmi.simplink": {
        "categorie": "other", "cle": "simplinkEnable", "acces": RW,
    },
    "general.peripheriques-externes.parametres-hdmi.hdmi-deep-color": {
        "categorie": "other", "cle": "uhdDeepColorHDMI<n>", "acces": RW,
        "note": "Une clé par entrée : uhdDeepColorHDMI1 à uhdDeepColorHDMI4.",
    },
    "general.peripheriques-externes.tv-allume-mobile.activer-via-wifi": {
        "categorie": "network", "cle": "wolwowlOnOff", "acces": RW,
    },
    "general.peripheriques-externes.tv-allume-mobile.activer-via-bluetooth": {
        "categorie": "network", "cle": "bleAdvertisingOnOff", "acces": RW,
    },
    "general.economie-energie.fonction-economie-energie": {
        "categorie": "picture", "cle": "energySaving", "acces": RW,
        "valeurs": {"Auto": "auto", "Désactivé": "off", "Minimum": "min",
                    "Moyen": "med", "Maximum": "max"},
    },
    "general.precautions-utilisation.reglages-famille.parametres-supplementaires.mode-limite-volume": {
        "categorie": "lock", "cle": "offHearingProtectFlag", "acces": RW,
        "note": "Clé liée : offHearingProtectMaxVolume (10–60).",
    },
    # ----- Assistance
    "assistance.mise-a-jour-logiciel.mise-a-jour-automatique": {
        "categorie": "support", "cle": "automaticUpdate", "acces": RW,
    },
    "assistance.mode-domicile-magasin": {
        "categorie": "option", "cle": "storeMode", "acces": RW,
        "valeurs": {"Mode Domicile": "home", "Mode Magasin": "store"},
    },
    "assistance.informations-televiseur": {
        "categorie": "network", "cle": "deviceName", "acces": RO,
        "note": "Seul le nom du périphérique est exposé ; modèle et numéro de série viennent de getSystemInfo.",
    },
}


def appliquer(entree: dict, avertissements: list[str]) -> None:
    corr = CORRESPONDANCES.get(entree.get("id", ""))
    if corr:
        entree["api"] = {"categorie": corr["categorie"], "cle": corr["cle"],
                         "acces": corr["acces"]}
        if "bornes" in corr:
            entree["bornes"] = corr["bornes"]
            if "a_verifier" in entree:
                entree["a_verifier"] = [x for x in entree["a_verifier"] if x != "bornes"] or None
                if entree["a_verifier"] is None:
                    del entree["a_verifier"]
        if "valeurs" in corr:
            choix = {c["libelle"]: c for c in entree.get("choix", [])}
            for libelle, valeur in corr["valeurs"].items():
                if libelle in choix:
                    choix[libelle]["valeur_api"] = valeur
                else:
                    avertissements.append(f"{entree['id']}: choix « {libelle} » introuvable")
        if "note" in corr:
            notes = entree.setdefault("notes", [])
            note = f"[API] {corr['note']}"
            if note not in notes:
                notes.append(note)
    elif not entree.get("enfants"):
        entree["api"] = {"acces": "aucun"}
    for enfant in entree.get("enfants", []):
        appliquer(enfant, avertissements)


def main() -> None:
    avertissements: list[str] = []
    utilises = set()

    def marquer(e):
        if e.get("id") in CORRESPONDANCES:
            utilises.add(e["id"])
        for c in e.get("enfants", []):
            marquer(c)

    for path in sorted(ROOT.rglob("*.json")):
        if path.name in ("schema.json", "index.json"):
            continue
        data = json.loads(path.read_text())
        appliquer(data, avertissements)
        marquer(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    for manquant in sorted(set(CORRESPONDANCES) - utilises):
        avertissements.append(f"correspondance sans entrée : {manquant}")
    for a in avertissements:
        print("AVERTISSEMENT :", a)
    print(f"{len(utilises)}/{len(CORRESPONDANCES)} correspondances appliquées")


if __name__ == "__main__":
    main()
