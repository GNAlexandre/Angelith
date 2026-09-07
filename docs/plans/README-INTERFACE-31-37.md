# Plans 31 à 37 — L'application : le menu, la progression, l'empaquetage

Établis le **2026-09-04**, à partir du dépôt en **2.24.1** (`8e5ee5a`).

**Commencez par [`00-CONTEXTE-AGENT.md`](00-CONTEXTE-AGENT.md).** Il porte ce qu'aucun plan de
cette série ne répète : conventions du dépôt, règle de numérotation, convention de commit avec
disclosure IA, commandes de test et de mesure, les sept interdits, la règle des chiffres, la
règle des affirmations d'état, et la définition de « terminé » en huit points.

## Comment lancer une session

```
Lis docs/plans/00-CONTEXTE-AGENT.md, docs/plans/README-INTERFACE-31-37.md,
puis docs/plans/PLAN-NN-….md.
Exécute l'étape 0, publie sa mesure, et arrête-toi pour que je la relise
avant d'écrire une ligne de code.
```

**Un plan = une session = une branche = un `[X.Y.Z]`.** Jamais deux plans dans la même session.

---

## 1. Ce que cette série adresse

Les trois briques (light novel, manga, webtoon) donnent des résultats stables, et le dépôt le
mesure. Ce qui manque n'est plus de la traduction, c'est **un logiciel** : un point d'entrée qui
demande ce qu'on veut faire, un run qu'on peut regarder, une gestion des œuvres, et un
`.exe` qu'on peut donner à quelqu'un.

Trois constats à la source, et ils sont l'origine de la série :

**(a) L'application ouvre un tome que personne n'a demandé.** `gui/fenetre.py` L167 appelle
`_remplir_projets()` alors que les deux `QComboBox` sont déjà branchés (L192, L196) : remplir la
liste **déclenche** `_ouvrir_tome` (L445) sur le premier projet par ordre alphabétique, ce qui
construit un `Tome`, un `Services` (donc les agents et le glossaire YAML), et lance la
composition d'aperçus. Quelqu'un qui voulait seulement lancer un run a payé tout ça.

**(b) La barre de progression recule.** `manga/orchestrator_manga.py` appelle `progres(i, total)`
au balayage A (L895) **et** au balayage B (L1616) sur le même dénominateur. `_avancer` (L975)
fait `setValue(courant)` sans mémoire : sur 131 planches, la barre monte à 131, retombe à 1,
remonte. C'est le défaut que la référence Microsoft nomme explicitement (« always increase
progress monotonically »). ⚠ `gui/avancement.py:Estimateur` a **déjà** traité le problème de son
côté (il vide sa fenêtre quand le compte recule) — le modèle est juste, la barre ne l'est pas.

**(c) Rien n'est empaqueté.** Pas de `pyproject.toml` (c'était un choix documenté dans
`core/version.py`), cinq `requirements-*.txt`, aucun `.spec`, lancement par `python gui.py`.

Et deux manques que l'audit a trouvés en chemin :

- **l'export de glossaire n'existe pas.** La seule fonction du dépôt dont le nom commence par
  `export` est `tools/banc_sfx.py:exporter_crops`. Le glossaire s'importe, se réintègre,
  s'optimise — il ne sort pas. C'est pourtant le différenciateur n° 1 du projet ;
- **l'interface graphique est la seule des trois interfaces à ne pas pouvoir lancer un run de
  nuit.** `--keep-awake` et `--shutdown` sont dans `core/cli.py`, proposés par `app.py`, absents
  de `gui/lanceur.py` — dans un projet qui a une branche nommée `run-de-nuit-v1.7.0`.

## 2. Ce que la série ne refait pas

L'interface actuelle est plus avancée que le diagnostic « elle pose plusieurs problèmes » ne le
suggère, et **il ne faut pas la réécrire**. Ce qui existe et qui est bon :

