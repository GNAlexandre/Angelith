# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fou de fuite, de corpus et de poids — trois risques dont le dépôt porte la trace.

## Pourquoi ces trois-là et pas d'autres

Aucun n'est hypothétique. Chacun a déjà eu lieu dans ce dépôt :

1. **La fuite vers le miroir public.** Un commit (`221a902`) existe déjà pour empêcher
   `docs/PUBLICATION-ANGELITH.md` de partir vers Angelith, et son message dit pourquoi : le
   fichier avait subsisté « non suivi » sur le disque après un passage sur la branche
   `public`, où un `git add -A` distrait l'aurait envoyé.
2. **Le corpus commercial.** La purge (`86c3d3d`, `b3d1eaa`) est un acquis. `.gitignore`
   exclut `sources/` et `build/` — mais `.gitignore` **a déjà échoué une fois** : son propre
   commentaire raconte qu'encodé en UTF-16LE il était entièrement inerte, et que 3 347
   fichiers se sont retrouvés suivis, dont 2 549 sous `build/` et 654 sous `sources/`. Une
   protection dont la panne est silencieuse a besoin d'une seconde.
3. **Les poids de modèles.** 104 Mo et 94,7 Mo. Ils se téléchargent (`manga/models.py`), ils
   ne se commitent pas — et une fois dans l'historique, ils y sont pour toujours.

## Les motifs de titres ne sont PAS dans ce fichier

Ils vivent dans `docs/PUBLICATION-ANGELITH.md`, bloc `<!-- motifs-de-fuite -->`, et ce script
les y lit. Les recopier ici publierait la liste des titres avec l'outil, alors que ce
fichier-ci est précisément celui que la procédure de publication retire de l'arbre public.

⚠ **Conséquence assumée : sur la branche `public`, le script ne trouve pas ses motifs.** Il le
DIT et sort en erreur avec `--index` ; il ne rend jamais un vert silencieux. Un garde-fou qui
ignore ce qu'il cherche doit se déclarer aveugle — c'est la règle du dépôt sur les CI vertes
qui ne testent plus rien, appliquée à lui-même.

## Ce qu'il ne fait pas

Il ne vérifie pas que « tout chiffre porte son dénominateur » : ce n'est pas décidable par une
expression régulière, et un garde-fou qui produit des faux positifs sur de la prose est
contourné avant d'avoir servi. Cette règle-là reste à la relecture humaine.

## Usage

    python tools/verifier_arbre.py --diff origin/main   # le diff d'une branche, en CI
    python tools/verifier_arbre.py --index              # l'INDEX, avant `git commit` (publication)
    python tools/verifier_arbre.py --suivi              # tout l'arbre suivi (mesure, non bloquant)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOURCE_DES_MOTIFS = RACINE / "docs" / "PUBLICATION-ANGELITH.md"

#: Extensions de poids de modèles. `.bin` n'y figure PAS volontairement : trop générique, il
#: attraperait des fichiers légitimes et le garde-fou serait désarmé au premier faux positif.
#: Les formats retenus sont ceux que ce projet manipule ou pourrait manipuler.
EXTENSIONS_POIDS = (".onnx", ".pt", ".pth", ".safetensors", ".ckpt", ".h5", ".tflite", ".pb")

#: Racines interdites. `.gitignore` les exclut déjà — c'est justement pourquoi un fichier qui
#: apparaît ici signale que l'exclusion a cessé de fonctionner.
PREFIXES_INTERDITS = ("sources/", "build/")

#: Fichiers qui ne doivent jamais partir vers le miroir. Leurs NOMS sont publiables (ils ne
#: nomment aucune œuvre) ; leur CONTENU ne l'est pas.
LISTE_NOIRE = (
    "docs/PUBLICATION-ANGELITH.md",   # décrit le dépôt privé et la purge
    "docs/purge-corpus.md",           # recense chaque occurrence purgée avec son texte réel
    ".sonar-token",                   # un jeton utilisateur ouvre l'API sur tout le compte
    "SONAR_TOKEN",                    # le meme, sous le nom de la variable d'environnement
    "sonar-token.txt",                # et sa variante la plus probable
    "sonar-issues.json",              # extraction régénérable
    "sonar-issues.md",
)

