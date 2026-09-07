# Contexte agent — à lire avant tout plan de ce dossier

> **À qui ce fichier s'adresse.** À une session Claude Code qui va exécuter un des plans
> `PLAN-17` … `PLAN-22`. Il porte ce qu'aucun de ces plans ne répète : les conventions du
> dépôt, les commandes, les interdits, et la définition de « terminé ».
>
> **Comment démarrer une session.** Ouvrir le dépôt, puis :
>
> ```
> Lis docs/plans/00-CONTEXTE-AGENT.md puis docs/plans/PLAN-NN-….md.
> Exécute l'étape 0, publie sa mesure, et arrête-toi pour que je la relise
> avant d'écrire une ligne de code.
> ```
>
> **Un plan = une session = une branche = un `[X.Y.Z]`.** Ne jamais entamer deux plans dans
> la même session : ils se mesurent séparément, donc ils se livrent séparément.

---

## 1. L'état du dépôt au 2026-08-26

- Version publiée : **2.6.0**. Source unique : `core/version.py`. `tests/test_version.py`
  vérifie qu'elle correspond à la première entrée datée du `CHANGELOG.md`.
- Branche de travail : `2.0.0`. Miroir public : `remote angelith` →
  `github.com/GNAlexandre/Angelith`. Le dépôt privé est `origin` → `Yume-Trad`.
- Nom public du projet : **Angelith**. `Yume-Trad` est le nom du dépôt de travail.
- Trois briques : light novel (`run.py`), manga/webtoon (`run_manga.py`), OCR de scans
  (`run_ocr.py`). Interfaces : `app.py` (console `rich`), `gui.py` (PySide6).
- Corpus réel présent sous `sources/` et `build/` : **17 projets**, dont un seul webtoon
  (`webtoon A` Chap.11), qui est aussi le seul volume à source latine — les deux
  effets sont confondus, et plusieurs plans en dépendent.

  > ⚠ **MISE À JOUR 2026-09-05, lot 34 : ce chiffre est FAUX, et il l'était déjà le
  > 2026-09-04.** Il y a **18 dossiers sous `sources/`**, et `docs/mesures/coquille-2026-09-04.md`
  > l'avait relevé sans que la ligne ci-dessus soit corrigée ; les sept plans de la série 31-37
  > l'ont donc recopié. Le relevé complet, produit par `tools/inventaire_oeuvres.py` :
  > **18 œuvres, 55 tomes, 3 493 planches et pages source dénombrées** (15 tomes sont
  > indénombrables sans extraction), **14 glossaires, 791 entrées**. Répartition par brique
  > principale : 27 manga, 1 webtoon, 26 light novel, 1 scan.
  >
  > ⚠ Et un tome peut porter **deux** briques : `manga C/Vol.1` porte 165
  > planches manga **et** 271 images de scan. Un plan qui compte « les projets manga » ne
  > compte donc pas la même chose qu'un plan qui compte « les dossiers de `sources/` » — la
  > phrase qui dit ce qu'on compte est obligatoire (`docs/chiffres-de-reference.md`).
  > Tout est dans `docs/mesures/bibliotheque-2026-09-05.md` §1.

## 2. La règle de numérotation, et elle est contraignante

Recopiée du `CHANGELOG.md`, parce que c'est elle qui décide du numéro de votre livraison :

- **MAJEUR** — l'utilisateur doit supprimer `build/` ou éditer `config.yaml` avant de
  relancer la même commande. Suppression d'un flag sans repli, changement de
  `.checkpoints/`, de `manga/checkpoints.py:STAGES` ou du schéma `glossaire.yaml` **qui
  invalide les caches**, abandon d'un format de sortie, rupture du contrat de styles de
  `templates/reference.docx`.
- **MINEUR** — nouvelle capacité, rien ne casse. Nouveau flag, nouvelle clé optionnelle à
  défaut iso-comportement, nouvel agent, nouveau garde-fou, **et toute réécriture de prompt
  qui change le caractère de la traduction**. Dans ce dernier cas l'entrée de changelog
  **doit nommer le fichier de prompt**, pour que `git checkout <tag> -- langues/` reproduise
  la voix d'un tome.
- **CORRECTIF** — aucun changement d'interface ni de sortie sur le chemin nominal.

