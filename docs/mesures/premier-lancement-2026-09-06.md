# Le premier lancement — diagnostic structuré, dépendances, poids

**Lot 36** (`PLAN-36-LE-PREMIER-LANCEMENT.md`) · mesuré le **2026-09-06** · dépôt en **2.29.0**,
commit de départ `699c7aa` · `config.yaml`
SHA-256 `77cb4bf311ae654ff4b713f47b411b3a128901cacc90ad00a5abbf5cf3aedd6b` ·
Windows 11 Pro 26200, Python 3.12.3, RX 7900 XT.

---

## 0. Ce que la mesure ne dit pas

Écrit en tête, comme le veut la règle de la mesure honnête (§6 du contexte agent).

1. **Une seule machine, et elle est complète.** Toutes les dépendances optionnelles y sont
   installées — c'est le contraire d'une installation neuve, et c'est pourquoi l'étape 0 procède
   par **masquage** plutôt que par observation. Un masquage reproduit un symptôme ; il ne
   reproduit pas un environnement.
2. **Aucune machine neuve n'a été testée.** Le lot ne dit donc rien du premier lancement réel
   chez quelqu'un d'autre : ni du temps d'installation, ni de ce que Windows fait d'un
   téléchargement de 104 Mo, ni du comportement derrière un proxy d'entreprise. C'est ce que le
   `PLAN-37` devra mesurer sur l'exécutable gelé.
3. **Le tableau de l'étape 0.1 relève le message du DIAGNOSTIC**, pas celui qu'on obtient au
   milieu d'un run de trois heures. Les deux diffèrent, et le pire cas — `manga-ocr` sans réseau
   au milieu d'un run — a donc été mesuré séparément, à la main (§1.3).
4. **Les licences relevées ici portent la date du 2026-09-06.** Une licence est une affirmation
   d'état : elle vieillit. Celle de LaMa n'est toujours **pas établie**, et aucun geste du lot ne
   propose de le récupérer.
5. **L'isométrie de la sortie console est vérifiée pour tout ce qui ne dépend pas du réseau.**
   La section « — Ollama — » n'est pas gelée dans un test : elle demanderait un serveur en CI, ce
   que le critère 11 interdit. Elle a été comparée **à la main**, avant/après, sur cette machine
   avec le serveur en marche (§2.1) — un relevé, pas une garantie permanente.

---

## 1. Étape 0 — l'inventaire des pannes, par masquage

### 1.1 Une prémisse du plan est fausse, et il faut le dire

Le `PLAN-36` §1.1 écrit :

> ⚠ **`torch` n'est pas installé dans tous les environnements de travail** — vérifié : un import
> `torch` échoue dans l'environnement de cette session.

**C'est faux sur cette machine au 2026-09-06.** Relevé :

| Module | Import |
|---|---|
| `torch`, `manga_ocr`, `transformers` | ✅ |
| `onnxruntime`, `numpy`, `PIL`, `rapidocr_onnxruntime` | ✅ |
| `PySide6`, `weasyprint`, `httpx`, `fitz`, `docx`, `rich`, `rarfile` | ✅ |

La conclusion que le plan tirait de cette prémisse — « la brique manga est **optionnelle en
pratique** et l'application doit savoir se décrire avec des briques absentes » — **reste juste**,
et le lot la met en œuvre : `core/diagnostic.py` rend un verdict par dépendance, avec sa brique,
et `bloquants_pour()` ne fait jamais dépendre une brique d'une autre. Mais la prémisse elle-même
était une observation d'un environnement, pas une propriété du dépôt, et elle est ici corrigée
plutôt que recopiée.

**Ce qui manque réellement sur cette machine** — un seul point, et il est réel :

| Outil externe | `shutil.which` |
|---|---|
| `pandoc` | `C:\Program Files\Pandoc\pandoc.EXE` |
| `ollama` | `…\Programs\Ollama\ollama.EXE` |
| **`unrar`** | **absent** |
| **`unar`** | **absent** |
| `xelatex`, `7z` | absents (non requis : le moteur PDF est weasyprint) |

Les `.cbr` ne sont donc pas lisibles ici, et le dépôt guidé le disait déjà (`gui/depot_guide.py`,
lot 34). C'est le seul manque non simulé du relevé.

### 1.2 Le tableau de masquage — étape 0.1

