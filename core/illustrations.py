# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Inventaire, classement et **signature de style** des illustrations d'un tome.

## Ce que ce module corrige

Le dépôt extrait les images de chaque source depuis toujours — **446 fichiers dans 15
dossiers `build/*/*/media/`** au 2026-08-29 — et n'a jamais su lesquelles étaient des
illustrations. Un `ls` compte pareillement une pleine page, une lettrine de 100×110 et un
logo d'éditeur de 192×192. `pipeline/images.py` connaît la POSITION d'une image dans son
chapitre ; personne ne connaissait sa NATURE.

Ce module répond aux deux questions, sans modèle et sans Qt :

- `inventaire` / `classer` — de quelle sorte d'image s'agit-il ?
- `rattacher` — dans quel chapitre est-elle posée, ou est-elle en tête de volume ?
- `signature` — à quoi ressemble le REGISTRE GRAPHIQUE du tome (`PLAN-23` L23.7) ?
- `boite_d_encre` / `cadre_propose` — **où est le dessin dans la page** (`PLAN-29` L29.1) ?

Il vit dans `core/` et non dans `pipeline/` parce que la brique manga en aura besoin aussi,
et pas dans `gui/` parce que tout ce qui décide se teste sans Qt (règle de couche).

## Les seuils, et pourquoi ceux-là

Tous sont **relatifs au tome** — la surface médiane de ses images, sa propre dynamique de
luminance. C'est déjà la doctrine de la brique scan : « les seuils, quoique tous relatifs et
non absolus, n'ont pas encore vu d'autre imprimeur ». Une norme absolue de surface n'aurait
aucun sens entre un tome stocké en 1400×1964 et un autre en 992×744.

⚠ **Un critère du plan a été mesuré puis abandonné, et c'est un résultat.** Le `PLAN-23`
étape 0.1 proposait de classer en vignette toute image de « moins de 3 couleurs dominantes ».
Mesuré sur les 446 fichiers : **48 images (10,8 %)** de surface supérieure à 10 % de la
médiane du tome tombent sous ce critère — dont **6 des 27** de roman G et **13 des
164** de *Pride and Prejudice*. Ce sont des illustrations au trait, noir sur blanc : deux
teintes dominantes, et exactement le matériau de référence le plus utile pour un tome
monochrome. Le critère est donc retiré du classement ; le compte de couleurs dominantes reste
MESURÉ (`Illustration.couleurs_dominantes`) parce que la signature de style s'en sert.

## Ce que ce module ne fait pas

Il ne détecte aucun visage, ne recadre rien, n'ouvre aucun fichier en écriture, et n'importe
ni `manga/`, ni Qt, ni OpenCV (interdit n° 4). Il lit des pixels et rend des nombres.

⚠ **`cadre_propose` n'est pas une exception à cette phrase, et son nom le dit** : il rend
quatre fractions et **aucun pixel n'est écrit**. Ce qu'il mesure est « où est l'encre », pas
« où est le personnage » — mesuré le 2026-09-03 sur les 402 illustrations de `build/`, la
boîte couvre une **médiane de 77,5 %** de la page. Elle retire les marges, pas la page ; c'est
pourquoi le `PLAN-29` fait **corriger** le rectangle par un humain.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, replace
from pathlib import Path

from .marqueurs import manifest_for_chapter, orphan_markers, split_marker

# ─────────────────────────────  Classes et contextes  ─────────────────────────────

#: Classes de forme. `INDETERMINEE` est **délibérément généreuse** : c'est la même doctrine
#: que le classifieur de type de bulle du `PLAN-17`. Une illustration mal rangée dans une
#: classe utile se propage dans tout ce qui la consomme ; une illustration rangée en
#: « indéterminée » attend simplement un œil.
COUVERTURE = "couverture"
PLEINE_PAGE = "pleine_page"
DOUBLE_PAGE = "double_page"
VIGNETTE = "vignette"
INDETERMINEE = "indeterminee"
ILLISIBLE = "illisible"

CLASSES = (COUVERTURE, PLEINE_PAGE, DOUBLE_PAGE, VIGNETTE, INDETERMINEE, ILLISIBLE)

#: Contextes de position, rendus par `rattacher`. Ce ne sont PAS des classes : une planche
#: couleur de tête de volume est une `pleine_page` dont le contexte est `tete_de_volume`.
TETE_DE_VOLUME = "tete_de_volume"
NON_REFERENCEE = "non_referencee"

#: Surface au-dessous de laquelle une image est une vignette / un logo / une lettrine.
#: 10 % de la médiane du tome. Mesuré : sépare nettement les 192×192 des éditeurs et les
#: lettrines de 100×110 de *Pride and Prejudice* des illustrations réelles, sans exception
#: constatée sur les 446 fichiers.
SEUIL_VIGNETTE = 0.10

#: Surface au-dessus de laquelle une image portrait est une pleine page. 60 % de la médiane.
SEUIL_PLEINE_PAGE = 0.60

#: Ratio largeur/hauteur au-dessus duquel une image est une double page. 1,30.
#:
#: ⚠ Ce n'est pas une intuition : les tomes du corpus sont stockés à un ratio de page de
#: 0,67 à 0,71, et deux pages côte à côte donnent 1,34 à 1,41 — c'est exactement ce qu'on
#: mesure (roman G 1800×1327 = 1,36 ; roman I Vol.1 992×744 = 1,33). Le seuil est
#: posé juste sous cette valeur.
#:
#: ⚠ **Et il laisse passer un cas connu** : roman D Vol.1 p209/p210 sont des doubles pages à
#: 1,25 et 1,23, qui tombent donc en `INDETERMINEE`. C'est le comportement voulu — la classe
#: généreuse absorbe le doute plutôt que de le trancher.
SEUIL_DOUBLE_PAGE = 1.30

#: Part d'une image qu'une teinte doit couvrir pour compter comme « dominante ».
SEUIL_DOMINANTE = 0.05