> ⚠ **Ne réservez jamais un numéro à l'avance.** `docs/roadmap.md` a supprimé ses jalons
> numérotés précisément parce que chaque lot livré forçait à renuméroter des jalons que
> personne n'avait commencés. Le numéro se décide **à la livraison**, d'après ce que le lot
> a réellement fait à l'utilisateur.

Chaque message de commit porte sa version en tête : `[2.7.0] feat(gui): …`.

## 3. La convention de commit — non négociable

`CONTRIBUTING.md` l'impose, et ce n'est pas une préférence de style : le dossier de
financement du projet repose sur une politique d'IA générative qui exige la traçabilité, et
un historique de douze mois ne se documente pas rétroactivement.

```
feat(manga): typer les bulles à partir de leur géométrie

Assisté par : Claude Code (claude-opus-5), 2026-08-27
Prompt : « exécute PLAN-17 étape L17.3 — classifieur déterministe de type
de bulle, classe « indéterminé » généreuse, aucun appel LLM »
Revu et testé manuellement : oui
```

Quand le prompt est trop long pour un message de commit, l'enregistrer dans
`docs/ai-provenance.md` et le référencer. **Une contribution non relue par un humain n'est
pas acceptable** — la ligne qui compte n'est pas « un modèle a-t-il participé » mais « un
humain a-t-il relu et peut-il défendre ceci ».

## 4. Les commandes

```powershell
# Tests
python -m pytest -q                                   # tout — 2 262 collectés au 2026-08-25
python -m pytest -q -m "not modeles and not lent"     # la boucle courte — 2 206
python -m pytest tests/test_manga_typeset.py -q       # un fichier
python -m pytest -q --durations=15                    # les 15 plus lents

# Linter — la CI le lance tel quel
ruff check .

# Diagnostics
python run_manga.py --check
python run.py --check

# Mesure
python tools/banc.py --tous                                 # tous les volumes de build/
python tools/banc.py --tous --markdown > docs/banc-<date>.md
python tools/banc.py --tous --traduction                    # sans appel LLM
python tools/banc.py --corpus tests/corpus/synthetique      # rappel / précision / F1
python tools/apercu_detection.py "<Projet>" <Tome> --page N --resolutions --balayage
python -m pytest --collect-only -q                          # le compte de tests
```