Relevé par `python tools/inventaire_pannes.py --markdown`, outil livré par ce lot. Chaque cas
masque **une** chose : un exécutable retiré de `shutil.which`, un `import` neutralisé, un chemin
de poids ou de police pointé ailleurs, une `base_url` sur un port fermé. Rien n'est désinstallé.

| Dépendance masquée | AVANT le lot (texte du doctor) | APRÈS le lot (verdict structuré) | Gravité | Geste attaché ? |
|---|---|---|---|---|
| **Ollama arrêté** | `❌ Serveur injoignable.` + 3 lignes (démarrer, `base_url`, détail) — **12,1 s d'attente** | mêmes lignes, **plus** : brique `socle`, conséquence « la détection, le nettoyage et l'OCR, eux, tourneraient » | `bloquant` (socle) | ✅ déjà bon avant, désormais **attaché** |
| **PySide6 absent** | `SystemExit` : cause, commande pip, **et ce qui marche quand même** | inchangé — c'est le gabarit que le plan citait | — | ✅ déjà bon |
| **Pandoc absent** | `❌ Pandoc introuvable — https://pandoc.org/installing.html` | + conséquence « les sorties DOCX et EPUB du LN ne seront pas produites » + « ⚠ Angelith n'installe aucun logiciel système » | `bloquant` **pour le LN seul** | ✅ lien, **pas de bouton** |
| **moteur PDF absent** (weasyprint masqué) | `⚠ weasyprint non importable — le PDF ne sera pas généré (pip install weasyprint)` | + « DOCX et EPUB, si » + l'avertissement sur les libs système GTK/Pango | `degrade` | ✅ commande copiable |
| **`unrar` absent** *(réel, non simulé)* | rien dans les doctors ; message correct dans le dépôt guidé et dans `manga/ingest.py` | verdict `unrar` relevé par l'inventaire, avec sa conséquence et le repli `.cbz` | `degrade` | ✅ lien + repli |
| **poids ONNX absents** (`telechargement_auto: false`) | `❌ modèle introuvable : … — voir manga_models/README.md.` + `→ telechargement_auto: true le récupérerait tout seul.` | mêmes lignes en console ; verdict `reparable=True`, licence affichée avant, empreinte enregistrée après | `bloquant` **pour le manga seul** | ✅ **bouton** |
| **police absente** (`font_path` sur un fichier absent) | `⚠ police : …ComicNeue-Bold.ttf` + `[police] font_path pointe un fichier ABSENT` | + conséquence « le tome sortirait en …, sans un mot de plus » | `bloquant` (manga) | ✅ `python tools/polices.py` |
| **`manga-ocr` sans réseau ni cache** | **`OSError` de `transformers`, répété planche après planche** — cf. §1.3 | verdict `modele_ocr` proposé **avant** le run, geste de récupération explicite | — | ✅ **bouton**, en préalable |
| **ComfyUI arrêté** | hors des deux doctors (brique illustration, expérimentale) | **non traité par ce lot** — cf. §4 | — | ❌ |

⚠ Le tableau ci-dessus est celui des **messages**. La sortie console, elle, n'a pas changé d'un
octet : c'est §2.

### 1.3 Le cas silencieux, mesuré — et il est pire que le plan ne le supposait

Le plan demandait : « Que fait `manga-ocr` sans réseau, au milieu de la planche 12 d'un run de
nuit de trois heures ? **Mesurez-le.** »

**Protocole.** `HF_HOME` pointé sur un dossier vide, `HF_HUB_OFFLINE=1`, puis construction de
`manga.ocr.MangaOCR`.

**Résultat, 2026-09-06 :**

```
DIRE: OCR : kha-white/manga-ocr-base absent du cache — premier téléchargement (~424 Mo), une seule fois.
OSError: Can't load image processor for 'kha-white/manga-ocr-base'. If you were trying to load it
from 'https://huggingface.co/models', make sure you don't have a local directory with the same
name. Otherwise, make sure 'kha-white/manga-ocr-base' is the correct path to a directory
containing a preprocessor_config.json file
7,4 s
```

Trois constats, et le troisième est le vrai défaut :

1. **le message ne dit ni la cause ni le geste.** « make sure you don't have a local directory
   with the same name » est une piste fausse : le problème est l'absence de réseau ;
2. **la ligne utile est écrite AVANT l'échec** (« premier téléchargement, ~424 Mo ») et se perd
   dans le journal d'un run de nuit ;
