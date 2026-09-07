# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Savoir qu'une version existe — **désarmé par défaut**, et rien de plus.

## Ce que ce module n'est pas, et le dire d'abord

Ce n'est **pas** un mécanisme de mise à jour (`PLAN-37` L37.6). Il ne télécharge rien,
n'installe rien, n'exécute rien. Une mise à jour automatique est un canal d'exécution de code
sur la machine de quelqu'un d'autre, et elle demande une infrastructure — signature, canal,
rollback — qu'aucune mesure ne justifie aujourd'hui pour ce projet.

Il fait une chose : un `GET` sur l'API des releases GitHub, et une comparaison de trois
entiers. Le résultat s'affiche dans « À propos », avec un lien.

## Désarmé par défaut, et le motif est un différenciateur du produit

`maj.verifier: false` dans le `config.yaml` livré. Le projet promet « 100 % local, rien ne sort
de la machine » ; un appel réseau au démarrage, même anodin, contredit la promesse. Il est donc
opt-in, et il le dit — `tests/test_core_maj.py` vérifie que le `config.yaml` **publié** le
laisse à `false`, sur `git show HEAD:config.yaml`, comme le lot 27 a appris à le faire après
qu'un `config.yaml` de travail est entré dans un commit.

## Ce qui ne part pas, énuméré plutôt que promis

- **aucun identifiant** : ni machine, ni installation, ni utilisateur, ni compteur ;
- **aucune télémétrie** : ni version installée, ni système, ni brique utilisée ;
- **aucun en-tête bavard** : l'agent utilisateur est la constante `AGENT` ci-dessous, sans
  numéro de version. ⚠ Y mettre la version installée serait déjà de la télémétrie — le serveur
  saurait quelle version tourne ici. Un `GET` anonyme sur une URL publique ne dit rien de plus
  que « quelqu'un a demandé cette page » ;
- **aucun envoi** : la requête n'a pas de corps.

Ce qui part, en entier : une ligne `GET /repos/<dépôt>/releases/latest`, et l'adresse IP que
tout `GET` porte — ce que ce module ne peut pas éviter, et qu'il vaut mieux écrire que taire.

## ⚠ MISE À JOUR lot 40 (2026-09-06) — la vérification est ARMÉE, et le module INSTALLE

Les deux affirmations du titre et du §3 ci-dessus — « désarmé par défaut » et « ce n'est **pas**
un mécanisme de mise à jour » — **sont levées ici**, sur décision du mainteneur. Elles ne sont
pas effacées : elles décrivent exactement ce que la 2.31.0 livrait, et le motif qui les
accompagnait n'était pas faux, il était **plus large que ce qu'il voulait dire**.

« 100 % local, rien ne sort de la machine » porte sur les **œuvres** : aucun texte, aucune
planche, aucun glossaire, aucune traduction ne quitte cette machine. Un `GET` anonyme sur une
URL publique ne dit rien d'une œuvre. La formulation de 2.31.0 mettait les deux dans le même
sac ; c'est elle qui est corrigée, pas la promesse.

Ce qui change, précisément :

- `maj.verifier` vaut **`true`** dans le `config.yaml` livré. ⚠ **La clé ABSENTE vaut toujours
  `False`** — cf. `armee()`. Une installation antérieure à ce lot n'a pas la section `maj:` et
  ne se met pas à faire un appel réseau parce que personne ne lui a rien dit ;
- le module sait **télécharger** l'installeur d'une release, **vérifier son empreinte** contre
  le `SHA256SUMS.txt` de la même release, et le **lancer**. Rien de tout cela ne part d'une
  vérification : ce sont trois fonctions distinctes, appelées sur un clic.

## ⚠ Ce que l'empreinte protège, et ce qu'elle ne protège pas

Elle attrape un téléchargement **tronqué ou altéré en transit**. Elle ne remplace **pas** une
signature de code : aucun certificat ne signe ces binaires (`docs/mesures/empaquetage-2026-09-06.md`
§6.2), et elle ne protégerait pas d'un compte GitHub compromis — le `SHA256SUMS.txt` vient de
la même release que l'exécutable, donc de la même main. Cela doit être écrit **à l'écran**, pas
seulement ici, et `gui/dialogues.py` le fait.

## ⚠ Ce que la mesure du 2026-09-06 dit, et ce qu'elle ne dit pas