#: Côté de la vignette d'analyse. Toute la mesure de couleur et de trait se fait sur une
#: réduction : lire 6 Mpx par image pour en tirer cinq scalaires coûterait cent fois le prix
#: du résultat. Mesuré : 446 images inventoriées en 7,0 s à ce côté.
COTE_ANALYSE = 256

_NUM = re.compile(r"(\d+)")


def _cle_naturelle(nom: str) -> list:
    """Tri « humain » d'un nom de fichier : `p2` avant `p12`, et non l'inverse.

    C'est ce qui permet de désigner la couverture sans lire le Markdown du tome — et il faut
    pouvoir : sur roman D Vol.1, la couverture (`p1_x226`) n'est référencée par AUCUN
    marqueur, parce qu'elle précède la première frontière de chapitre."""
    return [int(t) if t.isdigit() else t.lower() for t in _NUM.split(nom)]


@dataclass(frozen=True)
class Illustration:
    """Une image de `media/`, avec ce qu'on en sait sans la comprendre."""

    chemin: Path
    nom: str
    largeur: int
    hauteur: int
    octets: int
    #: Nombre de teintes couvrant chacune ≥ `SEUIL_DOMINANTE` de l'image. `None` = non mesuré.
    couleurs_dominantes: int | None = None
    #: `True` si les canaux RVB s'écartent, `False` en niveaux de gris, `None` = non mesuré.
    couleur: bool | None = None
    classe: str = ""
    contexte: str = ""

    @property
    def surface(self) -> int:
        return max(0, self.largeur) * max(0, self.hauteur)

    @property
    def ratio(self) -> float:
        return (self.largeur / self.hauteur) if self.hauteur > 0 else 0.0

    @property
    def lisible(self) -> bool:
        return self.largeur > 0 and self.hauteur > 0


@dataclass(frozen=True)
class ContexteTome:
    """Ce qu'il faut savoir DU TOME pour classer une de ses images. Tout est relatif à lui."""

    mediane_surface: float
    #: Nom de fichier retenu comme couverture, ou `""` si le tome n'en désigne pas.
    couverture: str = ""
    #: Noms des SOSIES de la couverture — la même image republiée ailleurs dans le volume.
    #: Cf. `sosies_de_la_couverture` : c'est un défaut mesuré, pas une élégance.
    sosies_couverture: frozenset = frozenset()


def classer(illus: Illustration, contexte: ContexteTome) -> str:
    """La classe de forme d'une illustration. **Pure : aucun accès disque.**

    L'ordre des tests est la définition. Une vignette est une vignette avant d'être quoi que
    ce soit d'autre — sinon un logo d'éditeur au ratio paysage deviendrait une double page."""
    if not illus.lisible:
        return ILLISIBLE
    mediane = contexte.mediane_surface
    if mediane > 0 and illus.surface <= SEUIL_VIGNETTE * mediane:
        return VIGNETTE
    if contexte.couverture and illus.nom == contexte.couverture:
        return COUVERTURE
    if illus.nom in contexte.sosies_couverture:
        return COUVERTURE
    if illus.ratio > SEUIL_DOUBLE_PAGE:
        return DOUBLE_PAGE
    if mediane > 0 and illus.surface >= SEUIL_PLEINE_PAGE * mediane and illus.ratio < 1.0:
        return PLEINE_PAGE
    return INDETERMINEE


def couverture_candidate(illustrations: list[Illustration], mediane_surface: float) -> str:
    """Le nom du fichier à traiter comme couverture, ou `""`. **Pure.**

    Règle : la première image dans l'ordre naturel des noms qui soit **portrait**, de surface
    **au moins médiane**, et non-vignette.

    ⚠ La règle proposée par le plan — « premier marqueur du volume » — a été mesurée et
    écartée : sur roman D Vol.1 le premier marqueur est `p12`, une pleine page en milieu de
    tome, parce que la couverture `p1` n'est référencée nulle part. Sur roman E, même
    défaut. L'ordre naturel des noms retrouve la couverture dans les deux cas.

    ⚠ Cette règle n'est ni universelle ni infaillible : elle suppose que le nom de fichier
    porte l'ordre de la source, ce qui est vrai des cinq schémas de nommage du corpus
    (`_pN_xM`, `_cover`, `imageN`, `kuchie-NNN`) et peut être faux ailleurs. Un tome qui n'a
    pas de couverture désignée n'est pas cassé — il a une classe `couverture` vide."""
    for illus in sorted(illustrations, key=lambda i: _cle_naturelle(i.nom)):
        if not illus.lisible:
            continue
        if mediane_surface > 0 and illus.surface <= SEUIL_VIGNETTE * mediane_surface:
            continue
        if illus.ratio >= 1.0:
            continue
        if mediane_surface > 0 and illus.surface < mediane_surface:
            continue
        return illus.nom
    return ""


def mediane_surface(illustrations: list[Illustration]) -> float:
    """Surface médiane des images LISIBLES du tome. 0,0 si aucune. **Pure.**"""
    surfaces = [i.surface for i in illustrations if i.lisible]
    return float(statistics.median(surfaces)) if surfaces else 0.0


def contexte_de(illustrations: list[Illustration],
                sosies: frozenset = frozenset()) -> ContexteTome:
    """Le `ContexteTome` déduit d'une liste d'illustrations. **Pure.**

    `sosies` vient de `sosies_de_la_couverture`, qui LIT des pixels : le calcul reste dehors
    pour que cette fonction-ci garde sa pureté, et pour qu'un appelant qui n'a pas besoin de
    la détection (le classement à sec) ne paie pas la lecture."""
    mediane = mediane_surface(illustrations)
    return ContexteTome(mediane_surface=mediane,
                        couverture=couverture_candidate(illustrations, mediane),
                        sosies_couverture=frozenset(sosies))