Marqueurs pytest : `modeles` (exige les poids sous `manga_models/`), `lent` (> 30 s,
mesuré), `llm` (aucun test aujourd'hui). **Un marqueur ne cache pas un test qui pend** :
quand un fichier ne se terminait pas, la cause était un vrai défaut.

CI (`.github/workflows/ci.yml`) : deux jobs, tous deux `windows-latest`, Python 3.12 —
`ruff check .` + `pytest -m "not lent and not modeles" -q`, puis un banc de détection sur le
corpus synthétique (`tests/test_banc_corpus_synthetique.py -m modeles`, avec cache des poids)
qui casse le build si le rappel baisse. `QT_QPA_PLATFORM: offscreen`.

⚠ **Le compte de tests a deux dénominateurs, ne les confondez pas.** `ci.yml` mesure l'effet
de PySide6 : **2 007 collectés avec, 1 879 sans**, soit **128 tests d'interface**. Le total du
dépôt toutes dépendances optionnelles installées est **2 262** au 2026-08-25 — un troisième
chiffre, avec sa date.

> ⚠ **CES TROIS CHIFFRES SONT PÉRIMÉS, et le lot 27 les a remesurés le 2026-09-02.** Ils
> dataient du 2026-08-25/26 et ont été cités tels quels par plusieurs plans depuis. L'état
> réel, toutes dépendances optionnelles installées :
>
> | | avec PySide6 | sans PySide6 | écart |
> |---|---:|---:|---:|
> | avant le lot 27 (`6779edc`) | 3 682 | 3 480 | 202 |
> | après le lot 27 | 3 811 | 3 592 | 219 |
> | après le lot 28 | 3 872 | *non remesuré* | — |
> | après le lot 29 | **3 969** | *non remesuré* | — |
> | après le lot 30 | **3 996** | *non remesuré* | — |
> | après le correctif 2.24.1 | **3 998** | 3 779 | 219 |
> | après le lot 31 | **4 112** | **3 846** | **266** |
> | après le correctif 2.25.1 | **4 130** | **3 864** | **266** |
> | après le lot 32 | **4 239** | **3 947** | **292** |
> | après le lot 33 | **4 378** | **4 039** | **339** |
> | après le lot 34 | **4 487** | **4 123** | **364** |
> | après le lot 35 | **4 567** | **4 175** | **392** |
> | après le lot 36 | **4 705** | **4 289** | **416** |
> | après le lot 37 | **4 846** | **4 430** | **416** |
> | après le lot 38 | **4 886** | **4 470** | **416** |
> | après le lot 39 | **4 912** | **4 496** | **416** |
> | après le lot 40 | **5 025** | **4 585** | **440** |
> | après le lot 41 | **5 034** | **4 591** | **443** |
> | après le lot 42 | **5 036** | **4 593** | **443** |
> | après le lot 43 | **5 038** | **4 595** | **443** |
> | après le lot 46 | **5 058** | **4 615** | **443** |
> | après le lot 47 | **5 060** | **4 617** | **443** |
> | après le lot 48 | **5 072** | **4 629** | **443** |
> | après le lot 49 | **5 076** | **4 633** | **443** |
> | après le lot 50 | **5 081** | **4 634** | **447** |
>
> ⚠ Le lot 28 (2026-09-02) ajoute **61 tests**, tous hors marqueur. La colonne « sans PySide6 »
> n'a pas été remesurée ce jour-là : aucun des 61 ne touche à l'interface, donc l'écart de 219
> devrait tenir — mais « devrait » n'est pas une mesure, et la case dit donc *non remesuré*
> plutôt qu'un chiffre déduit.
>
> ⚠ Le lot 29 (2026-09-03) ajoute **97 tests**, même remarque et même case vide. La boucle
> courte en exécute **3 912**, 57 étant désélectionnés par `lent` / `modeles`.
>
> ⚠ Le lot 30 (2026-09-03) ajoute **27 tests**, tous hors marqueur, même remarque et même case
> vide. La boucle courte en exécute **3 939**, les mêmes 57 restant désélectionnés.
> 
> ⚠ Le correctif 2.24.1 (2026-09-03, session sur le PC principal) ajoute **2 tests** de
> câblage de ligne de commande, hors marqueur. La boucle courte en exécute **3 941**, les
> mêmes 57 restant désélectionnés.
>
> ⚠ **Le lot 31 (2026-09-04) remplit enfin la colonne « sans PySide6 », et rétroactivement.**
> Elle était vide depuis le lot 27 parce que la remesurer demandait de désinstaller PySide6,
> donc de casser l'environnement de qui lance la mesure. `tools/compte_sans_pyside.py` rend le
> module introuvable le temps d'une collecte, et **la méthode est validée par reproduction** :
> appliquée à `1e41504` (2.24.1) elle rend 3 998 / 3 779, soit **exactement les 219** que le
> lot 27 avait mesurés en installant réellement les deux configurations. La ligne 2.24.1
> ci-dessus est donc une mesure, pas une déduction. Le lot 31 ajoute **114 tests** — 67 sans
> Qt, 47 avec — et la boucle courte en exécute **4 055**, les mêmes 57 restant
> désélectionnés.
> Reproduire : `python -m pytest --collect-only -q -p tools.compte_sans_pyside`.
>
> ⚠ Le correctif 2.25.1 (2026-09-04) ajoute **18 tests**, tous sans Qt et hors marqueur :
> l'écart de 266 est donc **inchangé**, et cette fois c'est une mesure et non une
> déduction — les deux colonnes ont été relevées. La boucle courte en exécute **4 073**,
> les mêmes 57 restant désélectionnés.
>
> ⚠ Le lot 33 (2026-09-05) ajoute **139 tests**, dont **92 sans Qt** — les deux colonnes ont
> été relevées, l'écart passe donc de 292 à **339**. La boucle courte en exécute **4 321**, les
> mêmes 57 restant désélectionnés. Cinq des six modules neufs du lot sont sans Qt
> (`gui/parametres.py`, `gui/profils.py`, `gui/extinction.py`, `core/modeles.py`,
> `tools/inventaire_drapeaux.py`), et c'est ce qui explique la proportion.
>
> ⚠ **Le lot 34 (2026-09-05) ajoute 109 tests, dont 84 sans Qt** — les deux colonnes ont été
> relevées, l'écart passe de 339 à **364**. La boucle courte en exécute **4 430**, les mêmes 57
> restant désélectionnés. Six des sept modules neufs sont sans Qt (`bibliotheque.py`,
> `core/glossary_export.py`, `gui/depot_guide.py`, `gui/sorties.py`, `gui/vue_oeuvres.py`,
> `tools/inventaire_oeuvres.py`), et c'est ce qui explique la proportion.
>
> ⚠ **Le lot 37 (2026-09-06) ajoute 141 tests, et les 141 sont SANS Qt** — les deux colonnes
> ont été relevées, l'écart de **416 est donc inchangé**, et c'est une mesure et non une
> déduction. La boucle courte en exécute **4 789**, les mêmes 57 restant désélectionnés. Le
> « avant » a été mesuré dans un `git worktree` propre : un `git stash` aurait laissé en place
> les fichiers de test NEUFS, qui ne sont pas suivis, et rendu un « avant » contenant déjà
> l'« après » — l'erreur a été faite avant d'être corrigée
> (`docs/mesures/empaquetage-2026-09-06.md` §10).
>
> ⚠ **Le lot 35 (2026-09-05) ajoute 80 tests, dont 52 sans Qt** — les deux colonnes ont été
> relevées, l'écart passe de 364 à **392**. La boucle courte en exécute **4 510**, les mêmes 57
> restant désélectionnés. Deux des trois modules neufs sont sans Qt (`gui/garde.py`,
> `gui/vue_retouche.py`) et le troisième est un outil de mesure (`tools/mesure_ouverture.py`).
>
> ⚠ Le lot 32 (2026-09-05) ajoute **109 tests**, dont **83 sans Qt** — les deux colonnes ont
> été relevées, l'écart passe donc de 266 à **292**. La boucle courte en exécute **4 182**,
> les mêmes 57 restant désélectionnés. ⚠ Une partie des 79 n'est pas neuve mais **libérée** :
> `progression_de_stage` a quitté `gui/travailleur.py` (qui importe Qt) pour
> `core/progression.py`, sans changer d'une ligne.
>
> La source qui fait foi est **`docs/chiffres-de-reference.md`**, que
> `tests/test_coherence_chiffres.py` garde. ⚠ Le couple de `ci.yml` (2 644 / 2 504, soit 140,
> au 2026-08-27) est mesuré dans une **autre configuration** — socle + GUI + dev, **sans**
> `requirements-manga.txt` — et il ne s'unifie donc pas à celui-ci. Un plan qui cite un compte
> de tests doit dire lequel des trois il cite.

`ci.yml` note en plus 30 tests non collectés en CI (`test_manga_detection.py`,
`test_manga_ocr.py`, qui font `importorskip`).

> ⚠ `windows-latest` n'est pas une préférence : `tests/conftest.py` fabrique sa planche
> synthétique avec `C:/Windows/Fonts/msgothic.ttc` et **skippe** la fixture si la police
> manque. Sur un runner Linux, toute la couverture détection/OCR/orchestrateur serait sautée
> en silence — CI verte, plus rien de testé. Rendre la police configurable est un prérequis
> de toute matrice d'OS (cf. `PLAN-20`).

## 5. La règle des chiffres

`docs/chiffres-de-reference.md` la pose, après que cinq nombres — 821, 813, 797, 790, 687 —
ont désigné le même tome sans qu'aucun porte son dénominateur :

> **Tout chiffre de communication du projet — README, docstring, commentaire de
> configuration, entrée de changelog — porte sa source et son dénominateur. Un chiffre sans
> dénominateur n'est pas une mesure, c'est une impression.**

Corollaire pour vous : **aucun plan de ce dossier ne se termine sans un tableau daté**, et
le tableau porte la date, le commit et l'empreinte SHA-256 de `config.yaml` — c'est ce que
`tools/banc.py --markdown` produit déjà.

## 5 bis. La règle des affirmations d'état — écrite le 2026-09-02, lot 28

Le corollaire de la règle des chiffres, et il a la même cause :

> **Toute affirmation d'ÉTAT dans le code — « n'a jamais tourné », « pas encore mesuré »,
> « non installé », « à vérifier » — porte SA DATE et le document qui l'établit. Un
> commentaire qui vieillit sans le dire est un faux avertissement, et un faux avertissement
> cesse d'être lu.**

Ce qui l'a motivée est un cas exact. `illustration/comfyui.py` a affirmé, de la 2.15.0 à la
2.21.0 : « ce client **n'a jamais tourné contre un vrai serveur ComfyUI** ». C'était vrai le
jour où la phrase a été écrite. C'était **faux depuis la 2.16.0** — 25 générations, 0 échec
d'exécution, le 2026-08-29 — et la phrase est restée six versions parce que rien, dans sa
formulation, ne disait de quand elle datait. Un lecteur qui la croyait renonçait à un moteur
qui marchait.

Comment l'écrire, dans l'ordre de préférence :

1. **la date dans la phrase** — « l'axe n'est pas mesuré **au 2026-09-02** » ;
2. **un bloc daté qui LÈVE l'affirmation précédente** plutôt que de la réécrire — c'est ce que
   `core/version.py` fait déjà, avec ses « ⚠ MISE À JOUR 2.16.0 : la première réserve est
   LEVÉE ». C'est la meilleure forme quand l'histoire de la mesure a de la valeur ;
3. **le document qui l'établit**, nommé, pour que la vérification ne coûte rien.

⚠ **Un document daté de `docs/mesures/` n'est PAS concerné.** Il décrit l'état de son jour,
c'est sa fonction, et le réécrire effacerait l'histoire de la mesure. Seuls le **code** et les
fiches de `docs/procedures/` sont visés.

⚠ **Cette règle n'est pas testée mécaniquement, et c'est délibéré** — même raison que pour la
règle des chiffres : « ce n'est pas décidable par une expression régulière, et un garde-fou qui
produit des faux positifs sur de la prose est contourné avant d'avoir servi »
(`tests/test_coherence_chiffres.py`). Elle tient à la relecture. Le relevé du lot 28
(`docs/mesures/comfy-visible-2026-09-02.md` §5) donne la commande qui le refait en dix
secondes.

## 6. La règle de la mesure honnête

Trois documents publiés par les lots précédents fixent le standard, et il est haut :

- `docs/mesures/escalade-2026-08-25.md` publie ce que la mesure **ne dit pas**.
- `docs/mesures/webtoon-2026-08-26.md` nomme **quatre affirmations du dépôt lui-même qui étaient
  fausses**, livre **trois réglages désarmés** parce que la mesure ne soutenait pas de les
  armer, et passe en revue **les huit critères du plan un par un**, y compris les deux non
  tenus.
- `docs/mesures/doubles-2026-08-25.md` fait de même pour la scission.

> **« Un tableau qui ne confirme jamais que le plan n'est pas une mesure. »**
>
> Attendu de vous, explicitement : si une prémisse de votre plan se révèle fausse à la
> mesure, **écrivez-le dans le document du lot et ne corrigez pas le plan en silence**. Si
> un réglage ne se justifie pas, **livrez-le désarmé** (valeur neutre) avec la mesure qui
> explique pourquoi. Un lot qui livre un résultat négatif documenté est un lot réussi.

## 7. Les interdits

1. **Ne pas invalider un cache sans le vouloir.** Une relance de tome coûte des heures de
   GPU. `checkpoints.FORMAT_VERSION` encode le contrat de *nombre et d'ordre* auquel
   `ocr.json` et `traduction.json` s'alignent **par position** ; `load_regions` rend `None`
   sur écart de version, ce qui déclenche `downstream("detection")` sur tous les projets.
   Un champ de provenance ne touche pas à ce contrat — **ne l'incrémentez pas pour ça**.
2. **`clean.py` a un invariant pixel-exact**, testé hors masque par
   `tests/test_manga_clean.py` : une seule écriture, `out_arr[paint] = style.background`,
   précédée de `paint = paint & region.mask`. Ce filet est gardé même quand il est redondant
   en théorie, « parce que l'invariant ne doit pas dépendre d'un raisonnement ». N'y touchez
   pas sans le dire dans le CHANGELOG.
3. **« L'IA ne dessine jamais »** (README §12) est un principe d'architecture, pas un
   réglage. `PLAN-22` est le seul plan autorisé à le renégocier, et il doit le faire
   explicitement, avec un mode opt-in, réversible, et une trace. Aucun autre plan n'y touche.

   **Sa PORTÉE, écrite le 2026-08-29 — décision d'Alexandre, livrée par le `PLAN-24`.** Le
   principe porte sur les **pixels de l'œuvre** : aucune écriture non déterministe dans une
   planche, une page ou un fichier source. Une brique qui ne modifie **aucun** fichier
   existant n'entre pas dans son périmètre : elle produit des fichiers neufs, dans un dossier
   qui lui est propre, marqués comme générés, et supprimables sans rien casser. L'effacement
   de pixels existants, lui, reste interdit hors du cadre que le `PLAN-22` a défini.

   ⚠ **Cette borne existe pour qu'une session ne s'arrête pas à tort — ni ne se croie
   autorisée à trop.** Elle autorise exactement une chose : créer des fichiers neufs ailleurs.
   Elle n'autorise ni à ouvrir un fichier de l'œuvre en écriture, ni à compositer dans une
   planche, ni à servir de précédent au `PLAN-22`, qui a tranché **contre** le modèle
   génératif après mesure (`docs/mesures/relettrage-2026-08-28.md`).

   ⚠ **Elle est testée, pas seulement écrite.** `illustration/frontiere.py` refuse à
   l'exécution toute écriture hors du dossier de la brique et toute image qui ne passe pas par
   le marquage ; `tests/test_illustration_frontiere.py` vérifie qu'un run complet laisse
   toutes les empreintes SHA-256 préexistantes inchangées.
4. **Pas d'OpenCV.** `requirements-manga.txt` le refuse (~60 Mo pour trois opérations de
   morphologie). `manga/geometry.py` fait son érosion et sa dilatation en numpy pur, par
   sommes cumulées, à coût indépendant de `k`. Toute nouvelle dépendance lourde se justifie
   par une mesure, pas par une commodité.
