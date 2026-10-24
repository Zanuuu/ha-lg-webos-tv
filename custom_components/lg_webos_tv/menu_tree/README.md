# Arbre des menus

Fichiers JSON déclaratifs décrivant le menu Réglages du LG OLED G5
(webOS 25, firmware 33.31.68), en français.

## Sources et méthode (phase 2)

1. **Passe 1** : transcription depuis le guide d'utilisation LG webOS 25
   français (copie locale : `data/guide-webos25-fre.html`, source
   `kr.eguide.lgappstv.com/manual/w25/`, chapitre 6 « Paramètres »).
   Libellés et descriptions repris à l'identique. L'arborescence suit les
   chemins de menu indiqués dans le guide (« Entrez le chemin suivant »),
   pas sa numérotation de chapitres.
2. **Passe 2** : rapprochement avec les clés API inventoriées en phase 1
   (`backend/app/inventaire-api.json`).
3. **Passe 3** : vérification contre les photos des menus réels ; le guide
   ne reflète pas toujours exactement le firmware installé.

Aucun libellé, description ou valeur ne doit être inventé : ce qui manque est
marqué dans `a_verifier`.

## Organisation

Un fichier par section de premier niveau du menu « Tous les paramètres »
(`image.json`, `son.json`, `assistance.json`), sauf « Général », découpé en
un fichier par branche dans `general/` (`general/accessibilite.json`,
`general/systeme.json`…). `index.json` donne l'ordre des sections et la
composition de Général. Le schéma formel est dans `schema.json` ; résumé :

- `id` : identifiant unique, kebab-case, hiérarchique
  (`image.parametres-avances.luminosite.luminosite-pixels-oled`).
- `chemin` : chemin d'affichage dans le menu, libellés exacts
  (`["Image", "Paramètres avancés", "Luminosité"]`).
- `libelle` : libellé français exact de l'entrée.
- `description` : description française exacte affichée par le téléviseur ou
  donnée par le guide. Chaîne vide si le guide n'en fournit pas.
- `notes` : remarques du guide (conditions, limitations), texte exact.
- `controle` : `sous-menu` | `curseur` | `liste` | `interrupteur` | `action`
  | `texte` (affichage seul).
- `choix` : pour les listes : `[{"libelle": "Activé", "valeur_api": "on"}]`.
  `valeur_api` absente tant que la correspondance n'est pas établie.
- `bornes` : pour les curseurs : `{"min": 0, "max": 100, "pas": 1}`.
- `api` : `{"categorie": "picture", "cle": "backlight", "acces": …}` avec
  `acces` ∈ `lecture_ecriture` | `lecture_seule` | `aucun`. Objet absent =
  pas encore rapproché ; `acces: "aucun"` = « À régler sur la TV ».
- `visibilite` : conditions de présence/grisage (ex. réglage limité à
  certains modes d'image), sous forme structurée quand elle est connue.
- `enfants` : sous-entrées (pour `sous-menu`).
- `source` : traçabilité (`{"guide": "6.2.4"}`, photos en passe 3).
- `a_verifier` : liste de points en attente de confirmation
  (`libelle`, `description`, `choix`, `bornes`, `visibilite`, `position`…).

## Statut

- Passe 1 : en cours.
- Passe 2 : non commencée.
- Passe 3 : non commencée.
