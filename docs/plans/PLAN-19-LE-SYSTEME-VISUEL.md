# PLAN 19 — Le système visuel : une interface qui a l'air d'un logiciel

> **Lire `00-CONTEXTE-AGENT.md` d'abord.**
>
> **Nature attendue** — MINEUR. Aucun cache, aucune clé de config supprimée. Le comportement
> ne change pas ; l'apparence, si.
>
> **Charge estimée** — 10 jours, dont 2 pour la passe d'accessibilité (L19.6) qui est la plus
> facile à sacrifier et la plus difficile à rattraper ensuite.
>
> **Faire `PLAN-18` d'abord** si vous devez choisir. Styler une interface dont il manque la
> moitié des actions revient à peindre une pièce sans porte. Les deux peuvent en revanche
> avancer en parallèle sur deux branches : celui-là touche la structure, celui-ci les tokens.

---

## Le constat : il n'y a pas de système de design, il y a vingt couleurs littérales

Répondu point par point, tout vérifié par recherche sur `gui/` :

| Question | Réponse |
|---|---|
| Feuille de style QSS ? | **Non.** Zéro fichier `.qss` dans le dépôt |
| Palette, thème ? | **Non.** Zéro `QPalette`, zéro `setPalette`, zéro `styleHints` |
| Mode sombre / clair ? | **Non.** Aucune bascule, aucune détection du thème système |
| Fichier de ressources ? | **Non.** Zéro `.qrc`, zéro `.svg`, zéro `.png`, zéro `.ico` |
| Icônes ? | **Aucune.** Un seul `QIcon`, généré à la volée : un aplat `#e9e9ec` de 200×300 comme placeholder de vignette. Aucun `setWindowIcon` — l'application porte l'icône Qt par défaut dans la barre des tâches |
| Style Qt ? | **Aucun `setStyle`.** Donc style natif de la plateforme (`windowsvista`), jamais Fusion |
| `setStyleSheet` | **quatre**, tous inline, tous sur un seul widget |
| Couleurs littérales | **vingt occurrences, dix-neuf valeurs distinctes** (`#d09030` sert deux fois), dans **quatre** fichiers, sans aucun point de définition commun |
| Tailles de police | **trois** valeurs, dont deux en `px`, une en `pt`. Aucune échelle |
| `setAccessibleName` | **zéro** |
| `setTabOrder` | **zéro** |

### Le défaut qui se voit à l'œil nu, et qui explique tout le reste

Les couleurs du journal (`info` à `#d2d2d2`) et les gris `#9aa` / `#7aa` sont des valeurs de
**thème sombre**. Le fond du canevas l'est aussi (`QColor(40,40,44)`). Mais **aucun thème sombre
n'est appliqué** : le style natif de Windows est clair. Donc un texte `#d2d2d2` s'affiche sur un
`QPlainTextEdit` blanc.

L'application mélange deux hypothèses de fond contradictoires, et le seul endroit qui nomme
l'idée d'un thème est une fonction de la pellicule qui rend `None` pour dire « couleur par
défaut du thème ». Elle a raison, et elle est seule.

---

## Étape 0 — Relever, et décider une seule chose

Pas de code. Un document, et **une décision** que rien d'autre ne pourra rattraper ensuite.

1. **Le relevé.** Les vingt occurrences de couleur, les 4 `setStyleSheet`, les 3 tailles de
   police, et **toutes**
   les valeurs d'espacement et de dimension codées en dur — la liste est longue : taille de
   fenêtre, marges de layouts, minimums de largeur, tailles de splitters, hauteurs maximales de
   champs, grille de la pellicule, côté des poignées, seuil de tracé. Une ligne par valeur, avec
   `fichier:ligne` et ce qu'elle fait.
2. **Des captures d'écran de l'existant**, avant toute modification. Deux au minimum : l'onglet
   « Planches » avec une planche ouverte, et l'onglet « Runs ». Elles vont dans le document du
   lot. C'est la seule preuve du « avant » qui existera, et une interface ne se mesure pas avec
   `tools/banc.py`.
