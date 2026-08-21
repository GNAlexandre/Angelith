# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Export PSD (lot 4.4) : structure du fichier, calques par bulle, calques de type.

Un écrivain de format binaire ne se teste pas en regardant le résultat : ce fichier embarque
donc son propre **analyseur** PSD, indépendant de l'écrivain, et vérifie ce qui est réellement
sur le disque — en-tête, nombre et noms de calques, rectangles, canaux, et la chaîne retrouvée
dans l'`EngineData`.

⚠ Ce que ces tests NE prouvent pas : qu'Adobe Photoshop ouvre le fichier. Un analyseur, même
indépendant, valide la conformité à la SPÉCIFICATION ; Photoshop valide ce qu'Adobe ACCEPTE, et
c'est le second qui décide. Cette preuve-là vient de `tools/valider_psd_photoshop.ps1`, qui pilote
Photoshop par son automation COM — outil manuel, car il ouvre l'application, donc hors pytest.

Le risque résiduel reste borné par le format lui-même : un calque de type porte AUSSI ses pixels,
donc un `TySh` refusé dégrade le calque en calque rasterisé plutôt que de perdre le lettrage.
"""
from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import psd
from manga.clean import analyze_regions
from manga.detection import BubbleRegion
from manga.typeset import typeset_page


# --------------------------------------------------------------------------- #
# Analyseur PSD indépendant de l'écrivain
# --------------------------------------------------------------------------- #

class Lecteur:
    def __init__(self, donnees: bytes):
        self.d = donnees
        self.i = 0

    def prendre(self, n: int) -> bytes:
        out = self.d[self.i:self.i + n]
        assert len(out) == n, "fichier tronqué"
        self.i += n
        return out

    def u16(self) -> int:
        return struct.unpack(">H", self.prendre(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.prendre(4))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self.prendre(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.prendre(4))[0]


def lire_psd(chemin) -> dict:
    """Analyse un PSD et renvoie sa structure. Volontairement strict : toute longueur
    incohérente déclenche une assertion, ce qui est le but."""
    lec = Lecteur(open(chemin, "rb").read())
    assert lec.prendre(4) == b"8BPS"
    assert lec.u16() == 1, "version 1 (PSD, pas PSB)"
    assert lec.prendre(6) == b"\x00" * 6
    canaux = lec.u16()
    hauteur, largeur = lec.u32(), lec.u32()
    profondeur, mode = lec.u16(), lec.u16()

    assert lec.u32() == 0, "pas de données de mode couleur en RVB"
    taille_ressources = lec.u32()
    ressources = lec.prendre(taille_ressources)

    # ⚠ Surtout pas `lec.i + lec.u32()` : Python évalue le membre GAUCHE d'abord, donc
    # `lec.i` serait lu avant que `u32()` ne consomme les quatre octets de longueur — une
    # borne trop courte de 4, et un décalage qui s'accumule d'un calque à l'autre.
    taille_section = lec.u32()
    fin_section = lec.i + taille_section
    taille_infos = lec.u32()
    fin_infos = lec.i + taille_infos
    n_calques = lec.i16()

    enregistrements = []
    for _ in range(abs(n_calques)):
        top, left, bottom, right = lec.i32(), lec.i32(), lec.i32(), lec.i32()
        nb = lec.u16()
        ids = []
        for _c in range(nb):
            ids.append((lec.i16(), lec.u32()))
        assert lec.prendre(4) == b"8BIM"
        blend = lec.prendre(4)
        opacite, ecretage, drapeaux, _filler = lec.prendre(4)
        taille_extra = lec.u32()
        fin_extra = lec.i + taille_extra
        taille_masque = lec.u32()
        lec.prendre(taille_masque)
        taille_plages = lec.u32()
        lec.prendre(taille_plages)
        n_nom = lec.prendre(1)[0]
        nom = lec.prendre(n_nom).decode("latin-1")
        # complément du nom Pascal à un multiple de 4
        lec.prendre((-(n_nom + 1)) % 4)
        blocs = {}
        while lec.i + 12 <= fin_extra:
            assert lec.prendre(4) in (b"8BIM", b"8B64")
            cle = lec.prendre(4)
            taille = lec.u32()
            blocs[cle] = lec.prendre(taille + (taille % 2))
        lec.i = fin_extra
        enregistrements.append({
            "rect": (top, left, bottom, right), "canaux": ids, "blend": blend,
            "opacite": opacite, "drapeaux": drapeaux, "nom": nom, "blocs": blocs,
        })

    for enr in enregistrements:
        plans = {}
        for ident, taille in enr["canaux"]:
            debut = lec.i
            compression = lec.u16()
            brut = lec.prendre(taille - 2)
            assert lec.i - debut == taille, "longueur de canal incohérente"
            h = enr["rect"][2] - enr["rect"][0]
            w = enr["rect"][3] - enr["rect"][1]
            if compression == 2:
                plat = np.frombuffer(zlib.decompress(brut), dtype=np.uint8)
                assert plat.size == h * w, "canal ZIP de taille inattendue"
                plans[ident] = plat.reshape(h, w)
            else:
                plans[ident] = None
        enr["plans"] = plans

    lec.i = fin_infos
    lec.i = fin_section

    compression = lec.u16()
    composite = None
    if compression == 1:
        longueurs = [lec.u16() for _ in range(hauteur * canaux)]
        plans = []
        for c in range(canaux):
            lignes = []
            for y in range(hauteur):
                lignes.append(_depackbits(lec.prendre(longueurs[c * hauteur + y]), largeur))
            plans.append(np.array(lignes, dtype=np.uint8))
        composite = np.stack(plans, axis=2)
    return {
        "taille": (largeur, hauteur), "canaux": canaux, "profondeur": profondeur,
        "mode": mode, "ressources": ressources, "calques": enregistrements,
        "composite": composite,
    }


def _depackbits(donnees: bytes, attendu: int) -> np.ndarray:
    out = bytearray()
    i = 0
    while i < len(donnees):
        n = donnees[i]
        i += 1
        if n < 128:
            out.extend(donnees[i:i + n + 1])
            i += n + 1
        else:
            out.extend([donnees[i]] * (257 - n))
            i += 1
    assert len(out) == attendu, f"ligne décompressée de {len(out)} au lieu de {attendu}"
    return np.frombuffer(bytes(out), dtype=np.uint8)


# --------------------------------------------------------------------------- #
# PackBits : aller-retour
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("donnees", [
    b"",
    b"A",
    b"AAAA",
    b"ABCDEF",
    b"\x00" * 500,
    b"AB" * 300,
    bytes(range(256)) * 3,
    b"\xff" * 130 + b"\x01\x02" + b"\x00" * 129,
])
def test_packbits_est_reversible(donnees):
    comprime = psd.packbits(donnees)
    assert bytes(_depackbits(comprime, len(donnees))) == donnees


def test_packbits_comprime_vraiment_les_aplats():
    """Une ligne de blanc pur — le cas dominant sur du trait de manga — doit s'effondrer."""
    assert len(psd.packbits(b"\xff" * 1125)) < 40