L'installeur de la 2.31.0 pèse **292,1 Mio** (1 fichier, mesuré sur cette machine). Son
empreinte SHA-256 se calcule en **0,27 s** (1 062 Mio/s) : la vérification est gratuite devant
le téléchargement. Un débit de **2,5 Mio/s** relevé sur un asset de release GitHub public
(1 mesure, 2,0 Mio lus, connexion de cette machine) donnerait **~115 s** pour 292 Mio — d'où la
barre de progression et le bouton d'annulation, et d'où le fait que rien de tout cela ne peut
tourner sur le fil d'affichage.

⚠ **Aucun aller-retour réel n'a pu être mesuré** : au 2026-09-06, `GET` sur l'API du miroir rend
**404 en 0,72 s** — le dépôt public est privé jusqu'à la candidature NLnet
(`docs/PUBLICATION-ANGELITH.md`), et aucune release n'y existe. Le chemin complet
« télécharger → vérifier → installer » est donc écrit et testé contre des doubles, **jamais
contre une vraie release**. C'est une limite nommée de ce lot.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

#: Le dépôt public interrogé. ⚠ C'est le MIROIR (`github.com/GNAlexandre/Angelith`), pas le
#: dépôt de travail : c'est là que les releases sont publiées, et c'est le seul des deux qu'un
#: utilisateur puisse ouvrir.
URL_DEFAUT = "https://api.github.com/repos/GNAlexandre/Angelith/releases/latest"

#: Où l'humain va cliquer. Une API JSON ne se lit pas dans un navigateur.
PAGE_DEFAUT = "https://github.com/GNAlexandre/Angelith/releases"

#: L'agent utilisateur envoyé. Une constante, **sans la version installée** — cf. l'en-tête.
AGENT = "Angelith"

#: Délai d'attente, en secondes. Court par construction : cette vérification est un confort
#: affiché dans une page « À propos », et une page « À propos » ne se fige pas dix secondes.
#: Même raisonnement que `gui/sondes.py:DELAI_RESEAU`, et même ordre de grandeur.
DELAI = 3.0

#: Délai d'attente du TÉLÉCHARGEMENT, en secondes. ⚠ Rien à voir avec `DELAI` : celui-ci est le
#: plafond d'un `GET` de 3 lignes de JSON, celui-là couvre 292 Mio. Mesuré le 2026-09-06 :
#: 2,5 Mio/s sur cette connexion (1 mesure) ⇒ ~115 s pour l'installeur de la 2.31.0. Le plafond
#: est posé à dix fois cette estimation, parce qu'une connexion dix fois plus lente existe et
#: qu'un téléchargement coupé au milieu est le pire des deux résultats.
DELAI_TELECHARGEMENT = 1200.0

#: La taille des blocs lus, en octets. Le compromis usuel : assez gros pour ne pas payer un
#: appel système par kilo-octet, assez petit pour que la progression bouge et que l'annulation
#: réponde. ⚠ C'est aussi le grain de l'annulation : elle est testée UNE FOIS PAR BLOC.
BLOC = 1024 * 256

#: Le suffixe de l'installeur dans la release. Il vient de `installeur/generer.py`, qui écrit
#: `Angelith-<version>-windows-x64-setup.exe`. ⚠ Cherché par SUFFIXE et non par nom exact : le
#: nom porte la version, qui est justement ce qu'on ne connaît pas avant d'avoir lu la release.
SUFFIXE_INSTALLEUR = "-setup.exe"

#: Le fichier d'empreintes attaché à la même release, écrit par
#: `tools/verifier_gel.py --empreintes`. Format coreutils : `<hex>  <nom>`, deux espaces.
NOM_SOMMES = "SHA256SUMS.txt"

_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class Asset:
    """Un fichier attaché à la release — lot 40.

    ⚠ **Sans asset, il n'y a pas de mise à jour**, et c'est le prérequis que le lot 37 avait
    laissé ouvert : `publication.yml` créait une release **sans aucun fichier**, et le job
    `artefact` téléversait des artefacts de *workflow*, qui n'en sont pas. `ci.yml` attache
    désormais l'installeur et `SHA256SUMS.txt` à la release ; ce qui suit lit ce qu'il attache.

    `taille` vient de l'API et sert à **deux** choses : afficher un poids avant de lancer les
    115 s, et détecter un téléchargement tronqué avant même de calculer l'empreinte. Elle vaut
    `0` si l'API ne l'a pas donnée, et `0` n'est alors pas une vérification qui échoue — c'est
    une vérification qu'on n'a pas les moyens de faire."""

    nom: str = ""
    url: str = ""
    taille: int = 0


