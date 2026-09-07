# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""D'où vient chaque poids présent sur cette machine — URL, date, taille, SHA-256, licence.

## Pourquoi ce fichier existe, et ce n'est pas une commodité

⚠ **Angelith ne redistribue aucun poids.** Il les *récupère*, avec consentement, en affichant
la licence avant, et en enregistrant l'empreinte de ce qu'il a récupéré. C'est la seule
position tenable : les poids que ce projet fait récupérer portent des conditions qui ne sont pas
les siennes — le détecteur de **texte sur le dessin** est sous GPL-3.0 amont avec des poids
entraînés pour partie sur **Manga109-s**, qui a ses propres conditions d'usage académique ; la
licence de LaMa n'est **pas établie au 2026-09-06**. Héberger un miroir ou livrer les poids dans
un `.exe` engagerait le projet sur des droits qu'il n'a pas.

⚠ **MISE À JOUR 2026-09-06, lot 38.** La phrase ci-dessus disait « le détecteur en place est
GPL-3.0 + Manga109-s », ce qui confondait les DEUX détecteurs. Les licences ne sont plus
énoncées qu'à un seul endroit, `manga/models.py`, et ce module-ci n'en cite plus que l'exemple
qui motive son existence.

La conséquence pratique est celle-ci : **rien, dans le dépôt, ne sait quelle licence porte le
fichier qui est réellement sur le disque de l'utilisateur** — sauf ce que ce module écrit. La
page « À propos » lit ces fiches (`PLAN-36` L36.5), et c'est ce qui permet de dire « voici les
licences des poids présents ICI », au lieu de réciter une liste théorique.

C'est la règle des chiffres (`docs/chiffres-de-reference.md`) appliquée aux artefacts : un
fichier de 104 Mo sans provenance n'est pas une mesure, c'est une impression.

## Ce que la fiche contient, et pourquoi ces champs-là

| Champ | Pourquoi |
|---|---|
| `url` | la **source primaire**, jamais un miroir du projet |
| `date` | ISO 8601, sans heure : la règle des affirmations d'état (§5 bis du contexte agent) |
| `octets` | ce qu'on a reçu, pas ce qu'on attendait — c'est ce qui détecte un fichier partiel |
| `sha256` | l'empreinte de ce qui est là. Une republication amont se voit ici |
| `licence` | le nom SPDX quand il existe, la phrase quand il n'existe pas |
| `licence_url` | pour aller vérifier à la source. Une licence citée sans lien n'est pas vérifiable |
| `version_angelith` | quelle version a récupéré ce fichier |

## Où elle est écrite

À côté du poids, sous `<nom du poids>.provenance.json`. **Pas** dans un index central : un
index se désynchronise du disque à la première suppression manuelle, et le disque a toujours
raison. Une fiche orpheline est ignorée ; un poids sans fiche est signalé comme tel plutôt que
d'être crédité d'une licence qu'on n'a pas vérifiée.

⚠ **Aucun import Qt, aucun réseau ici.** Ce module écrit et relit des fiches ; c'est
`core/reparations.py` qui télécharge, et une page d'interface qui demande.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

#: Suffixe de la fiche, à côté du fichier qu'elle décrit.
SUFFIXE = ".provenance.json"

#: Ce qu'on écrit quand la licence d'un poids n'est **pas établie**. ⚠ Ce n'est pas un défaut
#: de saisie : la licence de LaMa n'est pas établie au 2026-09-06, et écrire « inconnue » est
#: plus honnête que d'inventer un nom SPDX.
LICENCE_INDETERMINEE = "non établie — à vérifier à la source primaire avant tout usage"


@dataclass(frozen=True)
class Fiche:
    """La provenance d'un artefact récupéré. Sérialisée telle quelle en JSON."""

    fichier: str
    url: str
    date: str
    octets: int
    sha256: str
    licence: str
    licence_url: str = ""
    version_angelith: str = ""
    note: str = ""

    def resume(self) -> str:
        """Une ligne pour la page « À propos » : le fichier, sa licence, sa date."""
        return f"{self.fichier} — {self.licence} (récupéré le {self.date})"


def empreinte(chemin: Path, bloc: int = 1 << 20) -> str:
    """SHA-256 d'un fichier, lu par blocs d'un mégaoctet.

    ⚠ La même fonction existe dans `manga/models.py`. Elle n'est pas importée d'ici pour ne pas
    faire dépendre le socle d'une brique — c'est la règle de couche, et six lignes de
    `hashlib` ne valent pas de l'enfreindre."""
    h = hashlib.sha256()
    with open(chemin, "rb") as fh:
        for morceau in iter(lambda: fh.read(bloc), b""):
            h.update(morceau)
    return h.hexdigest()


