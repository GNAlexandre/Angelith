# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Où vivent les fichiers, selon qu'on lance le dépôt ou une installation gelée.

## Le mode de panne que ce module ferme — `PLAN-37` L37.3 et L37.4

Un exécutable PyInstaller n'a **ni le même `sys.path` ni le même `__file__`** que le dépôt :
les données livrées sont dépaquetées dans un dossier dont le chemin est dans `sys._MEIPASS`,
et le répertoire courant est celui d'où le raccourci a été lancé. Un chemin construit avec
`Path(__file__).parents[1]` désigne alors l'intérieur du gel, pas le dossier de données ; un
chemin relatif (`"langues"`, `"config.yaml"`) désigne le répertoire courant, qui n'a aucune
raison d'être le dossier d'installation.

C'est le mode de panne le plus courant de cet exercice, et il ne se voit **pas** en
développement : les deux chemins coïncident tant qu'on lance `python gui.py` depuis la racine.

D'où **une** fonction de résolution, `ressource()`, et le fait que le dépôt en interdise le
contournement : `tests/test_installation_chemins.py` échoue si `templates/`, `langues/`,
`config.yaml` ou `.angelith/` est de nouveau atteint par un `Path(__file__)`.

## Trois racines, et elles ne se confondent pas

| Racine | Contenu | Écriture |
|---|---|---|
| `racine_livree()` | le code et ses données — `config.yaml`, `templates/`, `langues/` | jamais |
| `dossier_utilisateur()` | le `config.yaml` modifiable, `.angelith/` | oui |
| `dossier_documents()` | `sources/`, `build/` — les œuvres | oui |

⚠ **La troisième existe parce que le dossier d'installation n'est pas un endroit où mettre des
œuvres**, et parce qu'une désinstallation le supprime. `chemins.sources` et `chemins.build`
valent `"sources"` et `"build"` dans le `config.yaml` livré : relatifs au dépôt, ce qui est
juste dans le dépôt et faux dans une installation. `ancrer_chemins()` les ancre sur
`dossier_documents()` — **et seulement en mode gelé**, ce qui est ce qui rend le lot
iso-comportement pour qui lance `python gui.py` (critère 3 de la définition de « terminé »).

## `config.yaml` est un DOCUMENT, et il n'est jamais réécrit

Interdit 5 du contexte agent : 158 Ko de prose commentée qu'un aller-retour `yaml.safe_dump`
effacerait. Ce module ne l'écrit qu'**une** fois, et par `shutil.copy2` — une copie d'octets,
au premier lancement, si et seulement si la copie utilisateur n'existe pas. Il ne la remplace
jamais, ne la fusionne jamais, et ne la relit jamais pour la réécrire.

La mise à jour du logiciel apporte un `config.yaml` livré plus récent dont l'utilisateur ne
bénéficiera pas : **c'est dit, pas fait**. `ecart_de_config()` compare la copie utilisateur au
fichier livré et rend les clés ajoutées depuis ; le diagnostic les affiche (`PLAN-37` L37.4,
piège 2). On ne fusionne pas un document.

## L'état, au 2026-09-06

Aucune de ces fonctions ne fait quoi que ce soit de différent quand le programme tourne depuis
le dépôt : `gele()` est faux, `racine_livree()` rend la racine du dépôt, `ancrer_chemins()`
rend sa configuration inchangée et `resoudre_config()` rend l'argument tel quel. C'est vérifié
par `tests/test_installation.py`, qui porte le critère 3.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

#: Le nom public du projet — celui du `pyproject.toml`, de l'installeur et du dossier de
#: données. `Yume-Trad` est le nom du dépôt de travail, jamais celui qu'un utilisateur voit.
NOM = "Angelith"

#: Variables d'environnement qui déplacent chaque racine. Elles existent pour les TESTS —
#: chacun écrit dans son `tmp_path` — et pour une installation qu'on veut déplacer sans
#: recompiler. Même mécanisme que `ANGELITH_REGLAGES` (`gui/reglages.py`), qui préexiste.
VAR_DONNEES = "ANGELITH_DONNEES"
VAR_DOCUMENTS = "ANGELITH_DOCUMENTS"