#: Côté de la vignette servant à comparer deux images. 32 × 32 en niveaux de gris : on cherche
#: à reconnaître LA MÊME image republiée, pas deux images qui se ressemblent, et une réduction
#: brutale suffit à cela tout en absorbant le rééchantillonnage d'un éditeur.
COTE_EMPREINTE = 32

#: Corrélation au-dessus de laquelle deux images sont **la même**.
#:
#: ⚠ **0,70, et le chiffre est posé au milieu d'un vide MESURÉ**, pas au bord d'une des deux
#: populations. Relevé le 2026-08-31 sur six tomes de deux œuvres, en comparant chaque image
#: à la couverture de son tome :
#:
#:   republications de la couverture  0,797 · 0,823 · 0,823 · 0,938 · 1,000 · 1,000
#:   toutes les autres, par tome      0,594 · 0,457 · 0,385 · 0,376 · 0,361 · 0,314
#:
#: Le vide va de **0,594 à 0,797**. Un seuil à 0,80 aurait manqué la republication de la
#: couverture du Vol.2 du tome de référence (0,797) ; un seuil à 0,60 aurait pris la plus
#: proche des non-couvertures. Les deux populations sont publiées avec le seuil, parce qu'un
#: seuil sans ses populations n'est pas une mesure.
#:
#: ⚠ Les deux valeurs à **0,823** sont une PAGE DE TITRE — la même composition délavée,
#: portant le titre et le nom de l'auteur en grandes lettres. Elle est classée `couverture`
#: par ce seuil, et c'est le bon classement pour l'usage qu'on en fait : la repousser en queue
#: des références d'identité évite d'envoyer un titre dans le conditionnement.
SEUIL_SOSIE = 0.70


def empreinte_perceptuelle(source):
    """Une vignette 32 × 32 en niveaux de gris, centrée-réduite. `None` si illisible.

    ⚠ Pas de dépendance nouvelle : `numpy` et Pillow suffisent, et le dépôt refuse OpenCV
    depuis l'interdit n° 4. Ce n'est pas un hachage perceptuel de la littérature — c'est la
    chose la plus simple qui sépare « la même image » de « une autre image », et sa mesure
    est publiée."""
    import numpy as np
    from PIL import Image

    try:
        with _ouvrir(source) as image:
            vignette = image.convert("L").resize((COTE_EMPREINTE, COTE_EMPREINTE),
                                                 Image.BILINEAR)
    except Exception:                                                # noqa: BLE001
        return None
    tableau = np.asarray(vignette, dtype=np.float64).ravel()
    ecart = tableau.std()
    if ecart <= 0:
        return None
    return (tableau - tableau.mean()) / ecart


def correlation(a, b) -> float:
    """Corrélation de deux empreintes centrées-réduites, dans `[-1, 1]`."""
    import numpy as np

    if a is None or b is None or a.shape != b.shape:
        return 0.0
    return float(np.dot(a, b) / a.size)


def sosies_de_la_couverture(illustrations: list[Illustration], couverture: str,
                            *, seuil: float = SEUIL_SOSIE) -> frozenset:
    """Les images qui SONT la couverture, republiées ailleurs dans le volume.

    ⚠ **Ceci corrige un défaut mesuré, et il coûtait cher.** `couverture_candidate` désigne
    la première image de l'ordre naturel — `p1` — et rien d'autre. Or un EPUB republie
    couramment sa couverture en fin de volume : sur le tome de référence, `p208_x1242` **est**
    la couverture du Vol.1, titre, auteur, illustrateur et numéro de tome compris, et le
    classifieur la rangeait en `pleine_page`.

    La conséquence n'était pas cosmétique : le lot 25 repousse les couvertures en queue de la
    sélection de références *précisément* pour ne pas envoyer un titre en grandes lettres dans
    le conditionnement du modèle d'image — et ce mécanisme ne se déclenchait pas sur celle qui
    en avait le plus besoin. Le lot 26 l'a découvert en faisant relire les références par un
    modèle de vision, qui, lui, lisait le titre.

    ⚠ **Ce que cela NE corrige pas** : une page intérieure typographiée qui n'est pas la
    couverture — une page de titre, une page « Afterword », une illustration portant un
    dialogue incrusté. Aucun descripteur de ce module ne lit du texte, et `core/` n'importe
    pas le détecteur de la brique manga. Le dire vaut mieux que de laisser croire le contraire."""
    if not couverture:
        return frozenset()
    par_nom = {i.nom: i for i in illustrations}
    modele = par_nom.get(couverture)
    if modele is None or not modele.lisible:
        return frozenset()
    candidates = [i for i in illustrations
                  if i.nom != couverture and _peut_etre_la_meme(i, modele)]
    if not candidates:
        return frozenset()
    reference = empreinte_perceptuelle(modele.chemin)
    if reference is None:
        return frozenset()
    return frozenset(
        i.nom for i in candidates
        if correlation(reference, empreinte_perceptuelle(i.chemin)) >= seuil)


#: Écart de RATIO toléré entre deux images pour qu'elles puissent être la même. 5 %.
#:
#: ⚠ C'est un pré-filtre de COÛT, pas un critère de décision : il évite de décoder les images
#: qui ne peuvent pas être la couverture. Mesuré le 2026-08-31 sur une œuvre de 98 images :
#: empreindre TOUT coûte **2,55 s**, empreindre les seules candidates de même ratio **1,06 s**.
#: La correction porte sur la republication d'une même image — jamais rognée, souvent
#: seulement réencodée —, donc un écart de ratio de 5 % est déjà généreux.
ECART_RATIO_SOSIE = 0.05


def _peut_etre_la_meme(illus, modele) -> bool:
    """Deux images de ratios très différents ne sont pas la même image republiée."""
    if not illus.lisible or not modele.lisible or modele.ratio <= 0:
        return False
    return abs(illus.ratio - modele.ratio) / modele.ratio <= ECART_RATIO_SOSIE