5. **`config.yaml` est un document.** 95 Ko dont l'essentiel est de la prose commentée qui
   justifie chaque valeur par un chiffre. Un aller-retour `yaml.safe_dump` l'effacerait —
   c'est pourquoi l'interface ne le réécrit jamais. Ajoutez une clé **avec le chiffre qui la
   justifie**, dans le style du fichier.
6. **Les prompts sont du code source.** Fichiers sous `langues/<code>/prompts/`. Modifier
   un prompt est un changement de comportement : dire ce que vous avez mesuré, sur quoi, et
   contre quelle référence. L'en-tête de licence d'un prompt est **à la fin** du fichier,
   jamais au début — un modèle lit le haut du fichier comme une instruction.
7. **Ne pas casser le contrat de numérotation des bulles.** Il tient à 127/127 sur le Vol.2
   du manga de référence. C'est la raison pour laquelle `_translate_sfx` est un appel LLM
   **séparé** de celui de la planche : y greffer une seconde liste risquerait ce qui marche
   pour ce qui n'existe pas encore.

## 8. La règle de couche

`gui/__init__.py` la pose : « toute logique métier vit dans `manga/`, en Python nu, et se
teste avec `pytest` sans que PySide6 soit installé. Ici on ne trouve que des fenêtres, des
scènes et des signaux. »

