# PLAN 27 — L'atelier dans l'interface, et ce qui sort du dossier

> **Lire `00-CONTEXTE-AGENT.md` puis `README-ILLUSTRATION-23-27.md` d'abord.**
>
> **Nature attendue** — **MINEUR**. Nouvelles capacités d'interface, insertion opt-in, défaut
> inchangé. Le `PLAN-18` (2.9.0) est le précédent exact : « aucun changement au pipeline… d'où le
> MINEUR ».
>
> **Charge estimée** — 10 jours.
>
> **⚠ Prérequis : `PLAN-25` conclu positivement et `PLAN-26` livré.** Un atelier qui présente des
> images qui ne ressemblent à personne est pire qu'aucun atelier : il donne à croire que le problème
> est réglé.
>
> **Recommandé avant** : `PLAN-19` (le système visuel). Ce lot ajoute un panneau ; le styler deux
> fois est du travail perdu.
>
> **La forme de l'atelier est imposée par le déroulé en deux phases** (`PLAN-24` étape 0.1 bis) :
> l'écran central de ce lot n'est pas la galerie, c'est **l'écran de relecture du prompt**. Une
> interface qui enchaînerait les deux phases d'un seul bouton supprimerait la porte humaine, donc la
> propriété qui rend cette brique défendable.

---

## 1. Ce que 2.9.0 a déjà posé, et qu'il ne faut pas refaire

Le `PLAN-18` a livré en 2.9.0 : l'état vide à deux boutons, `QFileDialog` (il n'y en avait **zéro**
dans tout `gui/` avant), le glisser-déposer (**zéro** `setAcceptDrops` avant), la persistance d'état
(**zéro** avant), cinq menus au lieu d'un, la création de projet via `manga/creation_projet.py`, et
la copie longue passée par le fil de travail pour ne pas geler la fenêtre.

**Réutilisez tout.** L'atelier est un panneau de plus dans une coquille qui existe :

| Brique existante | Ce qu'elle donne à l'atelier |
|---|---|
| `gui/travailleur.py` | le fil de travail, et `progression_de_stage` — une génération de 8 images ne gèle pas la fenêtre |
| `gui/pellicule.py`, `gui/cache_apercu.py` | la galerie de vignettes et son plafond mémoire (`gui.apercu.plafond_mo`) |
| `gui/dialogues.py`, `gui/actions.py` | les boîtes et les actions de menu |
| `gui/reglages.py` | l'écran de réglages, où `illustration.actif` se coche |
| règle de couche `gui/__init__.py` | **toute la logique va dans `illustration/`, en Python nu, testable sans PySide6** |

⚠ **La règle de couche est le piège de ce lot.** Un atelier attire naturellement la logique dans la
fenêtre : la sélection du personnage, le choix du cadrage, la file d'attente, le verdict de
ressemblance. Rien de cela n'est du Qt. `gui/` ne doit contenir que des fenêtres, des scènes et des
signaux — et `ci.yml` mesure déjà l'effet de PySide6 (**2 007 tests collectés avec, 1 879 sans**,
soit **128 tests d'interface**) : si votre lot ajoute 40 tests dont 35 exigent Qt, la règle a été
violée.

---

## 2. Étape 0 — mesurer l'attente, puis dessiner

### 0.1 — Combien de temps l'utilisateur attend-il ?