| Acquis | Où | Livré par |
|---|---|---|
| un fil de travail **unique**, une file, un verrou **par planche** | `gui/travailleur.py` | lot 18 |
| un catalogue d'actions en Python nu, source unique des menus et raccourcis, **testé** | `gui/actions.py` | lot 18 |
| un temps restant sur le **débit observé**, fenêtre glissante | `gui/avancement.py` | lot 20 |
| un système visuel : tokens, deux thèmes, accessibilité, ordres de tabulation | `gui/theme.py`, `PARCOURS` | lot 19 |
| une décision de glisser-déposer **sans Qt**, testable | `gui/depot.py` | lot 18 |
| des réglages persistés dans un JSON lisible, avec des clés **refusées** (`force`, `dry_run`) | `gui/reglages.py` | lot 18 |
| un modèle de progression à trois phases qui **refuse** d'inventer un pourcentage | `illustration/progression.py` | lot 27 |
| un atelier d'illustration complet : catalogue, coût, galerie, relecture | `gui/atelier.py` | lot 27 |
| un éditeur de planches mûr : zones, répliques, relettrage, webtoon | `gui/editeur.py` (107 Ko) | lots 16-22 |

⚠ **`illustration/progression.py` et `gui/avancement.py` sont les deux précédents à suivre**, et
la série les cite plutôt que de les remplacer. Leur discipline commune est celle du dépôt : *on
n'affiche pas un chiffre qu'on n'a pas mesuré*.

## 3. Les sept plans

| Plan | Objet | Nature | Jours |
|---|---|---|---:|
| [31](PLAN-31-LE-DEMARRAGE-NE-CHARGE-RIEN.md) | L'accueil, six destinations, construction paresseuse, le tome à la demande | MINEUR | 9 |
| [32](PLAN-32-LE-RUN-SE-REGARDE.md) | Progression monotone, phases, objet en cours, temps restant, titre de fenêtre | MINEUR | 8 |
| [33](PLAN-33-LES-QUATRE-LANCEURS.md) | Paramètres déclarés, run de nuit, choix du modèle, profils, webtoon | MINEUR | 11 |
| [34](PLAN-34-LA-BIBLIOTHEQUE-DES-OEUVRES.md) | Bibliothèque des œuvres, dépôt guidé, **export de glossaire**, exports de rendu | MINEUR | 12 |
| [35](PLAN-35-LA-RETOUCHE-DEVIENT-UNE-DESTINATION.md) | L'éditeur découplé, la garde déplacée, la bande webtoon | CORRECTIF + MINEUR | 7 |
| [36](PLAN-36-LE-PREMIER-LANCEMENT.md) | Diagnostic structuré, dépendances, poids récupérés avec licence, tome de démonstration | MINEUR | 9 |
| [37](PLAN-37-L-EMPAQUETAGE.md) | `pyproject.toml`, gel onedir, installeur, signature, artefact de CI | **livré en 2.31.0 — MINEUR** | 14 |

**Total : 70 jours.** Ce n'est pas un programme à exécuter d'un bloc, et les quatre premiers
plans donnent déjà une application utilisable.

## 4. Ordre d'exécution

```
        ┌──────────────┐
        │      31      │  la coquille — bloque tout le reste
        └──────┬───────┘
      ┌────────┼─────────┬──────────┐
      ▼        ▼         ▼          ▼
   ┌────┐  ┌──────┐  ┌──────┐   ┌──────┐
   │ 32 │  │  34  │  │  35  │   │  36  │
   └─┬──┘  └───┬──┘  └──────┘   └──┬───┘
     ▼         │                   │
   ┌────┐      │                   │
   │ 33 │◄─────┘ (34 utile mais    │
   └─┬──┘         pas requis)      │
     └────────────┬────────────────┘
                  ▼
              ┌──────┐
              │  37  │  l'empaquetage — en dernier, toujours
              └──────┘
```