Elle est déjà respectée : `pellicule.py`, `avancement.py`, `cache_apercu.py`,
`modele_tome.py`, `apercu.py` et `travailleur.progression_de_stage` sont sans Qt et
testables directement.

> ⚠ **Mise à jour 2026-09-05, lot 32.** `progression_de_stage` a déménagé dans
> `core/progression.py` — même fonction, même docstring, même test, et
> `gui.travailleur.progression_de_stage` la ré-exporte. Elle était sans Qt mais enfermée
> dans un module qui en importe : impossible de la charger sans PySide6, donc impossible de
> prouver la règle qu'elle respectait. Le modèle de progression lui-même vit désormais dans
> `core/`, et les décisions d'affichage du bandeau de run dans `gui/avancement.py`.
>
> ⚠ **Mise à jour 2026-09-05, lot 35.** Deux modules sans Qt de plus, et ils portent des
> GARDES : `gui/garde.py` (les six chemins par lesquels du travail non enregistré peut se
> perdre, chacun avec son verdict et son motif) et `gui/vue_retouche.py` (les phrases de la
> destination Retouche). `gui/cache_apercu.py`, déjà sans Qt, gagne `fenetre_tenable` et
> `fenetre_retenue` : le préchargement ne demande plus que ce que le plafond garde. Un
> emballement mesuré à 137 compositions pour 12 aperçus gardés en 120 s se réduit à 13 pour 12
> (`docs/mesures/retouche-2026-09-05.md`).
>
> ⚠ **Mise à jour 2026-09-05, lot 33.** Trois modules sans Qt de plus : `gui/parametres.py`
> (la table des paramètres de run, et la seule fonction qui sait où chaque valeur atterrit
> dans `config.yaml`), `gui/profils.py` et `gui/extinction.py`. Ce dernier est le cas limite
> de la règle et sa meilleure justification : éteindre le PC est la seule action de
> l'application qui touche au matériel, et une décision de cette portée ne vit pas dans un
> `QTimer`. La sonde de modèles, elle, est dans `core/modeles.py` — `app.py` en a le même
> usage que la fenêtre. **Tenez-la** : tout ce qui décide se teste sans modèle et sans Qt.

