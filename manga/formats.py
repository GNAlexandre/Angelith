# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Surcouche de configuration par FORMAT de planche (`manga`, `webtoon`).

Le principe est celui du moindre entretien : un format **réutilise tout le manga** et ne
redéclare que ce qui diffère vraiment. Le webtoon tient ainsi en trois lignes de
`config.yaml` — son sens de lecture — et hérite du reste (détection, nettoyage, OCR, rendu,
modèles, températures) sans qu'on ait à le maintenir en double.

Chaîne d'héritage complète, du plus général au plus précis :

    <cle>  →  manga.<cle>  →  manga.formats.<format>.<cle>

Les deux premières flèches sont déjà l'affaire de `core.config.section` ; ce module n'ajoute
que la troisième, par la même fusion profonde. On ne touche PAS à `section()` : elle est
utilisée par le LN et par `scan/`, qui n'ont pas de notion de format."""
from __future__ import annotations

from core import config as core_config

#: Sens de lecture par format. C'est LA particularité qui justifie la notion de format.
#:
#: ⚠ Ne jamais dériver ce réglage de la langue : un scan **anglais** d'un manga japonais se
#: lit droite→gauche, un webtoon **coréen** se lit gauche→droite. Confondre les deux axes
#: revient à commettre l'erreur inverse de celle qu'on corrige.
SENS_PAR_DEFAUT: dict[str, str] = {
    "manga": "droite_gauche",
    "webtoon": "gauche_droite",
}

SENS_DEFAUT = "droite_gauche"


def config_format(config: dict, format: str | None, cle: str) -> dict:
    """Bloc `cle` tel que le voit le format, hérité de `manga.<cle>` par fusion profonde."""
    base = core_config.section(config, "manga", cle)
    formats = ((config.get("manga") or {}).get("formats") or {})
    propre = ((formats.get(format or "") or {}).get(cle)) or {}
    return core_config.deep_merge(base, propre)


def sens_lecture(config: dict, format: str | None) -> str:
    """`"droite_gauche"` ou `"gauche_droite"`, pour la numérotation des bulles ET la
    métadonnée `ComicInfo.xml` — qui doivent être d'accord.

    Ordre de résolution : `manga.formats.<format>.rendu.sens_lecture`, puis
    `manga.rendu.sens_lecture`, puis le défaut du format. Le défaut du format ne s'applique
    donc QUE si l'utilisateur n'a rien dit — c'est ce qui laisse la main de bout en bout."""
    fmt = (format or "manga").lower()
    formats = ((config.get("manga") or {}).get("formats") or {})
    propre = ((formats.get(fmt) or {}).get("rendu")) or {}
    if propre.get("sens_lecture"):
        return str(propre["sens_lecture"])
    racine = core_config.section(config, "manga", "rendu")
    if racine.get("sens_lecture"):
        return str(racine["sens_lecture"])
    return SENS_PAR_DEFAUT.get(fmt, SENS_DEFAUT)
