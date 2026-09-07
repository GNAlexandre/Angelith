# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce qu'on vient de lâcher sur la fenêtre — **la décision, sans Qt**.

`dragEnterEvent` et `dropEvent` vivent dans `gui/fenetre.py` et ne font que deux choses :
convertir un `QMimeData` en liste de chemins, et appeler `classer()`. Toute la lecture est
ici, donc testable sans PySide6 — la règle de couche du dépôt.

## Les trois cas du plan, et le quatrième

| Ce qu'on lâche | Verdict |
|---|---|
| un dossier d'images, un `.cbz`, un `.cbr` | `SOURCES` — proposer la création d'un projet |
| un `.pdf`, un `.epub` | `SOURCES_LN` — proposer un projet **light novel** (lot 40) |
| un `.yaml`, un `.csv`, un `.docx`, un `.txt`, un `.md` | `GLOSSAIRE` — proposer l'import |
| autre chose | `INCONNU`, **avec un message qui dit pourquoi** |

Le quatrième cas est le mélange : deux `.cbz` et un `.docx` dans le même lâcher. On ne devine
pas — c'est `INCONNU`, et le message nomme les deux natures. Choisir à la place de
l'utilisateur créerait un projet ou fusionnerait un glossaire sur un geste ambigu, et l'un des
deux serait toujours le mauvais.

⚠ **Un lâcher de type inconnu doit produire un message, pas un silence.** Un geste qui ne
produit rien passe pour un défaut de l'application une fois sur deux ; c'est exactement ce que
le plan reproche à l'état vide du premier lancement.
"""
from __future__ import annotations

from pathlib import Path

# ⚠ IMPORTÉ, pas recopié. Deux listes d'extensions qui divergent, c'est un `.bmp` accepté au
# dépôt et refusé au scan — un projet créé qui s'ouvre vide.
from manga.ingest import IMG_EXTS

SOURCES = "sources"
GLOSSAIRE = "glossaire"
INCONNU = "inconnu"

#: Un tome de ROMAN lâché sur la fenêtre — lot 40.
#:
#: ⚠ **Seulement `.pdf` et `.epub`**, et c'est une décision, pas une omission. Les trois autres
#: extensions que `pipeline/sources.py` accepte — `.docx`, `.txt`, `.md` — sont **déjà** dans
#: `GLOSSAIRES_TEXTE` : un `.docx` lâché peut aussi bien être un glossaire rédigé à la main
#: qu'un tome de roman, et l'extension seule ne permet pas de trancher.
#:
#: Le dépôt refuse de deviner (cf. l'avertissement du module sur le lâcher mélangé). Le
#: comportement de ces trois-là est donc **inchangé**, et la création d'un roman à partir d'un
#: `.docx` passe par « Nouveau projet », où l'on dit ce qu'on veut.
SOURCES_LN = "sources_ln"

#: Archives de planches. `.zip` est accepté comme `manga.ingest.list_source_files` l'accepte.
ARCHIVES: tuple[str, ...] = (".cbz", ".cbr", ".zip")

#: Formats de glossaire. `.yaml`/`.yml` passent par `reintegrer_dans_projet` (un glossaire du
#: projet, antérieur) ; les autres par `import_into_project` (un glossaire rédigé à la main).
#:
#: ⚠ **La phrase qui était ici était fausse, et le lot 34 l'a mesuré le 2026-09-05.** Elle
#: annonçait que « `.csv` est lu par le parseur tolérant, qui accepte la tabulation et le
#: point-virgule ». Ni l'un ni l'autre : `glossary_import._to_text` levait
#: `RuntimeError: Format non géré` sur un `.csv`, et le point-virgule ne figure pas dans
#: `_SEPARATORS`. Un lâcher de `.csv` était donc classé `GLOSSAIRE`, accepté, puis mis en
#: échec à l'import.
#:
#: Le lot 34 rend la promesse vraie plutôt que de la retirer — il livre un EXPORT CSV, et un
#: export dont le réimport échoue serait une source de corruption de glossaire — mais par un
#: autre mécanisme : `parse_file` route un `.csv` **produit par ce dépôt** vers un vrai lecteur
#: CSV (`glossary_import.parse_csv`), avec ses catégories, ses genres, ses variantes et ses
#: formes interdites. Tout autre `.csv` retombe sur le parseur tolérant.
GLOSSAIRES_YAML: tuple[str, ...] = (".yaml", ".yml")
GLOSSAIRES_TEXTE: tuple[str, ...] = (".docx", ".txt", ".md", ".csv")

#: Les extensions de roman qui ne sont ambiguës avec **rien**. ⚠ `.docx`, `.txt` et `.md` en
#: sont volontairement absentes : elles appartiennent déjà à `GLOSSAIRES_TEXTE`, et une
#: extension ne dit pas si le fichier est un glossaire ou un tome.
SOURCES_LN_EXTENSIONS: tuple[str, ...] = (".pdf", ".epub")


def _porte_des_planches(dossier: Path) -> bool:
    """Le dossier contient-il, à plat ou d'un cran en dessous, des images ou une archive ?

    Un cran, pas plus : on cherche `Tome/manga/*.png` comme `Tome/*.png`, ce que
    `sources_manga.resoudre_source` accepte déjà. Descendre plus profond ferait passer un
    dossier de captures d'écran pour un tome."""
    try:
        entrees = list(dossier.iterdir())
    except OSError:
        return False
    for chemin in entrees:
        if chemin.is_file() and chemin.suffix.lower() in (*IMG_EXTS, *ARCHIVES):
            return True
    for chemin in entrees:
        if not chemin.is_dir():
            continue
        try:
            if any(p.is_file() and p.suffix.lower() in (*IMG_EXTS, *ARCHIVES)
                   for p in chemin.iterdir()):
                return True
        except OSError:
            continue
    return False