#: Fichiers dont l'analyse de CONTENU n'a pas de sens (binaire) ou serait circulaire.
_SANS_CONTENU = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".docx", ".epub", ".pdf",
                 ".ttf", ".ttc", ".otf", ".zip", ".onnx", ".psd", ".xlsx")

_DEBUT_MOTIFS = "<!-- motifs-de-fuite:début -->"
_FIN_MOTIFS = "<!-- motifs-de-fuite:fin -->"


class MotifsIndisponibles(RuntimeError):
    """`docs/PUBLICATION-ANGELITH.md` absent ou sans bloc de motifs. Ce n'est pas un
    « rien à vérifier » : c'est un garde-fou aveugle, et il doit le dire."""


@dataclass(frozen=True)
class Infraction:
    chemin: str
    regle: str
    detail: str

    def __str__(self) -> str:
        return f"{self.chemin} — {self.regle} : {self.detail}"


def motifs_de_fuite(source: Path | None = None) -> list[str]:
    """Les titres d'œuvres à ne jamais laisser passer, lus dans la procédure de publication."""
    source = source or SOURCE_DES_MOTIFS
    if not source.is_file():
        raise MotifsIndisponibles(
            f"{source} est absent : la liste des titres à surveiller vit là et nulle part "
            f"ailleurs (elle ne peut pas vivre dans un fichier publié). Sur la branche "
            f"`public`, c'est attendu — la vérification de fuite se fait AVANT la "
            f"transposition, sur la branche de développement.")
    texte = source.read_text(encoding="utf-8")
    try:
        bloc = texte.split(_DEBUT_MOTIFS, 1)[1].split(_FIN_MOTIFS, 1)[0]
    except IndexError as e:
        raise MotifsIndisponibles(
            f"{source} ne porte plus le bloc {_DEBUT_MOTIFS} … {_FIN_MOTIFS}. Le supprimer "
            f"rend ce garde-fou aveugle sans rien colorer en rouge — d'où cette erreur.") from e
    motifs = [ligne.strip() for ligne in bloc.splitlines()
              if ligne.strip() and not ligne.strip().startswith("```")]
    if not motifs:
        raise MotifsIndisponibles(f"le bloc de motifs de {source} est vide")
    return motifs


def juger_chemin(chemin: str, *, publication: bool = False) -> list[Infraction]:
    """Les trois règles qui se jugent sur le seul NOM du fichier.

    `publication` arme la liste noire. Elle est DÉSARMÉE par défaut, et ce n'est pas une
    faiblesse : `docs/PUBLICATION-ANGELITH.md` est légitimement suivi sur les branches de
    développement — c'est écrit dans `.gitignore`, « il reste SUIVI sur les branches de
    développement ». La liste noire ne dit pas « ce fichier ne doit pas exister », elle dit
    « ce fichier ne doit pas partir vers le miroir » : elle se juge donc au moment de la
    publication (`--index`), pas à chaque PR — sans quoi toute PR qui touche la procédure de
    publication serait rouge pour l'avoir touchée."""
    normalise = chemin.replace("\\", "/").lstrip("./")
    infractions = []
    for prefixe in PREFIXES_INTERDITS:
        if normalise.startswith(prefixe):
            infractions.append(Infraction(
                chemin, "corpus",
                f"sous `{prefixe}` — ce dossier est exclu par `.gitignore`, donc sa présence "
                f"ici signale que l'exclusion a cessé de fonctionner (elle l'a déjà fait : "
                f"3 347 fichiers suivis par accident)"))
    suffixe = Path(normalise).suffix.lower()
    if suffixe in EXTENSIONS_POIDS:
        infractions.append(Infraction(
            chemin, "poids",
            f"`{suffixe}` est un poids de modèle : il se télécharge (`manga/models.py`), il "
            f"ne se commite pas — une fois dans l'historique, il y est pour toujours"))
    if publication and normalise in LISTE_NOIRE:
        infractions.append(Infraction(
            chemin, "publication",
            "figure sur la liste noire de `docs/PUBLICATION-ANGELITH.md` : son contenu ne "
            "doit jamais atteindre le miroir public"))
    return infractions