@dataclass(frozen=True)
class Resultat:
    """Ce que la vérification a rendu, et **elle rend toujours quelque chose**.

    `arme` — la vérification était-elle autorisée ? `False` est le défaut du dépôt.
    `disponible` — une version publiée est-elle strictement plus récente que celle-ci ?
    `version` — celle qui a été lue, `""` si rien n'a été lu.
    `page` — l'adresse à ouvrir, pour l'humain.
    `detail` — pourquoi il n'y a pas de réponse : « désarmée », « httpx absent », le type de
    l'erreur réseau. ⚠ Jamais une exception qui remonte : personne n'accepte qu'une page « À
    propos » plante parce qu'un serveur ne répond pas.
    """

    arme: bool = False
    disponible: bool = False
    version: str = ""
    page: str = PAGE_DEFAUT
    detail: str = ""
    #: Les fichiers attachés à la release lue — lot 40. Vide quand la release n'en porte
    #: aucun, ce qui est **le cas de toutes les releases publiées avant ce lot**.
    assets: tuple[Asset, ...] = field(default_factory=tuple)

    def phrase(self) -> str:
        """La ligne de la page « À propos ». Toujours honnête sur ce qu'elle sait."""
        if not self.arme:
            return ("Vérification des versions : désarmée (config.yaml > maj.verifier). "
                    "Rien ne sort de cette machine.")
        if self.disponible:
            return f"Une version {self.version} est disponible — {self.page}"
        if self.version:
            return f"Vous avez la dernière version publiée ({self.version})."
        return f"Vérification impossible : {self.detail or 'aucune réponse'}."

    def installeur(self) -> Asset | None:
        """L'installeur Windows de cette release, s'il y en a un — lot 40.

        ⚠ Rend `None` **beaucoup plus souvent qu'on ne le croit** : une release publiée avant ce
        lot n'a aucun asset, et une release de source n'en a pas non plus. L'appelant doit
        traiter ce cas comme un cas normal — « va voir la page » — et pas comme une erreur."""
        for asset in self.assets:
            if asset.nom.lower().endswith(SUFFIXE_INSTALLEUR):
                return asset
        return None

    def sommes(self) -> Asset | None:
        """Le `SHA256SUMS.txt` de la MÊME release. Cf. l'avertissement de l'en-tête sur ce que
        cette empreinte protège : elle vient de la même main que l'exécutable."""
        for asset in self.assets:
            if asset.nom == NOM_SOMMES:
                return asset
        return None


def armee(config: dict) -> bool:
    """`maj.verifier`, et il vaut `false` dans le `config.yaml` livré.

    ⚠ La clé absente vaut `False`, pas `True`. Une installation antérieure à ce lot n'a pas la
    section `maj:` ; lui faire faire un appel réseau parce qu'elle n'a rien dit serait
    exactement l'inverse d'un opt-in."""
    return bool((config.get("maj") or {}).get("verifier", False))


def _triplet(texte: str) -> tuple[int, int, int] | None:
    trouve = _SEMVER.search(texte or "")
    return (int(trouve[1]), int(trouve[2]), int(trouve[3])) if trouve else None


def plus_recente(publiee: str, installee: str) -> bool:
    """`publiee` est-elle strictement plus récente que `installee` ?

    Comparaison sur trois entiers, jamais sur les chaînes : `"2.9.0" > "2.10.0"` est vrai en
    lexicographique et faux en version. Une étiquette illisible rend `False` — on ne signale
    pas une mise à jour dont on n'a pas su lire le numéro."""
    a, b = _triplet(publiee), _triplet(installee)
    return bool(a and b and a > b)


