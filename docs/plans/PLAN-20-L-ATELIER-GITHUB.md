# PLAN 20 — L'atelier GitHub : automatiser ce qui se vérifie

> **Lire `00-CONTEXTE-AGENT.md` d'abord.**
>
> **Nature attendue** — CORRECTIF pour l'essentiel : rien du chemin nominal ne change, aucun
> cache, aucune clé de config. MINEUR pour L20.2 (rendre la police de test configurable est une
> nouvelle clé) et L20.7 (le workflow de publication est une capacité neuve).
>
> **Charge estimée** — 8 jours. Le meilleur rapport du lot, parce que chaque garde-fou ajouté
> ici remplace une vérification manuelle que quelqu'un oubliera.
>
> **Indépendant de tout.** À faire tôt : les cinq plans suivants en bénéficient.

---

## Ce qui existe déjà, et c'est bien

`.github/workflows/ci.yml` porte **deux jobs**, tous deux `windows-latest`, Python 3.12 :

1. **tests** — `ruff check .` puis `pytest -m "not lent and not modeles" -q`, avec
   `QT_QPA_PLATFORM: offscreen` et l'installation de PySide6 justifiée par une mesure : « sans
   lui, cinq fichiers de tests GUI ne sont pas collectés du tout — **2 007 tests contre
   1 879** ». Le fichier note en plus 30 tests non collectés en CI
   (`test_manga_detection.py`, `test_manga_ocr.py`, qui font `importorskip`), et le dit.