def juger_contenu(chemin: str, texte: str, motifs: list[str]) -> list[Infraction]:
    """La quatrième règle : un titre d'œuvre écrit en clair dans un fichier suivi."""
    if Path(chemin).suffix.lower() in _SANS_CONTENU:
        return []
    if chemin.replace("\\", "/") == "docs/PUBLICATION-ANGELITH.md":
        # C'est le fichier qui PORTE les motifs. Se signaler soi-même n'apprend rien.
        return []
    trouves = sorted({m for m in motifs
                      if re.search(re.escape(m), texte, re.IGNORECASE)})
    if not trouves:
        return []
    return [Infraction(
        chemin, "fuite",
        f"{len(trouves)} titre(s) d'œuvre en clair — la règle du dépôt veut une désignation "
        f"neutre (`manga A`, `roman A`…). Les titres ne sont pas repris ici : "
        f"`grep -inE` avec le bloc de motifs de `docs/PUBLICATION-ANGELITH.md` les situe")]


# ---------------------------------------------------------------------------
# La couche git.

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def chemins_du_diff(base: str, tete: str = "HEAD") -> list[str]:
    """Les fichiers AJOUTÉS ou MODIFIÉS entre `base` et `tete`. Les suppressions sont
    exclues (`--diff-filter=d`) : effacer un fichier fautif est la correction, pas la faute."""
    sortie = _git("diff", "--name-only", "--diff-filter=d", f"{base}...{tete}")
    return [ligne for ligne in sortie.splitlines() if ligne.strip()]


def lignes_ajoutees_texte(diff: str) -> dict[str, str]:
    """Le texte AJOUTÉ par un diff unifié, par fichier. Fonction PURE : c'est elle qui est
    testée, la couche git au-dessus n'ajoute qu'un `subprocess`.

    ⚠ C'est le point qui décide si ce garde-fou est tenable. Juger le CONTENU ENTIER des
    fichiers modifiés rendrait rouge toute PR qui touche l'un des fichiers portant déjà un
    titre — et il y en a 19 au 2026-08-28 (mesure publiée dans
    `docs/mesures/atelier-github-2026-08-28.md`). Le garde-fou serait désarmé la semaine suivante. On
    juge donc ce que la PR AJOUTE : la fuite nouvelle est bloquée, la fuite héritée est
    mesurée à part et traitée à part.
    """
    par_fichier: dict[str, list[str]] = {}
    courant = None
    for ligne in diff.splitlines():
        if ligne.startswith("+++ b/"):
            courant = ligne[6:]
            par_fichier.setdefault(courant, [])
        elif ligne.startswith("+++ "):
            courant = None
        elif courant and ligne.startswith("+"):
            par_fichier[courant].append(ligne[1:])
    return {c: chr(10).join(lignes) for c, lignes in par_fichier.items()}


def ajouts_du_diff(base: str, tete: str = "HEAD") -> dict[str, str]:
    return lignes_ajoutees_texte(_git("diff", "-U0", "--diff-filter=d", f"{base}...{tete}"))


def chemins_de_l_index() -> list[str]:
    return [ligne for ligne in _git("diff", "--cached", "--name-only",
                                    "--diff-filter=d").splitlines() if ligne.strip()]


def chemins_suivis() -> list[str]:
    return [ligne for ligne in _git("ls-files").splitlines() if ligne.strip()]


def _lire(chemin: str) -> str | None:
    fichier = RACINE / chemin
    if not fichier.is_file():
        return None
    try:
        return fichier.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def juger(chemins: list[str], *, motifs: list[str] | None, publication: bool = False,
          contenus: dict[str, str] | None = None) -> list[Infraction]:
    """`contenus` remplace la lecture disque quand on ne juge pas le fichier entier — c'est
    ce qui permet au mode `--diff` de ne regarder que les LIGNES AJOUTÉES."""
    infractions: list[Infraction] = []
    for chemin in chemins:
        infractions.extend(juger_chemin(chemin, publication=publication))
        if motifs is None:
            continue
        texte = contenus.get(chemin) if contenus is not None else _lire(chemin)
        if texte:
            infractions.extend(juger_contenu(chemin, texte, motifs))
    return infractions


