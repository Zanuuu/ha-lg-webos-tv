# Incidents constatés lors des premières écritures réelles (phase 5)

Le développement des presets (phase 5) a fourni la première occasion
d'écrire, en une seule séquence, la quasi-totalité des réglages accessibles
en écriture d'après l'inventaire de phase 1. Trois écarts ont été constatés
le 17/08/2026 contre le téléviseur réel (firmware 33.31.68) ; tous ont été
corrigés dans l'arbre des menus et, pour le premier, dans le code.

## 1. `option.country` déclenche une réinitialisation en cascade

**Constat.** L'application d'un preset complet a écrit `option.country`
avec sa valeur déjà active (« FRA » → « FRA », un no-op en apparence). Le
téléviseur a immédiatement basculé le mode d'image sur « Éco » et, à la
vérification, plusieurs autres réglages sans rapport avaient changé sans
qu'aucune écriture de notre part ne les ait touchés :

| Réglage | Avant | Après (inattendu) |
|---|---|---|
| `picture.pictureMode` | expert2 | eco |
| `picture.backlight` (mode expert2) | 80 | 60 |
| `sound.soundOutputDigital` | passThrough | auto |
| `option.audioGuidance` | off | on |
| `lock.parentalControl` | false | true |
| `picture.energySaving` | off | auto |

Ces changements sont apparus **après** que notre séquence d'écriture a
confirmé ces mêmes valeurs comme correctes (relecture immédiate conforme),
avec un délai d'environ une demi-seconde après l'écriture de `country` —
signature d'un traitement asynchrone côté téléviseur, cohérent avec une
réinitialisation partielle des réglages dépendants de la région/du pays
(un comportement de type « nouvelle configuration pays », semblable à un
sous-ensemble du parcours de première mise en service).

**Conséquence.** Toutes les valeurs touchées ont été restaurées manuellement
à leur état d'origine et vérifiées. Le mode d'image et les réglages du
téléviseur de l'utilisateur sont revenus à l'identique de leur état avant
ce test.

**Correction.** `general.systeme.lieu.pays` passe en `lecture_seule` dans
l'arbre des menus : ni l'interface ni les presets ne peuvent plus l'écrire.
Aucune méthode d'écriture sûre n'a été identifiée ; à revoir seulement si le
besoin se présente, avec une confirmation explicite dans l'interface le cas
échéant.

## 2. `picture.blackLevel` : format de valeur erroné

**Constat.** L'entrée « Plage vidéo » avait été rapprochée d'un choix simple
(auto/low/high), mais l'API renvoie et attend en réalité un **objet** avec
une valeur par norme de diffusion (`{"ntsc": "auto", "pal": "auto", …}`),
comme déjà noté dans `docs/inventaire-api.json` en phase 1. L'écriture d'une
valeur simple a été rejetée côté validation avant même d'atteindre le
téléviseur.

**Correction.** Passé en `lecture_seule` ; le bon format d'écriture (quelle
sous-clé cibler, sur quelle base) reste à établir.

## 3. `picture.whiteBalanceLuminance` : hors plage

**Constat.** Ce rapprochement était déjà marqué « présumé, à confirmer »
en phase 2. L'écriture de la valeur relevée (130) a été refusée par le
téléviseur : « The value is Out of range or interval ».

**Correction.** Passé en `lecture_seule` ; la clé ou la plage exacte reste à
établir.

## 4. Bug corrigé : conversion booléenne trop générale

**Constat.** `general.systeme.securite.activer-la-fonction`
(`lock.parentalControl`) est un interrupteur, catégorie pour laquelle le
backend convertit systématiquement les booléens en chaînes `"on"`/`"off"`
avant écriture (convention correcte pour la quasi-totalité des interrupteurs
de l'API webOS). Cette clé attend en réalité un **booléen JSON natif** : la
conversion automatique produisait `"off"`, systématiquement refusé
(« No matched extended item »). Confirmé en écrivant directement le booléen
natif, qui est accepté.

**Correction.** `backend/app/arbre.py` exempte désormais `parentalControl`
de la conversion automatique (`CLES_BOOLEENNES_NATIVES`). Aucune autre clé
de ce type n'a été identifiée à ce jour.