def verifier(config: dict, *, delai: float = DELAI, installee: str = "") -> Resultat:
    """Le `GET` et la comparaison. **Ne lève jamais, et ne part pas si ce n'est pas armé.**

    ⚠ L'ordre des deux premières lignes est le contrat : on lit le drapeau AVANT d'importer
    `httpx`. Un import qui précéderait le test suggérerait qu'il peut y avoir un appel derrière
    — il n'y en a pas, et `tests/test_core_maj.py` le vérifie en donnant un client qui
    échouerait s'il était appelé."""
    from .version import __version__
    if not armee(config):
        return Resultat(arme=False, detail="désarmée")

    section = config.get("maj") or {}
    url = str(section.get("url") or URL_DEFAUT)
    page = str(section.get("page") or PAGE_DEFAUT)
    courante = installee or __version__

    try:
        import httpx
    except ImportError:                                # pragma: no cover — httpx est un socle
        return Resultat(arme=True, page=page, detail="httpx n'est pas installé")

    try:
        reponse = httpx.get(url, timeout=delai, headers={"User-Agent": AGENT},
                            follow_redirects=True)
        # ⚠ Le 404 est traité AVANT `raise_for_status`, et il n'est pas une erreur — lot 40.
        # Au 2026-09-06 c'est la réponse réelle du miroir : il est privé jusqu'à la candidature
        # NLnet, et aucune release n'y est publiée. « Vérification impossible :
        # HTTPStatusError » serait, sur une vérification désormais ARMÉE PAR DÉFAUT, la
        # première phrase que tout le monde lirait — et elle n'apprendrait rien.
        if reponse.status_code == 404:
            return Resultat(arme=True, page=page, detail="aucune version n'est publiée")
        reponse.raise_for_status()
        charge = reponse.json() or {}
        etiquette = str(charge.get("tag_name") or "")
        assets = _assets(charge)
    except Exception as err:                           # noqa: BLE001 — un réseau qui tombe
        return Resultat(arme=True, page=page, detail=type(err).__name__)

    publiee = etiquette.lstrip("vV")
    return Resultat(arme=True, disponible=plus_recente(publiee, courante),
                    version=publiee, page=page, assets=assets)


def _assets(charge: dict) -> tuple[Asset, ...]:
    """Les fichiers attachés, lus défensivement — lot 40.

    ⚠ Rien de ce JSON n'est de confiance : il vient du réseau. Un `size` en chaîne, un `name`
    absent, une entrée qui n'est pas un dictionnaire — chacun de ces cas existe dans la nature
    (miroirs, proxys d'entreprise qui réécrivent), et aucun ne doit faire remonter d'exception
    depuis une fonction dont tout le contrat est de ne jamais lever."""
    lus: list[Asset] = []
    for brut in (charge.get("assets") or []):
        if not isinstance(brut, dict):
            continue
        nom = str(brut.get("name") or "")
        adresse = str(brut.get("browser_download_url") or "")
        if not nom or not adresse:
            continue
        try:
            taille = int(brut.get("size") or 0)
        except (TypeError, ValueError):
            taille = 0
        lus.append(Asset(nom=nom, url=adresse, taille=max(taille, 0)))
    return tuple(lus)


# --------------------------------------------------------------------------- #
#  Télécharger, vérifier, installer — lot 40
#
#  ⚠ Les trois sont SÉPARÉES, et l'ordre est imposé par l'appelant. Une seule fonction
#  « mets-moi à jour » cacherait le seul moment où quelqu'un peut encore dire non : entre
#  l'empreinte vérifiée et l'installeur lancé.
# --------------------------------------------------------------------------- #

def empreinte(chemin: str | Path, *, bloc: int = 1024 * 1024) -> str:
    """Le SHA-256 d'un fichier, en minuscules. Lu par blocs : 292 Mio ne tiennent pas en RAM
    sans raison, et le coût est nul — 0,27 s pour l'installeur de la 2.31.0, mesuré."""
    condensat = hashlib.sha256()
    with Path(chemin).open("rb") as fichier:
        for morceau in iter(lambda: fichier.read(bloc), b""):
            condensat.update(morceau)
    return condensat.hexdigest()


def empreinte_attendue(contenu: str, nom: str) -> str:
    """L'empreinte de `nom` dans un `SHA256SUMS.txt`, ou `""` s'il n'y figure pas.

    Format coreutils : `<hex>  <nom>`, deux espaces. ⚠ On coupe sur le **premier** blanc et on
    compare le RESTE au nom, sans le `*` que le mode binaire de `sha256sum` préfixe parfois :
    un `split()` sur tous les blancs perdrait un nom de fichier qui en contient, ce qui est
    précisément le genre de faille silencieuse qu'une vérification d'intégrité ne peut pas se
    permettre."""
    for brut in (contenu or "").splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        morceaux = ligne.split(None, 1)
        if len(morceaux) != 2:
            continue
        somme, cible = morceaux[0], morceaux[1].strip().lstrip("*")
        if cible == nom:
            return somme.lower()
    return ""


