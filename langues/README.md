# Packs de langue cible

Un pack rassemble **tout ce qui, dans une traduction, dépend de la langue de sortie**.
Ajouter une langue au projet, c'est ajouter un dossier : aucun code Python à toucher.

```yaml
# config.yaml
langues:
  cible: fr        # le pack à utiliser
  packs: langues   # où les chercher
```

## Anatomie d'un pack

```
langues/<code>/
├── pack.yaml              métadonnées, typographie, styles de sortie, consignes
├── prompts/               les HUIT prompts système — obligatoires
│   ├── traducteur.md        ┐
│   ├── correcteur.md        │ light novel
│   ├── terminologue.md      │
│   ├── glossariste.md       │
│   ├── mise_en_page.md      ┘
│   ├── manga_traducteur.md    ┐
│   ├── manga_contexte.md      │ manga
│   └── manga_onomatopees.md   ┘
├── style_guide.md         conventions typographiques, données au modèle en contexte
└── templates/             facultatif
    ├── reference.docx       gabarit Word
    └── epub.css             feuille de style epub/pdf
```

**Les huit prompts sont obligatoires.** Un pack auquel il en manque un est refusé au
démarrage, en le nommant. Ce n'est pas de la rigidité : servir le prompt français d'un agent
absent produirait un tome dont les onomatopées seraient françaises et le reste anglais — six
heures de GPU pour un résultat inutilisable, et rien dans le journal pour dire pourquoi.

Les `templates/`, eux, sont facultatifs : un `reference.docx` est déjà un réglage que
l'utilisateur cale sur son propre document (`rendu.reference_docx`), et un pack qui n'en
fournit pas lui laisse simplement la main.

## `pack.yaml`

Voir [`fr/pack.yaml`](fr/pack.yaml), qui est commenté ligne à ligne. Les blocs :

| Bloc | Rôle |
|---|---|
| `code`, `nom` | identité. `nom` est ce qu'on écrit **au modèle** (« français »), jamais un code ISO — les modèles raisonnent sur des noms de langue |
| `typographie` | guillemets, tiret de dialogue, fin de phrase, verbes de parole, titre du guide de style |
| `styles_word` | noms XML des styles de `reference.docx`. `rendu.styles` de `config.yaml` **prime** : il est calé sur le document de l'utilisateur |
| `classes_css` | classes de `epub.css` |
| `consignes` | fragments de message injectés par le code (voir plus bas) |

### Le cas délicat : `verbes_de_parole`

Cette clé sert à décider si l'incise qui suit une réplique lui reste **collée** :
« — Viens, dit-il. » est un seul bloc de dialogue, pas une réplique suivie d'une narration.

C'est un **lexique**, pas un caractère à paramétrer, et cette construction n'existe pas dans
toutes les langues : l'anglais écrit `"...," he said`, sans inversion ni conjugaison à
énumérer.

> **Si ta langue n'a pas cette construction, laisse la clé absente.** Le rendu n'essaiera
> alors pas de coller d'incise — ce qui vaut infiniment mieux que de le faire selon des règles
> françaises.

## Les consignes

Certains fragments de message sont construits **par le code**, pas par les prompts, parce
qu'ils sont injectés **conditionnellement** : la romanisation ne part que sur un pivot CJK, la
naturalisation dépend de `naturalisation.intensite`, un séparateur de planche n'existe qu'en
mode par lots. Un pack non français **doit les déclarer toutes**.

La liste de référence est `core.langues.CONSIGNES_CONNUES`, et deux tests la tiennent à jour :
`tests/test_langues_pack.py` vérifie qu'aucune clé employée par le code n'y manque, et
`tests/test_langues_pack_en.py` qu'aucune ne manque au pack `en`.

### Le socle et le light novel

| Clé | Quand elle sert |
|---|---|
| `naturalisation_minimale` | `naturalisation.intensite` ≤ 0,15 |
| `naturalisation_legere` | ≤ 0,45 |
| `naturalisation_moderee` | ≤ 0,75 |
| `naturalisation_marquee` | au-delà |
| `titre_chapitre` | traduction du titre d'un chapitre |
| `romanisation_rendu` | ligne « `nom` = … » de la consigne CJK du terminologue |

### Le chemin manga (lot 15)

