# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Écriture de fichiers **PSD** en Python pur — un calque par bulle, pour retoucher une
planche à la main dans Photoshop.

## Pourquoi écrire le format à la main

`manga.rendu.formats` ne produisait que des sorties **aplaties** (`images`, `cbz`, `pdf`) :
corriger une réplique imposait de relancer le pipeline, et rien ne permettait de déplacer un
bloc de texte de trois pixels. Or `typeset._draw_fit` construisait déjà, par bulle, exactement
ce qu'un calque demande — un calque RGBA, un rectangle, une transparence — puis l'aplatissait
et le jetait.

Aucune dépendance ajoutée. `psd-tools` est orienté LECTURE (son écriture est marginale) et
`pytoshop` n'est plus maintenu ; le format, lui, est documenté et se sérialise avec `struct` et
`zlib` de la bibliothèque standard. C'est la même logique que `requirements-manga.txt`, qui
refuse OpenCV (~60 Mo) pour trois opérations de morphologie.

## Structure produite

Les calques sont stockés **du bas vers le haut** :

    Planche originale     le scan, masqué par défaut — pour comparer
    Planche nettoyée      bulles vidées : le fond sur lequel on relettre
    Texte 01 … Texte NN   une bulle par calque, nommée avec sa réplique

## Calque de type ou calque rasterisé

Un calque de **type** (`TySh`) porte la police, le corps, la couleur et la chaîne : Photoshop
l'ouvre avec l'outil Texte, on double-clique et on réécrit. Un calque **rasterisé** ne porte que
des pixels : déplaçable, redimensionnable, effaçable, mais pas réécrivable.

⚠ Ce qui est vérifié et ce qui ne l'est pas. Deux niveaux : `tests/test_manga_psd.py` analyse la
structure avec un analyseur maison (en-tête, calques, rectangles, canaux) et compare le composite
**pixel par pixel** à la planche aplatie ; `tests/test_manga_psd_relecture.py` relit le fichier
avec **`psd-tools`**, un lecteur tiers, et vérifie que les calques ressortent en `type` avec leur
texte, leur police et leurs paragraphes.

Ce second niveau n'est pas un luxe : la version 0.18.0 ne l'avait pas, et son analyseur maison —
écrit à partir de la même lecture de la spécification que l'écrivain — a validé pendant tout un
tome un descripteur mal formé (identifiant de classe manquant, cf. `_descripteur`). Photoshop, lui,
refusait chaque `TySh` et retombait sur les pixels. **Un écrivain de format binaire ne se valide
pas contre lui-même.**

Le risque résiduel reste borné par le format : un calque de type contient **aussi** ses pixels
(c'est ainsi que Photoshop l'écrit, pour que les autres lecteurs voient quelque chose). Si un
`TySh` était refusé, le calque se comporterait comme un rasterisé — on ne perdrait que la
réécriture au clavier. Et `manga.rendu.psd_texte: "rasterise"` coupe les calques de type sans rien
changer d'autre.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIGNATURE = b"8BPS"
# 0 = brut, 1 = RLE (PackBits), 2 = ZIP sans prédiction, 3 = ZIP avec prédiction.
# Les calques sont en ZIP (zlib de la bibliothèque standard, un appel par canal) ; le
# **composite** est en RLE, la seule compression que tous les lecteurs acceptent à cet endroit.
COMPRESSION_ZIP = 2
COMPRESSION_RLE = 1

CANAL_ALPHA = -1


# --------------------------------------------------------------------------- #
# Primitives binaires
# --------------------------------------------------------------------------- #

def _u16(v: int) -> bytes:
    return struct.pack(">H", v)


def _u32(v: int) -> bytes:
    return struct.pack(">I", v)


def _i16(v: int) -> bytes:
    return struct.pack(">h", v)


def _i32(v: int) -> bytes:
    return struct.pack(">i", v)


def _f64(v: float) -> bytes:
    return struct.pack(">d", v)


def _pad(donnees: bytes, multiple: int) -> bytes:
    reste = len(donnees) % multiple
    return donnees if reste == 0 else donnees + b"\x00" * (multiple - reste)


def _pascal(texte: str, multiple: int = 4) -> bytes:
    """Chaîne Pascal (longueur sur 1 octet), complétée à un multiple donné. Le nom de calque
    « historique » est en latin-1 ; l'Unicode passe par le bloc `luni`."""
    brut = texte.encode("latin-1", errors="replace")[:255]
    return _pad(bytes([len(brut)]) + brut, multiple)


def _unicode_str(texte: str) -> bytes:
    """Chaîne Unicode Photoshop : nombre de caractères sur 4 octets, puis UTF-16BE."""
    return _u32(len(texte)) + texte.encode("utf-16-be")


def _cle_bloc(cle: bytes, donnees: bytes) -> bytes:
    """Bloc d'information additionnelle de calque : `8BIM` + clé + longueur + données.

    La longueur déclarée est celle APRÈS arrondi au multiple de 2, comme le veut le format : un
    lecteur qui consomme la longueur BRUTE repart un octet trop tôt sur des données de taille
    impaire et manque le `8BIM` suivant. Les `TySh` produits tombent aujourd'hui sur des tailles
    paires — le bug attendait une `EngineData` impaire."""
    corps = _pad(donnees, 2)
    return b"8BIM" + cle + _u32(len(corps)) + corps


# --------------------------------------------------------------------------- #
# PackBits (RLE) — pour le composite
# --------------------------------------------------------------------------- #