def chemin_fiche(poids: Path | str) -> Path:
    """La fiche qui décrit `poids`. Le suffixe s'ajoute au nom COMPLET (`x.onnx` →
    `x.onnx.provenance.json`), pour qu'un dossier de poids reste lisible."""
    poids = Path(poids)
    return poids.with_name(poids.name + SUFFIXE)


def aujourdhui() -> str:
    """La date du jour, ISO 8601, sans heure. L'heure n'apporte rien et ferait diverger deux
    fiches du même téléchargement."""
    return _dt.date.today().isoformat()


def ecrire(poids: Path | str, *, url: str, licence: str, licence_url: str = "",
           note: str = "", date: str | None = None, version: str = "") -> Fiche:
    """Écrit la fiche de `poids`, en **relisant le fichier** pour sa taille et son empreinte.

    ⚠ On ne fait pas confiance à ce qu'annonçait le serveur : `Content-Length` peut mentir, et
    un téléchargement coupé produit un fichier court que le serveur avait pourtant annoncé
    complet. L'empreinte est celle de ce qui est sur le disque, mesurée après coup — sinon la
    fiche décrirait une intention, pas un fait."""
    poids = Path(poids)
    if not poids.is_file():
        raise FileNotFoundError(f"aucun fichier à décrire : {poids}")
    if not version:
        from .version import __version__ as version
    fiche = Fiche(fichier=poids.name, url=url, date=date or aujourdhui(),
                  octets=poids.stat().st_size, sha256=empreinte(poids),
                  licence=licence or LICENCE_INDETERMINEE, licence_url=licence_url,
                  version_angelith=version, note=note)
    cible = chemin_fiche(poids)
    cible.write_text(json.dumps(asdict(fiche), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    return fiche


def lire(poids: Path | str) -> Fiche | None:
    """La fiche de `poids`, ou `None` — fiche absente, illisible, ou incomplète.

    ⚠ Aucune exception ne sort d'ici. Cette fonction sert la page « À propos » et le
    diagnostic : une fiche corrompue doit produire « provenance inconnue », jamais une fenêtre
    qui ne s'ouvre pas."""
    cible = chemin_fiche(poids)
    try:
        brut = json.loads(cible.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(brut, dict):
        return None
    champs = {c: brut.get(c) for c in Fiche.__dataclass_fields__}
    if not champs.get("fichier") or not champs.get("sha256"):
        return None
    champs["octets"] = int(champs.get("octets") or 0)
    return Fiche(**{c: (v if v is not None else "") if c != "octets" else v
                    for c, v in champs.items()})


def concorde(poids: Path | str) -> bool | None:
    """Le fichier présent est-il celui que sa fiche décrit ?

    `True` / `False` / `None` (pas de fiche, ou pas de fichier). ⚠ La taille est comparée
    d'abord : elle coûte un `stat()` là où l'empreinte coûte la lecture de 104 Mo, et elle
    suffit à trancher le cas qui nous intéresse — le fichier tronqué."""
    poids = Path(poids)
    fiche = lire(poids)
    if fiche is None or not poids.is_file():
        return None
    if poids.stat().st_size != fiche.octets:
        return False
    return empreinte(poids) == fiche.sha256


def inventorier(dossiers) -> list[Fiche]:
    """Toutes les fiches trouvées sous `dossiers`, triées par nom de fichier.

    C'est ce que lit la page « À propos » : **les licences des poids réellement présents**, et
    non la liste théorique de ce que le projet sait télécharger. Un dossier absent n'est pas
    une erreur — une installation qui n'a jamais fait de manga n'a pas de `manga_models/`."""
    fiches: list[Fiche] = []
    vues: set[str] = set()
    for dossier in dossiers:
        racine = Path(dossier)
        if not racine.is_dir():
            continue
        for chemin in sorted(racine.rglob("*" + SUFFIXE)):
            poids = chemin.with_name(chemin.name[: -len(SUFFIXE)])
            # ⚠ **Le disque a toujours raison.** Une fiche dont le poids a été supprimé à la
            # main ne crédite rien : la page « À propos » annoncerait une licence pour un
            # fichier qui n'est plus là, ce qui est exactement le genre d'affirmation
            # périmée que la règle §5 bis du contexte agent proscrit.
            if not poids.is_file():
                continue
            fiche = lire(poids)
            if fiche is None or str(chemin) in vues:
                continue
            vues.add(str(chemin))
            fiches.append(fiche)
    return sorted(fiches, key=lambda f: f.fichier)