2. **banc de détection** — cache des poids ONNX (clé portant l'empreinte du modèle),
   récupération si le cache est froid avec une garde de taille, puis
   `pytest tests/test_banc_corpus_synthetique.py -m "modeles"` sur `tests/corpus/synthetique/`,
   et le build casse si le rappel baisse ou si les faux positifs montent.

Avec `concurrency` + `cancel-in-progress`, un `timeout-minutes`, le cache pip, et des
commentaires qui expliquent chaque choix. **C'est au-dessus de la moyenne**, et le second job
est exactement ce qu'un projet de vision par ordinateur devrait avoir et n'a presque jamais.

Ce plan n'y touche pas. Il ajoute ce qui manque.

---

## Étape 0 — Établir ce qui est vérifié à la main aujourd'hui

Un document, pas de code. Listez chaque vérification qu'un humain fait aujourd'hui avant ou
après un commit, et pour chacune : est-elle automatisable, et que coûterait son oubli ?

Les candidats connus, à compléter :

| Vérification | Coût d'un oubli |
|---|---|
| `core/version.py` correspond à la première entrée du CHANGELOG | `tests/test_version.py` le couvre **déjà** — vérifiez qu'il tourne bien en CI |
| le commit porte la disclosure IA de `CONTRIBUTING.md` | un historique non conforme à la politique de financement, **irréparable rétroactivement** |
| un chiffre de communication porte sa source et son dénominateur | la règle de `docs/chiffres-de-reference.md` violée en silence |
| `PUBLICATION-ANGELITH.md` ne partent pas vers le miroir public | une fuite — un commit existe déjà pour ça (`221a902`), donc le risque est réel |
| aucune œuvre commerciale ne rentre sous `sources/` ou `build/` | la purge du corpus (`86c3d3d`, `b3d1eaa`) défaite |
| le lot publie son tableau daté | la règle de `docs/roadmap.md` non tenue |
| les poids ONNX ne sont pas commités | 104 Mo + 94,7 Mo dans l'historique, définitivement |

Publiez le tableau. Il décide de l'ordre des étapes.

---

## L20.1 — Le garde-fou de la disclosure IA

**Pourquoi en premier.** `CONTRIBUTING.md` l'exige, et le dossier de financement du projet en
dépend : la politique d'IA générative de l'organisme visé prévoit que **les livrables purement
générés par IA ne sont pas éligibles au paiement**, et que le code généré doit voir ses prompts
figurer dans les messages de commit ou dans une documentation accessible. Un historique de douze
mois ne se documente pas rétroactivement.

**À faire.** Un job sur `pull_request` qui parcourt les commits de la branche et vérifie que
chaque message porte les trois lignes attendues :

```
Assisté par : <outil> (<modèle>), <date ISO>
Prompt : « … »
Revu et testé manuellement : oui|non
```

⚠ **Trois précautions, sinon le garde-fou devient un obstacle.**

1. **Un commit non assisté est légitime.** Une correction de coquille écrite à la main n'a pas de
   prompt. Le job doit accepter `Assisté par : aucun` — explicite — plutôt que d'exiger une
   ligne vide de sens ou de laisser passer l'absence.
2. **Ne bloquez pas, avertissez d'abord.** Livrez le job en `continue-on-error` pendant une
   période, publiez le taux de conformité, et **seulement alors** rendez-le bloquant. Un
   garde-fou qui casse tous les builds le jour de sa livraison est désarmé le lendemain.
3. **`Revu et testé manuellement : non` doit passer le job mais échouer la fusion.** C'est une
   information honnête, pas une faute — mais `CONTRIBUTING.md` dit que les contributions que
   personne n'a lues ne sont pas acceptées.

---

## L20.2 — Débloquer Linux, en réglant la vraie cause

**Le constat.** La CI est `windows-latest` et le commentaire explique pourquoi, honnêtement :
`tests/conftest.py` fabrique sa planche synthétique avec `C:/Windows/Fonts/msgothic.ttc` et
**skippe** la fixture si la police manque. Sur un runner Linux, toute la couverture détection /
OCR / orchestrateur serait sautée **en silence** — CI verte, plus rien de testé. Le commentaire
conclut : « Rendre la police configurable est souhaitable ; tant que ce n'est pas fait, le
système d'exploitation fait partie du contrat. »

**C'est la bonne analyse, et c'est le moment de la traiter.** Le projet vise l'empaquetage
Windows **et Linux** dans sa feuille de route ; une CI qui ne teste jamais Linux le découvrira
au moment de l'empaqueter.

**À faire, dans cet ordre.**

1. **Une variable d'environnement ou une clé de config** pour la police de test, avec une liste
   de candidats par plateforme et un repli documenté. Les runners Linux GitHub ont des polices
   installables en une ligne d'`apt` ; choisissez-en une qui couvre les kana et les kanji.
2. **Un test qui échoue si la fixture est sautée.** C'est le cœur du problème et pas la police :
   aujourd'hui, l'absence de police produit un skip **silencieux**. Un test de garde qui vérifie
   que `synthetic_manga_page` est disponible, et qui **échoue** si elle ne l'est pas, transforme
   une couverture perdue en erreur visible. **Écrivez-le d'abord** — même sur Windows, il ne coûte
   rien et il aurait rendu le problème visible depuis le début.
3. **Puis la matrice** `[windows-latest, ubuntu-latest]`, et publiez le compte de tests collectés
   sur chaque OS. Si Linux collecte moins, le job échoue — c'est la même logique que la mesure
   des **2 007 contre 1 879** qui justifie l'installation de PySide6.

⚠ **N'ajoutez pas macOS.** `docs/roadmap.md` le classe hors périmètre, faute de machine pour le
tester. Une CI verte sur un OS que personne n'utilise donne une fausse assurance.

---

## L20.3 — La cohérence des chiffres, vérifiée par un test

`docs/chiffres-de-reference.md` pose une règle de dépôt : **tout chiffre de communication porte
sa source et son dénominateur.** Rien ne la vérifie.

**À faire.** Un test — pas un workflow, un test : il doit tourner en local aussi — qui vérifie
les invariants **vérifiables mécaniquement** :

1. Le nombre de tests annoncé dans `README.md`, `CONTRIBUTING.md` et `docs/COMMANDES.fr.md` est
   **le même partout**, et porte sa date. Ces fichiers ont déjà divergé : 1 908, 1 657, « un
   millier et demi » et 2 262 ont tous circulé.

   ⚠ **Et le dépôt porte aujourd'hui trois dénominateurs légitimes qu'il ne faut pas unifier de
   force** : **2 262** (total, toutes dépendances optionnelles), **2 206** (la boucle courte,
   `-m "not lent and not modeles"`), et le couple **2 007 / 1 879** de `ci.yml` qui mesure
   l'effet de PySide6. Le test doit vérifier que chaque emplacement cite **le bon** avec **son
   étiquette**, pas qu'ils sont tous égaux.
2. `core/version.py` correspond à la première entrée datée du CHANGELOG — **déjà couvert** par
   `tests/test_version.py`, à conserver.
3. Tout fichier `docs/banc-*.md` porte une date, un commit et une empreinte de `config.yaml` —
   c'est ce que `tools/banc.py --markdown` produit, donc c'est vérifiable.
4. Les licences de modèles citées dans `manga_models/README.md`, `docs/ai-provenance.md` et
   `docs/chiffres-de-reference.md` **concordent**. Elles sont trois à les mentionner.

⚠ **Ne tentez pas de vérifier que « tout chiffre porte son dénominateur ».** Ce n'est pas
décidable par une expression régulière, et un garde-fou qui produit des faux positifs sur de la
prose sera contourné. Vérifiez les invariants ci-dessus, qui sont exacts, et laissez la règle
générale à la relecture humaine.

---

## L20.4 — Le garde-fou de fuite et de corpus

Deux risques dont le dépôt porte déjà la trace, donc deux risques réels.

**La fuite vers le miroir public.** Un commit (`221a902`) existe déjà pour empêcher
`PUBLICATION-ANGELITH.md` de partir vers `Angelith`. Un garde-fou de commit est plus fiable
qu'une consigne : un job qui, sur toute référence poussée vers le miroir, vérifie qu'aucun
fichier de la liste noire n'y figure.

**Le corpus commercial.** La purge (`86c3d3d`, `b3d1eaa`) est un acquis à ne pas défaire. Un job
qui échoue si un fichier apparaît sous `sources/` ou `build/` dans un diff — ces deux dossiers
sont dans `.gitignore`, mais `.gitignore` a déjà échoué une fois : son propre commentaire raconte
que « `git check-ignore -v build/` sortait en erreur et 3 347 fichiers se sont retrouvés suivis,
dont 2 549 sous `build/` et 654 sous `sources/` ».

Ajoutez au même job : aucun `.onnx`, aucun `.pt`, aucun `.safetensors` dans un diff. Les poids
se téléchargent, ils ne se committent pas — et une fois dans l'historique, ils y sont pour
toujours.

---

## L20.5 — Le banc étendu, et sa limite honnête

Le job de banc actuel tourne sur le **corpus synthétique** (`tests/corpus/synthetique`), qui est
dans le dépôt. C'est le bon choix : reproductible, redistribuable, et il attrape les régressions.

**Ce qu'il ne peut pas faire** : mesurer sur les 17 projets réels, qui ne sont pas dans le dépôt
et ne peuvent pas y être. Le tableau `--tous` restera donc une opération locale.

**À faire.**

1. **Un job qui vérifie que le banc tourne**, sur le synthétique, à chaque PR — c'est fait. En
   plus : publier son tableau en **résumé de job** (`$GITHUB_STEP_SUMMARY`), pour qu'il soit
   lisible sans ouvrir les logs. Trois lignes de `>>`.
2. **Un job hebdomadaire** (`schedule`) sur le synthétique, avec les poids réels et le marqueur
   `modeles`. Une régression due à une mise à jour d'`onnxruntime` ou de `numpy` n'apparaît
   aujourd'hui qu'au prochain run manuel.
3. **Un artefact.** Le tableau produit en CI est téléchargeable et conservé. C'est ce qui permet
   de comparer deux dates sans avoir gardé le terminal ouvert.
4. ⚠ **Écrire dans le job ce qu'il ne mesure pas.** Un job nommé « banc de détection » qui ne
   voit que le synthétique peut laisser croire que le corpus réel est couvert. Une ligne dans le
   résumé : « corpus synthétique uniquement — le corpus réel se mesure en local par
   `python tools/banc.py --tous` ».

---

## L20.6 — La discipline de livraison, automatisée

Chaque lot doit produire : une entrée de CHANGELOG datée, une version cohérente, un document de
mesure. C'est aujourd'hui tenu à la main, et remarquablement bien tenu — mais c'est exactement
ce qui glisse quand un lot est livré tard le soir.

**À faire.** Un job sur `pull_request` qui vérifie que si `manga/`, `core/`, `pipeline/`,
`gui/` ou `langues/` a changé, alors :

1. `CHANGELOG.md` a changé aussi ;
2. `core/version.py` a changé aussi, ou l'entrée de CHANGELOG est sous `[Non publié]` ;
3. si `langues/**/prompts/**` a changé, l'entrée de CHANGELOG **nomme le fichier** de prompt —
   la règle de numérotation l'exige littéralement, et c'est ce qui rend
   `git checkout <tag> -- langues/` utile ;
4. si un fichier de `docs/banc-*.md` est ajouté, il porte une date dans son nom.

⚠ Une échappatoire nommée est nécessaire — une étiquette de PR `sans-changelog` pour une
correction de commentaire — sinon le garde-fou coûtera plus qu'il ne rapporte. Mais elle doit
être **explicite et visible**, pas un mot magique dans le corps du message.

---

## L20.7 — Publier : tag, release, miroir

Trois automatisations qui remplacent trois gestes manuels.

1. **Sur un tag `vX.Y.Z`** : vérifier que le tag correspond à `core/version.py`, **extraire la
   section de CHANGELOG correspondante** et en faire le corps de la release GitHub. Le CHANGELOG
   fait 339 Ko et ses entrées sont détaillées — c'est déjà des notes de version, il n'y a qu'à
   les découper.
2. **La publication vers le miroir `Angelith`.** `docs/PUBLICATION-ANGELITH.md` décrit la
   procédure ; l'automatiser rend la liste noire de L20.4 obligatoire par construction plutôt que
   par vigilance.
3. **Dependabot**, sur `pip` et sur `github-actions`, en groupé et mensuel. ⚠ Pas en
   hebdomadaire : sur un projet à un mainteneur, un flux de PR de dépendances devient du bruit
   qu'on cesse de lire, et c'est comme cela qu'une mise à jour cassante passe.

⚠ **Aucun empaquetage dans ce lot.** Les installeurs un-clic Windows/Linux sont un jalon distinct
de `docs/roadmap.md`, avec son propre périmètre (dépendances embarquées, Pandoc, WeasyPrint,
Ollama). Ce lot livre le **squelette** — un job de release qui sait publier un artefact — pas
l'artefact.

---

## Critères d'acceptation

| # | Critère |
|---|---|
| 1 | Le tableau de l'étape 0 est publié : chaque vérification manuelle, son coût d'oubli, son statut (automatisée / laissée à l'humain / non décidable) |
| 2 | Le job de disclosure IA tourne, son taux de conformité sur l'historique récent est publié, et il est livré **non bloquant** avec la date à laquelle il le deviendra |
| 3 | Un test échoue si `synthetic_manga_page` est sautée. **Ce test seul justifie le lot** |
| 4 | La CI tourne sur Windows **et** Linux, et échoue si le nombre de tests collectés diffère entre les deux |
| 5 | Le nombre de tests annoncé est identique dans les trois fichiers qui le citent, et un test le vérifie |
| 6 | Un job refuse un diff contenant un poids de modèle, un fichier sous `sources/` ou `build/`, ou un fichier de la liste noire de publication |
| 7 | Le tableau du banc apparaît dans le résumé de job, avec la mention de ce qu'il ne mesure pas |
| 8 | Un tag produit une release dont le corps est la section de CHANGELOG correspondante |
| 9 | Chaque job a un `timeout-minutes` et une action épinglée par version |
| 10 | `ruff check .` et la boucle courte passent, sur les deux OS |

---

## Ce que ce lot ne fait pas

- Aucun empaquetage, aucun installeur.
- Aucune couverture de code. ⚠ **Et c'est volontaire** : un seuil de couverture sur un dépôt de
  57 000 lignes dont la valeur est dans des mesures et des garde-fous produirait des tests écrits
  pour le chiffre. Le projet a déjà une meilleure métrique — le banc — et elle mesure ce qui
  compte.
- Aucune publication sur PyPI. Le projet n'est pas empaqueté **et ne veut pas l'être** ; c'est
  écrit dans `core/version.py` et c'est la raison de l'absence de `pyproject.toml`.
- Aucun changement au pipeline ni à l'interface.