def packbits(donnees: bytes) -> bytes:
    """Compression PackBits d'une ligne, telle que le PSD l'attend.

    Implémentation assistée par numpy : les frontières de plages sont trouvées d'un coup
    (`a[1:] != a[:-1]`) et la boucle Python ne parcourt que les **plages**, pas les octets. Sur
    du trait de manga — de larges aplats de blanc — une ligne de 1125 px en compte quelques
    dizaines. Une boucle par octet aurait coûté des minutes par tome."""
    a = np.frombuffer(donnees, dtype=np.uint8)
    n = a.size
    if n == 0:
        return b""
    debuts = np.concatenate(([0], np.flatnonzero(a[1:] != a[:-1]) + 1))
    longueurs = np.diff(np.concatenate((debuts, [n])))

    sortie = bytearray()
    litteral = bytearray()

    def vider_litteral() -> None:
        i = 0
        while i < len(litteral):
            bloc = litteral[i:i + 128]
            sortie.append(len(bloc) - 1)
            sortie.extend(bloc)
            i += 128

    for debut, longueur in zip(debuts.tolist(), longueurs.tolist()):
        octet = int(a[debut])
        reste = longueur
        if reste >= 3:
            vider_litteral()
            litteral.clear()
        while reste >= 3:
            pris = min(reste, 128)
            # ⚠ Un bloc RLE compte au moins 3 octets. Découper 129 en 128 + 1 laisserait un
            # reliquat de 1, dont l'en-tête `257 - 1` vaut 256 — pas un octet. On rogne donc
            # le bloc pour que le reliquat soit nul ou ≥ 3.
            if 0 < reste - pris < 3:
                pris = reste - 3
            sortie.append(257 - pris)       # -(pris-1) en complément à deux sur 8 bits
            sortie.append(octet)
            reste -= pris
        if reste:                            # 1 ou 2 octets : en littéral
            litteral.extend([octet] * reste)
    vider_litteral()
    return bytes(sortie)


def _canal_rle(plan: np.ndarray) -> tuple[bytes, bytes]:
    """`(table des longueurs de ligne, données)` d'un canal compressé en RLE."""
    lignes = [packbits(plan[y].tobytes()) for y in range(plan.shape[0])]
    return b"".join(_u16(len(ligne)) for ligne in lignes), b"".join(lignes)


# --------------------------------------------------------------------------- #
# Calques
# --------------------------------------------------------------------------- #

@dataclass
class Calque:
    """Un calque prêt à sérialiser.

    `rgba` est un tableau `(h, w, 4)` en uint8 ; `rect` son coin supérieur gauche dans la page.
    Un calque de pleine page a un rect de la taille de la page — mais les calques de texte sont
    bornés à leur bulle, et c'est ce qui garde un PSD de planche autour de 4 Mo au lieu de 25."""
    nom: str
    rgba: np.ndarray
    x: int
    y: int
    visible: bool = True
    texte: dict | None = None          # paramètres du calque de TYPE, ou None (rasterisé)

    @property
    def rect(self) -> tuple[int, int, int, int]:
        h, w = self.rgba.shape[:2]
        return self.y, self.x, self.y + h, self.x + w


def _canaux_zip(rgba: np.ndarray) -> list[bytes]:
    """Données des quatre canaux (A, R, V, B) en ZIP sans prédiction, dans l'ordre où le
    format les attend : l'alpha (identifiant −1) **avant** les couleurs."""
    ordre = [3, 0, 1, 2]
    return [_u16(COMPRESSION_ZIP) + zlib.compress(np.ascontiguousarray(rgba[:, :, i]).tobytes())
            for i in ordre]


def _enregistrement_calque(calque: Calque, donnees_canaux: list[bytes]) -> bytes:
    top, left, bottom, right = calque.rect
    out = bytearray()
    out += _i32(top) + _i32(left) + _i32(bottom) + _i32(right)
    out += _u16(4)
    for ident, donnees in zip([CANAL_ALPHA, 0, 1, 2], donnees_canaux):
        out += _i16(ident) + _u32(len(donnees))
    out += b"8BIM" + b"norm"
    # opacité, écrêtage, drapeaux (bit 1 = calque MASQUÉ), remplissage
    out += bytes([255, 0, 0 if calque.visible else 0x02, 0])

    extra = bytearray()
    extra += _u32(0)                       # données de masque de calque : aucune
    extra += _u32(0)                       # plages de fusion : aucune
    extra += _pascal(calque.nom)
    # `luni` : le nom en Unicode. Sans lui, « Texte 03 — « Où ça ? » » perdrait ses accents,
    # le nom historique étant en latin-1.
    extra += _cle_bloc(b"luni", _unicode_str(calque.nom))
    if calque.texte is not None:
        extra += _cle_bloc(b"TySh", _tysh(calque.texte))
    out += _u32(len(extra))
    out += bytes(extra)
    return bytes(out)


# --------------------------------------------------------------------------- #
# Calque de TYPE : descripteurs et EngineData
# --------------------------------------------------------------------------- #