Reprenez les chiffres du `PLAN-24` étape 0.3 : secondes par image, pic de VRAM, et **le temps de
bascule du LLM** (`ollama_unload` + chargement du modèle d'image + rechargement du LLM à la fin).

Ce chiffre décide de l'interface, et lui seul :

| Temps par image | Interface juste |
|---|---|
| < 10 s | génération à la demande, l'utilisateur regarde |
| 10-60 s | file d'attente avec progression, l'utilisateur fait autre chose |
| > 60 s | **run par lot**, comme un tome : on lance, on revient. Une barre de progression qui tourne trois minutes est un défaut d'ergonomie, pas une barre de progression |

**Ne dessinez pas avant d'avoir ce chiffre.** C'est exactement l'erreur que `PLAN-18` a évitée en
faisant passer la copie d'archive par le fil de travail après avoir mesuré le poids réel des sources.

### 0.2 — Où vont les fichiers ?

Proposition, à trancher :

```
build/<Projet>/<Tome>/illustrations/
    <personnage>-<cadrage>-<graine>.png
    <personnage>-<cadrage>-<graine>.provenance.json
    rejetees/…                     # gardées, pas supprimées — voir L27.3
```

⚠ **`build/` est régénérable par contrat** — `.gitignore` l'écrit : « Sorties de traduction
(régénérables : `python run.py` / `run_manga.py`) ». Une image générée en 40 secondes de GPU, retenue
par un humain, **n'est pas régénérable** : la même graine sur un autre modèle ne rendra pas la même
image. Deux options, et il faut choisir explicitement :

1. **sous `build/`** — cohérent avec « tout ce qui est produit », mais un `rm -r build/` (que le
   dépôt recommande lui-même après un MAJEUR) détruit le travail de sélection ;
2. **sous `sources/<Projet>/illustrations/`** — survit à la suppression de `build/`, reste exclu de
   git, et c'est là que vit déjà le travail écrit à la main (les glossaires).

**Recommandation : les images retenues sous `sources/`, les candidates sous `build/`.** Le geste
« je garde » déplace le fichier. C'est aussi ce qui donne un sens fort à « garder ».

---

## L27.1 — Le panneau « Atelier »

Un onglet, à côté de « Planches » et « Runs ». Contenu minimal, dans cet ordre :

1. **liste des personnages** du projet, avec une pastille d'état : sans référence / référence
   proposée / **référence validée** — reprise directe de `bible.yaml:valide_par_humain`. Un
   personnage sans référence validée est **grisé et non cliquable**, avec l'infobulle qui dit quoi
   faire (le `PLAN-25` L25.2 refuse déjà de générer : l'interface doit le dire avant, pas après) ;
2. **cadrage** : trois boutons (visage / buste / entier), défaut = celui que le `PLAN-25` L25.1 a
   mesuré comme le meilleur ;
3. **nombre d'images** et graine (vide = aléatoire, remplie = reproductible) ;
4. **galerie** des résultats, avec sur chaque vignette **les trois verdicts** du `PLAN-25` L25.1 —
   ressemblance, nouveauté, **style** — et le badge « générée par IA » **non masquable**. Le verdict
   de style porte le descripteur qui décroche, pas un score nu : « saturation 2,4× la signature du
   tome » se comprend, « style 0,63 » ne se comprend pas ;
5. un bouton « Ouvrir la bible » qui renvoie vers `tools/bible.py --revue` ou son équivalent
   graphique — parce que 100 % des refus de génération se règlent là.

**L'état vide est un écran, pas un aplat gris.** C'est la leçon explicite du `PLAN-18` : la première
version de l'interface affichait deux listes vides et une phrase de journal décrivant un geste à
faire ailleurs. Ici l'état vide dit : « aucun personnage n'a de référence visuelle validée », avec le
bouton qui y mène.

## L27.1 bis — L'écran de relecture du prompt, et c'est le cœur du lot

À la fin de la phase 1, l'atelier présente `requete.yaml` — pas son chemin, son **contenu** :

1. **le prompt, dans un champ éditable multiligne**, avec le prompt d'origine conservé à côté (ou
   restaurable) : une correction doit être annulable sans relancer la phase 1, qui coûte des minutes
   de LLM ;
2. **le prompt négatif**, éditable lui aussi, chaque terme du gabarit avec son motif en infobulle ;
3. **les images de référence en vignettes**, chacune avec sa case « retenue » et son **motif** de
   sélection écrit par la phase 1 (`PLAN-26` L26.0) — c'est ce motif qui rend le décochage informé.
   ⚠ **Deux groupes visuellement distincts** : `references` (identité) et `ancrages_style` (registre
   du tome). Un utilisateur qui décoche une ancre de style doit voir qu'il ne touche pas à
   l'identité, et réciproquement ;
4. **la traçabilité des attributs** : chaque fragment du prompt avec la phrase du chapitre qui le
   justifie, dépliable. Un attribut sans source ne devrait pas être là ; s'il y est, l'écran le
   montre en anomalie ;
5. **les canaux structurés, s'il y en a un de livré** (`PLAN-26` étape 0.4) : masques d'entités ou
   image de contrôle, affichés en superposition sur une vignette, avec la possibilité de **désarmer
   le canal** — pas de l'éditer. Un éditeur de masque est un lot à lui seul, et il n'est pas celui-ci ;
6. **un bouton « Valider et générer »**, et **un bouton « Annuler »** qui laisse le `requete.yaml`
   sur le disque — un abandon ne détruit pas le travail du LLM.

⚠ **`valide: false` reste le défaut, y compris ici.** L'interface écrit `valide: true` au moment du
clic, et le sidecar de provenance enregistre *qui a validé, quand, et le prompt avant/après
correction* (`PLAN-24` L24.3). Sans ce couple, la porte humaine n'est qu'un écran.

⚠ **Aucun « générer directement » n'est ajouté**, ni bouton, ni raccourci, ni option de réglages —
pas même pour rejouer une requête déjà validée : le rejeu passe par `--rejouer` sur un sidecar
existant, donc sur un prompt déjà validé une fois.

## L27.2 — Le fil de travail, la bascule de modèle, et l'annulation qui décharge la VRAM

**La barre de progression a deux phases, et elles n'ont pas le même coût.** Affichez-les
séparément — « préparation (LLM) », « bascule de modèle », « génération (image) » — parce que le
chiffre mesuré au `PLAN-24` étape 0.1 bis peut faire de la bascule le poste le plus long. Une barre
unique qui reste bloquée sur « 30 % » pendant le déchargement du LLM est un défaut d'information, pas
un défaut de vitesse.

Une génération passe par `gui/travailleur.py`. Deux exigences que le dépôt tient déjà ailleurs et
qu'il faut tenir ici :

- **annulation propre** : le modèle est **déchargé de la VRAM avant de rendre la main**, et le
  déchargement est blindé contre un second Ctrl+C ou un second clic. `docs/README.fr.md` documente
  précisément ce comportement pour le LLM, et la raison est mesurée : un abandon sale a fait chuter
  le débit de **25 à 18 tok/s** en laissant le pilote AMD dans un mauvais état. Un modèle d'image de
  12 Go abandonné salement est le même défaut en pire ;
- **le LLM revient** : si la brique a déchargé `yume-27b` pour faire sa place, elle le recharge à la
  fin, y compris sur annulation et sur erreur. Sinon la traduction suivante paie le rechargement sans
  que l'utilisateur comprenne pourquoi.

## L27.3 — Garder, jeter, et ne rien perdre

- **Garder** : déplace l'image et son sidecar vers l'emplacement pérenne de l'étape 0.2, et écrit
  la référence dans `bible.yaml` sous une clé **distincte** de `references[]` —
  `images_generees[]` — parce qu'une image générée **ne doit jamais devenir la référence d'une
  génération suivante.** ⚠ C'est le point le plus important de ce lot : reboucler une sortie dans
  l'entrée fait dériver le personnage à chaque tour, et la dérive est invisible image par image.
  Un test doit rendre ce rebouclage **impossible**, pas seulement improbable.
- **Jeter** : déplace vers `rejetees/`, ne supprime pas. Un rejet est une donnée : le `PLAN-25`
  L25.4 en a besoin pour mesurer. Une purge explicite existe, elle est un geste séparé.
- **Rien n'est jamais réécrit.** Le dépôt a déjà ce contrat, écrit noir sur blanc pour l'édition :
  « Garder ma version » retient la réplique dans `traduction_manuelle.json` et « le pipeline ne la
  réécrira jamais » (`docs/README.fr.md`). Transposez-le — un nom de fichier qui existe déjà obtient
  un suffixe, jamais un écrasement.

## L27.4 — L'insertion dans les sorties, opt-in et étiquetée

Le tuyau existe déjà et il est bon : `pipeline/images.py` réinjecte les images à leur **position
proportionnelle** dans le texte français via les marqueurs `<!-- IMG: chemin -->` ou
`<!-- IMG: chemin|attrs -->`, et `manifest_for_chapter` rend `[(fraction, contenu_marqueur)]`.

**Ce que ce lot ajoute, et rien de plus :** une clé `illustration.inserer_dans_sorties: false` qui,
armée, insère les images **retenues** à une position choisie par l'utilisateur (début de chapitre par
défaut), avec une **légende obligatoire** — « Illustration générée par IA — ne fait pas partie de
l'œuvre originale » — dont le texte vit dans le pack de langue.