def nature(chemin: str | Path) -> str:
    """Ce qu'un chemin, seul, représente."""
    chemin = Path(chemin)
    if chemin.is_dir():
        return SOURCES if _porte_des_planches(chemin) else INCONNU
    suffixe = chemin.suffix.lower()
    if suffixe in (*IMG_EXTS, *ARCHIVES):
        return SOURCES
    # ⚠ AVANT les glossaires, et sans conflit : `.pdf` et `.epub` n'y figurent pas. Ce sont
    # les deux seules extensions de roman qui ne soient ambiguës avec rien.
    if suffixe in SOURCES_LN_EXTENSIONS:
        return SOURCES_LN
    if suffixe in (*GLOSSAIRES_YAML, *GLOSSAIRES_TEXTE):
        return GLOSSAIRE
    return INCONNU


def classer(chemins) -> tuple[str, list[Path], str]:
    """`(verdict, chemins retenus, message)`.

    Le message est **toujours** rempli, y compris quand le verdict est bon : c'est lui que la
    barre d'état affiche, et un geste réussi mérite autant d'être confirmé qu'un geste refusé
    d'être expliqué."""
    retenus = [Path(c) for c in chemins if str(c).strip()]
    if not retenus:
        return INCONNU, [], "Rien à lire dans ce dépôt."

    natures = {nature(c) for c in retenus}

    if natures == {SOURCES}:
        n = len(retenus)
        quoi = retenus[0].name if n == 1 else f"{n} éléments"
        return SOURCES, retenus, f"{quoi} — créer un projet à partir de ces sources ?"
    if natures == {SOURCES_LN}:
        n = len(retenus)
        quoi = retenus[0].name if n == 1 else f"{n} fichiers"
        return SOURCES_LN, retenus, (
            f"{quoi} — créer un projet LIGHT NOVEL à partir de ces sources ?")
    if natures == {GLOSSAIRE}:
        n = len(retenus)
        quoi = retenus[0].name if n == 1 else f"{n} fichiers"
        return GLOSSAIRE, retenus, f"{quoi} — importer dans le glossaire de l'œuvre ?"

    # ⚠ L'inconnu l'emporte sur le mélange, et pas l'inverse : entre « je n'ai pas su lire ce
    # fichier » et « tu m'as donné deux choses à la fois », c'est le premier qui apprend
    # quelque chose à qui vient de lâcher un `.pdf` avec ses planches.
    if INCONNU in natures:
        vus = sorted({(c.suffix.lower() or "dossier") for c in retenus
                      if nature(c) == INCONNU})
        return INCONNU, retenus, (
            f"Rien à faire de {', '.join(vus)}. Attendu : un dossier de planches, un "
            f".cbz/.cbr, une image, un tome de roman (.pdf, .epub), ou un glossaire "
            f"(.yaml, .docx, .txt, .md, .csv).")
    # ⚠ Le message NOMME les natures réellement vues, depuis le lot 40 : avec trois familles
    # au lieu de deux, « des planches et des glossaires » serait faux une fois sur trois — et
    # un message faux sur un refus est pire qu'un message générique.
    libelles = {SOURCES: "des sources de planches", SOURCES_LN: "des sources de roman",
                GLOSSAIRE: "des glossaires"}
    vues = [libelles[n] for n in (SOURCES, SOURCES_LN, GLOSSAIRE) if n in natures]
    return INCONNU, retenus, (
        f"Dépôt mélangé : il porte à la fois {' et '.join(vues)}. "
        "Lâche-les séparément — on ne devine pas lequel des gestes tu voulais.")


def est_glossaire_yaml(chemin: str | Path) -> bool:
    """Un glossaire YAML se réintègre (`reintegrer_dans_projet`), un glossaire rédigé
    s'importe (`import_into_project`). Deux fonctions, deux sémantiques — cf. la docstring
    de `core/glossary_import.py`."""
    return Path(chemin).suffix.lower() in GLOSSAIRES_YAML