def _descripteur(items: list[tuple[bytes, bytes]], classe: str = "",
                 classe_id: bytes = b"null") -> bytes:
    """Descripteur Photoshop : nom de classe Unicode, identifiant de classe, puis les items.
    Chaque item est `(clé, valeur_déjà_sérialisée_avec_son_type)`.

    ⚠ L'identifiant de classe fait TOUJOURS 4 octets quand sa longueur déclarée vaut 0 — c'est
    la convention du format, pas une absence. L'omettre décalait la lecture de 4 octets :
    Photoshop prenait le NOMBRE D'ITEMS pour l'identifiant, lisait ensuite « 0 item », et le
    descripteur de texte ressortait vide — ni `Txt `, ni `bounds`, ni `EngineData`. D'où
    « Problèmes à la lecture des calques […] utiliseront les données de pixel existantes » : le
    calque était bien de type, mais son `TySh` était illisible et Photoshop retombait sur les
    pixels."""
    out = bytearray()
    out += _unicode_str(classe)
    out += _u32(0) + classe_id
    out += _u32(len(items))
    for cle, valeur in items:
        out += (_u32(0) + cle) if len(cle) == 4 else (_u32(len(cle)) + cle)
        out += valeur
    return bytes(out)


def _v_texte(s: str) -> bytes:
    return b"TEXT" + _unicode_str(s + "\x00")


def _v_double(x: float) -> bytes:
    return b"doub" + _f64(x)


def _v_entier(n: int) -> bytes:
    return b"long" + _i32(n)


def _v_bool(b: bool) -> bytes:
    return b"bool" + bytes([1 if b else 0])


def _v_unite(x: float, unite: bytes = b"#Pnt") -> bytes:
    return b"UntF" + unite + _f64(x)


def _cle(nom: str) -> bytes:
    """Identifiant Photoshop : longueur puis caractères — mais une longueur de 0 signifie « clé
    de 4 caractères », et c'est la seule forme que Photoshop écrit lui-même pour `Ornt`, `Annt`,
    `Hrzn`… Les deux se lisent ; autant ne pas s'écarter de ce qu'il produit."""
    brut = nom.encode("ascii")
    return (_u32(0) if len(brut) == 4 else _u32(len(brut))) + brut


def _v_enum(type_: str, valeur: str) -> bytes:
    return b"enum" + _cle(type_) + _cle(valeur)


def _v_objet(items: list[tuple[bytes, bytes]], classe: str = "") -> bytes:
    return b"Objc" + _descripteur(items, classe)


def _v_donnees(brut: bytes) -> bytes:
    return b"tdta" + _u32(len(brut)) + brut


def _tysh(t: dict) -> bytes:
    """Bloc `TySh` (Type Tool Object Setting) : ce qui fait d'un calque un calque de TEXTE.

    Contenu : une matrice de transformation (position de la ligne de base), le descripteur de
    texte — dont l'`EngineData`, le vrai moteur de texte de Photoshop — et un descripteur de
    déformation vide."""
    out = bytearray()
    out += _i16(1)                                     # version
    # Transformation : identité + translation vers l'origine du texte (première ligne de base).
    for v in (1.0, 0.0, 0.0, 1.0, float(t["tx"]), float(t["ty"])):
        out += _f64(v)
    out += _i16(50)                                    # version du texte
    out += _i32(16)                                    # version du descripteur
    out += _descripteur([
        # MÊME normalisation que l'`EngineData` (cf. `texte_moteur`) : un écart d'un seul
        # caractère entre les deux fait planter Photoshop à l'ouverture.
        (b"Txt ", _v_texte(texte_moteur(t["texte"]))),
        (b"textGridding", _v_enum("textGridding", "None")),
        (b"Ornt", _v_enum("Ornt", "Hrzn")),
        (b"AntA", _v_enum("Annt", "antiAliasSharp")),
        (b"bounds", _v_objet([
            (b"Left", _v_unite(t["left"])), (b"Top ", _v_unite(t["top"])),
            (b"Rght", _v_unite(t["right"])), (b"Btom", _v_unite(t["bottom"]))])),
        (b"boundingBox", _v_objet([
            (b"Left", _v_unite(t["left"])), (b"Top ", _v_unite(t["top"])),
            (b"Rght", _v_unite(t["right"])), (b"Btom", _v_unite(t["bottom"]))])),
        (b"TextIndex", _v_entier(0)),
        (b"EngineData", _v_donnees(engine_data(t))),
    ])
    out += _i16(1)                                     # version de la déformation
    out += _i32(16)
    out += _descripteur([
        (b"warpStyle", _v_enum("warpStyle", "warpNone")),
        (b"warpValue", _v_double(0.0)),
        (b"warpPerspective", _v_double(0.0)),
        (b"warpPerspectiveOther", _v_double(0.0)),
        (b"warpRotate", _v_enum("Ornt", "Hrzn")),
    ])
    for v in (0, 0, 0, 0):
        out += _i32(v)
    return bytes(out)


def texte_moteur(s: str) -> str:
    """Texte tel que le moteur de Photoshop l'attend : chaque paragraphe clos par un `\\r`,
    y compris le dernier.

    ⚠ Cette normalisation doit s'appliquer AU MÊME ENDROIT dans le descripteur `Txt ` et dans
    l'`EngineData`. La v0.19.1 ne l'appliquait qu'à l'`EngineData` : `Txt ` annonçait 7
    caractères, les passes de style en couvraient 8, et Photoshop — qui dimensionne ses tampons
    sur `Txt ` — écrivait un caractère au-delà. Résultat : plantage à l'ouverture, sans même la
    boîte d'alerte précédente."""
    return s if s.endswith("\r") else s + "\r"