3. ⚠ **et l'échec se répète pour CHAQUE planche.** Le lecteur est construit paresseusement dans
   `get_reader()` (`manga/orchestrator_manga.py` L403), à l'intérieur du filet par planche
   (`with _filet(i, "analyse")`, L824). `_lazy["ocr"]` n'est donc jamais posé, et un tome de 150
   planches produit **150 fois le même `OSError`** — au rythme de 7,4 s chacun, soit ~18 minutes
   d'échecs, un `RAPPORT.md` de 150 lignes identiques, et zéro sortie.

**Ce que le lot fait de ce constat.** Il ne touche pas à l'orchestrateur — ce serait hors du
périmètre écrit au §4 du plan. Il rend le cas **évitable** : la réparation `modele_ocr` récupère
le modèle **avant** le run, depuis la page Diagnostic, avec sa licence (Apache-2.0) affichée
avant le clic. C'est exactement ce que L36.2 demandait : « télécharger le modèle `manga-ocr` —
**avant** le run, pas au milieu — c'est tout l'objet. »

⚠ **Ce que le lot NE fait pas, et qui reste ouvert** : un run lancé sans le modèle échoue
toujours 150 fois. Rendre `get_reader()` mémorisant-en-échec, ou remonter le premier échec d'OCR
en `SystemExit` (comme le fait déjà un `.onnx` absent), demanderait de toucher au filet par
planche. C'est un candidat pour un correctif ultérieur, et il est nommé ici pour ne pas être
oublié.

### 1.4 Les trois classes de geste — étape 0.2, tranchée

Écrites dans `core/reparations.py`, et **testées** :

| Classe | Ce qui y entre | Ce qui est permis |
|---|---|---|
| `RECUPERABLE` | poids de détection, poids de texte, modèle `manga-ocr`, polices du dépôt | téléchargement après clic explicite, licence affichée **avant**, SHA-256 enregistrée après |
| `UTILISATEUR` | Pandoc, `unrar`, serveur LLM, WeasyPrint, ComfyUI | un lien, une commande copiable, une revérification — **jamais un bouton** |
| `HORS_PERIMETRE` | pilotes GPU, CUDA/ROCm | dire ce qui manque, et s'arrêter là |

⚠ **Le cas limite est l'installation des polices, et il est dans `RECUPERABLE`.**
`tools/installer_polices.ps1` **enregistre** les polices de `templates/fonts/` pour l'utilisateur
courant : aucun droit administrateur, aucun autre compte touché, `-Desinstaller` remet tout en
place. Enregistrer une police n'installe aucun logiciel — rien ne s'exécute, rien ne devient un
service, et le geste est réversible. La justification est écrite dans le module, et le test
`test_le_seul_sous_processus_lance_est_le_script_de_polices` la borne : c'est **le seul**
sous-processus que `core/reparations.py` lance.

---

## 2. L36.1 — Le diagnostic rend une structure, puis s'affiche

### 2.1 L'isométrie de la sortie console, vérifiée deux fois

**À la main, sur cette machine, serveur en marche** — la mesure qui couvre *tout*, section
Ollama comprise :

```
python run.py --check       > avant.txt   (sur 699c7aa)
python run_manga.py --check > avant.txt   (sur 699c7aa)
… refactor …
diff avant.txt apres.txt  →  aucune différence, pour les deux briques
```

**Par un test, en permanence** — `tests/test_core_diagnostic_iso.py`, 8 tests :

| Ce qui est gelé | Comment |
|---|---|
| les lignes déterministes des deux doctors | gabarit relevé le 2026-09-06 **avant** le refactor |
| les deux lignes du poids absent | citées telles quelles dans `manga_models/README.md` |
| la phrase « Section « manga: » absente » | égalité stricte de la liste de lignes |
| « ce qui est écrit » == « ce qui est structuré » | `diag.texte_console(sections)` comparé aux lignes réellement émises |
| l'absence d'import de `run_manga` dans `gui/fenetre.py` | la règle de couche, testée par lecture de source |

⚠ **La section « — Ollama — » n'est pas dans le gabarit**, et c'est dit dans le fichier de test
plutôt que caché : la geler demanderait un serveur en CI, ce que le critère 11 interdit. À la
place, `tests/test_core_llm_ecrire.py` vérifie que le chemin `print` et le chemin `ecrire`
produisent **exactement les mêmes lignes**, et que les quatre lignes du serveur injoignable sont
inchangées.