3. **La décision : clair d'abord, ou sombre d'abord ?**

   Elle n'est pas cosmétique. Le canevas est sombre aujourd'hui — `QColor(40,40,44)` — et c'est
   **juste** : un fond sombre autour d'une planche évite d'éblouir et fait ressortir le dessin,
   c'est la convention de tous les outils d'image. Mais les listes, les formulaires et les
   champs de saisie sont clairs, parce que le style natif l'est.

   **Recommandation : les deux thèmes, avec le canevas toujours sombre.** C'est-à-dire trois
   surfaces et non deux — `chrome` (menus, panneaux, formulaires), `canevas` (toujours sombre),
   `journal` (monospace, contrasté). Un outil d'image a le droit d'avoir un canevas qui ne suit
   pas le thème ; il n'a pas le droit d'avoir un formulaire illisible.

   ⚠ Si vous décidez autrement, écrivez-le et assumez-le. Ce qui n'est pas acceptable est
   l'état actuel : ni l'un ni l'autre, par accident.

---

## L19.1 — Un fichier de tokens, et un seul

**À faire.** Un module Python — pas un YAML, pas un QSS — qui déclare les tokens et rien
d'autre. Python parce que le canevas en a besoin sous forme de `QColor`, la pellicule sous forme
de chaîne `#rrggbb`, et le QSS sous forme de texte : un seul endroit, trois consommateurs.

```
gui/theme.py
├── Palette          — les couleurs nommées PAR RÔLE, jamais par valeur
├── Espacement       — l'échelle (4, 8, 12, 16, 24, 32) et rien entre
├── Typo             — l'échelle de corps, en points, dérivée de la police système
├── qss(palette)     — assemble la feuille de style
└── appliquer(app)   — pose le style, la palette et la feuille
```

**Nommer par rôle, pas par valeur.** `Palette.avertissement`, pas `Palette.orange`. C'est ce qui
permet à un thème clair et un thème sombre de partager le même code d'appel — et c'est
exactement ce que les vingt couleurs actuelles ne font pas.

Les rôles à couvrir, tirés de l'usage réel :

| Rôle | Ce qu'il remplace aujourd'hui |
|---|---|
| `fond`, `fond_eleve`, `bordure`, `texte`, `texte_faible` | les gris `#9aa`, `#7aa`, `#d2d2d2` |
| `accent`, `accent_texte` | rien — il n'y a pas de couleur d'accent |
| `avertissement`, `erreur`, `succes`, `information` | les quatre couleurs du journal |
| `canevas_fond` | `QColor(40, 40, 44)` |
| `zone`, `zone_choisie`, `zone_vide`, `zone_main`, `zone_trace` | les cinq couleurs du canevas |
| `pastille_perimee`, `pastille_main`, `pastille_absente` | `#d09030`, `#6aa6d8`, `#777` |
| `vignette_attente` | `#e9e9ec` |
| `poignee_contour`, `numero_texte`, `numero_fond` | `QColor(30,30,34)`, `QColor(20,20,20)`, `QColor(255,210,90,230)` — les trois que le relevé initial avait manquées |

⚠ **Vérifiez le contraste, ne l'estimez pas.** Un rapport de contraste se calcule (WCAG, luminance
relative). Écrivez la fonction, mettez un test dessus, et publiez le tableau des paires
texte/fond avec leur rapport pour les deux thèmes. Une couleur choisie à l'œil sur un écran est
illisible sur un autre — c'est la même discipline que le reste du dépôt appliquée à un pixel au
lieu d'un token.

**Cible : 4,5:1 pour le texte courant, 3:1 pour les gros textes et les bordures d'état.** Si une
couleur d'état ne peut pas atteindre 3:1 sur les deux fonds, changez la couleur, pas la cible.

---

## L19.2 — Poser `Fusion`, et pourquoi