def _eng_texte(s: str) -> str:
    """Chaîne du moteur de texte : UTF-16BE avec marque d'ordre, entre parenthèses, les
    caractères spéciaux échappés par une barre oblique inverse.

    ⚠ La marque d'ordre s'écrit en octets BRUTS (`\\xfe\\xff`), jamais en échappements octaux
    (`\\376\\377`) : c'est à cette séquence exacte qu'un lecteur reconnaît une chaîne UTF-16 et
    cesse de découper aux espaces. Un nom échappé en octal comme « Normal RGB » se faisait couper
    en deux à son espace, et toute l'`EngineData` devenait illisible."""
    brut = "﻿" + s
    sortie = []
    for octet in brut.encode("utf-16-be"):
        c = chr(octet)
        sortie.append("\\" + c if c in "()\\" else c)
    return "(" + "".join(sortie) + ")"


def engine_data(t: dict) -> bytes:
    """`EngineData` : la structure de moteur de texte que Photoshop lit réellement pour
    afficher et rééditer un calque de type.

    Sérialisation à la Postscript (`<< /Clé valeur >>`), les chaînes en UTF-16BE. Les longueurs
    de `RunLengthArray` doivent couvrir **exactement** le texte, terminateur de paragraphe
    compris — c'est l'incohérence la plus classique et Photoshop refuse alors de réouvrir le
    calque.

    Le texte est joint par `\\r` : c'est le séparateur de paragraphe du moteur, pas `\\n`."""
    texte = texte_moteur(t["texte"])       # MÊME normalisation que le descripteur `Txt `
    n = len(texte)
    # UNE entrée de `RunArray` par paragraphe, et un `RunLengthArray` de MÊME cardinalité dont la
    # somme couvre exactement le texte. Un unique `[n]` — ce que faisait la version précédente —
    # ne tient que pour une bulle d'une seule ligne : dès deux lignes, Photoshop trouvait trois
    # paragraphes annoncés comme un seul et refusait le calque.
    longueurs_paragraphes = [len(segment) + 1 for segment in texte.split("\r")[:-1]] or [n]
    r, v, b = (c / 255.0 for c in t["couleur"])
    police = t["police_ps"]
    corps = float(t["corps"])
    interligne = float(t["interligne"])
    justification = int(t.get("justification", 2))     # 0 gauche, 1 droite, 2 centré

    # Feuille de style COMPLÈTE. Photoshop écrit toutes ces clés ; une feuille réduite à
    # cinq d'entre elles laisse le reste non initialisé de son côté — et c'est ce qui distingue
    # un calque « affichable » (Photopea le dessine) d'un calque « éditable » (l'outil Texte le
    # reprend). Les valeurs sont les défauts d'Adobe, sauf police, corps, interligne et couleur.
    style = (
        "\n\t\t\t\t<<\n"
        "\t\t\t\t\t/Font 0\n"
        f"\t\t\t\t\t/FontSize {corps:.1f}\n"
        "\t\t\t\t\t/FauxBold false\n"
        "\t\t\t\t\t/FauxItalic false\n"
        "\t\t\t\t\t/AutoLeading false\n"
        f"\t\t\t\t\t/Leading {interligne:.1f}\n"
        "\t\t\t\t\t/HorizontalScale 1.0\n"
        "\t\t\t\t\t/VerticalScale 1.0\n"
        "\t\t\t\t\t/Tracking 0\n"
        "\t\t\t\t\t/BaselineShift 0.0\n"
        "\t\t\t\t\t/AutoKerning true\n"
        "\t\t\t\t\t/Kerning 0\n"
        "\t\t\t\t\t/FontCaps 0\n"
        "\t\t\t\t\t/FontBaseline 0\n"
        "\t\t\t\t\t/Underline false\n"
        "\t\t\t\t\t/Strikethrough false\n"
        "\t\t\t\t\t/Ligatures true\n"
        "\t\t\t\t\t/DLigatures false\n"
        "\t\t\t\t\t/BaselineDirection 2\n"
        "\t\t\t\t\t/Tsume 0.0\n"
        "\t\t\t\t\t/StyleRunAlignment 2\n"
        "\t\t\t\t\t/Language 0\n"
        "\t\t\t\t\t/NoBreak false\n"
        "\t\t\t\t\t/FillColor\n"
        "\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t/Type 1\n"
        "\t\t\t\t\t\t/Values [ 1.0 "
        f"{r:.6f} {v:.6f} {b:.6f} ]\n"
        "\t\t\t\t\t>>\n"
        "\t\t\t\t\t/StrokeColor\n"
        "\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t/Type 1\n"
        "\t\t\t\t\t\t/Values [ 1.0 0.0 0.0 0.0 ]\n"
        "\t\t\t\t\t>>\n"
        "\t\t\t\t\t/FillFlag true\n"
        "\t\t\t\t\t/StrokeFlag false\n"
        "\t\t\t\t\t/FillFirst true\n"
        "\t\t\t\t\t/YUnderline 1\n"
        "\t\t\t\t\t/OutlineWidth 1.0\n"
        "\t\t\t\t\t/CharacterDirection 0\n"
        "\t\t\t\t\t/HindiNumbers false\n"
        "\t\t\t\t\t/Kashida 1\n"
        "\t\t\t\t\t/DiacriticPos 2\n"
        "\t\t\t\t>>"
    )
    # Propriétés de paragraphe, mêmes remarques. `/Justification` est la seule qui varie.
    props_paragraphe = (
        "<<\n"
        f"{{I}}\t/Justification {justification}\n"
        f"{{I}}\t/FirstLineIndent 0.0\n"
        f"{{I}}\t/StartIndent 0.0\n"
        f"{{I}}\t/EndIndent 0.0\n"
        f"{{I}}\t/SpaceBefore 0.0\n"
        f"{{I}}\t/SpaceAfter 0.0\n"
        f"{{I}}\t/AutoHyphenate false\n"
        f"{{I}}\t/HyphenatedWordSize 6\n"
        f"{{I}}\t/PreHyphen 2\n"
        f"{{I}}\t/PostHyphen 2\n"
        f"{{I}}\t/ConsecutiveHyphens 8\n"
        f"{{I}}\t/Zone 36.0\n"
        f"{{I}}\t/WordSpacing [ 0.8 1.0 1.33 ]\n"
        f"{{I}}\t/LetterSpacing [ 0.0 0.0 0.0 ]\n"
        f"{{I}}\t/GlyphSpacing [ 1.0 1.0 1.0 ]\n"
        f"{{I}}\t/AutoLeading 1.2\n"
        f"{{I}}\t/LeadingType 0\n"
        f"{{I}}\t/Hanging false\n"
        f"{{I}}\t/Burasagari false\n"
        f"{{I}}\t/KinsokuOrder 0\n"
        f"{{I}}\t/EveryLineComposer false\n"
        f"{{I}}>>"
    )

    def _props(indent: str) -> str:
        """Les `EngineData` de Photoshop sont indentées par tabulations ; on réinjecte le
        niveau attendu à chaque endroit où le bloc est répété."""
        return props_paragraphe.replace("{I}", indent)
    # Une entrée de `RunArray` de paragraphe, répétée autant de fois qu'il y a de paragraphes.
    entree_paragraphe = (
        "\t\t\t\t<<\n"
        "\t\t\t\t\t/ParagraphSheet\n"
        "\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t/DefaultStyleSheet 0\n"
        "\t\t\t\t\t\t/Properties\n"
        f"\t\t\t\t\t\t{_props(chr(9) * 6)}\n"
        "\t\t\t\t\t>>\n"
        "\t\t\t\t\t/Adjustments\n"
        "\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t/Axis [ 1.0 0.0 1.0 ]\n"
        "\t\t\t\t\t\t/XY [ 0.0 0.0 ]\n"
        "\t\t\t\t\t>>\n"
        "\t\t\t\t>>\n"
    )
    run_array_paragraphes = entree_paragraphe * len(longueurs_paragraphes)
    longueurs_texte = " ".join(str(x) for x in longueurs_paragraphes)
    corps_texte = (
        "\n\n<<\n"
        "\t/EngineDict\n"
        "\t<<\n"
        "\t\t/Editor\n"
        "\t\t<<\n"
        f"\t\t\t/Text {_eng_texte(texte)}\n"
        "\t\t>>\n"
        "\t\t/ParagraphRun\n"
        "\t\t<<\n"
        "\t\t\t/DefaultRunData\n"
        "\t\t\t<<\n"
        "\t\t\t\t/ParagraphSheet\n"
        "\t\t\t\t<<\n"
        "\t\t\t\t\t/DefaultStyleSheet 0\n"
        "\t\t\t\t\t/Properties\n"
        f"\t\t\t\t\t{_props(chr(9) * 5)}\n"
        "\t\t\t\t>>\n"
        "\t\t\t\t/Adjustments\n"
        "\t\t\t\t<<\n"
        "\t\t\t\t\t/Axis [ 1.0 0.0 1.0 ]\n"
        "\t\t\t\t\t/XY [ 0.0 0.0 ]\n"
        "\t\t\t\t>>\n"
        "\t\t\t>>\n"
        "\t\t\t/RunArray [\n"
        f"{run_array_paragraphes}"
        "\t\t\t]\n"
        f"\t\t\t/RunLengthArray [ {longueurs_texte} ]\n"
        "\t\t\t/IsJoinable 1\n"
        "\t\t>>\n"
        "\t\t/StyleRun\n"
        "\t\t<<\n"
        "\t\t\t/DefaultRunData\n"
        "\t\t\t<<\n"
        "\t\t\t\t/StyleSheet\n"
        "\t\t\t\t<<\n"
        "\t\t\t\t\t/StyleSheetData"
        f"{style}\n"
        "\t\t\t\t>>\n"
        "\t\t\t>>\n"
        "\t\t\t/RunArray [\n"
        "\t\t\t\t<<\n"
        "\t\t\t\t\t/StyleSheet\n"
        "\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t/StyleSheetData"
        f"{style}\n"
        "\t\t\t\t\t>>\n"
        "\t\t\t\t>>\n"
        "\t\t\t]\n"
        f"\t\t\t/RunLengthArray [ {n} ]\n"
        "\t\t\t/IsJoinable 2\n"
        "\t\t>>\n"
        "\t\t/GridInfo\n"
        "\t\t<<\n"
        "\t\t\t/GridIsOn false\n"
        "\t\t\t/ShowGrid false\n"
        "\t\t\t/GridSize 18.0\n"
        "\t\t\t/GridLeading 22.0\n"
        "\t\t\t/GridColor\n"
        "\t\t\t<<\n"
        "\t\t\t\t/Type 1\n"
        "\t\t\t\t/Values [ 0.0 0.0 0.0 1.0 ]\n"
        "\t\t\t>>\n"
        "\t\t\t/GridLeadingFillColor\n"
        "\t\t\t<<\n"
        "\t\t\t\t/Type 1\n"
        "\t\t\t\t/Values [ 0.0 0.0 0.0 1.0 ]\n"
        "\t\t\t>>\n"
        "\t\t\t/AlignLineHeightToGridFlags false\n"
        "\t\t>>\n"
        "\t\t/AntiAlias 4\n"
        "\t\t/UseFractionalGlyphWidths true\n"
        # `/Rendered` : la mise en page déjà calculée. Photoshop la recalcule, mais son
        # ABSENCE est ce qui distingue un calque que Photopea sait dessiner d'un calque qu'il
        # sait rouvrir à l'outil Texte. On écrit la coquille minimale documentée — un tracé
        # sans ligne — et le moteur la remplit à l'ouverture.
        "\t\t/Rendered\n"
        "\t\t<<\n"
        "\t\t\t/Version 1\n"
        "\t\t\t/Shapes\n"
        "\t\t\t<<\n"
        "\t\t\t\t/WritingDirection 0\n"
        "\t\t\t\t/Children [\n"
        "\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t/ShapeType 0\n"
        "\t\t\t\t\t\t/Procession 0\n"
        "\t\t\t\t\t\t/Lines\n"
        "\t\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t\t/WritingDirection 0\n"
        "\t\t\t\t\t\t\t/Children [ ]\n"
        "\t\t\t\t\t\t>>\n"
        "\t\t\t\t\t\t/Cookie\n"
        "\t\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t\t/Photoshop\n"
        "\t\t\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t\t\t/ShapeType 0\n"
        "\t\t\t\t\t\t\t\t/PointBase [ 0.0 0.0 ]\n"
        "\t\t\t\t\t\t\t\t/Base\n"
        "\t\t\t\t\t\t\t\t<<\n"
        "\t\t\t\t\t\t\t\t\t/ShapeType 0\n"
        "\t\t\t\t\t\t\t\t\t/TransformPoint0 [ 1.0 0.0 ]\n"
        "\t\t\t\t\t\t\t\t\t/TransformPoint1 [ 0.0 1.0 ]\n"
        "\t\t\t\t\t\t\t\t\t/TransformPoint2 [ 0.0 0.0 ]\n"
        "\t\t\t\t\t\t\t\t>>\n"
        "\t\t\t\t\t\t\t>>\n"
        "\t\t\t\t\t\t>>\n"
        "\t\t\t\t\t>>\n"
        "\t\t\t\t]\n"
        "\t\t\t>>\n"
        "\t\t>>\n"
        "\t>>\n"
        "\t/ResourceDict\n"
        "\t<<\n"
        "\t\t/KinsokuSet [ ]\n"
        "\t\t/MojiKumiSet [ ]\n"
        "\t\t/TheNormalStyleSheet 0\n"
        "\t\t/TheNormalParagraphSheet 0\n"
        "\t\t/SuperscriptSize 0.583\n"
        "\t\t/SuperscriptPosition 0.333\n"
        "\t\t/SubscriptSize 0.583\n"
        "\t\t/SubscriptPosition 0.333\n"
        "\t\t/SmallCapSize 0.7\n"
        "\t\t/ParagraphSheetSet [\n"
        "\t\t\t<<\n"
        f"\t\t\t\t/Name {_eng_texte('Normal RGB')}\n"
        "\t\t\t\t/DefaultStyleSheet 0\n"
        "\t\t\t\t/Properties\n"
        f"\t\t\t\t{_props(chr(9) * 4)}\n"
        "\t\t\t>>\n"
        "\t\t]\n"
        "\t\t/StyleSheetSet [\n"
        "\t\t\t<<\n"
        f"\t\t\t\t/Name {_eng_texte('Normal RGB')}\n"
        "\t\t\t\t/StyleSheetData"
        f"{style}\n"
        "\t\t\t>>\n"
        "\t\t]\n"
        "\t\t/FontSet [\n"
        "\t\t\t<<\n"
        f"\t\t\t\t/Name {_eng_texte(police)}\n"
        "\t\t\t\t/Script 0\n"
        "\t\t\t\t/FontType 1\n"
        "\t\t\t\t/Synthetic 0\n"
        "\t\t\t>>\n"
        "\t\t]\n"
        "\t>>\n"
        "\t/DocumentResources\n"
        "\t<<\n"
        "\t\t/FontSet [\n"
        "\t\t\t<<\n"
        f"\t\t\t\t/Name {_eng_texte(police)}\n"
        "\t\t\t\t/Script 0\n"
        "\t\t\t\t/FontType 1\n"
        "\t\t\t\t/Synthetic 0\n"
        "\t\t\t>>\n"
        "\t\t]\n"
        "\t>>\n"
        ">>"
    )
    return corps_texte.encode("latin-1", errors="replace")