### 2.2 Comment le refactor a été fait, et pourquoi ainsi

Le plan l'exigeait : « extraire le constat de l'impression, pas réécrire le texte ».

`ecrire` est devenu un **paramètre** de chaque collecteur. Là où le code appelait `print(x)`, il
appelle `diag.dire(ecrire, x)` — qui écrit si `ecrire` est fourni **et** rend les lignes dans
tous les cas. Le chemin console passe `print` : mêmes octets, même ordre, **même instant**. Le
chemin structuré passe `None` : rien ne sort, les `Verdict` sortent quand même.

⚠ **Le « même instant » n'est pas un détail.** Une capture de `stdout` (`redirect_stdout`) aurait
donné les mêmes octets *à la fin* — et laissé la console muette pendant les 12,1 s de la sonde
LLM. Sur une commande qu'on lance justement pour savoir si le serveur répond, c'est la différence
entre un diagnostic et un programme qui a l'air planté.

### 2.3 Une quatrième gravité, non prévue par le plan

Le plan en annonçait trois : `bloquant`, `degrade`, `information`. Il en fallait une quatrième,
`conforme` : un doctor rapporte **aussi** ce qui marche — les seize lignes `✓` de `run.py --check`
en sont — et sans elle la structure ne pouvait pas les reproduire, donc l'isométrie était
impossible. Elle sert aussi à la page, qui replie « 6 points vérifiés » au lieu de les étaler.

C'est un écart au plan, assumé et écrit ici plutôt que glissé dans le code.

### 2.4 Le déménagement du doctor manga

`run_manga._run_doctor` contenait 90 lignes de diagnostic, et **`gui/fenetre.py` faisait
`from run_manga import _run_doctor`** : la fenêtre dépendait d'une CLI. C'est l'inversion de
couche que le lot 2.6 avait défaite côté light novel (`pipeline/doctor.py`), et qu'`app.py`
écrit noir sur blanc.

Le corps est passé dans **`manga/doctor.py`**. `run_manga._run_doctor` reste — il est cité dans
la docstring de la CLI et appelé par `app.py` — et ne fait plus qu'appeler la brique. Un test
(`test_run_manga_expose_toujours_son_point_d_entree_historique`) empêche que le déménagement
devienne une rupture d'interface déguisée en refactor.

---

## 2 bis. L36.3 — une contradiction dans le plan, tranchée et écrite

Le plan demandait, dans le même paragraphe, deux choses qui ne tiennent pas ensemble telles
qu'elles sont écrites :

> Trois pastilles au plus sur l'accueil, **alimentées par `core/diagnostic.py`** […]
> ⚠ **Pas de diagnostic complet au démarrage.**

Un diagnostic complet est précisément ce qu'il ne faut pas lancer au premier pixel : il met
12,1 s contre un serveur arrêté, et le `PLAN-31` a mesuré ce que coûte un démarrage qui en fait
trop.

**Ce qui est livré tranche par la profondeur, pas par le vocabulaire.** Les trois sondes de
`gui/sondes.py` gardent ce qu'elles font — un GET, un `is_file()`, un `which` — et **empruntent
le vocabulaire** de `core/diagnostic.py` : `sondes.verdicts()` rend des `Verdict` portant les
**mêmes identifiants** que ceux des doctors (`serveur_llm`, `poids_detection`, `pandoc`), la
même brique, et le geste lu dans `core/reparations.py`.

| | les trois sondes | la page Diagnostic |
|---|---|---|
| coût | ~2 s au pire, hors du fil d'affichage | 12,1 s serveur arrêté, sur demande |
| ce qu'elle demande | « est-ce que ça répond ? » | « qu'est-ce qui manque, et qu'est-ce que ça coûte ? » |
| gravité maximale rendue | `degrade` | `bloquant` |
| quand | après `show()`, une fois par session | quand on clique |

⚠ **Une sonde injoignable est `degrade`, jamais `bloquant`** — même pour le serveur LLM. Elle
n'a fait qu'un GET sur une racine ; conclure au blocage sur une mesure aussi superficielle
serait afficher un verdict plus dur que ce qu'on a mesuré. Le diagnostic complet, lui, a le
droit : il a vraiment essayé de générer.

**Ce que ça garantit** : l'accueil et la page ne peuvent plus se contredire sur ce qu'il faut
faire, parce que le remède n'est plus écrit deux fois. **Ce que ça ne garantit pas** : qu'elles
disent la même chose au même instant — la sonde est plus superficielle, et c'est son rôle.

