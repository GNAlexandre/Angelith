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

| Police | Symboles manquants |
|---|---|
| ComicNeue-Bold | `♪ ♫ ♥ ★ ☆ → ← ↑ ↓ ※ 〜 ♂ ♀` |
| Lucida Sans Unicode | `★ ☆ 〜` |
| arial.ttf | `★ ☆ ※ 〜` |

`manga/typeset.py` choisit donc la police **par bulle** (`font_pour_texte`) : la première de
la chaîne qui sait dessiner tout le texte. La quasi-totalité des bulles garde Comic Neue ;
seules celles qui contiennent un symbole exotique basculent sur Lucida. Si aucune police de
la chaîne ne couvre le texte, les caractères concernés sont **signalés** dans `RAPPORT.md` —
jamais rendus en carré « tofu » sans le dire.

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

`manga/typeset.py` essaie dans cet ordre, et prend le premier fichier qui existe :

1. `config.yaml > manga.typeset.font_path` — ton choix explicite, toujours prioritaire ;
2. `templates/fonts/manga_typeset.ttf` — emplacement conventionnel si tu déposes **ta**
   police sans toucher à la config ;
3. `templates/fonts/ComicNeue-Bold.ttf` — le défaut livré ;
4. `C:/Windows/Fonts/l_10646.ttf` (**Lucida Sans Unicode**) — repli cohérent avec les rendus
   light novel, qui composent dans cette police (`templates/epub.css`) ;
5. `comic.ttf`, puis `arial.ttf` — derniers recours.

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
