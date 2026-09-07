# PLAN 32 — Le run se regarde : les phases, l'objet en cours, le temps qui reste

> **Lire `00-CONTEXTE-AGENT.md`, puis `README-INTERFACE-31-37.md`.**
>
> **Nature attendue** — **MINEUR**, avec une réserve : L32.2 étend le protocole `Reporter`, qui
> est partagé par les trois briques et les deux interfaces. L'extension doit être **iso pour la
> console** — une méthode de plus avec un corps vide dans la classe de base — sinon elle devient
> un MAJEUR de fait.
>
> **Charge estimée** — 8 jours, dont 2 de mesure pure à l'étape 0.
>
> **Prérequis : `PLAN-31`.** La progression doit se voir depuis n'importe quelle destination ;
> l'écrire avant que les destinations existent, c'est l'écrire deux fois.

---

## 1. L'état, relevé à la source le 2026-09-04 (2.24.1, `8e5ee5a`)

### 1.1 Ce qui existe déjà, et il y en a plus qu'on ne croit

Le diagnostic « on n'a aucune information sur le déroulement » est **faux à moitié**, et cette
moitié-là est bien faite. À ne pas réécrire :

| Brique existante | Fichier | Ce qu'elle fait |
|---|---|---|
| canal chiffré | `core/reporter.py:progres` (L74) | `(courant, total)`, appelé par l'orchestrateur |
| canal deviné | `gui/travailleur.py:progression_de_stage` (L234) | lit `Page 12/131` dans le libellé — **repli** documenté |
| signaux | `gui/travailleur.py:SignauxTravail` | `ligne`, `progression`, `debut`, `fin`, `file` |
| temps restant | `gui/avancement.py:Estimateur` | débit **observé**, fenêtre glissante de 12, minimum 4 points |
| barre | `gui/fenetre.py:_avancer` (L975) | `%v / %m (%p%) — ~1 h 40 restantes` |
| indéterminé | idem, branche `else` | `setRange(0, 0)` quand `total == 0` |
| trois phases | `illustration/progression.py` | modèle **sans Qt**, `fraction()` rend `None` plutôt qu'un faux % |

`illustration/progression.py` est le précédent à suivre, et sa docstring porte déjà la règle
que ce plan généralise : « il ne convertit jamais un temps en pourcentage tant qu'il n'a pas de
quoi », parce que le coût d'une image varie d'un facteur **14,7** sur la machine de référence
(103,7 s à 1 524 s).

### 1.2 Les quatre défauts, et trois sont mesurables

**(a) La barre recule, et elle recule beaucoup.** `manga/orchestrator_manga.py` appelle
`progres(i, total)` dans **deux balayages successifs sur le même dénominateur** :

| Ligne | Appel | Balayage |
|---|---|---|
| L894-895 | `stage(f"Page {i}/{total} …")` + `progres(i, total)` | A — détection, nettoyage, OCR |
| L1614-1616 | `stage(f"Page {i}/{total} …")` + `progres(i, total)` | B — traduction, planche par planche |
| L1666-1668 | `stage(f"Lot planches {a}→{b}")` + `progres(groupe[-1], total)` | B — traduction par lots |

`_avancer` fait `self.barre_progres.setValue(courant)` sans mémoire. Sur un tome de 131
planches, la barre monte donc à 131, **retombe à 1**, remonte à 131. La règle Microsoft est
explicite et elle est écrite pour ce cas exact : « a progress bar loses its value if it
restarts […] have all the steps in the operation share a portion of the progress and have the
progress bar go to completion once », et « always increase progress monotonically ».

⚠ **`Estimateur` a déjà vu le problème et l'a traité correctement de son côté** :
`avancement.py:noter` L63-69 vide sa fenêtre quand `courant` recule — « un run manga repasse
par la planche 1 au balayage B : c'est un NOUVEAU régime ». Le modèle est juste, **la barre
ne l'est pas**. Conséquence chiffrée à publier à l'étape 0 : à chaque changement de régime, le
temps restant disparaît pendant `MINIMUM = 4` planches.

