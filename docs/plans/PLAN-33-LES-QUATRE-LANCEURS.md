# PLAN 33 — Les quatre lanceurs : un formulaire déclaré, le modèle choisi, les profils

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **MINEUR**. Aucune clé de `config.yaml` ajoutée par ce lot n'est
> obligatoire, et **`config.yaml` n'est jamais réécrit** (interdit 5 du contexte agent, et
> docstring de `gui/lanceur.py`). Tout réglage de run est une mutation du dictionnaire **en
> mémoire**, exactement comme un drapeau de CLI.
>
> **Charge estimée** — 11 jours. C'est le plan le plus large en surface d'interface.
>
> **Prérequis : `PLAN-31`** (les quatre destinations doivent exister) **et `PLAN-32`** (un
> paramètre qui change le régime d'un run doit se voir dans la progression, sinon on ne saura
> pas ce qu'il a fait).

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Ce que le lanceur graphique expose, et ce qu'il n'expose pas

`gui/lanceur.py:PanneauLanceur._construire` (L66-176) offre neuf contrôles :

| Contrôle | Équivalent CLI |
|---|---|
| Brique (Manga / Light novel) | le choix du script |
| Projet, Tome | arguments positionnels |
| Reprendre à | `--from ÉTAPE` |
| Planche unique | `--page N` |
| Tout refaire depuis zéro | `--force` |
| Simuler sans traduire | `--dry-run` |
| Journal détaillé | `--verbose` |
| Planches par appel | `manga.lot.planches` |
| Raisonnement | `--think` |

`run_manga.py` porte **23 `add_argument`** (comptés le 2026-09-04) ; `run.py` 22,
`run_ocr.py` 15, `run_illustration.py` 22. Ce qui manque côté manga, relevé à la source :

| Drapeau CLI | Ligne | Ce qu'il fait | Dans l'interface ? |
|---|---:|---|---|
| `--format {manga,webtoon}` | L129 | choisit le jeu de seuils et le sens de lecture | ❌ |
| `--langue DOSSIER` | L123 | quelle source lire (`ENG`, `JP`, …) | ❌ |
| `--conf S` | L136 | seuil de confiance de détection | ❌ |
| `--iou S` | L142 | seuil de recouvrement | ❌ |
| `--all` | L99 | traite tous les tomes d'un projet | ❌ |
| `--keep-awake` / `--shutdown` | via `core.cli` | anti-veille, extinction en fin de run | ❌ (présents dans `app.py`) |
| `--extract-glossary` / `--optimize-glossary` | L171/L177 | glossaire | partiellement (menu Projet) |
| `--list` | L183 | inventaire | ❌ (c'est `PLAN-34`) |
| `--psd-test` | L185 | validation du PSD | ❌ (outil de dev, à laisser) |
| `--check` | L189 | diagnostic | ✅ (menu Aide) |

Et **le choix du modèle LLM n'existe nulle part dans l'interface**. Le seul réglage de modèle
exposé est `--think` (le niveau de raisonnement), avec une entrée « selon `config.yaml` » dont
le commentaire L143-148 explique pourquoi elle doit exister : poser `think: false` écraserait
aussi l'`endpoint:` de l'agent.

⚠ **Le run de nuit est le cas d'usage principal de ce projet** — le dépôt a une branche qui
s'appelle `run-de-nuit-v1.7.0`, `core/cli.py` porte l'anti-veille et l'extinction, `app.py` les
propose, et `docs/` mesure des runs de plusieurs heures. **L'interface graphique est la seule
des trois interfaces à ne pas pouvoir lancer un run de nuit.** C'est le manque le plus coûteux
de cette liste.

### 1.2 La brique scan n'a aucune interface

`run_ocr.py` (7 660 o) existe, `core/version.py:ETAT_BRIQUES` la donne **bêta** depuis la
1.4.0, `scan/` est un paquet complet, et la mesure de référence dit « ~2 h pour 270 pages,
reprenable page par page ». Elle n'apparaît ni dans `gui/lanceur.py`, ni dans `app.py`.

### 1.3 L'illustration a un lanceur, mais ailleurs

`gui/atelier.py:PanneauAtelier` (53 313 o) porte son propre parcours : catalogue de
personnages, propositions, coût, galerie, relecture, `_lancer_la_generation` (L969),
`_arreter` (L984). C'est un lanceur **et** un atelier de relecture, et il est bien fait.

⚠ **Ne le démembrez pas pour l'uniformiser.** La destination « Illustrations » du `PLAN-31`
l'accueille tel quel. Ce que ce lot lui doit, c'est de lui offrir la même déclaration de
paramètres que les trois autres **là où ses paramètres sont de même nature** (modèle, graine,
nombre d'images), et rien de plus.

---

## 2. Étape 0 — l'inventaire croisé, et deux décisions

### 0.1 — Le tableau complet drapeau × interface

Le tableau du §1.1 est un relevé partiel fait à la lecture. **Refaites-le exhaustivement**, par
introspection plutôt qu'à l'œil : `argparse` connaît ses actions, un petit script peut lister
tous les `add_argument` de `run.py`, `run_manga.py`, `run_ocr.py`, `run_illustration.py`, et les
croiser avec les attributs de `PanneauLanceur.PARCOURS` et de `PanneauAtelier`.

Publiez : **n drapeaux au total, n exposés, n délibérément non exposés (avec le motif), n
manquants**. C'est ce tableau qui devient le critère 1, et c'est lui qui empêche ce lot de
livrer « quelques cases en plus ».

⚠ **Un relevé à la main ne suffit pas** — le `PLAN-19` a appris ça sur les couleurs littérales :
« le relevé initial en annonçait dix-huit dans cinq fichiers et en avait manqué trois. D'où le
critère 1 : un inventaire à la main ne suffit pas, il faut le test. » Livrez donc le script,
pas seulement son résultat, et un test qui échoue si un drapeau neuf apparaît dans une CLI sans
être classé.

### 0.2 — Ce que l'endpoint LLM répond réellement

Le client est **OpenAI-compatible** (`llm.base_url`, défaut `http://localhost:11434/v1`). Avant
de dessiner un sélecteur de modèle, mesurez ce qu'on peut savoir :

1. `GET /v1/models` sur l'Ollama de la machine — la liste, telle quelle, avec les noms exacts ;
2. pour chacun : sait-on depuis cette réponse s'il est **vision-capable** ? Le modèle de
   référence du dépôt (`yume-27b`) l'est, et la brique manga en dépend (`manga.modeles`, mode
   vision du traducteur, `orchestrator_manga.py` L585). **Si la réponse ne le dit pas, le
   sélecteur ne doit pas le prétendre** ;
3. le `num_ctx` : le dépôt travaille à 32 768 avec `max_input_tokens: 24000`. Un modèle
   sélectionné avec une fenêtre plus courte casse la traduction par lots. Sait-on la lire ?
4. le temps de réponse de la sonde, et son comportement quand Ollama est arrêté.

Publiez la réponse brute de l'endpoint (anonymisée si besoin) et ce qu'on peut en déduire.
**Ce que la sonde ne sait pas décider, l'interface l'affiche comme inconnu**, elle ne le devine
pas.

### 0.3 — Décider du sort de la brique scan

Trois options, à trancher **par écrit** :

| Option | Ce qu'elle coûte | Ce qu'elle promet |
|---|---|---|
| une cinquième destination « Scans » | une page, un formulaire, des tests | une brique bêta au même rang que deux briques stables |
| un mode de la destination Manga | presque rien | brouille deux pipelines distincts (`run_ocr.py` ≠ `run_manga.py`) |
| rien, documenté | rien | l'interface reste muette sur une brique livrée |

⚠ **Le critère de décision n'est pas la difficulté, c'est l'honnêteté de l'affichage.** Une
destination qui porte visiblement « bêta » et la réserve mesurée est acceptable ; une case
perdue dans le lanceur manga ne l'est pas. Ma recommandation, à confirmer par la mesure : une
destination distincte, marquée bêta, **livrée après** les quatre autres, ou pas livrée.

---

## L33.1 — Une déclaration de paramètres, pas quatre formulaires

`gui/parametres.py`, sans un import Qt, même patron que `gui/actions.py` et
`gui/destinations.py` :

```python
@dataclass(frozen=True)
class Parametre:
    identifiant: str          # "format"
    briques: tuple[str, ...]  # ("manga", "webtoon")
    libelle: str              # dit l'EFFET, pas le drapeau
    genre: str                # "bascule" | "choix" | "entier" | "reel" | "texte"
    defaut: object            # None = « selon config.yaml », et ça ne pose PAS la clé
    equivalent: str           # "--format webtoon" — pour l'infobulle
    cout: str                 # "des heures sur un tome complet", ou ""
    persiste: bool            # False pour force / dry_run
```

Ce que la table achète :

- **un seul générateur de formulaire** pour LN, manga, webtoon et — pour ses paramètres de même
  nature — l'illustration. Quatre formulaires écrits à la main divergeraient au troisième
  ajout ;
- **le test que le lot 18 avait dû écrire à la main** : chaque paramètre a un libellé qui dit
  l'effet, une infobulle qui porte l'équivalent CLI, et un défaut ; aucun identifiant n'est
  déclaré deux fois pour la même brique ;
- **le croisement avec l'étape 0.1** : un test lit l'inventaire des drapeaux et vérifie que
  chacun est soit dans la table, soit dans une liste `NON_EXPOSES` **motivée dans le code**. Un
  drapeau ajouté demain à une CLI casse ce test — c'est exactement ce qu'on veut.

⚠ **La règle du défaut « selon `config.yaml` » est déjà écrite et elle est subtile** : la
première entrée du menu `--think` « ne vaut pas `false` : elle ne pose pas la clé du tout ».
Généralisez-la à **tous** les paramètres à trois états, et testez-la : le dictionnaire de
config muté ne doit pas contenir la clé quand l'utilisateur n'y a pas touché.

## L33.2 — Le run de nuit entre dans l'interface

Trois paramètres, tous déjà implémentés dans `core/cli.py` et déjà pilotés par `app.py` :

| Paramètre | Fonction du socle | Garde-fou attendu |
|---|---|---|
| Empêcher la mise en veille | `cli.preparer_veille` | aucun — c'est sans effet de bord |
| Éteindre le PC à la fin | `cli.finalize_power` | **confirmation explicite**, et le délai est réglable |
| Délai avant extinction | `shutdown_delay`, défaut 120 s | annulable, et l'interface dit comment |

⚠ **L'extinction est la seule action de l'application qui touche à la machine.** Elle demande :
une case décochée par défaut, `persiste: False` (comme `force` et `dry_run` — une extinction
héritée d'hier est le pire défaut possible), une confirmation qui nomme le délai, et une ligne
de journal au moment où le compte à rebours commence.

⚠ **Et elle interagit avec `PLAN-32` L32.5** : pas de modale à la fin d'un run, mais un compte
à rebours d'extinction **doit** être visible et annulable sans chercher. Le bandeau de run est
le bon endroit.

## L33.3 — Choisir le modèle, sans écrire dans `config.yaml`

Ce que l'interface offre, dans l'ordre de sûreté décroissante :

1. **la liste des modèles disponibles**, lue par `GET /v1/models` sur `llm.base_url`, avec un
   état « endpoint injoignable — les modèles de `config.yaml` restent en place » ;
2. **un modèle par run**, appliqué en mémoire, qui outrepasse la spec des agents de la brique
   choisie ;
3. **le cas par agent**, si et seulement si l'étape 0.2 montre que c'est lisible : le dépôt a
   des modèles distincts par agent (`manga.modeles`, `endpoint:` par agent, un endpoint
   `reflexion`). Un sélecteur global qui écraserait un endpoint spécialisé **sans le dire** est
   pire que pas de sélecteur — le commentaire de `--think` L143-148 a déjà rencontré ce piège.

Trois refus explicites :

- ⚠ **aucune écriture dans `config.yaml`**. Le choix persiste dans `.angelith/interface.json`,
  comme le thème et la disposition, « c'est une préférence d'installation, pas un réglage de
  pipeline » ;
- ⚠ **aucun `ollama pull` déclenché depuis le lanceur.** Télécharger des poids est un geste
  d'installation, avec sa licence et sa taille : c'est `PLAN-36` L36.2, avec consentement et
  provenance ;
- ⚠ **aucune promesse de compatibilité non mesurée.** Si la sonde ne sait pas dire qu'un modèle
  est vision-capable, l'interface affiche « capacité vision inconnue » et **avertit** quand la
  brique manga en dépend. Elle ne filtre pas la liste sur une devinette.

## L33.4 — Les profils, et ce qu'un profil n'a pas le droit de porter

Un run de ce projet a beaucoup de paramètres et trois ou quatre combinaisons réelles : « nuit
complet », « reprise rapide », « simulation sans LLM », « relettrage seul ». Des profils nommés,
stockés dans `.angelith/profils.json`.

⚠ **Un profil ne porte jamais `force`, `dry_run` ni `shutdown`.** C'est la règle
`NON_PERSISTES` de `gui/reglages.py`, dont le motif est chiffré : « une case cochée hier qui se
retrouve cochée aujourd'hui, c'est un tome relancé depuis la détection — des heures de GPU pour
un état que personne n'a redemandé ». Un profil est un raccourci de saisie, pas un mandat.
Le test de `tests/test_gui_reglages.py` qui vérifie que `nettoyer()` retire ces clés **quoi
qu'on lui donne, y compris un fichier écrit à la main**, doit être étendu aux profils.

Un profil porte donc : brique, format, langue source, étape de reprise, taille de lot,
raisonnement, modèle, verbose, anti-veille. Pas le projet ni le tome — un profil qui se
souvient d'un tome est un raccourci qui lance le mauvais run.

## L33.5 — La destination Webtoon, et la réserve qu'elle affiche

Rappel du `PLAN-31` L31.7 : le webtoon n'est pas une brique, c'est `--format webtoon` sur le
même orchestrateur. Ce lot lui donne ses réglages propres, remontés depuis `config.yaml` :

- le découpage des bandes très allongées (`config.yaml` §« Découpage des bandes TRÈS ALLONGÉES »,
  ~L1403), avec le ratio d'entrée en clair ;
- `fenetre_hauteur: 2160` (~L1455), et ce qu'il coûte en mémoire : « 10,8 Mo sur une bande
  webtoon 1080×10 000 » contre « sur une planche 1125×1600 » (~L894) ;
- le sens de lecture, qui n'a **pas** le même défaut (`SENS_PAR_DEFAUT["webtoon"]`,
  `manga/formats.py`) — et le commentaire de `config.yaml` L1788 avertit : les supprimer
  « numéroterait les bulles à l'envers sur toute la bande, sans un avertissement ».

⚠ **La réserve mesurée s'affiche dans la destination, pas dans une note de bas de page** :
15,1-17,0 % de fausses détections pour une cible de 5 %, et 5,9 bulles par bande là où 25-35
seraient attendues (`docs/mesures/webtoon-2026-08-26.md`). Un utilisateur qui lance son premier
webtoon doit savoir qu'il aura des zones à corriger à la main.

## L33.6 — La confirmation dit ce qui est mesuré, et se taise sur le reste

`gui/lanceur.py:_confirmer` (L359) refuse aujourd'hui de chiffrer la durée d'un run, et
`illustration/progression.py` cite ce refus comme précédent : « aucune constante mesurée ne
couvre un run complet […] l'annoncer serait inventer un chiffre ». **Gardez ce refus.**

Ce que la confirmation PEUT dire, parce que c'est mesuré et publié :

| Geste | Chiffre disponible | Source |
|---|---|---|
| relancer un chapitre déjà à jour | 629 ms pour le constater, 3 min 9 s pour le refaire | chiffres de référence |
| `--force` sur un tome complet | « reprend à la détection — des heures » | infobulle existante |
| détection seule | « modèle ONNX requis, des heures » | `ETAPES_MANGA`, `gui/lanceur.py` L42 |
| OCR de scans | ~2 h pour 270 pages, reprenable page par page | chiffres de référence |

⚠ **Chaque chiffre affiché porte son dénominateur**, sinon il ne s'affiche pas. C'est la règle
§5 du contexte agent, et une interface est le pire endroit pour l'enfreindre : un chiffre dans
une boîte de dialogue est lu comme une promesse.

---

## 3. Les critères de ce lot

1. Le tableau drapeau × interface de l'étape 0.1 est publié, **produit par un script livré**, et
   un test échoue si un drapeau de CLI n'est ni exposé ni classé « non exposé » avec un motif.
2. La réponse brute de `GET /v1/models` est publiée, avec ce qu'on peut et ne peut pas en
   déduire (vision, `num_ctx`), et le temps de réponse quand l'endpoint est arrêté.
3. Le sort de la brique scan est **tranché par écrit**, avec le motif — livrée marquée bêta, ou
   non livrée.
4. `gui/parametres.py` existe, ne connaît pas Qt, et un seul générateur construit les
   formulaires des quatre destinations. Aucun identifiant dupliqué pour une même brique.
5. Un test vérifie que le défaut « selon `config.yaml` » **ne pose pas la clé** dans le
   dictionnaire muté, pour tous les paramètres à trois états.
6. `config.yaml` n'est pas réécrit — un test compare son empreinte SHA-256 avant et après un run
   lancé depuis l'interface avec chaque paramètre modifié.
7. Le run de nuit est lançable depuis l'interface : anti-veille, extinction avec confirmation,
   délai réglable et annulable, compte à rebours visible dans le bandeau.
8. `force`, `dry_run` et `shutdown` ne sont persistés ni dans les réglages ni dans un profil ;
   le test de `nettoyer()` couvre les deux fichiers, y compris écrits à la main.
9. Le sélecteur de modèle n'écrit rien dans `config.yaml`, ne déclenche aucun téléchargement, et
   affiche « inconnu » là où la sonde ne sait pas.
10. La destination Webtoon nomme son format, expose ses trois réglages de bande avec leurs
    chiffres, et affiche la réserve mesurée.
11. Aucune boîte de confirmation n'annonce une durée. Les chiffres affichés portent leur
    dénominateur.
12. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans endpoint LLM.
13. `docs/mesures/lanceurs-<date>.md` reprend ces critères un par un, y compris les non tenus.

## 4. Ce que ce lot ne fait pas

- Il ne crée **aucun** chemin de traitement propre à l'interface. Tout passe par
  `process_volume` des orchestrateurs existants — c'est la règle de `gui/__init__.py`.
- Il n'écrit pas dans `config.yaml`, et il n'y ajoute aucune clé obligatoire.
- Il ne télécharge aucun poids et ne lance aucun `ollama pull`. C'est `PLAN-36`.
- Il ne démembre pas `PanneauAtelier` pour l'uniformiser.
- Il n'expose pas `--psd-test` (outil de validation Photoshop) ni `--list` (c'est `PLAN-34`).
- Il ne touche pas aux seuils de détection par défaut. Exposer `--conf` et `--iou` **n'autorise
  pas** à changer leur valeur de `config.yaml`, dont chaque chiffre est justifié par une mesure
  dans le fichier lui-même.