def exploitable(illus: Illustration) -> bool:
    """Cette illustration peut-elle servir de RÉFÉRENCE (identité ou style) ?

    Les classes utiles, plus toute image de tête de volume — une planche couleur d'ouverture
    est souvent la meilleure référence du tome, et `pipeline/images.py` documente qu'elles
    étaient purement et simplement perdues avant son correctif (« 12 illustrations sur 20 »)."""
    return illus.classe in (COUVERTURE, PLEINE_PAGE, DOUBLE_PAGE) or \
        illus.contexte == TETE_DE_VOLUME


# ────────────────────────────────  Lecture disque  ────────────────────────────────

def _ouvrir(source):
    """`Image.open` avec la limite de pixels levée. Import local : Pillow est une dépendance
    du light novel, mais ce module doit rester importable pour ses fonctions pures.

    `source` est un chemin ou un objet fichier — `Image.open` accepte les deux, et le second
    sert à mesurer une image qui n'est pas encore écrite."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    return Image.open(source)


def _en_rvb(image):
    """`convert("RGB")`, sans l'avertissement Pillow qu'il déclenche sur une image à palette
    porteuse de transparence.

    ⚠ Filtre NOMMÉ et local, jamais un `simplefilter("ignore")` global. Ces images existent
    vraiment dans le corpus — 8 des 164 fichiers de *Pride and Prejudice* Vol.1 — et
    l'avertissement est juste : la transparence est aplatie. Ici, c'est ce qu'on veut, parce
    qu'on mesure un registre graphique et non un rendu. Masquer l'avertissement pour tout le
    processus masquerait aussi celui d'un appelant qui, lui, aurait tort de l'ignorer."""
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*Palette images with Transparency.*")
        return image.convert("RGB")


def _mesures_de_couleur(chemin: Path) -> tuple[int, bool]:
    """(nombre de teintes dominantes, image en couleur ?) — sur une vignette d'analyse.

    La quantification est grossière et assumée : 8 niveaux par canal, soit 512 cases. On ne
    cherche pas une palette exacte, on cherche à distinguer un aplat bicolore d'un dessin."""
    import numpy as np
    with _ouvrir(chemin) as im:
        im = _en_rvb(im)
        im.thumbnail((COTE_ANALYSE, COTE_ANALYSE))
        arr = np.asarray(im, dtype=np.uint8)
    reduit = (arr // 32).astype(np.int32)
    codes = (reduit[..., 0] * 64 + reduit[..., 1] * 8 + reduit[..., 2]).ravel()
    comptes = np.bincount(codes, minlength=512)
    dominantes = int((comptes >= SEUIL_DOMINANTE * codes.size).sum())
    ecart = arr.max(axis=2).astype(np.int16) - arr.min(axis=2).astype(np.int16)
    return dominantes, bool(float(ecart.mean()) > 8.0)


def inventaire(tome: Path, *, avec_couleurs: bool = True) -> list[Illustration]:
    """Toutes les images de `<tome>/media/`, classées.

    `avec_couleurs=False` saute la lecture des pixels : seules les dimensions sont lues (via
    l'en-tête du fichier, sans décoder l'image), ce qui suffit au classement. Le défaut est
    `True` parce que la signature de style en a besoin et que le surcoût est mesuré à
    ~15 ms par image.

    Une image illisible n'interrompt rien : elle entre dans l'inventaire en classe
    `ILLISIBLE`, avec ses dimensions à zéro. Un dossier `media/` absent rend une liste vide."""
    dossier = Path(tome) / "media"
    if not dossier.is_dir():
        return []
    brut: list[Illustration] = []
    for fichier in sorted(dossier.iterdir(), key=lambda p: _cle_naturelle(p.name)):
        if not fichier.is_file():
            continue
        try:
            octets = fichier.stat().st_size
        except OSError:
            octets = 0
        try:
            with _ouvrir(fichier) as im:
                largeur, hauteur = im.size
        except Exception:                                            # noqa: BLE001
            brut.append(Illustration(fichier, fichier.name, 0, 0, octets, classe=ILLISIBLE))
            continue
        dominantes = couleur = None
        if avec_couleurs:
            try:
                dominantes, couleur = _mesures_de_couleur(fichier)
            except Exception:                                        # noqa: BLE001
                dominantes = couleur = None
        brut.append(Illustration(fichier, fichier.name, largeur, hauteur, octets,
                                 couleurs_dominantes=dominantes, couleur=couleur))
    contexte = contexte_de(brut)
    if contexte.couverture:
        # ⚠ **Toujours, y compris en `avec_couleurs=False`**, et c'est un arbitrage assumé.
        # La détection a d'abord été adossée à ce drapeau, par souci de coût — et le résultat
        # était une CLASSIFICATION QUI DÉPEND DE LA VITESSE : `inventaire` disait
        # `couverture` là où `identite.classes_du_projet`, qui classe à sec, disait
        # `pleine_page`. Deux réponses à la même question, c'est une de trop — c'est la règle
        # que le dépôt s'est déjà donnée pour la résolution des références.
        #
        # Le coût est mesuré, et il est publié plutôt qu'estimé : sur une œuvre de 98
        # images, le classement à sec passe de **0,03 s à 1,09 s**. C'est cher en relatif et
        # petit en absolu — l'inventaire complet avec mesure de couleur en coûte 6,23, une
        # génération d'image en coûte cent fois plus, et `identite._CLASSES` met le résultat
        # en cache pour tout le run.
        contexte = contexte_de(brut, sosies_de_la_couverture(brut, contexte.couverture))
    return [replace(i, classe=classer(i, contexte)) for i in brut]


def inventaire_projet(racine_projet, *, avec_couleurs: bool = True) -> list:
    """Toutes les illustrations de TOUS les tomes d'une œuvre, dans l'ordre des tomes.

    ⚠ **Une œuvre n'est pas un tome, et c'est la brique d'illustration qui l'a rendu
    évident.** Les références d'un personnage vivent où l'éditeur les a mises : sur le tome de
    référence, 7 des 10 références validées sont dans le Vol.2. Un atelier qui n'inventorierait
    que le tome courant ne verrait qu'une fraction de ce dont il dispose — sur `roman N`,
    23 illustrations exploitables sur les 80 de l'œuvre.

    ⚠ **Chaque illustration reste classée DANS SON TOME.** Les seuils de `classer` sont tous
    relatifs — la surface médiane du tome, sa dynamique de luminance — et les mélanger ferait
    juger une vignette d'un tome à l'aune de la médiane d'un autre. On concatène des
    classements, on ne classe pas un mélange.

    ⚠ **Le nom du tome est porté par le chemin, pas par le nom de fichier.** Sur `roman N`,
    les Vol.1 et Vol.2 ont tous deux un `image1` : c'est `Illustration.chemin` qui les
    distingue, et c'est pourquoi les références s'écrivent désormais `<Tome>/media/<nom>`."""
    racine = Path(racine_projet)
    if not racine.is_dir():
        return []
    sortie: list = []
    for tome in sorted(t for t in racine.iterdir() if t.is_dir()):
        sortie.extend(inventaire_rattache(tome, avec_couleurs=avec_couleurs))
    return sortie


def relatif_au_projet(illus, racine_projet) -> str:
    """`<Tome>/media/<nom>` — la forme sous laquelle une référence s'écrit dans la bible.

    ⚠ Elle porte son TOME depuis le 2026-08-31. `media/<nom>` seul était AMBIGU sur une œuvre
    à plusieurs volumes, et `core/bible.py:reference_existe` acceptait « n'importe quel tome
    du projet » : le premier gagnait, en silence."""
    try:
        return Path(illus.chemin).resolve().relative_to(
            Path(racine_projet).resolve()).as_posix()
    except ValueError:
        return f"media/{illus.nom}"


# ───────────────────────────  Rattachement aux chapitres  ──────────────────────────

class _Chapitre:
    """Le minimum que `pipeline.images.orphan_markers` attend d'un chapitre : un `.body`."""

    __slots__ = ("body",)

    def __init__(self, body: str):
        self.body = body


def _md_complet(tome: Path) -> Path | None:
    """Le Markdown du tome entier, `<Projet>_<Tome>.md`. `None` si le tome n'a pas de rendu —
    trois tomes du corpus sont dans ce cas (`roman I` Vol.1, `roman K` Vol.1, `roman L`
    Vol.1 au 2026-08-29) : ils ont des images extraites et aucun texte produit."""
    tome = Path(tome)
    candidats = [p for p in tome.glob("*.md") if p.name != "RAPPORT.md"]
    return candidats[0] if candidats else None


def rattacher(tome: Path) -> dict[str, list[Illustration]]:
    """Les illustrations du tome, rangées par CONTEXTE de position.

    Clés : `ch01`, `ch02`… pour les images posées dans un chapitre ; `TETE_DE_VOLUME` pour
    les orphelines (celles qui précèdent la première frontière de chapitre — les planches
    couleur d'ouverture) ; `NON_REFERENCEE` pour les fichiers de `media/` qu'aucun marqueur
    ne cite.

    ⚠ **Aucun second parseur de marqueurs n'est écrit ici.** `core.marqueurs` porte le
    contrat du format — `MARQUEUR_RE`, `split_marker`, `manifest_for_chapter`,
    `orphan_markers` — et c'est lui qui répond ; la position fractionnaire vient de
    `manifest_for_chapter` telle quelle.

    ⚠ Ce module vivait dans `pipeline/` avant le lot 23. Le `PLAN-23` L23.1 demandait de
    « réutiliser l'existant » depuis `core/`, ce que la règle de couche du dépôt interdit :
    `core/` ne peut pas importer `pipeline/`. Déplacer le contrat partagé dans le socle est
    la seule sortie qui tienne les deux — voir l'en-tête de `core/marqueurs.py`."""
    tome = Path(tome)
    illus = {i.nom: i for i in inventaire(tome, avec_couleurs=False)}
    sortie: dict[str, list[Illustration]] = {}
    vus: set[str] = set()

    def _nom_de(brut: str) -> str:
        chemin, _ = split_marker(brut)
        return Path(chemin.strip()).name

    chapitres: list[_Chapitre] = []
    dossier_ch = tome / "chapters"
    for fichier in sorted(dossier_ch.glob("ch*.md")) if dossier_ch.is_dir() else []:
        corps = fichier.read_text(encoding="utf-8", errors="replace")
        chapitres.append(_Chapitre(corps))
        for fraction, brut in manifest_for_chapter(corps):
            nom = _nom_de(brut)
            image = illus.get(nom)
            if image is None:
                continue
            vus.add(nom)
            sortie.setdefault(fichier.stem, []).append(
                replace(image, contexte=f"{fichier.stem}@{fraction:.2f}"))

    complet = _md_complet(tome)
    if complet is not None:
        texte = complet.read_text(encoding="utf-8", errors="replace")
        for brut in orphan_markers(texte, chapitres):
            nom = _nom_de(brut)
            image = illus.get(nom)
            if image is None or nom in vus:
                continue
            vus.add(nom)
            sortie.setdefault(TETE_DE_VOLUME, []).append(
                replace(image, contexte=TETE_DE_VOLUME))

    for nom, image in illus.items():
        if nom not in vus:
            sortie.setdefault(NON_REFERENCEE, []).append(
                replace(image, contexte=NON_REFERENCEE))
    return sortie


def inventaire_rattache(tome: Path, *, avec_couleurs: bool = True) -> list[Illustration]:
    """L'inventaire complet, chaque illustration portant SA classe **et** son contexte.

    C'est la vue dont l'outil et la bible se servent : `classer` dit la forme, `rattacher`
    dit la place, et une décision d'exploitation a besoin des deux."""
    complet = inventaire(tome, avec_couleurs=avec_couleurs)
    contextes: dict[str, str] = {}
    for images in rattacher(tome).values():
        for image in images:
            contextes.setdefault(image.nom, image.contexte)
    return [replace(i, contexte=contextes.get(i.nom, "")) for i in complet]


# ─────────────────────────  L23.7 — la signature de style  ─────────────────────────

#: Descripteurs scalaires de la signature, dans l'ordre où ils sont publiés.
DESCRIPTEURS = ("saturation_moyenne", "contraste", "densite_trait", "part_aplats")

#: Part de la dynamique de luminance de l'image au-dessus de laquelle un gradient compte
#: comme un contour. **Relatif à l'image, jamais absolu** — un seuil en niveaux de gris
#: classerait une planche pâle comme « sans trait ».
SEUIL_TRAIT = 0.10

#: Part de la dynamique au-dessous de laquelle le voisinage d'un pixel est un aplat. La
#: notion est celle de l'**uniformité de fond** de `manga/clean.py`, déjà calibrée sur
#: 797 bulles (médiane 0,892) ; le seuil est ici bien plus serré parce qu'on mesure une
#: planche entière et non l'intérieur d'une bulle.
SEUIL_APLAT = 0.02

#: Nombre de teintes publiées dans la palette dominante d'un tome.
TAILLE_PALETTE = 5


def _descripteurs_image(source) -> dict | None:
    """Les descripteurs déterministes d'UNE image, ou `None` si elle est illisible.

    `source` est un chemin ou un objet fichier — cf. `descripteurs`."""
    import numpy as np
    try:
        with _ouvrir(source) as im:
            im = _en_rvb(im)
            im.thumbnail((COTE_ANALYSE, COTE_ANALYSE))
            arr = np.asarray(im, dtype=np.float32) / 255.0
    except Exception:                                                # noqa: BLE001
        return None
    if arr.size == 0 or min(arr.shape[:2]) < 3:
        return None

    maxi = arr.max(axis=2)
    mini = arr.min(axis=2)
    # Saturation HSV : (max - min) / max, indéfinie sur le noir pur — mise à zéro.
    saturation = np.divide(maxi - mini, maxi, out=np.zeros_like(maxi), where=maxi > 0)
    lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    dynamique = float(lum.max() - lum.min())

    if dynamique <= 0:                     # image d'une seule luminance : ni trait ni relief
        trait = aplats = 0.0
        contraste = 0.0
    else:
        contraste = float(lum.std())
        gx = np.abs(np.diff(lum, axis=1, prepend=lum[:, :1]))
        gy = np.abs(np.diff(lum, axis=0, prepend=lum[:1, :]))
        gradient = np.maximum(gx, gy)
        trait = float((gradient > SEUIL_TRAIT * dynamique).mean())
        # Étendue locale sur les quatre voisins : max - min du voisinage immédiat. Assez
        # pour séparer un aplat d'un dégradé, et sans filtre morphologique (interdit n° 4).
        voisins = np.stack([
            np.roll(lum, 1, axis=0), np.roll(lum, -1, axis=0),
            np.roll(lum, 1, axis=1), np.roll(lum, -1, axis=1), lum,
        ])
        etendue = voisins.max(axis=0) - voisins.min(axis=0)
        aplats = float((etendue < SEUIL_APLAT * dynamique).mean())

    reduit = (arr * 255).astype(np.uint8) // 32
    codes = (reduit[..., 0].astype(np.int32) * 64
             + reduit[..., 1] * 8 + reduit[..., 2]).ravel()
    return {
        "saturation_moyenne": float(saturation.mean()),
        "contraste": contraste,
        "densite_trait": trait,
        "part_aplats": aplats,
        "couleur": bool(float((maxi - mini).mean()) > 8.0 / 255.0),
        "_codes": np.bincount(codes, minlength=512),
        "_pixels": int(codes.size),
    }


def descripteurs(source) -> dict | None:
    """Les descripteurs déterministes d'UNE image quelconque, sous la forme d'une signature.

    Même bloc que `signature`, mais pour un seul fichier et **sans palette** : `echantillon`
    vaut 1, et c'est le dénominateur qu'il faut lire. Rend `None` si l'image est illisible.

    ⚠ Elle existe pour que le `PLAN-25` puisse comparer une image GÉNÉRÉE à la signature du
    tome avec exactement les mêmes règles que celles qui ont produit cette signature. Passer
    par une seconde implémentation aurait rendu les deux nombres incomparables — c'est le
    défaut de la « seconde règle de résolution des références », trouvé le 2026-08-29.

    ⚠ `source` peut être un chemin **ou un objet fichier** (`BytesIO`). C'est ce qui permet de
    juger une image AVANT de l'écrire : le `PLAN-25` demande qu'une image trop proche de sa
    référence soit *rejetée*, et rejeter un fichier déjà posé sur le disque n'est pas la même
    chose que ne pas l'écrire.
    """
    mesures = _descripteurs_image(source)
    if not mesures:
        return None
    return {"palette": [], **{d: round(float(mesures[d]), 4) for d in DESCRIPTEURS},
            "couleur": bool(mesures["couleur"]), "echantillon": 1}


def _hex_de_code(code: int) -> str:
    """Teinte représentative d'une case de la quantification 8×8×8 : son CENTRE."""
    r, g, b = code // 64, (code // 8) % 8, code % 8
    return "#%02x%02x%02x" % (r * 32 + 16, g * 32 + 16, b * 32 + 16)


def signature(illustrations: list[Illustration]) -> dict:
    """La signature de style d'un tome, mesurée sur ses illustrations **exploitables**.

    Rend exactement le bloc `style.signature` de `bible.yaml`, `echantillon` compris.

    ⚠ **`echantillon` n'est pas décoratif, il est la mesure.** Une signature calculée sur
    3 images et une calculée sur 30 ne valent pas la même chose, et rien dans les nombres ne
    le dit — c'est la règle des chiffres du dépôt, transposée : un descripteur sans son
    dénominateur est une impression.

    ⚠ **Ce module ne fait rien de cette signature.** Il la mesure et l'écrit. Lui donner une
    échelle est l'affaire du `PLAN-25`, la consommer celle du `PLAN-26`."""
    import numpy as np
    retenues = [i for i in illustrations if exploitable(i)]
    mesures = [m for m in (_descripteurs_image(i.chemin) for i in retenues) if m]
    if not mesures:
        return {"palette": [], "saturation_moyenne": None, "contraste": None,
                "densite_trait": None, "part_aplats": None, "couleur": None,
                "echantillon": 0}

    total = np.zeros(512, dtype=np.int64)
    pixels = 0
    for m in mesures:
        total += m["_codes"]
        pixels += m["_pixels"]
    ordre = np.argsort(total)[::-1][:TAILLE_PALETTE]
    palette = [{"hex": _hex_de_code(int(c)), "part": round(float(total[c]) / pixels, 4)}
               for c in ordre if total[c] > 0]

    return {
        "palette": palette,
        **{d: round(float(statistics.mean(m[d] for m in mesures)), 4)
           for d in DESCRIPTEURS},
        # Un tome est « en couleur » si la MAJORITÉ de ses illustrations le sont : une seule
        # planche couleur au milieu de quinze planches au trait ne fait pas un tome couleur.
        "couleur": sum(1 for m in mesures if m["couleur"]) * 2 > len(mesures),
        "echantillon": len(mesures),
    }


def ecart_signature(a: dict, b: dict) -> dict:
    """Écart descripteur par descripteur entre deux signatures, plus une moyenne.

    ⚠ **Cet écart n'a pas encore d'échelle — au 2026-09-02.** Il dit que deux tomes diffèrent
    de 0,08 sur la densité de trait ; il ne dit pas si 0,08 est beaucoup. Poser cette échelle est l'étape 0.2
    du `PLAN-25`, et publier l'écart brut sans prétendre le juger est la bonne façon de le
    lui préparer."""
    sortie: dict = {}
    valeurs: list[float] = []
    for d in DESCRIPTEURS:
        va, vb = a.get(d), b.get(d)
        if va is None or vb is None:
            sortie[d] = None
            continue
        sortie[d] = round(abs(float(va) - float(vb)), 4)
        valeurs.append(sortie[d])
    sortie["moyenne"] = round(sum(valeurs) / len(valeurs), 4) if valeurs else None
    sortie["meme_regime_couleur"] = (a.get("couleur") == b.get("couleur"))
    sortie["echantillons"] = [a.get("echantillon"), b.get("echantillon")]
    return sortie


def ancrages_proposes(illustrations: list[Illustration], nombre: int = 3) -> list[dict]:
    """Les illustrations les plus REPRÉSENTATIVES du registre du tome, à faire valider.

    Le déterministe propose : celles dont les descripteurs sont les plus proches du centre de
    la distribution du tome. L'humain confirme — et c'est la règle, pas une politesse. Une
    couverture porte un logo d'éditeur et un bandeau de prix ; aucun descripteur ne le sait,
    et elle ferait une mauvaise ancre.

    ⚠ Le `PLAN-26` étape 0.2 impose en plus de **préférer des ancres sans visage** : une
    ancre de style qui montre un personnage contamine l'identité de l'image générée. Ce
    module ne sait pas voir un visage et ne cherche pas à l'apprendre — la préférence est
    donc laissée au geste humain, et cette limite est écrite plutôt que masquée."""
    retenues = [i for i in illustrations if exploitable(i)]
    couples = [(i, m) for i, m in ((i, _descripteurs_image(i.chemin)) for i in retenues) if m]
    if not couples:
        return []
    centre = {d: statistics.mean(m[d] for _, m in couples) for d in DESCRIPTEURS}
    etendues = {d: (max(m[d] for _, m in couples) - min(m[d] for _, m in couples)) or 1.0
                for d in DESCRIPTEURS}

    def _distance(m: dict) -> float:
        return sum(abs(m[d] - centre[d]) / etendues[d] for d in DESCRIPTEURS)

    couples.sort(key=lambda c: (_distance(c[1]), _cle_naturelle(c[0].nom)))
    return [{
        "fichier": f"media/{i.nom}",
        "classe": i.contexte if i.contexte == TETE_DE_VOLUME else i.classe,
        "motif": f"écart au centre du tome : {_distance(m):.3f} sur "
                 f"{len(DESCRIPTEURS)} descripteurs",
        "valide_par_humain": False,
    } for i, m in couples[:max(0, nombre)]]


# ─────────────────────  Le cadre proposé, L29.1 — un rectangle, pas un visage  ─────────────────────

#: Les cadrages que le gabarit d'image sait écrire, et pour lesquels un rectangle se propose.
#: Ce sont les mêmes noms que `illustration/gabarits/portrait.yaml:cadrages` — deux
#: vocabulaires pour la même notion divergeraient au premier ajout.
CADRAGES_PROPOSES = ("visage", "buste", "pied")

#: Part de la MASSE d'encre rognée de chaque côté avant de fermer la boîte. 2 %.
#:
#: ⚠ Ce n'est pas une marge de confort, c'est ce qui rend la boîte robuste : un scan porte des
#: poussières, un liseré de reliure et parfois un numéro de page, tous à gradient fort et tous
#: aux bords. Une boîte fermée sur le PREMIER pixel d'encre les inclurait et rendrait la page
#: entière. Fermer sur 98 % de la masse les laisse dehors sans jeter de dessin — la queue de
#: distribution d'une illustration au trait est plate, celle d'une poussière ne l'est pas.
MARGE_ENCRE = 0.02

#: Part de la boîte d'encre que chaque cadrage retient, en hauteur, depuis le HAUT.
#:
#: ⚠ **Ces trois fractions sont POSÉES, pas mesurées, et c'est le point à contester.** Elles
#: encodent une hypothèse — « le haut de la masse d'encre est la tête » — qui est vraie d'une
#: figure debout et fausse d'un plan de trois quarts, d'une figure couchée ou d'une planche à
#: deux personnages. Aucun descripteur de ce module ne sait voir un visage, et le `PLAN-29`
#: L29.1 l'interdit explicitement : « pas de détection de visage, pas d'OpenCV ; un rectangle
#: proposé, un rectangle corrigé ». La proposition est donc un point de départ pour l'œil, et
#: `motif` dit à l'humain, en toutes lettres, sur quoi elle repose.
PARTS_CADRAGE = {"visage": 0.30, "buste": 0.55, "pied": 1.00}


def boite_d_encre(source) -> tuple | None:
    """La boîte englobante du DESSIN dans une image, en fractions `[x, y, largeur, hauteur]`.

    Rend `None` si l'image est illisible ou d'une seule luminance (rien à encadrer).

    ## Ce qui est mesuré, exactement

    Le même gradient que `densite_trait` — `SEUIL_TRAIT` fois la dynamique de l'image, donc
    **relatif à l'image et jamais absolu**, sans quoi une page pâle n'aurait « pas de trait ».
    On en tire deux profils, par ligne et par colonne, et on ferme la boîte sur `MARGE_ENCRE`
    de la masse à chaque bord.

    ⚠ **Ce n'est pas un détecteur de personnage.** C'est « où y a-t-il de l'encre », rien de
    plus : sur une planche à deux figures, la boîte les contient toutes les deux ; sur une
    page de texte, elle contient le texte. Le nom du concept est choisi pour ne pas promettre
    davantage — et c'est exactement pour cela que le `PLAN-29` fait corriger le rectangle par
    un humain plutôt que de le retenir tel quel."""
    import numpy as np
    try:
        with _ouvrir(source) as im:
            im = _en_rvb(im)
            im.thumbnail((COTE_ANALYSE, COTE_ANALYSE))
            arr = np.asarray(im, dtype=np.float32) / 255.0
    except Exception:                                                # noqa: BLE001
        return None
    if arr.size == 0 or min(arr.shape[:2]) < 3:
        return None

    lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    dynamique = float(lum.max() - lum.min())
    if dynamique <= 0:
        return None
    gx = np.abs(np.diff(lum, axis=1, prepend=lum[:, :1]))
    gy = np.abs(np.diff(lum, axis=0, prepend=lum[:1, :]))
    encre = (np.maximum(gx, gy) > SEUIL_TRAIT * dynamique).astype(np.float64)
    if encre.sum() <= 0:
        return None

    haut, bas = _bornes(encre.sum(axis=1))          # profil par LIGNE   → bornes verticales
    gauche, droite = _bornes(encre.sum(axis=0))     # profil par COLONNE → bornes horizontales
    hauteur, largeur = encre.shape
    return (gauche / largeur, haut / hauteur,
            (droite - gauche) / largeur, (bas - haut) / hauteur)


def _bornes(profil) -> tuple:
    """Les deux indices entre lesquels se tient `1 - 2 × MARGE_ENCRE` de la masse du profil.

    La borne haute est **exclusive** (comme une tranche Python), et la boîte est donc large
    d'au moins un pixel même quand toute la masse tient sur une seule ligne."""
    import numpy as np
    cumul = np.cumsum(profil)
    total = float(cumul[-1])
    debut = int(np.searchsorted(cumul, total * MARGE_ENCRE, side="left"))
    fin = int(np.searchsorted(cumul, total * (1.0 - MARGE_ENCRE), side="left"))
    return debut, max(fin + 1, debut + 1)


def cadre_propose(source, cadrage: str = "buste") -> dict | None:
    """Le rectangle à PROPOSER pour recadrer une référence d'identité, et son motif.

    Rend `{"cadre": [x, y, l, h], "motif": "…", "part_de_la_page": …}` — les quatre fractions
    du champ `cadre` de `core/bible.py`, prêtes à être écrites telles quelles —, ou `None` si
    l'image ne se mesure pas.

    ⚠ **Le motif dit ce sur quoi le rectangle repose, y compris son hypothèse fausse.** C'est
    la doctrine des motifs nommés du dépôt (`manga/detection_retry.py`), et elle compte
    doublement ici : l'humain qui corrige le rectangle ne peut le faire à bon escient que s'il
    sait que « visage » veut dire « le tiers supérieur de l'encre » et non « le visage ».

    ⚠ **Rien n'est écrit sur le disque, et aucune image n'est recadrée.** Cette fonction rend
    quatre nombres ; c'est `illustration/identite.py:preparer` qui recadre, et seulement après
    qu'un humain a validé le champ."""
    if cadrage not in PARTS_CADRAGE:
        raise ValueError(
            f"cadrage « {cadrage} » inconnu — {', '.join(CADRAGES_PROPOSES)}. "
            f"Ce sont les noms du gabarit d'image ; deux vocabulaires pour la même notion "
            f"divergeraient au premier ajout.")
    boite = boite_d_encre(source)
    if boite is None:
        return None
    x, y, largeur, hauteur = boite
    part = PARTS_CADRAGE[cadrage]
    retenue = max(hauteur * part, 1e-4)
    return {
        "cadre": [round(x, 4), round(y, 4), round(largeur, 4), round(retenue, 4)],
        "part_de_la_page": round(largeur * retenue, 4),
        "motif": (f"boîte d'encre {largeur:.0%}×{hauteur:.0%} de la page, puis les "
                  f"{part:.0%} SUPÉRIEURS pour « {cadrage} » — hypothèse : le haut de "
                  f"l'encre est la tête. À corriger à l'œil."),
    }