## 9. Définition de « terminé », pour tout plan de ce dossier

Un lot n'est livrable que si les huit points suivants sont vrais.

1. `ruff check .` passe.
2. `python -m pytest -q -m "not modeles and not lent"` passe, et **des tests neufs existent
   pour chaque étape**, avec un test qui aurait échoué avant le lot.
3. Le comportement livré par défaut est **iso** pour un utilisateur qui ne touche à rien :
   toute nouvelle clé a un défaut qui ne change pas la sortie, ou le contraire est écrit en
   tête du CHANGELOG.
4. Une entrée `CHANGELOG.md` datée, portant le bon niveau (§2), nommant les fichiers de
   prompt touchés s'il y en a.
5. `core/version.py` est à jour et `tests/test_version.py` passe.
6. Un document **`docs/mesures/<sujet>-<date>.md`** publie le tableau avant/après, **et ce que la mesure
   ne dit pas** (§6). Les critères du plan sont repris **un par un**, avec leur verdict, y
   compris les non tenus.
7. Aucun cache existant n'est invalidé, ou la migration est écrite et vérifiée **sur des
   copies** des caches réels.
8. Le commit porte la disclosure IA du §3.

## 10. Où sont les lots 15 et 16

Ils sont **déjà planifiés ailleurs** et ne sont pas repris ici :