`QApplication` n'appelle jamais `setStyle`. Le style est donc `windowsvista`, qui **ignore une
grande partie du QSS** et ne respecte pas une palette. C'est la raison technique pour laquelle
les quatre `setStyleSheet` actuels sont inline sur un widget : c'est le seul endroit où ils
prennent.

`Fusion` est le style Qt neutre, identique sur les trois plateformes, et il respecte à la fois
`QPalette` et le QSS. C'est le prérequis de tout le reste du plan.

⚠ **Fusion change l'apparence de tous les widgets, y compris ceux que vous ne touchez pas.**
Les captures de l'étape 0 servent à voir ce qui régresse : listes, en-têtes, cases à cocher,
listes déroulantes. Prévoyez une passe de vérification visuelle de chaque panneau, et gardez la
possibilité de repasser au style natif par une variable d'environnement — le temps de la mise au
point, pas dans la version livrée.

---

## L19.3 — La typographie, et le défaut Windows caché dedans

Trois valeurs aujourd'hui : `font-size: 11px` deux fois, `setPointSizeF(16)` une fois. Et une
famille : `font-family: Consolas, monospace` pour le journal — **`Consolas` est une police
Windows**. Le repli `monospace` sauve la mise, mais c'est le genre de valeur qui rend un logiciel
« développé sur Windows » visible au premier coup d'œil ailleurs.

**À faire.**

1. **Une échelle, en points, dérivée de la police de l'application** — pas de valeurs absolues.
   Quatre corps suffisent : `petit` (0,85×), `normal` (1×), `grand` (1,15×), `titre` (1,3×). Le
   1× vient de `QApplication.font()`, donc du réglage système, donc de l'utilisateur.
2. **`px` → `pt` partout.** Une taille en pixels ne suit ni le réglage système ni le facteur DPI.
   C'est la cause la plus fréquente d'une interface illisible sur un écran à forte densité, et il
   n'y a aucune raison de la garder.
3. **Une pile de polices monospace multiplateforme** pour le journal, `Consolas` en premier,
   avec des replis nommés et `monospace` en dernier.
4. **Un test.** Que l'échelle rende des valeurs croissantes pour une police de base de 8 pt comme
   de 16 pt. C'est trivial, et c'est ce qui empêche un `max()` mal placé d'écraser l'échelle.

---

## L19.4 — Les icônes, et le piège à éviter

Aucune icône aujourd'hui. Cinq boutons d'outils en **texte seul**, un bouton dont le libellé
complet est `🔒`, et des pastilles en caractères Unicode sans légende.

**À faire.**

1. **Des SVG inline, dans un module Python**, plutôt qu'un `.qrc` compilé. Le projet n'est pas
   empaqueté et ne veut pas l'être — pas de `pyproject.toml`, c'est un choix écrit dans
   `core/version.py`. Une étape de compilation de ressources (`pyside6-rcc`) ajouterait un
   artefact généré à committer et une étape de build à un projet qui n'en a pas.
2. **`currentColor`, ou une teinte appliquée au chargement.** Une icône qui ne suit pas le thème
   est pire qu'un libellé texte. Le plus simple qui marche : le SVG déclare `currentColor`, et
   la fonction de chargement substitue la couleur du token avant de rendre le `QPixmap`.
3. **Icône **et** libellé sur les cinq boutons de mode** (`ToolButtonTextBesideIcon`), pas
   l'icône seule.
   Ces cinq outils font des choses irréversibles hors annulation — « Redessiner » **remet l'OCR
   et la traduction à zéro**, et rien à l'écran ne le distingue d'un simple retaillage. Une
   icône seule ne dira jamais cela.
4. **Un `setWindowIcon`.** Une seule, l'identité du logiciel.
5. **Les pastilles Unicode : les garder.** Elles sont compactes, elles fonctionnent, et le lot 18
   leur livre une légende. Remplacer six glyphes par six SVG dans une grille de vignettes à 150
   éléments coûterait plus qu'il ne rapporte. **En revanche, leur donner la couleur du token** au
   lieu de `#d09030` et `#6aa6d8`.