# --------------------------------------------------------------------------- #
# Fixtures : une planche minimale
# --------------------------------------------------------------------------- #

TAILLE = (300, 400)
BOX = (50, 40, 250, 200)
BOX2 = (60, 230, 240, 370)


def _planche():
    img = Image.new("RGB", TAILLE, (30, 30, 30))
    d = ImageDraw.Draw(img)
    for box in (BOX, BOX2):
        d.ellipse(list(box), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    regions = []
    for box in (BOX, BOX2):
        m = Image.new("L", TAILLE, 0)
        ImageDraw.Draw(m).ellipse(list(box), fill=255)
        regions.append(BubbleRegion(bbox=box, mask=np.asarray(m) > 127, score=0.9, cls=0))
    return img, regions


def _rendre(textes, mode_texte="type", avec_originale=True, font_path=None):
    """Lettre une planche et renvoie tout ce qu'il faut pour écrire son PSD."""
    from manga.clean import clean_bubbles

    img, regions = _planche()
    styles = analyze_regions(img, regions)
    nettoyee = clean_bubbles(img, regions, styles=styles)
    fits: list[dict] = []
    finale = typeset_page(nettoyee.copy(), regions, textes, styles=styles, fits_out=fits,
                          font_path=font_path)
    return dict(finale=finale, nettoyee=nettoyee, fits=fits,
                originale=img if avec_originale else None, mode_texte=mode_texte)


# --------------------------------------------------------------------------- #
# Structure du fichier
# --------------------------------------------------------------------------- #

def test_len_tete_decrit_la_planche(tmp_path):
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut à toi"]))
    lu = lire_psd(p)
    assert lu["taille"] == TAILLE
    assert (lu["canaux"], lu["profondeur"], lu["mode"]) == (3, 8, 3)


def test_un_calque_par_bulle_plus_les_deux_fonds(tmp_path):
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut à toi"]))
    noms = [c["nom"] for c in lire_psd(p)["calques"]]
    assert noms[0] == "Planche originale"
    assert noms[1] == "Planche nettoyée"
    assert len(noms) == 4
    assert noms[2].startswith("Texte 01") and noms[3].startswith("Texte 02")


def test_la_planche_originale_est_masquee(tmp_path):
    """Elle est là pour comparer, pas pour cacher le travail : elle doit s'ouvrir invisible."""
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut"]))
    calques = lire_psd(p)["calques"]
    assert calques[0]["drapeaux"] & 0x02, "« Planche originale » doit être masquée"
    assert not calques[1]["drapeaux"] & 0x02, "« Planche nettoyée » doit être visible"


def test_les_calques_de_texte_sont_bornes_a_leur_bulle(tmp_path):
    """C'est ce qui garde un PSD de planche léger : un calque par bulle à la taille de la
    page pèserait la page entière à chaque fois."""
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut à toi"]))
    calques = lire_psd(p)["calques"]
    assert calques[1]["rect"] == (0, 0, TAILLE[1], TAILLE[0]), "le fond couvre la page"
    for c in calques[2:]:
        top, left, bottom, right = c["rect"]
        assert (right - left) < TAILLE[0] and (bottom - top) < TAILLE[1]


def test_chaque_calque_a_ses_quatre_canaux(tmp_path):
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut"]))
    for c in lire_psd(p)["calques"]:
        assert [ident for ident, _ in c["canaux"]] == [-1, 0, 1, 2]
        for ident, _ in c["canaux"]:
            assert c["plans"][ident] is not None
        h = c["rect"][2] - c["rect"][0]
        w = c["rect"][3] - c["rect"][1]
        assert c["plans"][0].shape == (h, w)


def test_le_nom_unicode_est_present_et_exact(tmp_path):
    """Le nom Pascal « historique » est en latin-1 : sans le bloc `luni`, « nettoyée » et les
    guillemets français seraient abîmés dans le panneau des calques."""
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Où ça ?", "Déjà !"]))
    calques = lire_psd(p)["calques"]
    luni = calques[1]["blocs"][b"luni"]
    n = struct.unpack(">I", luni[:4])[0]
    assert luni[4:4 + 2 * n].decode("utf-16-be") == "Planche nettoyée"
    assert "Où ça ?" in calques[2]["blocs"][b"luni"][4:].decode("utf-16-be")


def test_le_composite_est_la_planche_aplatie_pixel_pour_pixel(tmp_path):
    """Un lecteur qui ignore les calques doit voir exactement ce que `pages_out/` contient."""
    donnees = _rendre(["Bonjour", "Salut à toi"])
    p = psd.ecrire_planche(tmp_path / "p.psd", **donnees)
    lu = lire_psd(p)
    assert lu["composite"] is not None
    assert (lu["composite"] == np.asarray(donnees["finale"].convert("RGB"))).all()


def test_le_calque_de_fond_est_la_planche_nettoyee_pixel_pour_pixel(tmp_path):
    donnees = _rendre(["Bonjour", "Salut"])
    p = psd.ecrire_planche(tmp_path / "p.psd", **donnees)
    fond = lire_psd(p)["calques"][1]
    attendu = np.asarray(donnees["nettoyee"].convert("RGB"))
    obtenu = np.stack([fond["plans"][0], fond["plans"][1], fond["plans"][2]], axis=2)
    assert (obtenu == attendu).all()
    assert (fond["plans"][-1] == 255).all(), "un fond est opaque"


def test_la_resolution_est_ecrite(tmp_path):
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut"]), dpi=300)
    res = lire_psd(p)["ressources"]
    assert b"8BIM" in res
    assert struct.pack(">H", 1005) in res


def test_une_planche_sans_bulle_donne_un_psd_valide(tmp_path):
    """Cas réel : 19 planches du tome de référence n'ont aucune détection."""
    img = Image.new("RGB", TAILLE, (255, 255, 255))
    p = psd.ecrire_planche(tmp_path / "p.psd", finale=img, nettoyee=img, fits=[],
                           originale=None)
    lu = lire_psd(p)
    assert [c["nom"] for c in lu["calques"]] == ["Planche nettoyée"]
    assert (lu["composite"] == np.asarray(img)).all()


def test_sans_planche_originale_la_pile_na_que_le_fond(tmp_path):
    p = psd.ecrire_planche(tmp_path / "p.psd",
                           **_rendre(["Bonjour", "Salut"], avec_originale=False))
    noms = [c["nom"] for c in lire_psd(p)["calques"]]
    assert noms[0] == "Planche nettoyée" and len(noms) == 3


# --------------------------------------------------------------------------- #
# Calques de TYPE
# --------------------------------------------------------------------------- #

def test_en_mode_type_les_calques_de_texte_portent_un_TySh(tmp_path):
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Bonjour", "Salut à toi"]))
    calques = lire_psd(p)["calques"]
    assert b"TySh" not in calques[1]["blocs"], "un fond n'est pas un calque de texte"
    for c in calques[2:]:
        assert b"TySh" in c["blocs"]


def test_en_mode_rasterise_aucun_TySh(tmp_path):
    """L'échappatoire, si Photoshop refuse les calques de type sur ta machine."""
    p = psd.ecrire_planche(tmp_path / "p.psd",
                           **_rendre(["Bonjour", "Salut"], mode_texte="rasterise"))
    for c in lire_psd(p)["calques"]:
        assert b"TySh" not in c["blocs"]


def test_le_mode_rasterise_garde_les_memes_pixels(tmp_path):
    """Un `TySh` n'ajoute que des métadonnées : le dessin ne doit pas bouger d'un pixel."""
    a = psd.ecrire_planche(tmp_path / "a.psd", **_rendre(["Bonjour", "Salut"]))
    b = psd.ecrire_planche(tmp_path / "b.psd",
                           **_rendre(["Bonjour", "Salut"], mode_texte="rasterise"))
    ca, cb = lire_psd(a)["calques"], lire_psd(b)["calques"]
    for x, y in zip(ca, cb):
        assert x["rect"] == y["rect"]
        for ident in (-1, 0, 1, 2):
            assert (x["plans"][ident] == y["plans"][ident]).all()


def test_le_texte_francais_se_retrouve_dans_l_engine_data(tmp_path):
    """L'`EngineData` est ce que Photoshop lit réellement pour rééditer le calque. Le texte y
    est en UTF-16BE : on le recherche sous cette forme, accents compris."""
    p = psd.ecrire_planche(tmp_path / "p.psd", **_rendre(["Où ça, déjà ?", "Salut"]))
    tysh = lire_psd(p)["calques"][2]["blocs"][b"TySh"]
    # Les octets UTF-16BE apparaissent tels quels dans le flux latin-1 de l'EngineData.
    for mot in ("Où", "déjà"):
        assert mot.encode("utf-16-be") in tysh, mot


def test_l_engine_data_declare_la_bonne_longueur_de_texte():
    """Incohérence la plus classique : un `RunLengthArray` qui ne couvre pas exactement le
    texte, et Photoshop refuse de réouvrir le calque.

    ⚠ Ce test affirmait `[ len(texte) ]` DEUX fois — l'hypothèse fausse qui a laissé passer le
    bug. `ParagraphRun` compte UN paragraphe par `\\r` (donc une longueur par paragraphe), là où
    `StyleRun` couvre tout le texte d'un seul style. Et le texte est clos par un `\\r` final, que
    les longueurs doivent inclure."""
    texte = "Bonjour\rle monde"
    brut = psd.engine_data({
        "texte": texte, "police_ps": "ComicNeue-Bold", "corps": 24, "interligne": 27,
        "couleur": (0, 0, 0), "justification": 2,
    }).decode("latin-1")
    total = len(texte) + 1                                   # + le retour chariot terminal
    assert "/RunLengthArray [ 8 9 ]" in brut                 # « Bonjour\r » puis « le monde\r »
    assert 8 + 9 == total
    assert f"/RunLengthArray [ {total} ]" in brut            # StyleRun : un seul style
    assert brut.count("/RunLengthArray") == 2


def test_l_engine_data_porte_police_corps_couleur_et_justification():
    brut = psd.engine_data({
        "texte": "Oui", "police_ps": "MaPolice-Bold", "corps": 31, "interligne": 35,
        "couleur": (255, 0, 0), "justification": 2,
    }).decode("latin-1")
    assert "/FontSize 31.0" in brut
    assert "/Leading 35.0" in brut
    assert "/Justification 2" in brut
    assert "/Values [ 1.0 1.000000 0.000000 0.000000 ]" in brut
    assert "MaPolice-Bold".encode("utf-16-be").decode("latin-1") in brut


def test_les_lignes_sont_jointes_par_un_retour_chariot():
    """Le séparateur de paragraphe du moteur de texte est `\\r`, pas `\\n`."""
    donnees = _rendre(["Un texte assez long pour tenir sur plusieurs lignes dans la bulle"])
    fit = donnees["fits"][0]["fit"]
    assert len(fit.lines) > 1, "le cas n'a pas de sens sur une seule ligne"
    calques = psd.calques_de_planche(donnees["nettoyee"], donnees["fits"])
    params = calques[-1].texte
    assert params is not None
    assert params["texte"] == "\r".join(fit.lines)
    assert "\n" not in params["texte"]


def test_une_bulle_en_debordement_retombe_en_calque_rasterise(tmp_path):
    """Un débordement signifie que la mise en page n'est plus celle qu'un calque de type
    saurait reproduire : mieux vaut des pixels justes qu'un calque éditable faux."""
    donnees = _rendre(["A" * 200, "Salut"])
    assert donnees["fits"][0]["fit"].overflow, "le cas doit bien déborder"
    p = psd.ecrire_planche(tmp_path / "p.psd", **donnees)
    calques = lire_psd(p)["calques"]
    debordante = next(c for c in calques if c["nom"].startswith("Texte 01"))
    assert b"TySh" not in debordante["blocs"]


def test_la_ligne_de_base_tient_compte_de_l_ascendante():
    """`_draw_fit` dessine avec `anchor="ma"` : `fit.top` est le haut de l'ascendante, alors
    qu'un calque de type se positionne sur la LIGNE DE BASE. Confondre les deux décalerait
    tout le texte vers le haut d'une ascendante entière."""
    from PIL import ImageFont

    donnees = _rendre(["Bonjour"])
    entree = donnees["fits"][0]
    fit, police = entree["fit"], entree["police"]
    montant, _ = ImageFont.truetype(police, fit.size).getmetrics()
    params = psd.calques_de_planche(donnees["nettoyee"], donnees["fits"])[-1].texte
    assert params["ty"] == pytest.approx(fit.top + montant)
    assert params["tx"] == pytest.approx(fit.center_x)


# --------------------------------------------------------------------------- #
# Nom PostScript — celui que Photoshop cherche parmi les polices INSTALLÉES
#
# S'il ne le trouve pas, il affiche « Polices manquantes » à l'ouverture et SUBSTITUE dès la
# première modification : la bulle réécrite change de dessin et jure avec ses voisines.
# --------------------------------------------------------------------------- #

def test_nom_postscript_concatene_famille_et_style():
    from manga.typeset import resolve_font
    nom = psd.nom_postscript(resolve_font())
    assert " " not in nom and nom


@pytest.mark.parametrize("fichier,attendu", [
    ("ComicNeue-Bold.ttf", "ComicNeue-Bold"),
    ("ComicNeue-Italic.ttf", "ComicNeue-Italic"),
    ("ComicNeue-BoldItalic.ttf", "ComicNeue-BoldItalic"),
    # ⚠ Celle-ci est LE cas qui a motivé le correctif : l'ancienne heuristique
    # `(famille, style)` supprimait le suffixe et écrivait `ComicNeue`, une police qui
    # n'existe nulle part — même installée, elle serait restée « manquante ».
    ("ComicNeue-Regular.ttf", "ComicNeue-Regular"),
])
def test_le_nom_postscript_est_celui_que_LA_POLICE_declare(fichier, attendu):
    """Lu dans la table `name` (entrée ID 6), pas deviné : c'est la seule chaîne qui fasse
    autorité, et c'est exactement celle que Photoshop compare à ses polices installées."""
    import pathlib
    racine = pathlib.Path(__file__).resolve().parents[1]
    assert psd.nom_postscript(str(racine / "templates" / "fonts" / fichier)) == attendu


def test_le_nom_declare_prime_sur_lheuristique():
    """Sur Arial, `(famille, style)` donne « Arial » alors que la police déclare « ArialMT ».
    Le repli n'est donc pas équivalent — il ne sert qu'aux fichiers dont la table est
    illisible."""
    import pathlib
    arial = pathlib.Path("C:/Windows/Fonts/arial.ttf")
    if not arial.exists():
        pytest.skip("arial.ttf absent (machine non Windows)")
    assert psd.nom_postscript(str(arial)) == "ArialMT"


def test_une_police_illisible_retombe_sur_le_nom_de_fichier(tmp_path):
    """Ni table `name`, ni Pillow : on ne lève pas, on nomme au mieux — un PSD sans FontSet
    serait bien plus grave qu'un PSD au nom de police approximatif."""
    faux = tmp_path / "MaPolice.ttf"
    faux.write_bytes(b"pas du tout une police")
    assert psd.nom_postscript(str(faux)) == "MaPolice"


def test_le_FontSet_du_PSD_porte_le_nom_declare(tmp_path):
    """Bout en bout : ce que la police déclare finit tel quel dans l'`EngineData`."""
    import pathlib
    regular = str(pathlib.Path(__file__).resolve().parents[1]
                  / "templates" / "fonts" / "ComicNeue-Regular.ttf")
    chemin = psd.ecrire_planche(tmp_path / "regular.psd",
                                **_rendre(["Bonjour"], font_path=regular))
    donnees = lire_psd(chemin)
    moteurs = [c["blocs"][b"TySh"] for c in donnees["calques"] if b"TySh" in c["blocs"]]
    assert moteurs
    # L'`EngineData` écrit ses chaînes en UTF-16BE précédées de la marque d'ordre BRUTE.
    attendu = b"(\xfe\xff" + "ComicNeue-Regular".encode("utf-16-be") + b")"
    assert attendu in moteurs[0]
    # …et surtout PAS le nom tronqué qu'écrivait l'ancienne heuristique.
    assert b"(\xfe\xff" + "ComicNeue".encode("utf-16-be") + b")" not in moteurs[0]


# --------------------------------------------------------------------------- #
# Câblage dans l'orchestrateur
# --------------------------------------------------------------------------- #

@pytest.fixture
def tome_psd(tmp_path):
    """Tome d'une planche, en cache jusqu'à la traduction, avec le format « psd » demandé."""
    import yaml

    from manga import checkpoints
    from manga.clean import clean_bubbles

    racine = __import__("pathlib").Path(__file__).resolve().parents[1]
    vol = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol.mkdir(parents=True)
    img, regions = _planche()
    img.save(vol / "page_0001.png")

    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    (build_dir / "pages_out").mkdir(parents=True)
    (build_dir / "pages_clean").mkdir(parents=True)
    ckpt = checkpoints.page_checkpoint_dir(build_dir, 1)
    checkpoints.save_regions(ckpt, regions, img.size)
    clean_bubbles(img, regions).save(checkpoints.clean_page_path(build_dir, 1))
    checkpoints.save_ocr(ckpt, ["こんにちは", "さようなら"])
    checkpoints.save_traduction(ckpt, ["Bonjour à toi", "Adieu"])

    config = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(racine / "prompts")
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    # ⚠ Neutraliser le détecteur de BULLES ne suffit pas : la passe `sfx` est hors du graphe
    # d'invalidation, donc elle tourne même sur un tome déjà en cache et charge le vrai
    # `text_detector.onnx` — 110 s d'inférence CPU par planche. Aucun test d'ici ne porte sur
    # le texte hors bulle ; `test_manga_text_detection.py` s'en charge.
    config["manga"]["onomatopees"]["actif"] = False
    config["manga"]["rendu"]["formats"] = ["images", "psd"]
    config.setdefault("options", {})["dry_run"] = True
    return config, build_dir


def _run(config, **kw):
    from core.reporter import Reporter

    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=Reporter(), **kw)