def _nom_postscript_declare(chemin_police: str) -> str:
    """Nom PostScript LU dans la table `name` du fichier (entrée ID 6), ou `""`.

    C'est la seule source qui fasse autorité : c'est cette chaîne exacte que Photoshop
    compare aux polices installées pour décider s'il affiche « Polices manquantes ».

    Lecture directe en `struct`, comme le reste de ce module lit et écrit du binaire à la
    main — `fontTools` ne serait tiré que pour ces quinze lignes."""
    try:
        donnees = Path(chemin_police).read_bytes()
        n_tables = struct.unpack(">H", donnees[4:6])[0]
        debut = next((struct.unpack(">I", donnees[p + 8:p + 12])[0]
                      for p in (12 + 16 * i for i in range(n_tables))
                      if donnees[p:p + 4] == b"name"), None)
        if debut is None:
            return ""
        _fmt, nombre, debut_chaines = struct.unpack(">HHH", donnees[debut:debut + 6])
        par_plateforme: dict[int, str] = {}
        for i in range(nombre):
            p = debut + 6 + 12 * i
            plateforme, _enc, _lang, ident, longueur, decalage = struct.unpack(
                ">HHHHHH", donnees[p:p + 12])
            if ident != 6 or plateforme in par_plateforme:   # 6 = PostScript name
                continue
            brut = donnees[debut + debut_chaines + decalage:][:longueur]
            # ⚠ Les plateformes 3 (Windows) ET 0 (Unicode) encodent en UTF-16BE ; seule la 1
            # (Macintosh) est sur un octet. N'en traiter qu'une rendait ` A r i a l M T` pour
            # `arial.ttf` — des NUL pris pour des caractères, invisibles à l'affichage.
            par_plateforme[plateforme] = (
                brut.decode("utf-16-be") if plateforme in (0, 3) else brut.decode("latin-1"))
        for plateforme in (3, 0, 1):           # Windows d'abord : c'est le nom que PS cherche
            nom = par_plateforme.get(plateforme, "").strip().strip("\x00")
            if nom:
                return nom
    except Exception:
        return ""
    return ""