⚠ **Ne dessinez pas trente icônes.** Douze suffisent : les cinq outils, supprimer, annuler,
refaire, enregistrer, zoom ±, ajuster. Le reste du logiciel n'en a pas besoin, et une icône
médiocre sur une action rare nuit plus qu'un libellé clair.

---

## L19.5 — Les états, qui n'existent pas aujourd'hui

Sans QSS, aucun widget n'a d'état visuel au-delà de ce que le style natif fournit. Or ce logiciel
en a besoin plus que la moyenne, parce qu'il **grise beaucoup** : pendant un run, huit widgets
mutants sont désactivés et les champs passent en lecture seule pour rester lisibles.

Les états à traiter explicitement :

| État | Où il compte |
|---|---|
| `:disabled` | les huit widgets mutants pendant un run — doit rester **lisible**, pas effacé |
| lecture seule ≠ désactivé | un champ en lecture seule doit se distinguer d'un champ désactivé, c'est déjà la logique du code |
| `:checked` | « Comparer au rendu du pipeline » (**qui désactive silencieusement l'édition**), le verrou de cadrage, les cinq outils |
| `:focus` | prérequis de toute navigation au clavier — invisible aujourd'hui |
| `:hover` | sur les vignettes de la pellicule, qui sont cliquables sans le montrer |
| modifié non écrit | le `[*]` du titre est le seul indice ; le lot 18 en ajoute un dans le panneau, celui-ci lui donne sa couleur |

⚠ **Le cas « Comparer au rendu du pipeline » est le plus important de la liste.** Le cocher coupe
toute interaction du canevas — les poignées et les calques disparaissent — et le seul indice est
l'état enfoncé d'un bouton. Le cas voisin du run, lui, affiche « — affichage seul ». Donnez au
mode comparaison **le même bandeau**, et faites-le porter par le token, pas par une chaîne.

---

## L19.6 — L'accessibilité, qui est aussi la navigation au clavier

Ce n'est pas une case à cocher morale : la moitié de ce paragraphe rend le logiciel plus rapide
pour quelqu'un qui l'utilise huit heures par jour.

**L'état.** Six séquences de raccourci pour sept déclarations, `PagePrec`/`PageSuiv`/`Échap`
codés à la main, **29** infobulles — c'est correct. Et : **zéro `setAccessibleName`**, zéro `setTabOrder`, zéro `setFocusPolicy`, zéro
`setWhatsThis`. Aucune alternative clavier aux gestes de canevas : dessiner, retailler, scinder,
déplacer un bloc de texte ne sont accessibles qu'à la souris.

**À faire, par ordre de rapport.**

1. **`setAccessibleName` sur tout widget dont le libellé visible n'est pas un mot** : `🔒`, `−`,
   `+`, `%`, et les trois listes qui n'ont pas de `QLabel` associé. C'est une heure de travail et
   c'est ce qui décide qu'un lecteur d'écran est utilisable ou pas.
2. **Un `setTabOrder` explicite par panneau.** L'ordre actuel est celui de la construction, jamais
   vérifié : sur l'éditeur il traverse recherche → remplacement → bouton → résultats → filtre →
   pellicule → **les quatorze boutons de la barre du canevas** → vue → liste de bulles →
   inspecteur. Un utilisateur qui
   veut passer du champ de réplique au bouton « Retraduire » fait une dizaine de tabulations.
3. **Un anneau de focus visible** (L19.5). Sans lui, les deux points précédents ne servent à rien.
4. **`setFocusPolicy(Qt.NoFocus)` sur ce qui ne doit pas être dans le parcours** — les boutons de
   zoom, par exemple, qui ont des raccourcis.
5. **Les infobulles de menu.** Une infobulle posée sur un `QAction` de menu **ne s'affiche pas**
   par défaut : le texte est écrit et invisible. Utilisez `setStatusTip`, qui va dans la barre
   d'état, ou activez explicitement les infobulles de menu.
6. **Une alternative clavier aux gestes de canevas.** ⚠ **C'est la seule étape de ce plan dont
   j'estime le coût mal cerné.** Déplacer et retailler la zone sélectionnée aux flèches (avec
   `Maj` pour un pas large) est faisable en une journée et couvre l'essentiel. **Dessiner** une
   zone au clavier est un autre problème, qui demande une notion de curseur dans la scène.
   Livrez le déplacement et le retaillage ; écrivez que le dessin n'est pas couvert, plutôt que
   de le prétendre.