def test_le_format_psd_produit_un_fichier_par_planche(tome_psd):
    config, build_dir = tome_psd
    assert _run(config, restart_from="rendu") is True
    from manga import checkpoints
    chemin = checkpoints.psd_page_path(build_dir, 1)
    assert chemin.exists()
    lu = lire_psd(chemin)
    noms = [c["nom"] for c in lu["calques"]]
    assert noms[:2] == ["Planche originale", "Planche nettoyée"]
    assert len(noms) == 4


def test_le_psd_recoit_la_planche_NETTOYEE_pas_la_planche_lettree(tome_psd):
    """`typeset_page` mute l'image qu'on lui donne : sans copie, le calque « Planche
    nettoyée » du PSD contiendrait déjà le texte français, et le letteur repeindrait
    par-dessus."""
    config, build_dir = tome_psd
    _run(config, restart_from="rendu")
    from manga import checkpoints
    lu = lire_psd(checkpoints.psd_page_path(build_dir, 1))
    fond = lu["calques"][1]
    attendu = np.asarray(Image.open(checkpoints.clean_page_path(build_dir, 1)).convert("RGB"))
    obtenu = np.stack([fond["plans"][0], fond["plans"][1], fond["plans"][2]], axis=2)
    assert (obtenu == attendu).all()


