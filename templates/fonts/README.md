# Polices de lettrage manga

Polices utilisées par `manga/typeset.py` pour réinjecter le texte français dans les bulles.

## Ce qui est livré ici

| Fichier | Rôle | Licence |
|---|---|---|
| `ComicNeue-Bold.ttf` | **police par défaut** du lettrage | SIL OFL 1.1 |
| `ComicNeue-Regular.ttf` | corps de texte si tu préfères moins gras | SIL OFL 1.1 |
| `ComicNeue-BoldItalic.ttf` | emphase (`manga.typeset.font_path_italique`) | SIL OFL 1.1 |
| `ComicNeue-Italic.ttf` | emphase, variante non grasse | SIL OFL 1.1 |
| `OFL.txt` | texte intégral de la licence | — |

**Comic Neue** — Copyright 2014 The Comic Neue Project Authors,
<https://github.com/crozynski/comicneue>. Récupérée depuis le dépôt Google Fonts
(`google/fonts/ofl/comicneue`), qui distribue la famille avec son `OFL.txt`.

La SIL Open Font License 1.1 est la seule catégorie qui autorise **sans ambiguïté** à
redistribuer le fichier de police dans ce dépôt, à condition de conserver `OFL.txt` à côté
et de mentionner l'origine — ce que fait ce fichier. Elle autorise aussi la diffusion des
images produites.

**Couverture** — le français est intégralement couvert : `é è à ç ù œ É È À Ç Ù Œ`,
`î ï ô û ë ÿ â ê Ê Â Î Ï Ô Û Ë`, `æ Æ`, `« » — … ’ ‘ “ ” –`. Aucun glyphe manquant.
Métriques (ascendante, descendante) = (29, 8) à 32 px.

⚠ En revanche, Comic Neue est une police **latine** : elle n'a **pas** les symboles que le
traducteur produit parfois (« Moi, je préfère les filles ♪ »). Mesuré sur la chaîne :

| Police | Plateforme | Symboles manquants |
|---|---|---|
| ComicNeue-Bold | livrée | `♪ ♫ ♥ ★ ☆ → ← ↑ ↓ ※ 〜 ♂ ♀` |
| Lucida Sans Unicode | Windows | `★ ☆ 〜` |
| arial.ttf | Windows | `★ ☆ ※ 〜` |
| DejaVuSans-Bold | Linux | `〜` |

`manga/typeset.py` choisit la police **par bulle** (`font_pour_texte`) : la première de la
chaîne qui sait dessiner tout le texte. Si aucune ne le couvre, les caractères concernés
sont **signalés** dans `RAPPORT.md` — jamais rendus en carré « tofu » sans le dire.

⚠ **Mais la bascule elle-même n'est pas signalée**, et ça n'a rien d'anecdotique. Un repli
« propre » — la chaîne a trouvé une police couvrante — ne produit aucune entrée de rapport :
seuls les caractères *substitués* ou *supprimés* en produisent une. Ce n'est un détail que
tant que la police demandée couvre le français. Mesuré sur manga A /
Vol.1, `font_path` pointé sur une police de 135 glyphes à qui manquaient `« » œ Ç À — ♪` :
**63 bulles sur 818, sur 45 planches sur 150**, sont sorties en ComicNeue-Bold ou en Lucida
Sans Unicode. Le tome était lettré en trois polices, et le seul indice était la ligne
« PSD — police(s) à installer » du rapport, qui ressemble à une note d'installation.

Deux garde-fous en découlent :

- **le pré-vol du run** (`manga.typeset.couverture`) mesure la police sur les traductions en
  cache **avant** de lettrer, et dit les signes absents, le nombre de bulles et de planches
  qui basculeront, et la largeur relative à ComicNeue-Bold. `python run_manga.py --check`
  fait la même mesure sans lancer de run ;
- **`tools/completer_police.py`** complète une police à partir de ses propres tracés
  (l'accent grave détaché du `È` et reposé sur le `A`, la cédille du `ç` sur le `C`, `œ` un
  `o` et un `e` accolés…), et greffe depuis une autre police ce qu'elle ne peut pas
  produire, en le disant glyphe par glyphe. ⚠ Le fichier produit est un **travail dérivé** :
  cf. `NOTICE` avant de t'en servir.

⚠ **La police à symboles dépend de l'OS, et son absence ne lève rien.** La chaîne ne
contenait que des chemins Windows : hors Windows elle se réduisait à Comic Neue, et `♪`
n'était pas dessiné — il était **supprimé** de la bulle, la perte n'apparaissant que dans
`RAPPORT.md`. Sous Linux, installe donc `fonts-dejavu-core` (ce que fait
`.github/workflows/ci.yml`). `tests/test_manga_typeset.py` **échoue** — il ne skippe pas —
quand aucune police à symboles n'est trouvable, avec le message de
`manga.typeset.explication_absence_symboles`.

⚠ Et **aucune police CJK** dans cette chaîne, si tentante soit-elle : `font_pour_texte`
bascule **toute la bulle** d'un coup, donc un seul `・` redessinerait un paragraphe entier de
français en CJK — et court-circuiterait la table de substitution, qui est le bon traitement
pour ces signes-là.

> Détail utile si tu écris un test : `font.getmask(c).getbbox() is None` **ne détecte pas**
> un glyphe absent. Pillow substitue le `.notdef`, dont la boîte est non vide — ce test
> déclarait Comic Neue couvrante pour `♪ ♥ ★ →` alors que la planche sortait avec des tofus.
> Il faut comparer le rendu à celui d'un caractère à coup sûr absent (zone à usage privé).