**(b) Rien de durable ne dit où on en est.** Le libellé d'étape part dans `_journaliser` (L950)
qui écrit une ligne de journal **et** appelle `statusBar().showMessage(message, 8000)`. Huit
secondes. Sur un run de plusieurs heures, l'étape en cours n'est lisible que dans un journal
replié à zéro par défaut (`reglages.DEFAUTS["journal"] = [940, 0]`), qui ne se déplie tout
seul que sur un `warn`.

**(c) L'objet en cours existe dans la chaîne et n'arrive nulle part.** Le nom du fichier est
là — `f"Page {i}/{total} — {page_path.name} ({', '.join(etapes_cv)})"` — mais il voyage dans un
libellé d'étape, donc dans le journal. La barre, elle, ne connaît que deux entiers. NN/g
demande le contraire : « text explaining the process (e.g. *Updating address 3 of 50*) ».

**(d) La phase n'est pas un concept.** Un run manga traverse détection → nettoyage → OCR →
sfx → terminologie → traduction → rendu (`ETAPES_MANGA`, `gui/lanceur.py` L34-42), et un run LN
traverse `STAGES` de `pipeline/orchestrator.py`. L'interface n'affiche jamais « phase 3 sur 7 » :
elle affiche l'étape courante en texte, une fois, huit secondes.

### 1.3 Les normes, et elles sont utilisables telles quelles

- **Déterminé plutôt qu'indéterminé** dès que l'opération est bornée, « even if duration cannot
  be accurately predicted » ; l'indéterminé se **convertit** en déterminé dès qu'on sait.