Enfin, l'accueil ne se contente plus de constater : quand une sonde dit « absent », un bouton
**« Voir le diagnostic »** apparaît. ⚠ Il n'apparaît pas sur `inconnu` — « je n'ai pas encore
regardé » n'est pas « c'est cassé » — et il ne navigue jamais tout seul.

---

## 3. Les douze critères du lot, un par un

### 1. Le tableau de masquage est publié, avec avant/après, et le cas `manga-ocr` est mesuré

✅ **Tenu.** §1.2 pour le tableau, §1.3 pour le cas `manga-ocr`, qui s'avère pire que supposé
(150 échecs identiques sur un tome de 150 planches, mesurés). L'outil qui reproduit le tableau
est livré : `python tools/inventaire_pannes.py --markdown`.

⚠ **Réserve** : le cas ComfyUI n'est pas relevé (§4), et le cas « machine neuve » n'existe pas
(§0.2).

### 2. `core/diagnostic.py` rend des `Verdict` ; les deux doctors le consomment ; la console est iso

✅ **Tenu.** §2.1 et §2.2. Vérifié par `diff` à la main (les deux briques, section Ollama
comprise) et par 8 tests permanents pour tout ce qui ne dépend pas du réseau.

### 3. `gravite` distingue bloquant et dégradé, et le blocage est relatif à une brique

✅ **Tenu.** `diagnostic.bloquants_pour(sections, brique)` et la table `DEPENDANCES_BRIQUE`.
Quatre tests le portent, dont les deux que le plan nomme :
`test_une_absence_du_light_novel_ne_bloque_pas_un_usage_manga` et sa réciproque. La page le rend
visible par la phrase « Utilisable en l'état : … », qui retire la brique bloquée et **laisse les
autres**.

### 4. La page affiche constat, conséquence et geste ; aucun verdict sans geste

✅ **Tenu.** `gui/vue_diagnostic.phrase_geste()` garantit qu'un verdict non conforme a toujours
quelque chose à lire — son geste, celui de sa réparation, ou « hors périmètre », explicitement.
Testé à la source (`test_tout_verdict_non_conforme_porte_un_geste`) et à l'écran
(`test_chaque_verdict_montre_constat_consequence_et_geste`).

### 5. Aucun téléchargement sans clic ; aucun pendant un run ; licence avant, provenance après

✅ **Tenu.** `reparations.executer()` exige `consentement=True` **et** `run_en_cours=False`, et
les deux refus sont vérifiés avant toute lecture de config. La licence est dans `consigne()`,
affichée dans l'infobulle du bouton **et** dans la confirmation qui précède le téléchargement. La
fiche de provenance — URL, date, taille, SHA-256, licence — est écrite après, à côté du poids.

⚠ **Une exception, nommée** : `run_manga.py --check` télécharge toujours le détecteur manquant,
comme depuis la 2.9.0. Taper cette commande **est** le geste explicite ; ouvrir une page ne l'est
pas. D'où le paramètre `telechargement`, à `True` en console (comportement inchangé, isométrie
préservée) et à `False` partout ailleurs. Un test fait échouer tout appel au téléchargeur depuis
le chemin structuré.

### 6. Aucun logiciel système n'est installé ; un test le vérifie

✅ **Tenu.** `test_aucun_chemin_de_reparation_n_appelle_un_installateur_ni_un_gestionnaire_de_paquets`
lit **`core/reparations.py` et `manga/reparations.py`** par `ast`, trouve tous les appels
susceptibles de lancer un programme (`subprocess.*`, `os.system`, `os.popen`, `os.exec*`,
`os.spawn*`) et vérifie qu'aucun ne nomme `winget`, `choco`, `scoop`, `apt`, `dnf`, `pacman`,
`brew`, `msiexec`, `snap`, `flatpak`, `npm`…

⚠ **Le test regarde les APPELS, pas les chaînes.** `winget install --id JohnMacFarlane.Pandoc`
figure bien dans le fichier — comme **commande copiable** proposée à l'utilisateur, ce que le
plan autorise explicitement. Ce qui est interdit est de l'exécuter.

Deux tests bornent le reste : le socle ne lance **aucun** sous-processus, et le seul de la brique
est `tools/installer_polices.ps1` (§1.4).

