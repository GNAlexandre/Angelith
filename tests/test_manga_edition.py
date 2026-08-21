# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Édition manuelle des zones d'une planche — ajouter, déplacer, supprimer, scinder.

Ce que ces tests protègent tient en une phrase : **corriger une bulle ne doit pas coûter les
autres**. Le réflexe du pipeline face à un changement du nombre de régions est
`checkpoints.invalider_textes`, qui jette OCR et traduction de toute la planche ; c'est juste
pour une re-détection, et ruineux pour une retouche. D'où l'appariement par IoU, et d'où ces
tests, qui vérifient à chaque opération que les bulles NON touchées gardent leur texte, leur
place et leurs corrections manuelles.

Aucun modèle, aucun LLM : on écrit un cache de régions à la main et on relit ce qui en sort.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import checkpoints, edition
from manga.detection import BubbleRegion

TAILLE = (400, 900)          # (largeur, hauteur)


def _boite(k: int) -> tuple[int, int, int, int]:
    """Bulles empilées verticalement, franchement séparées : l'ordre de lecture est alors
    l'ordre des index, et les tests ne dépendent pas de la coupe X-Y."""
    haut = 40 + k * 250
    return (60, haut, 340, haut + 180)


def _masque(bbox) -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse([bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1], fill=255)
    return np.asarray(m) > 127