def nom_postscript(chemin_police: str) -> str:
    """Nom PostScript d'une police, pour le `FontSet` de l'`EngineData`.

    ⚠ Ce nom n'est pas décoratif : Photoshop s'en sert pour retrouver la police **installée**.
    S'il ne la trouve pas, il affiche « Polices manquantes » à l'ouverture et **substitue** dès
    la première modification — le calque reste éditable, mais la bulle réécrite change de
    dessin et jure avec ses voisines, restées sur les pixels d'origine.
    `tools/installer_polices.ps1` installe les polices livrées ; le validateur Photoshop
    vérifie qu'il les voit.

    On LIT donc le nom déclaré par le fichier, au lieu de le deviner. L'ancienne heuristique
    — concaténer le `(famille, style)` de Pillow — reste en repli pour les polices dont la
    table `name` est illisible, mais elle se trompe : mesurée sur les quatre fichiers livrés,
    elle est exacte pour Bold, Italic et BoldItalic, et **fausse pour Regular**, dont elle
    supprime le suffixe (`ComicNeue` au lieu de `ComicNeue-Regular`). Le PSD réclamait alors
    une police qui n'existe nulle part, et l'installer n'y aurait rien changé."""
    declare = _nom_postscript_declare(chemin_police)
    if declare:
        return declare
    try:
        famille, style = ImageFont.truetype(chemin_police, 24).getname()
    except Exception:
        return Path(chemin_police).stem
    famille = (famille or "").replace(" ", "")
    style = (style or "").replace(" ", "")
    if not style or style.lower() == "regular":
        return famille or Path(chemin_police).stem
    return f"{famille}-{style}"