#: Le fichier témoin écrit à côté de la copie utilisateur de `config.yaml`. Il porte la
#: version du logiciel et l'empreinte du fichier livré **au moment de la copie**.
#:
#: ⚠ Il n'est pas DANS `config.yaml` : y écrire un numéro demanderait d'écrire dans le
#: document, ce que ce module refuse. Un fichier témoin à côté dit la même chose sans toucher
#: à un octet de prose.
TEMOIN = "config-livree.json"

#: Les clés de configuration qui désignent un dossier d'ŒUVRES, en notation pointée. Elles
#: s'ancrent sur `dossier_documents()`.
#:
#: ⚠ `manga.chemins.*` y figure parce que `core/config.py` en fait un héritage PROFOND : la
#: section manga peut porter ses propres `sources`/`build`, et n'ancrer que la racine
#: laisserait la brique manga écrire dans le dossier d'installation.
CHEMINS_D_OEUVRES: tuple[str, ...] = (
    "chemins.sources", "chemins.build",
    "manga.chemins.sources", "manga.chemins.build",
)

#: Les clés qui désignent un POIDS téléchargé. Elles s'ancrent sur `dossier_utilisateur()`.
#:
#: ⚠ **Aucun de ces fichiers n'est livré** (`PLAN-37` §0.3) : le détecteur est GPL-3.0 +
#: Manga109-s, donc non redistribuable. Ils sont récupérés par `core/reparations.py`, avec
#: consentement — donc ils doivent atterrir dans un dossier INSCRIPTIBLE qui survit à une mise
#: à jour, ce que le dossier d'installation n'est ni l'un ni l'autre.
CHEMINS_DE_POIDS: tuple[str, ...] = (
    "manga.detection.model_path", "manga.onomatopees.model_path",
    "illustration.poids.dossier", "illustration.identite.encodeur.dossier",
)


# --------------------------------------------------------------------------- #
#  Où l'on tourne
# --------------------------------------------------------------------------- #

def gele() -> bool:
    """Vrai si le programme tourne depuis un gel PyInstaller.

    ⚠ Les deux conditions, et pas seulement `sys.frozen` : d'autres empaqueteurs posent
    l'attribut sans poser `_MEIPASS`, et c'est `_MEIPASS` que `racine_livree()` lit. Tester ce
    qu'on va utiliser vaut mieux que tester ce qui le suggère."""
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def racine_livree() -> Path:
    """Le dossier des données LIVRÉES — `config.yaml`, `templates/`, `langues/`, les icônes.

    En gel : `sys._MEIPASS`. Dans le dépôt : la racine du dépôt, c'est-à-dire le parent de
    `core/`. **En lecture seule dans les deux cas** — le dépôt ne s'écrit pas plus qu'une
    installation."""
    if gele():
        return Path(sys._MEIPASS)                                    # noqa: SLF001
    return Path(__file__).resolve().parents[1]


def ressource(*parties: str | os.PathLike) -> Path:
    """**LA** fonction de résolution d'une donnée livrée. `ressource("langues", "fr")`.

    Tout ce que le dépôt lit et ne réécrit jamais passe par ici : les prompts, les gabarits
    Word, les polices livrées, les icônes, le `config.yaml` de référence. C'est la seule
    fonction du dépôt qui connaisse `sys._MEIPASS`, et c'est ce qui rend la règle
    vérifiable."""
    return racine_livree().joinpath(*parties)


def dossier_utilisateur() -> Path:
    """Où vivent le `config.yaml` modifiable et `.angelith/`.

    `%LOCALAPPDATA%/Angelith` sous Windows — et **pas** `%APPDATA%` : ce n'est pas un profil
    itinérant, et un `config.yaml` de 158 Ko qui suivrait l'utilisateur sur le réseau n'est
    pas ce qu'on veut. Ailleurs, `$XDG_DATA_HOME/Angelith` puis `~/.local/share/Angelith`.

    ⚠ Ce dossier n'est PAS supprimé par la désinstallation (`PLAN-37` L37.5 point 3) : il
    porte les réglages d'un humain."""
    force = os.environ.get(VAR_DONNEES)
    if force:
        return Path(force)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / NOM
        return Path.home() / "AppData" / "Local" / NOM
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / NOM