class Annule(Exception):
    """Levée par `telecharger` quand `arret()` rend vrai. **Ce n'est pas une erreur** : c'est
    l'utilisateur qui a cliqué « Annuler », et l'appelant doit la distinguer d'un réseau qui
    tombe — l'un ne mérite aucun message d'erreur, l'autre si."""


def telecharger(asset: Asset, destination: str | Path, *,
                delai: float = DELAI_TELECHARGEMENT, progres=None, arret=None) -> Path:
    """Écrit `asset` dans `destination` et rend le chemin. **Celle-ci LÈVE**, contrairement à
    `verifier()` — et c'est délibéré : une vérification muette est un confort, un téléchargement
    muet qui échoue laisserait croire à une installation qui n'a pas eu lieu.

    `progres(lus, total)` est appelé une fois par bloc, `total` valant `0` quand ni l'API ni
    l'en-tête n'ont donné de taille. `arret()` est testé au même rythme et lève `Annule`.

    ⚠ **Écriture sous un nom temporaire, renommage à la fin.** Un fichier partiel qui porterait
    le nom final serait vérifié, refusé, et resterait sur le disque à ressembler à un
    installeur. Le partiel est effacé sur **toute** sortie anormale, annulation comprise."""
    cible = Path(destination)
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".partiel")
    import httpx

    lus = 0
    try:
        with httpx.stream("GET", asset.url, timeout=delai, follow_redirects=True,
                          headers={"User-Agent": AGENT}) as reponse:
            reponse.raise_for_status()
            total = asset.taille or int(reponse.headers.get("content-length") or 0)
            with partiel.open("wb") as sortie:
                for morceau in reponse.iter_bytes(BLOC):
                    if arret is not None and arret():
                        raise Annule("téléchargement annulé")
                    sortie.write(morceau)
                    lus += len(morceau)
                    if progres is not None:
                        progres(lus, total)
    except BaseException:
        partiel.unlink(missing_ok=True)
        raise
    partiel.replace(cible)
    return cible


def lire_texte(asset: Asset, *, delai: float = DELAI) -> str:
    """Le contenu texte d'un petit asset — `SHA256SUMS.txt` fait 105 octets. Séparé de
    `telecharger` parce qu'il n'a besoin ni de progression, ni d'annulation, ni de disque."""
    import httpx
    reponse = httpx.get(asset.url, timeout=delai, follow_redirects=True,
                        headers={"User-Agent": AGENT})
    reponse.raise_for_status()
    return reponse.text


def installer(chemin: str | Path) -> None:
    """Lance l'installeur téléchargé et **rend la main immédiatement**. L'appelant quitte.

    ⚠ **Refusé hors installation gelée.** Lancer un installeur depuis un dépôt git remplacerait
    un arbre de travail par une installation — on ne fait pas ça à quelqu'un qui a cloné le
    dépôt. Hors gel, l'interface ouvre la page des releases et n'appelle jamais cette fonction ;
    si elle l'appelait quand même, c'est ici que ça s'arrête.

    ⚠ **`Popen`, pas `run`.** L'installeur remplace l'installation en place (l'`AppId` d'Inno
    Setup est fixe) et ne peut donc pas écraser des fichiers que ce processus tient encore
    ouverts : il faut lui rendre la main, puis quitter."""
    import subprocess

    from .installation import gele
    if not gele():
        raise RuntimeError(
            "installation depuis les sources : l'installeur n'est pas lancé. "
            "Mets à jour avec `git pull`, ou récupère l'installeur depuis la page des "
            "releases.")
    cible = Path(chemin)
    if not cible.is_file():
        raise FileNotFoundError(str(cible))
    # noqa: S603 — le chemin est celui que l'on vient d'écrire, et dont l'empreinte a été
    # vérifiée par l'appelant contre le `SHA256SUMS.txt` de la même release.
    subprocess.Popen([str(cible)], close_fds=True)  # noqa: S603