# --------------------------------------------------------------------------- #
# Assemblage du fichier
# --------------------------------------------------------------------------- #

def _ressources_image(dpi: int) -> bytes:
    """Bloc 1005 (ResolutionInfo). Sans lui, un lecteur suppose 72 ppp et une planche
    prévue pour l'impression se retrouve à une taille physique fantaisiste."""
    fixe = _u32(int(dpi) << 16)
    corps = fixe + _u16(1) + _u16(1) + fixe + _u16(1) + _u16(1)
    bloc = b"8BIM" + _u16(1005) + _pad(b"\x00", 2) + _u32(len(corps)) + _pad(corps, 2)
    return _u32(len(bloc)) + bloc


def ecrire(chemin: Path, composite: Image.Image, calques: list[Calque], *,
           dpi: int = 300) -> Path:
    """Écrit un PSD : `composite` est l'image aplatie (ce que voit un lecteur qui ignore les
    calques), `calques` la pile du **bas vers le haut**."""
    comp = composite.convert("RGB")
    w, h = comp.size
    plans = np.asarray(comp).transpose(2, 0, 1)        # (3, h, w)

    entete = (SIGNATURE + _u16(1) + b"\x00" * 6 + _u16(3) + _u32(h) + _u32(w)
              + _u16(8) + _u16(3))

    enregistrements = bytearray()
    donnees = bytearray()
    for calque in calques:
        canaux = _canaux_zip(calque.rgba)
        enregistrements += _enregistrement_calque(calque, canaux)
        for c in canaux:
            donnees += c

    infos_calques = _i16(len(calques)) + bytes(enregistrements) + bytes(donnees)
    # La section « layer info » est complétée à un multiple de 2 et sa longueur l'inclut.
    infos_calques = _pad(infos_calques, 2)
    section = _u32(len(infos_calques)) + infos_calques + _u32(0)   # + masque global : aucun
    section_calques = _u32(len(section)) + section

    tables, corps = [], []
    for i in range(3):
        table, data = _canal_rle(plans[i])
        tables.append(table)
        corps.append(data)
    image_donnees = _u16(COMPRESSION_RLE) + b"".join(tables) + b"".join(corps)

    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "wb") as fh:
        fh.write(entete)
        fh.write(_u32(0))                  # données de mode couleur : aucune (RVB)
        fh.write(_ressources_image(dpi))
        fh.write(section_calques)
        fh.write(image_donnees)
    return chemin


# --------------------------------------------------------------------------- #
# Construction des calques d'une planche
# --------------------------------------------------------------------------- #