@pytest.fixture
def planche(tmp_path):
    """Trois bulles, OCR et traduction en cache, plus une correction manuelle sur la 3e."""
    ckpt = tmp_path / "page_0001"
    regions = [BubbleRegion(bbox=_boite(k), mask=_masque(_boite(k)), score=0.9, cls=0)
               for k in range(3)]
    checkpoints.save_regions(ckpt, regions, TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア", "イイイ", "ウウウ"])
    checkpoints.save_traduction(ckpt, ["Un", "Deux", "Trois"])
    checkpoints.save_traduction_manuelle(ckpt, {2: "Trois, à la main"})
    (ckpt / checkpoints.QA_FILENAME).write_text("{}", encoding="utf-8")
    return ckpt


def _lu(ckpt):
    return (checkpoints.load_ocr(ckpt), checkpoints.load_traduction(ckpt),
            checkpoints.load_traduction_manuelle(ckpt))


# --------------------------------------------------------------------------- #
# Masques et boîtes
# --------------------------------------------------------------------------- #

def test_masque_ellipse_est_plus_petit_que_le_rectangle():
    """L'ellipse n'est pas cosmétique : sur un ballon rond, un masque rectangulaire fait
    repeindre les quatre coins de la case par le nettoyage."""
    rect = edition.masque_de_forme("rectangle", (0, 0, 100, 100), TAILLE)
    ell = edition.masque_de_forme("ellipse", (0, 0, 100, 100), TAILLE)
    assert ell.sum() < rect.sum()
    assert 0.70 < ell.sum() / rect.sum() < 0.85          # ~π/4


def test_masque_est_borne_a_la_planche():
    m = edition.masque_de_forme("rectangle", (-50, -50, 200, 200), TAILLE)
    assert m.shape == (TAILLE[1], TAILLE[0])
    assert edition.bbox_du_masque(m)[:2] == (0, 0)


def test_une_zone_minuscule_ou_hors_planche_est_refusee():
    with pytest.raises(edition.ErreurEdition):
        edition.masque_de_forme("rectangle", (10, 10, 11, 11), TAILLE)
    with pytest.raises(edition.ErreurEdition):
        edition.masque_de_forme("rectangle", (900, 900, 999, 999), TAILLE)


def test_forme_inconnue_est_refusee():
    with pytest.raises(edition.ErreurEdition):
        edition.masque_de_forme("polygone", (0, 0, 50, 50), TAILLE)


# --------------------------------------------------------------------------- #
# Ajouter
# --------------------------------------------------------------------------- #

def test_ajouter_une_zone_conserve_le_texte_des_autres(planche):
    """LE test de ce module. Ajouter une bulle oubliée ne doit pas jeter les trois
    traductions déjà payées."""
    # Une 4e bulle, APRÈS les trois autres dans l'ordre de lecture.
    res = edition.ajouter_zone(planche, (60, 790, 340, 890), forme="ellipse")

    ocr, trad, manuelles = _lu(planche)
    assert res["regions"] == 4
    assert ocr == ["アアア", "イイイ", "ウウウ", ""]
    assert trad == ["Un", "Deux", "Trois", ""]
    assert res["indices_a_relire"] == [3]
    assert res["textes_conserves"] == 3
    assert manuelles == {2: "Trois, à la main"}


def test_une_zone_ajoutee_en_tete_decale_tout_sans_rien_perdre(planche):
    """Le cas qui casse un report naïf par index : la nouvelle bulle se lit EN PREMIER, donc
    toutes les autres changent d'index — y compris la clé de la correction manuelle."""
    edition.ajouter_zone(planche, (60, 5, 340, 35))

    ocr, trad, manuelles = _lu(planche)
    assert ocr == ["", "アアア", "イイイ", "ウウウ"]
    assert trad == ["", "Un", "Deux", "Trois"]
    assert manuelles == {3: "Trois, à la main"}, "la correction suit sa bulle, pas son index"


def test_ajouter_une_zone_supprime_le_qa(planche):
    """`qa.json` décrit le rendu PRÉCÉDENT : après une édition il ne décrit plus rien."""
    edition.ajouter_zone(planche, (60, 790, 340, 890))
    assert not (planche / checkpoints.QA_FILENAME).exists()


def test_la_provenance_dit_que_la_planche_a_ete_editee(planche):
    edition.ajouter_zone(planche, (60, 790, 340, 890))
    assert checkpoints.load_detection_meta(planche)["motif"] == "edition_manuelle"


def test_une_zone_ajoutee_ne_mord_pas_sur_sa_voisine(planche):
    """`masks.png` est une image d'ÉTIQUETTES : deux masques qui se recouvrent verraient le
    second effacer le premier au rechargement, sans que rien ne le signale."""
    avant = checkpoints.load_regions(planche)[0].mask.copy()
    edition.ajouter_zone(planche, (60, 100, 340, 300))     # chevauche la bulle 0

    regions = checkpoints.load_regions(planche)
    masques = [r.mask for r in regions]
    for i in range(len(masques)):
        for j in range(i + 1, len(masques)):
            assert not (masques[i] & masques[j]).any(), "deux régions partagent un pixel"
    # La bulle préexistante garde ses pixels : c'est la NOUVELLE qui cède le terrain.
    assert (masques[0] == avant).all()


def test_une_zone_entierement_contenue_dans_une_autre_est_refusee(planche):
    """Elle n'aurait aucun pixel à elle après la mise en disjonction. Le dire, plutôt que
    d'annoncer un succès et de ne rien faire — le geste de l'utilisateur n'a pas pris."""
    interieure = (150, 100, 250, 180)          # bien à l'intérieur de _boite(0)
    with pytest.raises(edition.ErreurEdition, match="entièrement contenue"):
        edition.ajouter_zone(planche, interieure)
    assert len(checkpoints.load_regions(planche)) == 3, "rien n'a été écrit"


# --------------------------------------------------------------------------- #
# Modifier / supprimer
# --------------------------------------------------------------------------- #

def test_modifier_une_zone_remet_son_texte_a_zero_et_garde_les_autres(planche):
    """Les pixels lus ont changé : l'OCR qu'on en avait tiré ne vaut plus rien. Mais celui des
    deux autres bulles, si."""
    res = edition.modifier_zone(planche, 1, (50, 300, 350, 500), forme="ellipse")

    ocr, trad, _m = _lu(planche)
    assert ocr == ["アアア", "", "ウウウ"]
    assert trad == ["Un", "", "Trois"]
    assert res["indices_a_relire"] == [1] and res["indices_a_retraduire"] == [1]


def test_supprimer_une_zone_ne_touche_a_rien_d_autre(planche):
    res = edition.supprimer_zone(planche, 0)

    ocr, trad, manuelles = _lu(planche)
    assert res["regions"] == 2
    assert ocr == ["イイイ", "ウウウ"]
    assert trad == ["Deux", "Trois"]
    assert res["indices_a_relire"] == []
    assert manuelles == {1: "Trois, à la main"}, "la correction a suivi la bulle"


def test_supprimer_la_derniere_bulle_est_refuse(tmp_path):
    """Une planche sans région se relit comme « jamais détectée » et repartirait à l'ONNX."""
    ckpt = tmp_path / "page_0001"
    r = BubbleRegion(bbox=_boite(0), mask=_masque(_boite(0)), score=0.9, cls=0)
    checkpoints.save_regions(ckpt, [r], TAILLE)
    with pytest.raises(edition.ErreurEdition):
        edition.supprimer_zone(ckpt, 0)


def test_un_index_inconnu_est_refuse(planche):
    with pytest.raises(edition.ErreurEdition):
        edition.modifier_zone(planche, 7, (60, 60, 200, 200))


def test_un_cache_absent_est_refuse_clairement(tmp_path):
    with pytest.raises(edition.ErreurEdition, match="détectée"):
        edition.ajouter_zone(tmp_path / "vide", (10, 10, 100, 100))


# --------------------------------------------------------------------------- #
# Scinder
# --------------------------------------------------------------------------- #

@pytest.fixture
def planche_bilobee(tmp_path):
    """Une région faite de DEUX ballons qui se touchent — ce que le détecteur rend parfois
    comme une seule bulle, avec les deux répliques dans une seule chaîne d'OCR."""
    ckpt = tmp_path / "page_0001"
    m = Image.new("L", TAILLE, 0)
    d = ImageDraw.Draw(m)
    d.ellipse([60, 40, 339, 219], fill=255)
    d.ellipse([60, 200, 339, 379], fill=255)
    mask = np.asarray(m) > 127
    regions = [BubbleRegion(bbox=(60, 40, 340, 380), mask=mask, score=0.7, cls=0),
               BubbleRegion(bbox=_boite(2), mask=_masque(_boite(2)), score=0.9, cls=0)]
    checkpoints.save_regions(ckpt, regions, TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア イイイ", "ウウウ"])
    checkpoints.save_traduction(ckpt, ["Un Deux", "Trois"])
    return ckpt


def test_scinder_produit_deux_bulles_et_epargne_la_voisine(planche_bilobee):
    res = edition.scinder_zone(planche_bilobee, 0, ((0, 210), (400, 210)))

    ocr, trad, _m = _lu(planche_bilobee)
    assert res["regions"] == 3
    assert res["indices_a_relire"] == [0, 1], "les deux lobes sont à relire"
    assert ocr == ["", "", "ウウウ"]
    assert trad == ["", "", "Trois"], "la bulle voisine garde sa traduction"


def test_les_deux_lobes_sont_marques_scindes(planche_bilobee):
    edition.scinder_zone(planche_bilobee, 0, ((0, 210), (400, 210)))
    regions = checkpoints.load_regions(planche_bilobee)
    assert [r.scindee for r in regions] == [True, True, False]


def test_les_lobes_ne_se_recouvrent_pas_et_couvrent_l_original(planche_bilobee):
    avant = checkpoints.load_regions(planche_bilobee)[0].mask.copy()
    edition.scinder_zone(planche_bilobee, 0, ((0, 210), (400, 210)))
    a, b = [r.mask for r in checkpoints.load_regions(planche_bilobee)[:2]]
    assert not (a & b).any()
    assert (a | b).sum() == avant.sum(), "aucun pixel perdu ni inventé"


def test_un_trait_qui_rate_la_bulle_est_refuse(planche_bilobee):
    with pytest.raises(edition.ErreurEdition, match="deux morceaux"):
        edition.scinder_zone(planche_bilobee, 0, ((0, 880), (400, 880)))


def test_un_trait_reduit_a_un_point_est_refuse(planche_bilobee):
    with pytest.raises(edition.ErreurEdition, match="point"):
        edition.scinder_zone(planche_bilobee, 0, ((100, 100), (100, 100)))


def test_une_coupe_oblique_fonctionne(planche_bilobee):
    """Le trait est une droite prolongée à l'infini, pas un segment : une oblique qui traverse
    la région la coupe aussi bien qu'une horizontale."""
    res = edition.scinder_zone(planche_bilobee, 0, ((0, 120), (400, 300)))
    assert res["regions"] == 3


# --------------------------------------------------------------------------- #
# Retraduire une bulle
# --------------------------------------------------------------------------- #

class _Agent:
    temperature = 0.3
    dry_run = False
    llm = None

    def __init__(self, reponse="Nouvelle version"):
        self.reponse = reponse
        self.prompts: list[str] = []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.prompts.append(user)
        return self.reponse


def test_retraduire_n_ecrit_que_sa_bulle(planche):
    texte, motif = edition.retraduire_zone(planche, 1, _Agent("Deux, revu"))

    assert (texte, motif) == ("Deux, revu", None)
    assert checkpoints.load_traduction(planche) == ["Un", "Deux, revu", "Trois"]


def test_retraduire_ecrit_dans_traduction_pas_dans_la_manuelle(planche):
    """La distinction est le cœur du dispositif : cette réplique vient du MODÈLE, donc un
    `--from traduction` ultérieur a le droit de l'écraser. Une correction écrite au clavier,
    non — et elle est ici intacte."""
    edition.retraduire_zone(planche, 2, _Agent("Trois, revu"))

    assert checkpoints.load_traduction(planche)[2] == "Trois, revu"
    assert checkpoints.load_traduction_manuelle(planche) == {2: "Trois, à la main"}


def test_une_reponse_refusee_n_ecrase_rien(planche):
    """Une mauvaise réplique dessinée est pire qu'une bulle vide : le refus doit laisser le
    cache exactement comme il était."""
    avant = checkpoints.load_traduction(planche)
    texte, motif = edition.retraduire_zone(planche, 0, _Agent("アアア"))

    assert (texte, motif) == ("", "japonais_residuel")
    assert checkpoints.load_traduction(planche) == avant


def test_retraduire_passe_la_bbox_au_prompt(planche):
    """Le gabarit de place disponible vient de la région : sans lui, le prompt demande d'être
    bref sans jamais dire à quel point."""
    agent = _Agent()
    edition.retraduire_zone(planche, 0, agent)
    x0, y0, x1, y1 = _boite(0)
    assert f"{x1 - x0}×{y1 - y0} px" in agent.prompts[0]


def test_retraduire_un_index_inconnu_est_refuse(planche):
    with pytest.raises(edition.ErreurEdition):
        edition.retraduire_zone(planche, 9, _Agent())


# --------------------------------------------------------------------------- #
# Repeinte de pages_clean — le lot 21
#
# LE défaut visible de la 1.1.0 : `ajouter_zone` ne touchait jamais la planche nettoyée, et
# aucune étape de reprise proposée par l'éditeur ne relance le nettoyage
# (`downstream("rendu") == {"rendu"}`). Le lettrage recomposait donc sur une planche où la
# nouvelle zone n'avait jamais été vidée : le français s'écrivait par-dessus le japonais.
# --------------------------------------------------------------------------- #

def _planche_source() -> Image.Image:
    """Un scan : fond gris, trois ballons blancs avec du « texte » noir dedans."""
    img = Image.new("RGB", TAILLE, (128, 128, 128))
    d = ImageDraw.Draw(img)
    for k in range(3):
        b = _boite(k)
        d.ellipse([b[0], b[1], b[2] - 1, b[3] - 1], fill=(255, 255, 255))
        d.rectangle([b[0] + 40, b[1] + 60, b[2] - 40, b[1] + 100], fill=(0, 0, 0))
    return img


@pytest.fixture
def planche_avec_clean(tmp_path):
    """Cache complet + un `pages_clean` où seules les deux PREMIÈRES bulles sont vidées : la
    troisième joue la zone que la détection avait manquée."""
    ckpt = tmp_path / "page_0001"
    source = _planche_source()
    source.save(tmp_path / "source.png")

    regions = [BubbleRegion(bbox=_boite(k), mask=_masque(_boite(k)), score=0.9, cls=0)
               for k in range(3)]
    checkpoints.save_regions(ckpt, regions[:2], TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア", "イイイ"])
    checkpoints.save_traduction(ckpt, ["Un", "Deux"])

    from manga.clean import clean_bubbles
    clean = clean_bubbles(source, regions[:2])
    chemin_clean = tmp_path / "page_clean.png"
    clean.save(chemin_clean)

    ctx = edition.ContextePlanche(image_source=tmp_path / "source.png",
                                  chemin_clean=chemin_clean)
    return ckpt, ctx, regions[2]


def _uni(chemin, bbox) -> bool:
    """Le cœur de la zone est-il d'une seule couleur ? C'est ce que « vidée » veut dire."""
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    coeur = Image.open(chemin).convert("RGB").crop((cx - 30, cy - 20, cx + 30, cy + 20))
    return len(coeur.getcolors(maxcolors=4096) or [(0, 0)]) == 1


def test_une_zone_ajoutee_est_videe_dans_pages_clean(planche_avec_clean):
    """L'invariant du lot 21. Sans lui, la bulle 3 garde son japonais sous le français."""
    ckpt, ctx, zone3 = planche_avec_clean
    assert not _uni(ctx.chemin_clean, zone3.bbox), "la zone n'est pas encore vidée"

    res = edition.ajouter_zone(ckpt, zone3.bbox, forme="ellipse", ctx=ctx)

    assert res["nettoyage"]["videes"] == 1
    assert _uni(ctx.chemin_clean, zone3.bbox), "la zone ajoutée doit être vidée"


def test_les_bulles_deja_nettoyees_ne_sont_pas_retouchees(planche_avec_clean):
    """Seules les zones TOUCHÉES sont repeintes : repasser sur les autres serait du travail
    inutile, et surtout une occasion de les abîmer."""
    ckpt, ctx, zone3 = planche_avec_clean
    avant = Image.open(ctx.chemin_clean).convert("RGB").crop(_boite(0)).tobytes()

    edition.ajouter_zone(ckpt, zone3.bbox, forme="ellipse", ctx=ctx)

    apres = Image.open(ctx.chemin_clean).convert("RGB").crop(_boite(0)).tobytes()
    assert avant == apres


def test_le_dessin_hors_bulle_reste_intact(planche_avec_clean):
    """L'invariant permanent du dépôt : hors des masques, tout pixel reste bit-à-bit
    identique. Une zone ajoutée ne doit pas repeindre la gouttière entre deux cases."""
    ckpt, ctx, zone3 = planche_avec_clean
    coin = (0, 0, 50, 40)
    avant = Image.open(ctx.chemin_clean).convert("RGB").crop(coin).tobytes()

    edition.ajouter_zone(ckpt, zone3.bbox, forme="ellipse", ctx=ctx)

    assert Image.open(ctx.chemin_clean).convert("RGB").crop(coin).tobytes() == avant


def test_supprimer_une_zone_restaure_le_dessin_d_origine(planche_avec_clean):
    """Une fausse détection déjà nettoyée a laissé un aplat blanc SUR le dessin. La supprimer
    sans restaurer laisserait un trou définitif que rien ne signale."""
    ckpt, ctx, _zone3 = planche_avec_clean
    assert _uni(ctx.chemin_clean, _boite(0)), "bulle 0 vidée au départ"

    res = edition.supprimer_zone(ckpt, 0, ctx=ctx)

    assert res["nettoyage"]["restaurees"] == 1
    assert not _uni(ctx.chemin_clean, _boite(0)), "le dessin d'origine est revenu"


def test_sans_contexte_pages_clean_n_est_pas_touche(planche_avec_clean):
    """Le mode métadonnées seules reste légitime — c'est celui de tous les autres tests, et
    d'un script qui ne ferait que réordonner."""
    ckpt, ctx, zone3 = planche_avec_clean
    avant = ctx.chemin_clean.read_bytes()

    res = edition.ajouter_zone(ckpt, zone3.bbox, forme="ellipse")

    assert res["nettoyage"] is None
    assert ctx.chemin_clean.read_bytes() == avant


def test_une_planche_jamais_nettoyee_est_signalee(tmp_path, planche_avec_clean):
    ckpt, ctx, zone3 = planche_avec_clean
    ctx.chemin_clean.unlink()
    with pytest.raises(edition.ErreurEdition, match="jamais été nettoyée"):
        edition.ajouter_zone(ckpt, zone3.bbox, ctx=ctx)


def test_reprendre_zone_enchaine_vider_lire_traduire(planche_avec_clean):
    """Le bouton unique. On vérifie l'ORDRE par ses effets : la zone est vidée, l'OCR a écrit,
    la traduction a écrit — et le refus du modèle serait remonté."""
    ckpt, ctx, zone3 = planche_avec_clean
    edition.ajouter_zone(ckpt, zone3.bbox, forme="ellipse", ctx=ctx)

    class _Lecteur:
        def read(self, image, region, background=None, cfg=None):
            return "ウウウ"

    compte = edition.reprendre_zone(ckpt, 2, ctx=ctx, lecteur=_Lecteur(),
                                    agent=_Agent("Trois !"))

    assert compte["refus"] is None
    assert compte["ocr"] == "ウウウ" and compte["traduction"] == "Trois !"
    assert checkpoints.load_ocr(ckpt)[2] == "ウウウ"
    assert checkpoints.load_traduction(ckpt)[2] == "Trois !"
    assert _uni(ctx.chemin_clean, zone3.bbox)


def test_reprendre_zone_sans_agent_ne_traduit_pas(planche_avec_clean):
    """Chaque étape est optionnelle par ses dépendances : « juste vider » est un geste
    légitime quand le texte est déjà bon."""
    ckpt, ctx, zone3 = planche_avec_clean
    edition.ajouter_zone(ckpt, zone3.bbox, forme="ellipse", ctx=ctx)

    compte = edition.reprendre_zone(ckpt, 2, ctx=ctx)

    assert compte["ocr"] is None and compte["traduction"] is None
    assert compte["nettoyage"]["videes"] == 1


# --------------------------------------------------------------------------- #
# Retailler — la même bulle, une autre boîte, le même texte
# --------------------------------------------------------------------------- #
#
# La différence avec « redessiner » est tout l'objet de cette section. `modifier_zone` repart
# d'une forme neuve : les pixels lus changent, l'OCR ne vaut plus rien, on le jette à bon
# droit. `retailler_zone` ajuste la même bulle — quelques pixels pour mieux épouser le ballon —
# et refaire payer une lecture (voire une traduction) à chaque ajustement rendrait le
# redimensionnement par poignées inutilisable.

def _queue(bbox, longueur=3):
    """Un ballon plus un appendice fin — la queue qui pointe vers le locuteur.

    C'est le détail que tout rééchantillonnage lisse fait disparaître en réduction, et
    l'unique raison pour laquelle `etirer_masque` impose NEAREST."""
    m = Image.new("L", TAILLE, 0)
    d = ImageDraw.Draw(m)
    d.ellipse([bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1], fill=255)
    cx = (bbox[0] + bbox[2]) // 2
    d.rectangle([cx, bbox[3] - 1, cx + longueur - 1, bbox[3] + 39], fill=255)
    return np.asarray(m) > 127


def test_etirer_a_boite_egale_est_l_identite():
    """Idempotence : sans elle, tirer une poignée puis la ramener n'aurait pas rendu la bulle
    d'origine, et les allers-retours grignoteraient le contour."""
    bbox = _boite(0)
    masque = _masque(bbox)
    assert np.array_equal(edition.etirer_masque(masque, bbox, bbox, TAILLE), masque)


def test_etirer_un_deplacement_pur_est_une_translation():
    """Déplacer, c'est retailler à taille constante. Le masque doit se retrouver **exactement**,
    pas à un pixel de rééchantillonnage près."""
    bbox = _boite(0)
    masque = _masque(bbox)
    cible = (bbox[0] + 20, bbox[1] + 30, bbox[2] + 20, bbox[3] + 30)
    etire = edition.etirer_masque(masque, bbox, cible, TAILLE)
    assert np.array_equal(etire, np.roll(masque, (30, 20), axis=(0, 1)))


def test_etirer_preserve_la_forme_du_ballon():
    """Un ballon agrandi reste le même ballon : le rapport aire/aire-de-boîte est conservé.

    Si l'implémentation fabriquait un rectangle ou une ellipse neufs, ce rapport sauterait."""
    bbox = _boite(0)
    masque = _masque(bbox)
    # ⚠ La cible doit tenir dans la planche : `etirer_masque` la clampe sinon, et le ratio se
    # comparerait à une boîte qui n'a jamais existé.
    cible = (10, 40, 390, 580)
    etire = edition.etirer_masque(masque, bbox, cible, TAILLE)

    avant = masque.sum() / ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    apres = etire.sum() / ((cible[2] - cible[0]) * (cible[3] - cible[1]))
    assert abs(avant - apres) / avant < 0.05


def test_etirer_conserve_une_queue_fine_en_reduction():
    """**Le test qui interdit BILINEAR.** Une queue de 3 px réduite à 0,4× tombe à ~40 % de
    gris sous un rééchantillonnage lisse, donc sous le seuil, donc disparaît en silence."""
    bbox = _boite(0)
    source = (bbox[0], bbox[1], bbox[2], bbox[3] + 40)      # ballon + queue
    masque = _queue(bbox)
    largeur, hauteur = source[2] - source[0], source[3] - source[1]
    cible = (bbox[0], bbox[1], bbox[0] + int(largeur * 0.4), bbox[1] + int(hauteur * 0.4))

    etire = edition.etirer_masque(masque, source, cible, TAILLE)
    # La queue est ce qui dépasse sous le corps du ballon : elle doit survivre.
    bas = int(cible[1] + (cible[3] - cible[1]) * 0.88)
    assert etire[bas:cible[3], :].any(), "la queue a été dissoute par le rééchantillonnage"


def test_etirer_refuse_une_boite_degeneree():
    bbox = _boite(0)
    with pytest.raises(edition.ErreurEdition):
        edition.etirer_masque(_masque(bbox), bbox, (10, 10, 11, 11), TAILLE)


def test_etirer_refuse_un_masque_vide():
    """Un masque vide n'a rien à étirer, et le dire vaut mieux que rendre une zone fantôme."""
    bbox = _boite(0)
    with pytest.raises(edition.ErreurEdition):
        edition.etirer_masque(np.zeros(TAILLE[::-1], dtype=bool), bbox, bbox, TAILLE)


def test_retailler_garde_l_ocr_et_la_traduction(planche):
    """**L'invariant de cette section**, et l'exact opposé de la garantie de `modifier_zone`."""
    boite = _boite(1)
    agrandie = (boite[0] - 20, boite[1] - 20, boite[2] + 20, boite[3] + 20)
    edition.retailler_zone(planche, 1, agrandie)

    ocr, trad, manuelles = _lu(planche)
    assert ocr == ["アアア", "イイイ", "ウウウ"]
    assert trad == ["Un", "Deux", "Trois"]
    assert manuelles == {2: "Trois, à la main"}


def test_redessiner_jette_toujours_le_texte(planche):
    """Le contraste qui donne son sens au test précédent : les deux gestes coexistent, et
    « Redessiner » doit continuer de repartir de zéro."""
    boite = _boite(1)
    edition.modifier_zone(planche, 1, (boite[0] - 20, boite[1] - 20, boite[2] + 20,
                                       boite[3] + 20), forme="ellipse")
    ocr, trad, _manuelles = _lu(planche)
    assert ocr[1] == "" and trad[1] == ""
    assert ocr[0] == "アアア" and trad[2] == "Trois"      # les autres sont intactes


def test_retailler_conserve_la_correction_manuelle(planche):
    """Les clés de `traduction_manuelle.json` sont des index de bulle : elles doivent suivre le
    réordonnancement, sinon la correction pointerait une autre réplique."""
    boite = _boite(2)
    edition.retailler_zone(planche, 2, (boite[0], boite[1], boite[2] + 30, boite[3]))
    assert checkpoints.load_traduction_manuelle(planche) == {2: "Trois, à la main"}


def test_retailler_ne_marque_rien_a_relire(planche):
    rapport = edition.retailler_zone(planche, 0, _boite(0))
    assert rapport["indices_a_relire"] == []
    assert rapport["indices_touches"] == [0]
    assert rapport["textes_conserves"] == 3


def test_retailler_sur_une_autre_bulle_perd_le_texte(planche):
    """L'appariement par IoU reste seul juge. Traîner une zone franchement ailleurs n'est plus
    « la même bulle », et prétendre le contraire y collerait une réplique qui n'a rien à y
    faire."""
    edition.retailler_zone(planche, 0, (60, 700, 340, 880))
    ocr, trad, _m = _lu(planche)
    # La zone déplacée arrive en DERNIÈRE position de l'ordre de lecture, et repart vierge.
    assert ocr[-1] == "" and trad[-1] == ""
    assert "アアア" not in ocr


def test_retailler_refuse_un_index_inconnu(planche):
    with pytest.raises(edition.ErreurEdition):
        edition.retailler_zone(planche, 9, _boite(0))


def test_retailler_repeint_la_planche_nettoyee(planche_avec_clean):
    """**Le test qui protège `indices_touches`.**

    Avec `relire=False`, `indices_a_relire` est vide : une repeinte qui s'y fierait ne ferait
    rien, et le japonais réapparaîtrait sur la bande gagnée par l'agrandissement — sans que
    rien ne le signale, puisque le lettrage écrirait le français par-dessus."""
    ckpt, ctx, _zone3 = planche_avec_clean
    boite = _boite(0)
    # Un ajustement MODESTE, qui reste dans le ballon dessiné : agrandir au-delà ferait entrer
    # du fond de case dans la mesure d'uniformité, et le nettoyage refuserait de peindre — on
    # testerait alors `analyze_bubble`, pas la repeinte.
    agrandie = (boite[0] - 8, boite[1] - 8, boite[2] + 8, boite[3] + 8)

    res = edition.retailler_zone(ckpt, 0, agrandie, ctx=ctx)

    # Avec l'ancienne dérivation (`indices_a_relire`), `relire=False` rendait cette liste vide
    # et `videes` valait 0 : la planche nettoyée restait en désaccord avec son masque.
    assert res["nettoyage"] is not None
    assert res["nettoyage"]["videes"] == 1 and res["nettoyage"]["abandons"] == []
    assert _uni(ctx.chemin_clean, agrandie)


def test_retailler_restaure_l_ancienne_emprise(planche_avec_clean):
    """Rétrécir une zone doit rendre le dessin d'origine sur la bande abandonnée, sinon
    l'aplat blanc du nettoyage précédent y reste définitivement."""
    ckpt, ctx, _zone3 = planche_avec_clean
    boite = _boite(0)
    retrecie = (boite[0] + 60, boite[1] + 40, boite[2] - 60, boite[3] - 40)

    res = edition.retailler_zone(ckpt, 0, retrecie, ctx=ctx)

    assert res["nettoyage"]["restaurees"] == 1
    apres = np.asarray(Image.open(ctx.chemin_clean).convert("RGB"))
    source = np.asarray(_planche_source())
    bande = (slice(boite[1] + 5, boite[1] + 20), slice(boite[0] + 100, boite[0] + 140))
    assert np.array_equal(apres[bande], source[bande]), "le dessin n'a pas été rendu"


def test_retailler_sans_contexte_ne_touche_pas_au_nettoyage(planche):
    """Le mode « cache seul » reste légitime : c'est celui d'un script qui ne fait que
    réordonner, et celui de la plupart de ces tests."""
    assert edition.retailler_zone(planche, 0, _boite(0))["nettoyage"] is None


def test_repeindre_restaure_avant_de_vider(planche_avec_clean):
    """**L'ordre des deux gestes, et pourquoi il n'est pas indifférent.**

    `modifier_zone` et `retailler_zone` passent la MÊME bulle des deux côtés : son ancienne
    emprise à restaurer, sa nouvelle à vider. Vider en premier puis restaurer recollait le
    japonais de la source par-dessus la zone fraîchement nettoyée — la bulle ressortait avec
    son texte d'origine, sous lequel le lettrage écrivait ensuite le français. Le défaut était
    invisible en lisant `modifier_zone`, dont la docstring promet déjà cet ordre-ci."""
    ckpt, ctx, _zone3 = planche_avec_clean
    boite = _boite(0)
    edition.retailler_zone(ckpt, 0, (boite[0] - 8, boite[1] - 8, boite[2] + 8, boite[3] + 8),
                           ctx=ctx)
    assert _uni(ctx.chemin_clean, boite), "le japonais est réapparu sous la bulle"