- **Ne jamais combiner** indéterminé et pourcentage, ou indéterminé et temps restant.
- **Temps restant, pas temps écoulé**, rafraîchi au moins toutes les 5 s, sans fausse précision
  (« si la plus grande unité est l'heure, donner les minutes mais pas les secondes ») — c'est
  déjà exactement ce que fait `avancement.duree_lisible`, dont la docstring dit « annoncer
  1 h 42 min 07 s sur une estimation à ±20 % affiche une précision qu'on n'a pas ».
- **`Arrêter` et non `Annuler`** quand l'opération partiellement faite est conservée. Le bouton
  du dépôt s'appelle déjà « Arrêter proprement » et son infobulle décrit la garantie. C'est
  conforme, ne le touchez pas.
- **Sous les 10 s, pas de barre déterminée** ; entre 2 et 10 s, une animation ; au-delà,
  pourcentage et compte d'étapes.

---

## 2. Étape 0 — enregistrer le canal réel avant de modéliser

### 0.1 — La trace d'un run, brique par brique

Ajoutez un enregistreur temporaire (un `Reporter` décorateur qui journalise
`(horodatage, méthode, arguments)` en JSONL) et capturez **trois** runs réels :

| Run | Ce qu'on veut savoir |
|---|---|
| un tome manga paginé (~130 planches) | la séquence complète des `stage` / `progres` / `block` |
| la bande webtoon du corpus (`webtoon A` Chap.11) | idem, sur le seul volume à bande longue |
| un tome light novel | `volume` / `chapter` / `stage` / `block` — le LN a un `volume()`, le manga non |

Publiez, pour chacun : le nombre de fois où `courant` **recule**, le nombre de dénominateurs
distincts vus, la durée de chaque phase en secondes et en pourcentage du run, et le nombre de
secondes cumulées pendant lesquelles **aucun** temps restant n'était affichable.

⚠ **C'est ce dernier chiffre qui justifie le lot ou l'enterre.** S'il est de 30 s sur un run de
trois heures, il n'y a pas de sujet et il faut l'écrire. Le tableau du dépôt suggère le
contraire — deux changements de régime × 4 planches, sur des planches qui coûtent des dizaines
de secondes chacune — mais « suggère » n'est pas une mesure.

### 0.2 — Le poids des phases, mesuré ou rien

Un modèle monotone a besoin d'un poids par phase. **Ces poids doivent être mesurés**, et le
dépôt a déjà de quoi : `perf.log` est écrit par `cli.make_reporter` dans tous les cas (le flag
`--verbose` ne décide que de l'AFFICHAGE — c'est écrit dans `app.py` et dans `fenetre.py`), et
`tools/banc.py --tous` agrège les volumes de `build/`.

Livrez `tools/banc_progression.py` qui rend, depuis les `perf.log` des 15 volumes de `build/` :

| Brique | Phase | Part médiane du run | n volumes | écart min-max |
|---|---|---:|---:|---:|

⚠ **Si l'écart min-max d'une phase dépasse un facteur 3, cette phase n'a pas de poids
utilisable** — et la règle est alors celle d'`illustration/progression.py` : on n'invente pas
un pourcentage, on affiche l'avancement **compté** (« planche 42 sur 131, phase traduction »)
et la barre reste sur le compte d'objets, pas sur un temps.

⚠ **Le saut intelligent fausse tout poids naïf.** Le dépôt mesure 629 ms pour constater qu'un
chapitre est à jour contre 3 min 9 s pour le refaire. Un run de reprise n'a donc pas du tout la
même répartition qu'un run complet. Publiez **deux** tableaux — run neuf, run de reprise — ou
dites que le second n'a pas assez d'échantillons.

---

## L32.1 — Un modèle de progression sans Qt, et monotone par construction

`core/progression.py` — pas dans `gui/`, parce que la console en a besoin aussi, et pas dans
`manga/`, parce que le LN et l'illustration s'en servent.

Ce qu'il porte :

```python
Phase = namedtuple("Phase", "identifiant libelle poids")   # poids MESURÉ, ou None

class Progression:
    def declarer(self, phases: list[Phase]) -> None: ...
    def entrer(self, identifiant: str) -> None: ...        # change de phase
    def avancer(self, courant: int, total: int, objet: str = "") -> None: ...
    def fraction(self) -> float | None: ...                # None = indéterminé, JAMAIS un faux %
    def restant(self) -> float | None: ...                 # via avancement.Estimateur
    def libelle(self) -> str: ...                          # « Traduction (4/7) — planche 42/131 »
```

Trois invariants, chacun avec son test :

1. **`fraction()` ne décroît jamais.** Rejouez les traces JSONL de l'étape 0 dans le modèle et
   assertez la monotonie sur la séquence entière. C'est le test qui aurait échoué avant le lot ;
2. **une phase sans poids rend `None`**, et le modèle passe alors en « compté » : `avancer`
   reste utile, `fraction` se tait. Pas de repli sur des poids égaux — des poids égaux inventés
   sont un faux pourcentage avec l'aplomb d'un vrai ;
3. **aucune horloge murale** : l'horloge est injectée, comme dans `avancement.Estimateur` et
   `illustration/progression.py`, pour que chaque durée se teste à la milliseconde sans dormir.

⚠ **`Estimateur` n'est pas remplacé, il est utilisé.** Sa fenêtre glissante de 12 et son
minimum de 4 sont motivés par une mesure (changement de régime en moins d'une minute). Ce lot
lui donne un débit qui ne recule plus, ce qui fait exactement disparaître le vidage de fenêtre
de `noter` L63-69 — vérifiez-le sur les traces, et **gardez le vidage** : il reste juste si un
jour un canal recule.

⚠ **`illustration/progression.py` n'est PAS fusionné dans ce module.** Il porte trois phases
nommées et un état propre à la brique (bascule VRAM), il est testé, il marche. Ce lot lui donne
au plus une façade commune si elle sort naturellement — sinon deux modèles cohabitent, et ce
n'est pas une dette.

## L32.2 — Le canal apprend à dire QUOI, et la console ne bouge pas

`Reporter.progres(courant, total)` ne dit pas sur quoi il progresse. Deux options, à trancher
et à écrire :

| Option | Coût | Effet |
|---|---|---|
| `progres(courant, total, objet="")` — argument optionnel | tous les appelants restent valides | l'objet arrive **chiffré**, plus par regex |
| `Reporter.objet(nom)` — méthode neuve à corps vide | une méthode de plus dans 4 reporters | sépare les canaux, plus verbeux |

⚠ **Quel que soit le choix : la sortie console doit être identique octet pour octet.** Le
critère 3 du contexte agent l'exige (« le comportement livré par défaut est iso pour un
utilisateur qui ne touche à rien »). `RichReporter` et le `Reporter` texte ignorent le nouveau
champ, et un test compare la capture d'un run `--dry-run` avant/après.

⚠ **`progression_de_stage` (le repli par regex) reste.** Sa docstring dit pourquoi : « si un
jour le libellé change, la barre cesse d'avancer et rien d'autre ne casse. Une progression est
un confort, pas une donnée. » Les étapes non instrumentées existent encore ; le repli les
couvre. Ce lot **ajoute** un canal, il n'en retire pas.

## L32.3 — Le bandeau de run, visible de partout

Un widget persistant, en pied de fenêtre, propriété de la fenêtre (donc visible depuis les six
destinations du `PLAN-31`), portant **exactement** :

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Manga · Mon Manga / Vol.2      Traduction (5/7)                            │
│ ███████████████████░░░░░░░░░░  planche 84 / 131   ~1 h 10 restantes        │
│ page_0084.png · lot 80→99 · 3 planches par appel        [Arrêter proprement]│
└────────────────────────────────────────────────────────────────────────────┘
```

Les règles qui décident de son contenu, chacune tirée d'une source citée au §1.3 :

1. **temps restant, jamais temps écoulé** en position principale ; rafraîchi au moins toutes les
   5 s ; formaté par `avancement.duree_lisible`, qui est déjà conforme ;
2. **indéterminé = ni %, ni ETA.** Quand `fraction()` rend `None`, la barre passe en
   `setRange(0, 0)` et la ligne de droite affiche le compte (« planche 84 / 131 ») **sans**
   temps. C'est ce que fait déjà `_sur_debut` pour l'illustration (L781-789) et le commentaire
   qui l'accompagne est le bon argument ;
3. **l'objet en cours est nommé** — nom de fichier, ou plage de lot. C'est le « 3 of 50 » de
   NN/g ;
4. **`Arrêter proprement` reste `Arrêter`**, avec l'infobulle existante qui décrit la garantie
   (frontière propre, tout ce qui est fait est conservé, même mécanisme que `--stop`) ;
5. **rien n'y clignote**, et il disparaît quand aucun run ne tourne — un bandeau vide en
   permanence devient du décor qu'on cesse de lire.

⚠ **Le journal reste.** Il n'est pas décoratif — la docstring de `fenetre.py` le dit — et il est
le seul endroit où l'on relit ce qui s'est passé après un incident. Le bandeau ne le remplace
pas ; il cesse d'obliger à le lire pour savoir où on en est.

## L32.4 — La fenêtre le dit aussi quand elle n'est pas devant

Un run dure des heures : l'utilisateur va faire autre chose. Deux gestes, et le second est une
décision à trancher sur mesure.

**(a) Le titre de fenêtre porte l'avancement.** Microsoft le recommande explicitement pour la
lisibilité dans la barre des tâches : « optimize the title for display on the taskbar by
concisely placing the distinguishing information first. Example: *66% Complete* ». Donc
`66 % — Manga Vol.2 — Angelith [*]`.

⚠ **Attention au `[*]`** : c'est l'emplacement où Qt insère la marque « document modifié »
(`setWindowModified`, cf. L147). Le titre est déjà un gabarit à contrainte — ne le construisez
pas par concaténation naïve, et gardez un test sur les quatre combinaisons (run/pas de run ×
modifié/pas modifié).

**(b) La barre des tâches Windows.** ⚠ `QtWinExtras` — donc `QWinTaskbarProgress` — **n'existe
plus en Qt 6**. Les options réelles sont : `ITaskbarList3` par `ctypes`, une dépendance tierce,
ou **rien**. Ce lot :

1. vérifie ce qu'il en est **sur la version de PySide6 installée le jour du lot**, et publie le
   constat (règle des affirmations d'état, §5 bis du contexte) ;
2. si c'est `ctypes`, mesure ce que ça coûte : du code Windows-spécifique dans `gui/`, dans un
   dépôt qui garde `Linux/macOS` en ligne de mire (`PLAN-20`), pour un confort ;
3. **et a le droit de livrer « rien », documenté.** Le titre de fenêtre couvre déjà le besoin de
   la barre des tâches, et c'est précisément l'usage que Microsoft prête au titre.

## L32.5 — La fin du run se remarque

Aujourd'hui `_sur_fin` (L796) écrit une ligne de journal (`info` ou `warn`) et libère les
reporters. Un run de nuit qui finit à 3 h du matin ne laisse donc qu'une ligne dans un journal
replié.

Ce lot ajoute, sans dépendance nouvelle :

- un **état terminal persistant** dans le bandeau : « Terminé — 131 planches, 2 h 14, 3
  avertissements » avec un bouton qui déplie le journal filtré sur les avertissements ;
- ⚠ **rien qui vole le focus.** Pas de boîte modale à la fin d'un run : l'utilisateur peut être
  en train de taper une réplique dans la retouche, et un dialogue qui surgit avale la frappe.
  `QSystemTrayIcon.showMessage` est acceptable **si** elle est optionnelle et désarmée par
  défaut ; une modale ne l'est pas.
- la conservation de ce que fait déjà `cli.finalize_power` : `--keep-awake` et `--shutdown`
  existent côté CLI et TUI (`app.py`), **et ne sont pas exposés dans le lanceur graphique**.
  Les exposer est du `PLAN-33` ; ce lot ne fait que ne pas les casser.

## L32.6 — Ce qui reste indéterminé le reste, et le dit

Trois endroits du dépôt sont légitimement indéterminés, et le lot doit les **nommer** plutôt que
leur inventer une barre :

| Endroit | Pourquoi | Ce que le bandeau affiche |
|---|---|---|
| une génération d'image | facteur 14,7 entre la plus rapide et la plus lente | phase + images terminées / demandées |
| un lot de traduction en cours | l'unité d'avancement est le lot, pas la planche | `Lot 80→99` + barre indéterminée |
| la première inférence de détection | le chargement du modèle ONNX est dans la première planche | « chargement du modèle » explicite |

⚠ Le troisième cas est celui qui fait mentir un ETA naïf, et `avancement.py` le dit déjà dans
son commentaire sur `MINIMUM` : « un débit tiré de deux planches dont l'une portait le
chargement du modèle ONNX est une estimation inventée ». Ne réglez pas ça par une constante
d'amorçage ; annoncez la phase.

---

## 3. Les critères de ce lot

1. Les trois traces JSONL de l'étape 0.1 sont publiées, avec le nombre de reculs, le nombre de
   dénominateurs distincts et **les secondes cumulées sans temps restant affichable**, par
   brique.
2. Le tableau de poids de phases de l'étape 0.2 est publié avec son `n` de volumes et son écart
   min-max ; toute phase dont l'écart dépasse un facteur 3 est livrée **sans poids**, et c'est
   écrit.
3. `core/progression.py` existe, ne connaît ni Qt ni horloge murale, et un test rejoue les
   traces réelles en assertant que `fraction()` **ne décroît jamais**. Ce test échoue avant le
   lot, sur la séquence enregistrée.
4. La sortie console d'un run `--dry-run` est identique avant/après, comparée octet pour octet
   par un test.
5. Le bandeau affiche phase (i/n), objet en cours, avancement compté et temps restant ; il
   n'affiche **jamais** un pourcentage ou un ETA quand la fraction est indéterminée, et un test
   le vérifie sur les trois cas de L32.6.
6. Le titre de fenêtre porte l'avancement en tête, sans casser la marque `[*]` ; les quatre
   combinaisons sont testées.
7. La question de la barre des tâches est **tranchée par écrit** : `ctypes` mesuré et adopté, ou
   refusé avec son motif et sa date. Aucune dépendance tierce ajoutée pour ce confort.
8. Aucune boîte modale n'apparaît à la fin d'un run. La notification système, si elle est
   livrée, est désarmée par défaut.
9. `progression_de_stage` et son test existent toujours ; les étapes non instrumentées
   continuent d'avancer la barre.
10. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans modèle, sans GPU
    et sans endpoint LLM.
11. `docs/mesures/progression-<date>.md` reprend ces critères un par un, y compris les non
    tenus, et dit ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il ne change **aucun** ordre d'étapes de l'orchestrateur, aucune frontière d'arrêt propre,
  aucun checkpoint. Il observe.
- Il n'ajoute pas de paramètre de run et n'expose ni `--keep-awake` ni `--shutdown` : c'est
  `PLAN-33`.
- Il ne fusionne pas `illustration/progression.py` de force.
- Il ne remplace pas le journal, et ne le déplie pas plus souvent qu'aujourd'hui (`warn` reste
  le seul déclencheur).
- Il n'ajoute aucune dépendance, ni pour la barre des tâches, ni pour les notifications.
- Il ne mesure pas la qualité de traduction. Aucune ligne de ce lot ne touche à un prompt.