## Installer la police pour Photoshop

**Uniquement nécessaire pour l'export PSD.** Les sorties images, CBZ et PDF n'ont besoin
d'aucune installation : le lettrage est dessiné en lisant directement le fichier `.ttf` de ce
dossier.

Le PSD est différent. Un calque de texte ne peut pas embarquer sa police — il n'en déclare que
le **nom PostScript**, et Photoshop va chercher la police correspondante parmi celles
**installées sur la machine**. Sans elle :

1. « Polices manquantes » à chaque ouverture ;
2. et surtout, **substitution dès la première modification** : la bulle réécrite change de
   dessin et jure avec ses voisines, restées sur les pixels d'origine.

```
powershell -ExecutionPolicy Bypass -File tools/installer_polices.ps1
```

Installe les quatre fichiers **pour ton compte utilisateur** — aucun droit administrateur, rien
qui touche les autres comptes. `-Machine` installe pour tous (console administrateur),
`-Desinstaller` retire exactement ce qui a été posé. Idempotent. **Redémarre Photoshop** après :
il ne relit sa liste de polices qu'au démarrage.

Pour vérifier, plutôt que d'ouvrir une planche et regarder :

```
powershell -ExecutionPolicy Bypass -File tools/valider_psd_photoshop.ps1
```

Le script interroge `Application.Fonts` — la liste même que Photoshop consulte pour décider
d'afficher la boîte — et nomme les polices absentes.

> ⚠ **Le nom PostScript n'est pas déductible du nom de fichier ni du couple (famille, style).**
> `manga/psd.py` le lit dans la table `name` du fichier (entrée ID 6), parce que le deviner se
> trompe : sur les quatre polices livrées, la concaténation `famille + style` est exacte pour
> Bold, Italic et BoldItalic, et **fausse pour Regular** (`ComicNeue` au lieu de
> `ComicNeue-Regular`). Elle se trompe aussi sur Arial, dont le vrai nom est `ArialMT`. Un PSD
> qui réclame un nom inexistant reste « polices manquantes » même une fois la police installée.

## Chaîne de repli

`manga/typeset.py` essaie dans cet ordre, et prend le premier fichier qui existe. ⚠ Les
chemins des polices livrées sont **absolus**, ancrés sur la racine du dépôt : relatifs, ils
étaient résolus contre le répertoire courant, et un run lancé d'ailleurs sautait directement
aux polices système.

⚠ Un `font_path` qui désigne un fichier **absent** ne lève rien : `resolve_font` retombe en
silence sur la suite de la chaîne. C'est le cas que `--check` et le pré-vol signalent
désormais — une police non livrée avec le dépôt est absente de toute autre machine, et le
tome y sortirait entièrement en Comic Neue sans un mot.


1. `config.yaml > manga.typeset.font_path` — ton choix explicite, toujours prioritaire ;
2. `templates/fonts/manga_typeset.ttf` — emplacement conventionnel si tu déposes **ta**
   police sans toucher à la config ;
3. `templates/fonts/ComicNeue-Bold.ttf` — le défaut livré ;
4. les polices **à symboles du système**, par plateforme
   (`manga/typeset.py > POLICES_SYMBOLES`) :
   - Windows — `C:/Windows/Fonts/l_10646.ttf` (**Lucida Sans Unicode**), repli cohérent avec
     les rendus light novel, qui composent dans cette police (`templates/epub.css`), puis
     `comic.ttf` et `arial.ttf` en derniers recours ;
   - Linux — **DejaVu Sans** (`fonts-dejavu-core`), aux emplacements Debian/Ubuntu, Fedora
     et Arch ;
   - macOS — **Arial Unicode** (hors périmètre de la CI, cf. `docs/roadmap.md`).

Avant ce lot, `templates/fonts/` n'existait pas et la chaîne tombait **systématiquement sur
Arial** : une police de traitement de texte, au dessin étroit et aux terminaisons droites,
qui trahit immédiatement une planche.

## Polices de référence NON livrées, et pourquoi

- **Anime Ace 2.0 BB**, **Digital Strip** (Blambot) — les références du lettrage manga
  anglophone, mais **gratuites en usage non commercial seulement**. À télécharger toi-même
  sur <https://blambot.com> si ton usage le permet, puis à déposer en
  `templates/fonts/manga_typeset.ttf` (ou à pointer par `font_path`).
- **CC Wild Words** — la police des éditions Marvel/Panini, strictement **commerciale**.
- `comicbd.ttf` (Comic Sans MS Bold) — présente sur les machines Windows mais **non
  redistribuable**, d'où sa place tardive dans la chaîne : utilisable en local, jamais
  livrable dans le dépôt.

## Substituer ta propre police

Le plus simple, sans toucher à `config.yaml` :

```
templates/fonts/manga_typeset.ttf      <- ta police
```

Sinon, explicitement :

```yaml
manga:
  typeset:
    font_path: "C:/chemin/vers/MaPolice.ttf"
    font_path_gras: "C:/chemin/vers/MaPolice-Bold.ttf"
    font_path_italique: "C:/chemin/vers/MaPolice-Italic.ttf"
```

⚠ Vérifie la licence de diffusion de toute police que tu substitues **avant** de partager
les planches produites : la contrainte porte sur le fichier de police *et*, pour certaines
licences gratuites, sur le caractère non commercial des images.