def test_sans_le_format_psd_aucun_fichier_nest_ecrit(tome_psd):
    config, build_dir = tome_psd
    config["manga"]["rendu"]["formats"] = ["images"]
    assert _run(config, restart_from="rendu") is True
    assert not (build_dir / "pages_psd").exists()


def test_psd_original_false_retire_le_calque_du_scan(tome_psd):
    config, build_dir = tome_psd
    config["manga"]["rendu"]["psd_original"] = False
    _run(config, restart_from="rendu")
    from manga import checkpoints
    noms = [c["nom"] for c in lire_psd(checkpoints.psd_page_path(build_dir, 1))["calques"]]
    assert noms[0] == "Planche nettoyée"
    assert "Planche originale" not in noms


def test_psd_texte_rasterise_coupe_les_calques_de_type(tome_psd):
    config, build_dir = tome_psd
    config["manga"]["rendu"]["psd_texte"] = "rasterise"
    _run(config, restart_from="rendu")
    from manga import checkpoints
    for c in lire_psd(checkpoints.psd_page_path(build_dir, 1))["calques"]:
        assert b"TySh" not in c["blocs"]


def test_le_defaut_livre_ecrit_de_VRAIS_calques_de_texte(tome_psd):
    """Le défaut de `config.yaml` est passé à « type » en v0.27.0, après validation par le
    moteur de Photoshop lui-même (`tools/valider_psd_photoshop.ps1`, automation COM) : sur
    quatre planches et 34 calques, il annonce `LayerKind.TEXTLAYER`, relit le contenu et
    accepte la réécriture.

    Ce test ne rejoue pas cette preuve — il verrouille le CHOIX qu'elle a permis, pour qu'un
    retour silencieux à « rasterise » se voie."""
    import pathlib

    import yaml
    racine = pathlib.Path(__file__).resolve().parents[1]
    livre = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    assert livre["manga"]["rendu"]["psd_texte"] == "type"

    config, build_dir = tome_psd
    config["manga"]["rendu"].pop("psd_texte", None)      # …et le repli du code suit le défaut
    _run(config, restart_from="rendu")
    from manga import checkpoints
    calques = lire_psd(checkpoints.psd_page_path(build_dir, 1))["calques"]
    assert any(b"TySh" in c["blocs"] for c in calques)