Le prompt d'une planche n'est pas un fichier : il est **assemblé ligne à ligne** par
`manga/orchestrator_manga.py`. Ces fragments-là décident réellement de ce que le modèle
reçoit, et ils étaient tous écrits en dur, en français, dans du Python. Leur texte français
vit désormais dans `manga/consignes.py` (et `manga/relecture.py` pour le relecteur), à son
site d'appel ; un pack les surcharge par les clés ci-dessous.

| Clé | Quand elle sert |
|---|---|
| `traduction_unitaire` | retraduction d'une bulle isolée (manga, éditeur) |
| `traduction_unitaire_place` | gabarit de place, dans ce même prompt |
| `traduction_unitaire_replique` | en-tête de la réplique, dans ce même prompt |
| `manga_bulles_entete` | en-tête de la liste numérotée d'une planche |
| `manga_gabarits_entete` | en-tête du bloc « place disponible par bulle » |
| `manga_gabarit_ligne` | une ligne de ce bloc |
| `manga_precedentes_entete` | en-tête des répliques des planches précédentes |
| `manga_precedente_ligne` | une ligne de ce bloc |
| `manga_origine_planche` | « Planche N−1 », l'origine d'une de ces lignes |
| `manga_separateur_planche` | « — Planche 42 (bulles 1 à 7) — », en mode par lots |
| `manga_lot_consigne` | la consigne de numérotation continue d'un lot |
| `manga_ordre_droite_gauche` / `manga_ordre_gauche_droite` | le sens de lecture annoncé |
| `manga_groupe_entete` | « — Groupe N — » |
| `manga_type_pensee` / `manga_type_recitatif` / `manga_type_cri` | la mention de forme d'une bulle |
| `manga_structure_note` | ce que valent groupes, types et étiquettes de locuteur |
| `manga_image_planche` | « L'image jointe n° 2 est la planche 42 » |
| `manga_image_zone` | la même chose pour une zone hors bulle |
| `manga_crops_entete` | en-tête de la seconde tentative en mode `cible` |
| `manga_echantillon_entete` | échantillon du tome, pour la fiche de contexte |
| `manga_hors_bulle_entete` | en-tête des zones hors bulle (onomatopées) |
| `manga_relecteur` | la consigne de mandat du relecteur |
| `manga_relecteur_manques` / `manga_relecteur_manque_ligne` | termes du glossaire perdus |
| `manga_relecteur_source` / `manga_relecteur_rendu` | les deux listes qu'il compare |
| `legende_illustration_ia` | la légende sous une illustration générée insérée dans un tome |

⚠ **`legende_illustration_ia` n'est pas un fragment de prompt : c'est du texte que LE LECTEUR
verra**, sous chaque illustration générée par IA insérée dans un tome
(`illustration.inserer_dans_sorties`). Elle doit donc être écrite dans la langue du tome, et
non « adaptée » : c'est une mention de transparence, pas une consigne de style. Elle n'a pas
d'interrupteur — `core/insertion.py` lève sur une légende vide, et un pack qui oublierait la
clé retombe sur le texte français plutôt que sur rien.

⚠ **Les gabarits portent des champs** — `{langue}`, `{planche}`, `{budget}`, `{groupe}`… —
et le code n'en fournit qu'un jeu fini. Un champ inconnu ou une accolade mal fermée fait
**refuser le pack au démarrage** (`manga.consignes.verifier`), avec la liste des champs
disponibles : jamais au milieu d'un run de six heures.

⚠ **Quatre noms qu'un pack ne doit PAS traduire** : `registre`, `accord`, `contradiction`,
`glossaire`. Ce sont les noms de règle que le relecteur doit citer, et `manga/relecture.py`
les compare littéralement — une règle traduite est une proposition rejetée sans être lue.

Une clé absente rend le texte français resté à son site d'appel dans le code. Pour `fr` c'est
correct — et c'est pourquoi `fr/pack.yaml` déclare `consignes: {}`. Pour tout autre pack,
c'est un **oubli visible** : la consigne française sortira, et se remarquera.

## Ajouter une langue

1. `cp -r langues/fr langues/<code>`
2. Éditer `pack.yaml` : `code`, `nom`, la typographie, et **toutes les consignes**
   (`core.langues.CONSIGNES_CONNUES` en donne la liste à jour ; les tests la vérifient).
3. Traduire les prompts — les huit requis, plus `manga_relecteur.md` si tu veux pouvoir
   activer la relecture. **Adapter, pas traduire mot à mot** : les consignes de registre,
   de politesse et de rendu des honorifiques japonais diffèrent radicalement d'une sortie
   française à une sortie anglaise. Un prompt est le code source de la voix de la traduction.