### 7. Un fichier de poids partiel est détecté avant usage, et la reprise est proposée

✅ **Tenu.** `reparations.etat_fichier()` répond à trois questions distinctes : présent (un
`is_file()`), entier (taille contre `FRACTION_PARTIEL = 0.9`, plus l'existence d'un `.part`),
conforme (empreinte contre la fiche — seulement si les deux premières sont réglées).

⚠ **Une empreinte différente n'est PAS disqualifiante**, et c'est délibéré : même règle que
`manga/models.py` — « un dépôt amont qui republie ses poids ne doit pas bloquer le pipeline,
seulement faire dire que le fichier n'est plus celui d'origine ». Seules l'absence et la
troncature rendent un fichier inutilisable.

### 8. L'accueil affiche trois pastilles, sans sonde sur le fil, et s'affiche en < 1 s Ollama arrêté

✅ **Tenu, et remesuré.** `python tools/mesure_demarrage.py --config <config avec base_url sur un
port fermé> --attente 6` :

| Mesure | Valeur |
|---|---|
| premier pixel | **0,138 s** |
| `QApplication` | 0,011 s |
| construction de la fenêtre | 0,113 s |
| fichiers ouverts avant le premier pixel | **1** |
| panneaux construits | `['accueil']` |
| tome ouvert | `None` |
| aperçus composés | 0 |
| pic mémoire | 107,9 Mo |

Le budget d'une seconde est tenu avec un facteur 7. Les trois sondes (`gui/sondes.py`, lot 31)
sont inchangées : elles partent après `show()`, dans le fil de travail, et l'accueil s'affiche
avec les trois marqueurs en `INCONNU`.

⚠ **La page Diagnostic n'est pas construite au démarrage** et n'inspecte rien à sa
construction : elle s'ouvre en disant qu'aucun diagnostic n'a tourné, ce qui est vrai. Un test le
vérifie (`test_la_page_n_inspecte_rien_a_la_construction`).

### 9. « Créer un tome de démonstration » produit un tome utilisable, marqué, supprimable

✅ **Tenu, et vérifié de bout en bout.** `manga/demonstration.py` écrit
`sources/_Démonstration Angelith/Tome de démonstration/` : deux planches, quatre bulles,
checkpoints complets (régions, OCR, traduction, page nettoyée) écrits d'avance pour que la
retouche et le rendu marchent **sans aucun modèle et sans réseau**.

Vérification réelle, 2026-09-06 :

```
process_volume(…, restart_from="rendu")  →  ok=True en 4,8 s
CBZ écrit : _Démonstration Angelith_Tome de démonstration.cbz (2 pages)
PSD à calques : 2 planches
… avec manga.rendu.formats = [cbz, pdf] :
PDF écrit : _Démonstration Angelith_Tome de démonstration.pdf (2 pages, 48 860 o)
```

⚠ **Le PDF demande `manga.rendu.formats: [cbz, pdf]`** — la configuration du dépôt sort
`[cbz, psd]`. Le critère parlait de « produire un CBZ et un PDF réels » : les deux sont produits,
le second sur une configuration qui le demande. Ce n'est pas un défaut du tome, c'est un réglage.

**Marqué** : le dossier s'appelle `_Démonstration Angelith` (le tiret bas le range en tête) et
porte un `DEMONSTRATION.txt` qui dit ce qu'il est, ce qu'il n'est pas, et comment le supprimer.
**Supprimable** : `supprimer()` efface sources et build, et **refuse d'effacer un dossier qui ne
porte pas exactement ce nom** — même principe que `illustration/frontiere.py`. Un test vérifie
qu'une œuvre voisine survit.

**Il se refuse proprement sans police** : `PoliceIndisponible` porte le message de
`tools.polices.explication_absence` — la variable d'environnement, les candidats essayés, la
commande d'installation. La police est résolue **avant** toute écriture : un refus laisse le
disque exactement comme il était, et ne détruit pas un tome existant. Quatre tests le portent.

### 10. La page « À propos » liste la licence du logiciel et celles des poids présents

✅ **Tenu.** `gui/dialogues.licences_des_poids_presents()` lit les fiches de provenance sous
`manga_models/` et `illustration_models/`, et la page distingue deux blocs :

- ce que le projet **sait récupérer**, avec les licences amont ;
- ce qui est **réellement là**, d'après les fiches.