def dossier_documents() -> Path:
    """Où vivent les ŒUVRES d'une installation — `sources/` et `build/`.

    `%USERPROFILE%/Documents/Angelith` sous Windows, `~/Angelith` ailleurs. C'est la valeur
    par défaut que le `PLAN-37` L37.4 piège 3 demandait de **décider et d'écrire** : un tome
    pèse des gigaoctets, il n'a rien à faire dans `%LOCALAPPDATA%`, et encore moins dans le
    dossier d'installation qu'une désinstallation supprime.

    ⚠ Non créé ici. Un dossier créé par le seul fait de lire une configuration serait un effet
    de bord ; c'est le premier écrit qui le crée, comme aujourd'hui dans le dépôt."""
    force = os.environ.get(VAR_DOCUMENTS)
    if force:
        return Path(force)
    if sys.platform == "win32":
        profil = os.environ.get("USERPROFILE")
        base = Path(profil) if profil else Path.home()
        return base / "Documents" / NOM
    return Path.home() / NOM


# --------------------------------------------------------------------------- #
#  `config.yaml` — trois rangs, une copie, aucune réécriture
# --------------------------------------------------------------------------- #

def config_livree() -> Path:
    """Le `config.yaml` de référence, celui du paquet. **Lecture seule.**"""
    return ressource("config.yaml")


def config_utilisateur() -> Path:
    """La copie modifiable, celle qu'une mise à jour n'écrase pas."""
    return dossier_utilisateur() / "config.yaml"


def empreinte(chemin: str | os.PathLike) -> str:
    """SHA-256 d'un fichier, en hexadécimal. Vide si le fichier est illisible.

    Ne lève pas : cette empreinte sert à un diagnostic et à un test de non-réécriture, deux
    usages où « je n'ai pas pu lire » est une réponse, pas une panne."""
    h = hashlib.sha256()
    try:
        with open(chemin, "rb") as fh:
            for bloc in iter(lambda: fh.read(1 << 20), b""):
                h.update(bloc)
    except OSError:
        return ""
    return h.hexdigest()


def installer_config_utilisateur(*, livree: Path | None = None,
                                 cible: Path | None = None) -> Path | None:
    """Copie le `config.yaml` livré chez l'utilisateur **s'il n'y est pas encore**.

    Rend le chemin écrit, ou `None` si rien n'a été fait — parce que la copie existait déjà,
    parce que le fichier livré est introuvable, ou parce que le dossier n'est pas inscriptible.

    ⚠ **Ne remplace JAMAIS une copie existante** (`PLAN-37` L37.4, piège 1). C'est le seul
    endroit du dépôt qui écrive un `config.yaml`, et il ne sait faire qu'une chose : le créer.
    `shutil.copy2` recopie les octets — pas de `yaml.safe_dump`, donc pas un commentaire perdu
    (interdit 5).
    """
    source = Path(livree) if livree is not None else config_livree()
    destination = Path(cible) if cible is not None else config_utilisateur()
    if destination.exists() or not source.is_file():
        return None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    except OSError:
        return None
    _ecrire_temoin(source, destination)
    return destination