- **lot 15** — externaliser les **seize** instructions codées en dur en Python que
  `docs/mesures/inventaire-couplage-fr.md` §5 liste site par site, dont une seule est aujourd'hui
  surchargeable par un pack (`traduction_unitaire.CLE_CONSIGNE`).
- **lot 16** — évaluer les deux poids **Apache-2.0** entraînés sur du webtoon avant tout
  affinage. `docs/mesures/webtoon-2026-08-26.md` conclut que sa condition d'ouverture est remplie :
  le taux de fausses détections reste à 15–17 % contre une cible de 5 %, et le
  sous-comptage (5,9 bulles par bande là où ~25–35 seraient attendues) désigne le
  **détecteur**, pas l'OCR.

  ⚠ **Son étape L9.0 est faite** (2.8.0, `docs/mesures/detecteurs-candidats-2026-08-26.md`) : aucun des
  deux poids ne remplace le détecteur, et celui qui récupère 52 des 188 planches muettes ne
  détecte **pas des ballons** — sur un échantillon labellisé de 33 régions, zéro. Il est
  reporté au `PLAN-21`. Le sous-comptage du webtoon reste entier, les quatre seuils d'abandon
  de L9.3 sont écrits (`docs/mesures/seuils-affinage-detecteur.md`), et **aucun entraînement n'a
  commencé**. Le banc qui reproduit tout cela est `tools/banc_candidats.py`.

`PLAN-17` consomme le lot 15 comme prérequis plutôt que de refaire son relevé.
`PLAN-21` et `PLAN-22` se placent après le lot 16, sans en dépendre.