4. Traduire `style_guide.md`, et reporter son titre dans
   `typographie.titre_guide_de_style` — c'est lui que cherche le garde-fou « le modèle a
   régurgité le guide de style ».
5. Fournir `templates/` si la langue a besoin de ses propres gabarits, sinon les omettre.
6. `python run.py --check` : le bloc « Langue cible » dit quel pack sert et d'où viennent
   réellement les fichiers.

### ⚠ Aucun exemple tiré d'une œuvre

Les prompts et le guide de style **ne doivent contenir aucun nom de personnage, de lieu ni
aucune réplique d'une œuvre précise**. Un exemple concret dans une instruction se fait
recopier littéralement dans une traduction — c'est un défaut mesuré sur ce projet, pas une
précaution théorique. La règle vaut pour tous les packs.

## ⚠ Ce qui reste en français dans les messages

Certains **libellés de structure** sont émis par le code, pas par les prompts, et sont donc
encore français quel que soit le pack :

| Libellé | Émis par |
|---|---|
| `# CONSIGNE DE NATURALISATION` | `pipeline/orchestrator.py` |
| `# SOURCE(S) ÉTRANGÈRE(S)` | `pipeline/orchestrator.py` |
| `[FORCÉ]`, `[NE PAS TRADUIRE]`, `[À ROMANISER]` | `core/glossary.py` |
| `variantes :`, `mot(s) source à repérer :`, `jamais :` | `core/glossary.py` |
| `### PERSONNAGES`, `### LIEUX`… en ENTRÉE du glossariste | `core/glossary.py:to_sectioned` |

Ce n'est pas un oubli : les trois tags entre crochets sont **relus** par des garde-fous
(`pipeline/orchestrator.py`, `pipeline/render.py`), donc les traduire demande de changer
l'émission *et* la lecture, des deux côtés, en même temps.

**Conséquence pour un pack non français : nomme-les tels quels dans tes prompts.** Écrire
« the section headed `# FOREIGN SOURCES` » décrirait au modèle une section qu'il ne verra
jamais — pire qu'un libellé français, qu'il comprend très bien. `langues/en/` le fait, en
tête de chaque prompt concerné.

En SORTIE, en revanche, tu peux écrire tes sections en anglais : le parseur de glossaire
(`core/glossary_build.py`) accepte les deux jeux de mots-clés, en-têtes comme noms de champs
(`gender:`, `variants:`, `source_terms:`, `forbidden:`, `translate:`).

## Le glossaire

Le glossaire est **multi-cibles** : un même terme source porte un rendu par langue de sortie.

```yaml
personnages:
  - termes_source: [魔王]
    description: Souverain des armées du gouffre.
    cibles:
      fr: {nom: Roi-démon, pluriel: Rois-démons, genre: masculin}
      en: {nom: Demon King}
```

Sous `cibles.<code>` va ce qui décrit le **rendu** — `nom`, `pluriel`, `genre`, `variantes`,
`interdits`, `force`. Un genre masculin ne dit rien de l'anglais, et une forme interdite en
français ne l'est pas en anglais. Au niveau de l'entrée reste ce qui décrit **l'entité** :
`termes_source` (la graphie d'origine), `traduire`, `role`, `description`.

⚠ **Enregistrer dans une cible n'efface pas les autres.** Traduire un tome vers l'anglais
laisse le travail français intact — c'est l'invariant central du format.

Un glossaire à l'ancien format est **migré automatiquement** à la première lecture, avec une
sauvegarde `glossaire.yaml.avant-multicibles.bak` écrite avant toute réécriture.

### `accord:`

Le forçage déterministe des entrées `force: true` remplace une forme bannie par la forme
retenue. En français, cela demande d'accorder le déterminant et de réparer l'élision
(« l'infirmière » → « **la** médecin de combat », pas « l'médecin de combat »).

| Valeur | Pour |
|---|---|
| `francais` | langues à genre grammatical et élision |
| `aucun` | langues sans accord — l'anglais |

> ⚠ `aucun` est une réponse **complète**, pas une implémentation en attente. L'anglais n'a ni
> genre, ni élision, ni déterminant à réécrire : le forçage s'y réduit à la substitution, ce
> qui est exactement ce qu'il doit être.

Le principe vaut pour toute implémentation future : **le déterministe ne doit jamais
introduire une faute que le modèle n'aurait pas faite.** En français, un remplacement dont le
genre est incertain est refusé et signalé, jamais rendu fautif.