⚠ **Sur cette machine, le second bloc est vide** — et il le dit : « aucune fiche de provenance :
soit aucun poids n'a été récupéré par Angelith sur cette machine, soit ils ont été posés à la
main — dans ce cas leur licence n'est pas établie ici, va la vérifier à la source. » C'est exact :
les poids présents datent d'avant ce lot. **La liste se remplira au premier téléchargement fait
par la page Diagnostic**, et pas avant. Inventer une licence pour un fichier arrivé par un chemin
inconnu aurait été précisément l'affirmation que ce lot combat.

La page tranche aussi, en toutes lettres, la question ouverte depuis le 2026-08-26 :
**« Angelith » est le nom public du logiciel ; « Yume-Trad » est le nom du dépôt de travail.**

### 11. `ruff check .` passe ; la boucle courte passe **sans réseau**

✅ **Tenu.** `ruff check .` → *All checks passed*. Aucun test neuf n'ouvre de socket : les clients
OpenAI et les téléchargements sont doublés, les collecteurs prennent `reseau=False`, et le
diagnostic structuré prend `telechargement=False`. Aucun marqueur neuf n'a été nécessaire.

### 12. Ce document reprend les critères un par un

✅ **Tenu** — c'est cette section.

---

## 3 bis. Une faute d'architecture, trouvée par la suite de tests et corrigée

Écrit ici parce que la règle du dépôt le demande : ce qui a été trouvé se publie, y compris
quand c'est le lot lui-même qui l'a introduit.

La première version de ce lot déclarait **tout** le catalogue de réparations dans
`core/reparations.py`, et le tome de démonstration dans `core/demonstration.py`. Les deux
importaient `manga` — `manga.models` pour les URL et les empreintes, `manga.checkpoints` pour
écrire un tome. `tests/test_imports_briques.py` l'a refusé, et il a eu raison trois fois :

```
« core » importe ['manga'], qui n'est pas dans son graphe autorisé []
core n'importe aucune brique          → échec
le graphe est sans cycle              → cycle d'imports : core → manga → core
```

Ce test existe depuis le lot 24 et son message dit exactement quoi faire : « si c'est voulu, il
faut le justifier et mettre à jour `GRAPHE` — **pas seulement faire passer le test**. Une arête
nouvelle change ce qu'on peut dire du dépôt dans un dossier de financement. »

**Ce n'était pas voulu.** Le graphe n'a pas été élargi ; le code a été redécoupé, selon le
partage que ce même lot avait déjà appliqué aux doctors :

| Ce qui était dans `core/` | Où c'est maintenant | Pourquoi |
|---|---|---|
| catalogue complet des réparations | vocabulaire dans `core/reparations.py`, gestes dans `manga/reparations.py` | récupérer un poids demande `manga.models` |
| `core/demonstration.py` | `manga/demonstration.py` | un tome de démonstration est un tome de **manga** : `BubbleRegion`, checkpoints, page nettoyée |

⚠ **Le mécanisme est un registre**, et il a une conséquence qu'il faut connaître :
`reparations.par_identifiant("poids_detection")` rend `None` tant que `manga.reparations` n'a pas
été importé. Ce n'est pas un défaut — on ne répare pas une brique qu'on n'a pas chargée — et le
message de refus le dit en toutes lettres. Les trois appelants qui en ont besoin
(`gui/fenetre.py`, `gui/vue_diagnostic.py`, `gui/sondes.py`) l'importent explicitement, avec le
commentaire qui explique pourquoi.

**Ce que cet épisode dit du dépôt** : le garde-fou a fonctionné exactement comme il a été conçu.
Il a coûté un redécoupage d'une heure, et il a évité une arête que personne n'aurait vue dans une
revue de diff.

---

## 3 ter. Un second défaut, trouvé de la même façon — et il aurait été invisible en production

Les deux gestes neufs du lot — la réparation et le tome de démonstration — passaient au fil de
travail un rappel d'avancement écrit ainsi :

```python
dire=lambda m: self.signaux.journal.emit("info", str(m))
```

⚠ **`SignauxTravail` n'a pas de signal `journal`** : il s'appelle `ligne`. Le rappel levait donc
un `AttributeError` **dans le fil de travail**, à la première ligne d'avancement — c'est-à-dire
avant le premier octet téléchargé.