⚠ **Quatre garde-fous, tous non négociables :**

1. **Défaut `false`.** Un tome relancé sans que l'utilisateur ait rien demandé sort **identique**.
2. **La légende n'est pas désactivable.** C'est la lecture de l'art. 50 de l'AI Act retenue au
   `PLAN-24` étape 0.2, transposée à la sortie visible : le marquage machine est dans le PNG, la
   mention lisible est sous l'image.
3. **`RAPPORT.md` liste les images insérées**, avec leur personnage et leur graine.
4. **Aucune insertion dans un fichier destiné à autrui.** L'usage arrêté est privé (README de série
   §1). Le lot n'ajoute **aucune** fonction d'export, de partage, de publication ou de mise en ligne,
   et n'en facilite aucune.

⚠ **Vérifiez l'interaction avec `langues.priorite_images`** avant d'écrire une ligne :
`pipeline/images.py` documente que la source d'images est **une seule langue à la fois**, jamais un
mélange, « qui provoquerait des collisions de noms de fichiers (chaque document renumérote ses médias
depuis 1) et donc de mauvaises images ». Une illustration générée n'appartient à aucune langue
source : donnez-lui un espace de noms qui ne peut pas collisionner avec la renumérotation d'un
document, et ajoutez le test de collision.

## L27.5 — Le nettoyage, et le poids sur le disque