1. **31 d'abord, et seul.** C'est lui qui déplace la propriété du tome ; tout plan écrit avant
   lui devrait être réécrit après. Il est aussi le seul dont l'étape 0 mesure quelque chose que
   la refonte va effacer (le coût du démarrage actuel).
2. **32 puis 33.** Un paramètre qui change le régime d'un run (taille de lot, raisonnement,
   modèle) doit se voir dans la progression, sinon on ne saura pas ce qu'il a fait.
3. **34 et 35 en parallèle** de 32/33 si vous avez deux branches. Ils ne se touchent qu'en un
   point : le geste « Retoucher » depuis la bibliothèque (L35.2).
4. **36 avant 37, sans exception.** Un `.exe` qui ne sait pas dire ce qui lui manque est un
   `.exe` qu'on ne peut pas donner à quelqu'un.
5. **37 en dernier.** Il gèle ce que les six autres ont livré ; le geler plus tôt, c'est le
   refaire.

⚠ **Les plans 31 et 35 forment une paire.** Le 31 **ouvre** un trou (quitter la retouche en
changeant de destination n'est gardé par rien) et le 35 le referme. Si vous ne comptez pas
exécuter le 35, alors le 31 doit porter la garde lui-même — ne laissez pas ce trou ouvert entre
deux livraisons.

## 5. Les normes consultées, et ce qu'on en retient

Vérifiées le 2026-09-04. Elles sont citées dans les plans à l'endroit où elles décident.

| Source | Ce qu'on en retient |
|---|---|
| Fluent / WinUI `NavigationView` | nav **latérale** de 5 à 10 destinations, nav haute en dessous de 5 ; modes adaptatifs à 1008 px et 641 px ; les réglages **en pied** de pane |
| NN/g, *Progress Indicators* | < 1 s rien, 2-10 s une animation, > 10 s un pourcentage ; le texte doit dire l'objet (« 3 of 50 ») ; ne jamais reculer ni stagner |
| Microsoft, *Progress Bars* | déterminé dès que c'est borné ; **jamais** de % ni d'ETA avec une barre indéterminée ; « time remaining », pas « elapsed » ; rafraîchi ≥ toutes les 5 s ; pas de fausse précision ; **jamais de redémarrage ni de recul** ; `Arrêter` (et non `Annuler`) quand le travail partiel est conservé ; le titre porte l'avancement pour la barre des tâches |
| PyInstaller, retours de terrain antivirus | **onedir** plutôt que onefile (l'extraction au démarrage déclenche les heuristiques) ; la signature réduit fortement les faux positifs ; recompiler le chargeur change l'empreinte ; les éditeurs acceptent les signalements ; Nuitka comme repli |

⚠ **Trois de ces règles condamnent la barre de progression actuelle** : elle redémarre, elle
recule, et elle affiche un pourcentage sur un dénominateur qui change en cours de run. C'est le
`PLAN-32`.

## 6. Le nom des destinations

L'utilisateur a demandé **LN / MANGA / WEB / Génération d'Image / Gestion des Œuvres /
Modification**. La série propose de retenir :

| Demandé | Retenu | Motif |
|---|---|---|
| — | **Accueil** | il faut un endroit qui n'ouvre rien (`PLAN-31`) |
| LN | **Light novel** | déjà le libellé du dépôt ; un sigle en nav latérale ne se devine pas |
| MANGA | **Manga** | — |
| WEB | **Webtoon** | ⚠ « WEB » se lira « site web ». Et ce **n'est pas une brique** : c'est `--format webtoon` du même orchestrateur (`PLAN-31` L31.7) |
| Génération d'Image | **Illustrations** | la destination porte un catalogue et une galerie, pas seulement un bouton |
| Gestion des Œuvres | **Œuvres** | une nav latérale nomme l'objet, pas l'activité |
| Modification | **Retouche** | « Modification » ne dit pas de quoi. Le panneau retouche des **planches** |
| — | **Réglages**, **Diagnostic** | en pied de pane, convention Fluent |

Sept destinations plus deux entrées de pied : dans la fourchette de la nav latérale, hors de
celle des onglets. **Le tableau est à confirmer à l'étape 0.2 du `PLAN-31`** — c'est une
proposition argumentée, pas une décision prise à votre place.

## 7. Ce que la série refuse de faire

Écrit ici une fois, pour les sept plans :

- **aucun chemin de traitement propre à l'interface.** Tout passe par `process_volume` des
  orchestrateurs existants ; « un tome retouché ici se relance à l'identique avec
  `run_manga.py` » (`gui/__init__.py`) ;
- **`config.yaml` n'est jamais réécrit.** 158 Ko dont l'essentiel est de la prose qui justifie
  chaque valeur par un chiffre — un aller-retour `yaml.safe_dump` l'effacerait (interdit 5) ;
- **aucun poids redistribué, aucun téléchargement automatique.** Le détecteur en place est
  GPL-3.0 + Manga109-s ; Angelith récupère avec consentement, affiche la licence, enregistre
  l'empreinte ;
- **aucun chiffre sans dénominateur**, y compris dans une boîte de dialogue — un chiffre affiché
  est lu comme une promesse ;
- **aucune œuvre du corpus dans une capture, un rapport ou un artefact.** Les 17 projets de
  `sources/` sont sous droit d'auteur ; les captures se font sur le tome synthétique de
  `tools/captures_gui.py`, pour la raison que ce script écrit déjà ;
- **rien qui affaiblisse un garde-fou existant** pour faire passer un cas : ni le verrou de run
  global, ni la garde de travail non enregistré, ni le refus de chiffrer la durée d'un run, ni
  `NON_PERSISTES`.

## 8. Ce que la série laisse ouvert

À trancher dans les plans où c'est écrit, et un « non » documenté est une réponse conforme :

| Question | Où | Une réponse « non » est-elle acceptable ? |
|---|---|---|
| la brique scan (bêta) entre-t-elle dans l'interface ? | `PLAN-33` L33.5 | oui, avec motif |
| barre des tâches Windows, alors que `QtWinExtras` n'existe plus en Qt 6 ? | `PLAN-32` L32.4 | oui — le titre de fenêtre couvre le besoin |
| navigation par segment dans la bande webtoon ? | `PLAN-35` L35.3 | oui, si la mesure ne la justifie pas |
| `torch` dans le paquet, ou paquet sans OCR japonais ? | `PLAN-37` étape 0.2 | c'est **la** décision du plan |
| certificat de signature de code ? | `PLAN-37` L37.5 | oui — l'avertissement SmartScreen documenté |
| mise à jour automatique ? | `PLAN-37` L37.6 | **la réponse par défaut est non** |

## 9. Ce que la série apporte à `docs/roadmap.md`

Quatre jalons de la section « Planned » sont exactement cette série, et ils y sont déjà
qualifiés de MINEUR pour la bonne raison — « adding menus to the graphical interface breaks
nothing, so it is not a 3.0.0 » :

| Jalon de la roadmap | Plan |
|---|---|
| Menus and project management in the interface | 31, 33, 34 |
| Glossary and project import/export, drag and drop | 34 |
| Automatic detection, installation and deployment of language models | 36 |
| One-click Windows/Linux packaging, English documentation, accessibility pass | 37 (Windows seulement — Linux reste bloqué par `PLAN-20` L20.2) |

⚠ **`docs/roadmap.md` est périmé** : il annonce « Current released version: 2.7.0 » alors que
`core/version.py` dit **2.24.1**, et sa table « Shipped » s'arrête à 2.8.0. Le premier plan de
cette série qui livre devrait le remettre à jour — c'est trois lignes, et un document de
planification faux est pire qu'absent.