def _ecrire_temoin(source: Path, destination: Path) -> None:
    """Note la version et l'empreinte du fichier livré au moment de la copie.

    Silencieux sur échec : sans témoin, `ecart_de_config()` dit « version inconnue », ce qui
    est vrai et sans gravité — alors qu'une exception ici ferait échouer un premier
    lancement."""
    from .version import __version__
    charge = {"version": __version__, "sha256": empreinte(source), "source": str(source)}
    try:
        (destination.parent / TEMOIN).write_text(
            json.dumps(charge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def resoudre_config(argument: str | os.PathLike | None,
                    *, defaut: str = "config.yaml") -> Path:
    """Le `config.yaml` du run, dans l'ordre du `PLAN-37` L37.4 : CLI → utilisateur → livré.

    1. `--config <chemin>` **gagne toujours**, gelé ou non. L'argument existe déjà dans les
       cinq points d'entrée, et une résolution qui le contournerait serait un piège ;
    2. hors gel, on rend l'argument tel quel — c'est ce qui garde le dépôt strictement iso ;
    3. en gel : la copie utilisateur (créée au besoin depuis le fichier livré), et à défaut le
       fichier livré, qui reste lisible même si le dossier utilisateur ne l'est pas.

    ⚠ Le cas 2 n'est pas une commodité : dans le dépôt, `Path("config.yaml")` relatif au
    répertoire courant EST le comportement historique, et le remplacer par un chemin absolu
    ferait qu'une copie du dépôt lirait la configuration d'une autre.
    """
    if argument is not None and str(argument) != defaut:
        return Path(argument)
    if not gele():
        return Path(argument if argument is not None else defaut)
    installer_config_utilisateur()
    utilisateur = config_utilisateur()
    if utilisateur.is_file():
        return utilisateur
    return config_livree()


@dataclass(frozen=True)
class EcartDeConfig:
    """Ce qui sépare la copie utilisateur du `config.yaml` livré — `PLAN-37` L37.4, piège 2.

    `version_copie` — la version du logiciel au moment de la copie, `""` si le témoin manque.
    `version_livree` — celle du logiciel qui pose la question, aujourd'hui.
    `identiques` — les deux fichiers ont la même empreinte : il n'y a rien à dire.
    `cles_ajoutees` — les chemins de clés présents dans le fichier livré et absents de la
    copie. **C'est le « voici ce qui a été ajouté » du plan**, et c'est une lecture : rien
    n'est fusionné, rien n'est proposé à l'écriture.
    """

    version_copie: str = ""
    version_livree: str = ""
    identiques: bool = True
    cles_ajoutees: tuple[str, ...] = ()
    lisible: bool = True

    @property
    def a_signaler(self) -> bool:
        return self.lisible and not self.identiques and bool(self.cles_ajoutees)

    def phrase(self) -> str:
        """La phrase que le diagnostic affiche. Vide s'il n'y a rien à signaler."""
        if not self.a_signaler:
            return ""
        origine = (f"date de la version {self.version_copie}" if self.version_copie
                   else "est d'une version inconnue")
        n = len(self.cles_ajoutees)
        return (f"votre config.yaml {origine}, la version livrée est {self.version_livree} — "
                f"{n} clé(s) ajoutée(s) depuis : "
                + ", ".join(self.cles_ajoutees[:5]) + (" …" if n > 5 else ""))


def _cles(noeud, prefixe: str = "") -> set[str]:
    """Les chemins de clés d'un arbre YAML, en notation pointée."""
    trouvees: set[str] = set()
    if not isinstance(noeud, dict):
        return trouvees
    for cle, valeur in noeud.items():
        chemin = f"{prefixe}{cle}"
        trouvees.add(chemin)
        trouvees |= _cles(valeur, f"{chemin}.")
    return trouvees


def ecart_de_config(*, copie: Path | None = None,
                    livree: Path | None = None) -> EcartDeConfig:
    """Compare la copie utilisateur au fichier livré. **Lecture seule, toujours.**

    ⚠ `yaml.safe_load` des deux côtés, et le résultat sert à COMPTER des clés — jamais à
    réécrire. Le fichier livré est le seul des deux dont on soit sûr qu'il n'a pas été édité à
    la main, et c'est pourquoi la comparaison va dans ce sens : on dit ce qui a été ajouté
    depuis, pas ce que l'utilisateur a retiré."""
    from .version import __version__
    fichier_copie = Path(copie) if copie is not None else config_utilisateur()
    fichier_livree = Path(livree) if livree is not None else config_livree()
    if not fichier_copie.is_file() or not fichier_livree.is_file():
        return EcartDeConfig(version_livree=__version__, lisible=False)

    sha_copie = empreinte(fichier_copie)
    sha_livree = empreinte(fichier_livree)
    temoin = _lire_temoin(fichier_copie.parent)
    if sha_copie and sha_copie == sha_livree:
        return EcartDeConfig(version_copie=temoin.get("version", ""),
                             version_livree=__version__, identiques=True)

    import yaml
    try:
        arbre_copie = yaml.safe_load(fichier_copie.read_text(encoding="utf-8")) or {}
        arbre_livree = yaml.safe_load(fichier_livree.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return EcartDeConfig(version_copie=temoin.get("version", ""),
                             version_livree=__version__, identiques=False, lisible=False)

    ajoutees = tuple(sorted(_cles(arbre_livree) - _cles(arbre_copie)))
    return EcartDeConfig(version_copie=temoin.get("version", ""), version_livree=__version__,
                         identiques=False, cles_ajoutees=ajoutees)


def _lire_temoin(dossier: Path) -> dict:
    try:
        charge = json.loads((dossier / TEMOIN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return charge if isinstance(charge, dict) else {}


# --------------------------------------------------------------------------- #
#  Les œuvres — `chemins.sources` et `chemins.build`
# --------------------------------------------------------------------------- #

def _ancrer_cle(config: dict, pointee: str, base: Path) -> bool:
    """Ancre UNE clé pointée sur `base`, si elle existe et si sa valeur est relative.

    Rend `True` quand la valeur a changé. Une clé absente, vide, non textuelle ou déjà absolue
    est laissée telle quelle — silencieusement, parce que c'est le cas normal : le dépôt lit sa
    configuration à travers des centaines de `.get(...)` à défaut, et une clé qu'un utilisateur
    n'a pas écrite n'est pas une anomalie."""
    *parents, derniere = pointee.split(".")
    noeud = config
    for segment in parents:
        noeud = noeud.get(segment) if isinstance(noeud, dict) else None
        if not isinstance(noeud, dict):
            return False
    valeur = noeud.get(derniere) if isinstance(noeud, dict) else None
    if not valeur or not isinstance(valeur, str) or Path(valeur).is_absolute():
        return False
    noeud[derniere] = str(base / valeur)
    return True


def ancrer_chemins(config: dict) -> dict:
    """Ancre les chemins RELATIFS d'une installation gelée, **et rien hors gel**.

    Deux destinations, et elles ne se confondent pas : les œuvres vont dans
    `dossier_documents()`, les poids téléchargés dans `dossier_utilisateur()`. Ni l'une ni
    l'autre n'est le dossier d'installation, qu'une désinstallation supprime.

    Rend la configuration telle quelle hors gel — c'est la ligne qui garde le lot
    iso-comportement pour le dépôt, et `tests/test_installation.py` la tient.

    ⚠ **Mute le dictionnaire reçu**, comme `core.modeles.outrepasser` : la configuration est
    déjà chargée en mémoire, et une copie profonde de 158 Ko de YAML à chaque démarrage
    coûterait plus qu'elle ne protège. Rien n'est écrit sur le disque.

    ⚠ Un chemin ABSOLU est laissé intact. Quelqu'un qui a écrit `D:/Manga/sources` l'a voulu,
    et le déplacer serait exactement le genre de décision silencieuse que ce dépôt refuse.
    """
    if not gele() or not isinstance(config, dict):
        return config
    for pointee in CHEMINS_D_OEUVRES:
        _ancrer_cle(config, pointee, dossier_documents())
    for pointee in CHEMINS_DE_POIDS:
        _ancrer_cle(config, pointee, dossier_utilisateur())
    return config


def donnee_livree(relatif: str | os.PathLike) -> Path:
    """Un chemin de donnée livrée, tel qu'une configuration l'écrit — `"langues"`, `"prompts"`.

    Ce que le répertoire courant offre gagne ; le paquet n'est qu'un repli, **et seulement en
    gel**.

    ⚠ **Le `gele()` de la dernière ligne n'est pas une précaution, c'est une correction.** Sans
    lui, un repli inconditionnel casse une propriété nommée du dépôt : `resoudre_pack` rend un
    pack de COMPATIBILITÉ (prompts lus à leurs emplacements historiques) quand aucun dossier
    `langues/` n'existe et que la cible est la langue par défaut. Depuis un répertoire courant
    vide, le repli trouvait `langues/fr` dans le dépôt et le mode compatibilité ne se
    déclenchait plus — `tests/test_langues_pack.py` l'a attrapé le 2026-09-06, et c'est
    exactement le critère 3 de la définition de « terminé ». En gel, la question ne se pose
    pas : il n'y a plus d'emplacement historique à préserver."""
    chemin = Path(relatif)
    if chemin.is_absolute() or chemin.exists() or not gele():
        return chemin
    livree = ressource(chemin)
    return livree if livree.exists() else chemin


def dossier_reglages() -> Path:
    """La racine sous laquelle `.angelith/` vit quand rien ne la force.

    Le dépôt : le répertoire courant, exactement comme avant (`gui/reglages.py` le documente —
    « deux copies du dépôt ont deux dispositions »). Le gel : le dossier utilisateur, parce
    que le répertoire courant d'un raccourci Windows n'est pas un endroit stable et que le
    dossier d'installation peut être en lecture seule."""
    return dossier_utilisateur() if gele() else Path.cwd()