---

## L19.7 — Les états vides et les messages

Deux endroits affichent un aplat gris vide et envoient l'explication dans un journal replié : un
tome sans planche traitée, et une planche sans détection.

**À faire.** Un état vide dessiné dans le canevas : un titre, une phrase, et le bouton de
l'action attendue. Le lot 18 fournit les actions ; celui-ci leur donne une place et une forme.
Trois cas : `sources/` vide (lot 18 L18.1), tome non traité, planche sans détection.

Et pour les messages d'erreur : `f"{type(err).__name__} : {err}"` expose un nom de classe Python
à l'utilisateur. Gardez-le dans le journal — il est utile pour un rapport de bug — mais la boîte
de dialogue dit ce qui s'est passé et ce qu'on peut faire.

---

## Critères d'acceptation

| # | Critère |
|---|---|
| 1 | Les vingt occurrences de couleur littérale, les 4 `setStyleSheet` et les 3 tailles de police ne sont plus qu'un import de `gui/theme.py`. **Vérifié par un test** qui échoue si un `#rrggbb` ou un `QColor(...)` littéral réapparaît dans `gui/` hors de `theme.py` |
| 2 | Les deux thèmes existent, le canevas reste sombre dans les deux, et la bascule est dans le menu Affichage |
| 3 | **Le tableau de contraste est publié** : chaque paire texte/fond, son rapport, pour les deux thèmes. Aucune sous 4,5:1 pour du texte courant, aucune sous 3:1 pour une bordure d'état |
| 4 | Plus une seule taille de police en `px` dans `gui/` ; l'échelle dérive de `QApplication.font()` |
| 5 | Captures avant/après de chaque panneau dans le document du lot, pour les deux thèmes |
| 6 | Chaque widget dont le libellé n'est pas un mot a un `setAccessibleName` ; chaque panneau a un `setTabOrder` explicite ; le focus est visible |
| 7 | La zone sélectionnée se déplace et se retaille au clavier. Le dessin au clavier n'est **pas** couvert, et c'est écrit |
| 8 | Les 128 tests d'interface passent, et des tests neufs couvrent : absence de littéral de couleur, monotonie de l'échelle typographique, présence des noms accessibles, calcul de contraste |
| 9 | `ruff check .` et la boucle courte passent |

⚠ **Le critère 8 demande un test que rien ne remplace** : un test qui parcourt les fichiers de
`gui/` et échoue sur toute couleur littérale hors `theme.py`. C'est lui qui empêchera les vingt
couleurs de revenir une par une — et le relevé initial en avait manqué trois, ce qui montre
qu'un inventaire à la main ne suffit pas.

---

## Ce que ce lot ne fait pas

- Aucune action nouvelle, aucun menu nouveau : `PLAN-18`.
- Aucune refonte de la disposition. Trois colonnes et deux onglets, c'est bien : tout est visible
  d'un coup et ça convient à un travail de relecture planche par planche. **Ne réorganisez pas
  ce qui marche** parce que c'est l'occasion.
- Aucune animation, aucune transition. Un logiciel qui fait tourner des inférences ONNX pendant
  deux minutes n'a pas besoin d'animer un panneau.
- Aucun changement au pipeline.

---

## Note sur la maquette

Ce plan décrit un système, pas une image. Si une maquette visuelle est utile avant de coder —
les deux thèmes, les trois surfaces, l'inspecteur, les états — elle se fait **avant** l'étape 0
et sert de référence de relecture. Elle n'est pas un livrable de ce lot et ne doit pas devenir
un troisième chantier.