def rendre(infractions: list[Infraction], nb_chemins: int, *, markdown: bool = False,
           note: str = "") -> str:
    lignes: list[str] = []
    if markdown:
        lignes += ["### Garde-fou d'arbre", ""]
        if note:
            lignes += [note, ""]
        if not infractions:
            lignes.append(f"✅ {nb_chemins} fichier(s) examiné(s), aucune infraction.")
        else:
            lignes += [f"❌ **{len(infractions)} infraction(s)** sur {nb_chemins} fichier(s).",
                       "", "| fichier | règle | détail |", "|---|---|---|"]
            lignes += [f"| `{i.chemin}` | {i.regle} | {i.detail} |" for i in infractions]
    else:
        if note:
            lignes.append(note)
        lignes += [str(i) for i in infractions]
        lignes.append(f"{len(infractions)} infraction(s) sur {nb_chemins} fichier(s) examiné(s).")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`, et ce n'est pas un oubli.** Ce fichier
    # n'importe QUE la bibliothèque standard, et le job « Garde-fous » le lance sur un Python
    # nu — `.github/workflows/garde-fous.yml` ne fait aucun `pip install`. Importer
    # `core.cli` tirerait `yaml` et casserait le job. D'où ces quatre lignes, répétées dans
    # les outils sans dépendance et tenues en phase par `tests/test_outils_sortie.py`.
    #
    # Sans elles, une console Windows en cp1252 fait tomber l'outil sur le premier « ⚠ » —
    # mesuré le 2026-09-04 : `verifier_disclosure.py --historique 3` levait un
    # `UnicodeEncodeError` APRÈS avoir jugé les commits, donc en perdant son verdict.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description="Garde-fou de fuite, de corpus et de poids.")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--diff", metavar="BASE", help="fichiers ajoutés/modifiés depuis BASE")
    source.add_argument("--index", action="store_true", help="fichiers de l'index (publication)")
    source.add_argument("--suivi", action="store_true", help="tout l'arbre suivi (mesure)")
    ap.add_argument("--tete", default="HEAD")
    ap.add_argument("--markdown", action="store_true", help="sortie pour $GITHUB_STEP_SUMMARY")
    ap.add_argument("--sans-fuite", action="store_true",
                    help="ne pas juger le contenu (règle « fuite ») — pour mesurer les trois "
                         "autres règles là où les motifs sont indisponibles")
    ap.add_argument("--non-bloquant", action="store_true",
                    help="rapporter et sortir 0 (mesure d'un état existant)")
    a = ap.parse_args(argv)

    contenus: dict[str, str] | None = None
    if a.diff:
        chemins = chemins_du_diff(a.diff, a.tete)
        contenus = ajouts_du_diff(a.diff, a.tete)
        quoi = f"diff {a.diff}...{a.tete} — lignes AJOUTÉES uniquement"
    elif a.index:
        chemins, quoi = chemins_de_l_index(), "index, contenu entier (publication)"
    else:
        chemins, quoi = chemins_suivis(), "arbre suivi, contenu entier"

    note = ""
    motifs: list[str] | None = None
    if not a.sans_fuite:
        try:
            motifs = motifs_de_fuite()
        except MotifsIndisponibles as e:
            print(f"MOTIFS INDISPONIBLES — {e}", file=sys.stderr)
            # `--suivi` est une mesure : on la poursuit en disant ce qu'elle ne couvre plus.
            # Les deux modes bloquants, eux, refusent de rendre un vert aveugle.
            if not a.suivi:
                return 3
            note = ("⚠ règle « fuite » NON évaluée : les motifs sont indisponibles "
                    "(cf. docs/PUBLICATION-ANGELITH.md).")

    infractions = juger(chemins, motifs=motifs, publication=a.index, contenus=contenus)
    print(rendre(infractions, len(chemins), markdown=a.markdown,
                 note=note or f"Source : {quoi}."))
    if a.non_bloquant:
        return 0
    return 1 if infractions else 0


if __name__ == "__main__":
    sys.exit(main())