Une commande et un bouton : combien pèsent les illustrations du projet, combien de candidates, combien
de rejetées, et une purge des rejetées avec confirmation. À 1 à 3 Mo par PNG et 8 images par
personnage, un projet à 119 personnages (`manga D`, chiffre réel) atteindrait ~2 à 3 Go. Ce
n'est pas hypothétique : publiez le calcul dans le document du lot.

---

## 3. Les critères de ce lot

1. Le chiffre de l'étape 0.1 est publié et l'interface choisie **correspond à la tranche** du tableau.
1 bis. L'écran de relecture montre prompt, prompt négatif, vignettes de référence **avec leur
   motif**, et la source de chaque attribut. Un test vérifie qu'aucun chemin de l'interface ne peut
   lancer la phase 2 sans passage par cet écran.
1 ter. La progression distingue préparation / bascule / génération, avec le temps réel de chacune.
2. Un personnage sans référence validée est grisé, avec l'infobulle qui dit quoi faire. Aucune
   génération ne part et aucun message d'erreur n'apparaît **après** le clic.
3. Toute la logique de l'atelier est dans `illustration/`, testable sans PySide6. Comptez et publiez
   vos tests neufs **avec et sans Qt** — le dénominateur existe déjà (2 007 / 1 879).
4. L'annulation décharge la VRAM et recharge le LLM. Testé, y compris sur erreur.
5. Une image générée **ne peut pas** devenir une référence de génération. Test dédié.
6. Un rejet ne supprime rien.
7. `illustration.inserer_dans_sorties: false` par défaut ; un tome relancé est **iso-octet** sur ses
   sorties, empreinte SHA-256 de `config.yaml` annoncée.
8. La légende est présente dans les trois formats de sortie (DOCX, EPUB, PDF) quand l'insertion est
   armée, et elle n'est pas désactivable. Vérifié format par format — les styles Word réels de
   `langues/<code>/templates/reference.docx` ont un contrat, ne le cassez pas pour une légende
   (⚠ ce n'est **pas** `templates/reference.docx`, voir README de série §8).
9. Le test de collision de noms avec la renumérotation des médias de document existe.
10. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans poids ni GPU.
11. `docs/atelier-illustration-<date>.md` reprend ces critères un par un, y compris les non tenus,
    et publie le calcul de poids disque et ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Aucune fonction de partage, d'export public, de mise en ligne, de génération de planche
  publiable, ni d'aide à la diffusion. L'usage arrêté est privé, et l'outil ne doit pas rendre facile
  ce que la décision a exclu.
- Aucune retouche de l'image générée dans l'interface (recadrage, correction). Si le besoin apparaît,
  c'est un lot séparé, et il rouvre la question du §4 du README de série.
- Aucun changement au pipeline de traduction. Comme le `PLAN-18` : « aucun prompt, aucun seuil,
  aucune étape, aucun format de sortie » — sauf la clé d'insertion, désarmée.