def _opaque(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    return np.dstack([rgb, np.full((h, w), 255, dtype=np.uint8)])


def _abrege(texte: str, maxi: int = 40) -> str:
    plat = " ".join(texte.split())
    return plat if len(plat) <= maxi else plat[:maxi - 1] + "…"


def calques_de_planche(nettoyee: Image.Image, fits: list[dict], *,
                       originale: Image.Image | None = None,
                       mode_texte: str = "type") -> list[Calque]:
    """Pile de calques d'une planche, du bas vers le haut, à partir des recettes de lettrage
    rendues par `typeset.typeset_page(fits_out=…)`.

    `mode_texte` vaut `"type"` (calques de texte réels) ou `"rasterise"`."""
    from .typeset import calque_fit

    calques: list[Calque] = []
    if originale is not None:
        calques.append(Calque("Planche originale", _opaque(originale), 0, 0, visible=False))
    calques.append(Calque("Planche nettoyée", _opaque(nettoyee), 0, 0))

    for entree in fits:
        fit, style, police = entree["fit"], entree["style"], entree["police"]
        produit = calque_fit(fit, style, police)
        if produit is None:
            continue
        calque_img, x, y = produit
        texte = "\r".join(fit.lines)
        nom = f"Texte {entree['index'] + 1:02d} — {_abrege(texte.replace(chr(13), ' '))}"

        params = None
        if mode_texte == "type" and not fit.overflow:
            police_font = ImageFont.truetype(police, fit.size)
            montant, _descendant = police_font.getmetrics()
            largeurs = [police_font.getlength(ligne) for ligne in fit.lines] or [0.0]
            demi = max(largeurs) / 2.0
            params = {
                "texte": texte,
                "police_ps": nom_postscript(police),
                "corps": fit.size,
                "interligne": fit.line_h,
                "couleur": tuple(style.text_color),
                "justification": 2,
                # `_draw_fit` dessine avec `anchor="ma"` : `fit.top` est le haut de
                # l'ascendante, donc la ligne de base de la première ligne est `top + montant`.
                "tx": float(fit.center_x),
                "ty": float(fit.top + montant),
                "left": -demi, "right": demi,
                "top": float(-montant),
                "bottom": float(fit.line_h * (len(fit.lines) - 1) + police_font.getmetrics()[1]),
            }
        calques.append(Calque(nom, np.asarray(calque_img), x, y, texte=params))
    return calques


def psd_minimal(chemin: Path, texte: str = "Test", *, font_path: str | None = None,
                taille: tuple[int, int] = (400, 200), corps: int = 48) -> Path:
    """PSD le plus simple possible : un fond blanc, UN calque de texte. Rien d'autre.

    C'est l'outil de diagnostic qui manquait. Valider les calques de type sur un tome de
    150 planches coûte un run complet et un Photoshop qui plante ; ici le cycle
    « écrire → ouvrir → constater » dure dix secondes, et si ce fichier-là ne s'ouvre pas,
    le problème est dans le `TySh`, pas dans le reste du document. Exposé par
    `run_manga.py --psd-test`."""
    from .typeset import load_font, resolve_font

    police = resolve_font(font_path)
    font = load_font(police, corps)
    montant, descendant = font.getmetrics()
    largeur = font.getlength(texte)

    w, h = taille
    fond = Image.new("RGB", (w, h), (255, 255, 255))
    calque_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(calque_img).text((w // 2, (h - montant - descendant) // 2), texte,
                                    font=font, fill=(0, 0, 0, 255), anchor="ma")
    apercu = fond.copy()
    apercu.paste(calque_img, (0, 0), calque_img)

    params = {
        "texte": texte,
        "police_ps": nom_postscript(police),
        "corps": corps,
        "interligne": montant + descendant,
        "couleur": (0, 0, 0),
        "justification": 2,
        "tx": float(w // 2),
        "ty": float((h - montant - descendant) // 2 + montant),
        "left": -largeur / 2.0, "right": largeur / 2.0,
        "top": float(-montant), "bottom": float(descendant),
    }
    calques = [
        Calque("Fond", _opaque(fond), 0, 0),
        Calque(f"Texte — {texte}", np.asarray(calque_img), 0, 0, texte=params),
    ]
    return ecrire(chemin, apercu, calques)


def polices_utilisees(fits: list[dict], mode_texte: str = "type") -> list[str]:
    """Noms PostScript déclarés dans les calques de type d'une planche.

    À remonter dans `RAPPORT.md` : si Photoshop ne trouve pas l'un de ces noms sur le système,
    il **substitue** silencieusement une autre police. Le calque reste éditable, mais le dessin
    change — et rien à l'écran ne dit pourquoi. Savoir quoi installer évite la chasse."""
    if mode_texte != "type":
        return []
    noms = {nom_postscript(entree["police"]) for entree in fits
            if entree.get("police") and not entree["fit"].overflow}
    return sorted(noms)


def ecrire_planche(chemin: Path, *, finale: Image.Image, nettoyee: Image.Image,
                   fits: list[dict], originale: Image.Image | None = None,
                   mode_texte: str = "type", dpi: int = 300) -> Path:
    """Écrit le PSD d'une planche. `finale` est la page aplatie telle que le pipeline la
    produit — elle sert de composite, donc un lecteur qui ignore les calques voit exactement
    la même chose que dans `pages_out/`."""
    calques = calques_de_planche(nettoyee, fits, originale=originale, mode_texte=mode_texte)
    return ecrire(chemin, finale, calques, dpi=dpi)