**Pourquoi c'était invisible.** Le fil rattrape les exceptions de ses tâches et les rapporte
comme un échec, dans le journal. Pour l'utilisateur, cliquer sur « Télécharger les poids » aurait
produit une ligne d'erreur et rien d'autre : pas de fichier, pas d'explication utilisable. Un
téléchargement de 104 Mo qui échoue en silence est **exactement** le mode de panne que ce lot est
censé supprimer.

**Comment il a été trouvé.** Le premier test de bout en bout du tome de démonstration passait —
parce que `existe()` reposait sur un marqueur écrit **en premier**, donc vrai avant même que la
première planche soit peinte. Deux corrections en ont découlé, et la première est un vrai
changement de comportement :

1. ⚠ **le marqueur est maintenant écrit EN DERNIER.** `existe()` veut désormais dire « là **et
   complet** ». Un demi-tome — ou un tome dont l'écriture vient d'échouer — ne passe plus pour
   une démonstration, et un appelant qui attend « c'est prêt » n'a plus à courir après la fin
   d'une écriture. Sans ce changement, le second défaut serait resté caché ;
2. **le test capture le journal et le montre dans son message d'échec.** C'est ce qui a
   transformé un `assert False is True` illisible en un `AttributeError` nommé.

Un test supplémentaire garde maintenant le même chemin côté réparation
(`test_une_reparation_journalise_son_avancement`) : il vérifie que la **licence est dite avant le
transfert** et qu'elle **atteint le journal**.

**Ce que cet épisode dit** : un geste dont l'échec ne se voit que dans un panneau que rien ne lit
est un geste non testé. Les deux tests de bout en bout coûtent dix secondes ; ils ont trouvé le
seul défaut du lot qui aurait atteint l'utilisateur.

---

## 4. Ce que ce lot ne fait pas, et ce qui reste ouvert

Repris du §4 du plan, plus ce que la mesure a fait apparaître.

- **il n'empaquette rien**, ne produit aucun `.exe`, ne crée pas `pyproject.toml` — c'est le
  `PLAN-37` ;
- **il n'installe aucun logiciel système** (critère 6, testé) ;
- **il ne redistribue aucun poids** et n'héberge aucun miroir ;
- **il ne télécharge rien automatiquement**, sauf `run_manga.py --check`, comportement de 2.9.0
  conservé pour l'isométrie et justifié au critère 5 ;
- **il ne modifie aucun seuil, aucun prompt, aucun chemin de traitement.** Le seul fichier du
  pipeline touché est `core/llm.py`, qui gagne un paramètre `ecrire` à défaut `print` ;
- **il ne rend pas la brique illustration diagnosticable.** ComfyUI n'a pas de verdict : la brique
  est expérimentale, son diagnostic vivrait dans `illustration/`, et l'ajouter ici aurait demandé
  un serveur ComfyUI pour être mesuré. La réparation `comfyui` existe dans le catalogue, en
  classe `UTILISATEUR` — elle dit ce qu'il faut faire, et rien de plus ;
- ⚠ **il ne corrige pas les 150 échecs de `manga-ocr` sans réseau** (§1.3). Le cas est rendu
  évitable, pas impossible. Le corriger demande de toucher au filet par planche de
  `orchestrator_manga.py`, ce que le périmètre du lot exclut. **C'est le candidat n° 1 d'un
  correctif ultérieur, et il est nommé ici pour ne pas être oublié.**

---

## 5. Les chiffres du lot

| | avec PySide6 | sans PySide6 | écart |
|---|---:|---:|---:|
| après le lot 35 (2.29.0) | 4 567 | 4 175 | 392 |
| **après le lot 36** | **4 705** | **4 289** | **416** |

**+138 tests**, dont **114 sans Qt** — les deux colonnes ont été relevées, pas déduites. La
proportion s'explique par les modules neufs : sur les sept, **six sont sans Qt**
(`core/diagnostic.py`, `core/provenance.py`, `core/reparations.py`, `manga/doctor.py`,
`manga/reparations.py`, `manga/demonstration.py`), un est sans Qt côté décisions
(`gui/vue_diagnostic.py`), et un seul importe PySide6 (`gui/diagnostic.py`).

La boucle courte en exécute **4 648**, les mêmes **57** restant désélectionnés par `lent` /
`modeles` (4 648 + 57 = 4 705).

Reproduire : `python tools/compte_de_tests.py`,
`python tools/compte_de_tests.py -m "not lent and not modeles"`, et
`python -m pytest --collect-only -q -p tools.compte_sans_pyside`.
