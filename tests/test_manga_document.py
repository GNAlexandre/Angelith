# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le document tamponné — rien n'est écrit avant `enregistrer()`, et tout s'annule.

Jusqu'ici chaque geste de l'éditeur écrivait immédiatement : ajouter une zone réécrivait quatre
fichiers, corriger une réplique un cinquième. C'était honnête et sans surprise, mais cela
rendait impossible ce qu'on attend d'un éditeur — hésiter, essayer, revenir en arrière, et ne
valider qu'à la fin.

Ce que ces tests protègent :

- **rien sur le disque avant l'enregistrement** — c'est la promesse entière du lot ;
- **l'historique est exact** — un instantané partagé ne doit pas laisser une opération ultérieure
  corrompre un état passé, ce qui arriverait si un masque était muté en place ;
- **le contrôle de fraîcheur** — un run qui a retouché la planche pendant la session fait
  refuser l'écriture plutôt qu'écraser ;
- **le cœur pur est bien partagé** avec `manga/edition.py`, sinon les deux chemins divergeraient
  sur la question qui compte : qu'est-ce qui est conservé, qu'est-ce qui est perdu.

Aucun modèle, aucun LLM, aucun serveur : on écrit un cache à la main et on relit ce qui en sort.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import checkpoints, document
from manga.detection import BubbleRegion

TAILLE = (400, 900)


def _boite(k: int) -> tuple[int, int, int, int]:
    """Bulles empilées verticalement, franchement séparées : l'ordre de lecture est alors
    l'ordre des index, et les tests ne dépendent pas de la coupe X-Y."""
    haut = 40 + k * 250
    return (60, haut, 340, haut + 180)


def _masque(bbox) -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse([bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1], fill=255)
    return np.asarray(m) > 127


def _region(k: int, score: float = 0.9) -> BubbleRegion:
    b = _boite(k)
    return BubbleRegion(bbox=b, mask=_masque(b), score=score, cls=0)


@pytest.fixture
def ckpt(tmp_path):
    """Trois bulles, OCR et traduction en cache, une correction manuelle sur la 3e."""
    d = tmp_path / "page_0001"
    checkpoints.save_regions(d, [_region(k) for k in range(3)], TAILLE)
    checkpoints.save_ocr(d, ["アアア", "イイイ", "ウウウ"])
    checkpoints.save_traduction(d, ["Un", "Deux", "Trois"])
    checkpoints.save_traduction_manuelle(d, {2: "Trois, à la main"})
    (d / checkpoints.QA_FILENAME).write_text("{}", encoding="utf-8")
    return d


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #

def test_lire_etat_charge_tout(ckpt):
    etat = document.lire_etat(ckpt)
    assert len(etat.regions) == 3
    assert etat.ocr == ["アアア", "イイイ", "ウウウ"]
    assert etat.traduction == ["Un", "Deux", "Trois"]
    assert etat.manuelles == {2: "Trois, à la main"}
    assert etat.taille == TAILLE


def test_un_cache_de_textes_plus_court_est_aligne(tmp_path):
    """Une traduction partielle existe — un run interrompu en laisse. La laisser courte ferait
    lever à la première lecture indexée."""
    d = tmp_path / "page_0001"
    checkpoints.save_regions(d, [_region(k) for k in range(3)], TAILLE)
    checkpoints.save_traduction(d, ["Un"])
    etat = document.lire_etat(d)
    assert etat.traduction == ["Un", "", ""]
    assert etat.ocr == ["", "", ""]


def test_une_planche_sans_detection_est_refusee_clairement(tmp_path):
    with pytest.raises(document.ErreurDocument, match="détectée"):
        document.lire_etat(tmp_path / "vide")


# --------------------------------------------------------------------------- #
# Rien n'est écrit avant l'enregistrement
# --------------------------------------------------------------------------- #

def _empreinte(d):
    return {p.name: p.read_bytes() for p in sorted(d.iterdir())}


def test_aucune_ecriture_avant_enregistrer(ckpt):
    """La promesse entière du lot."""
    avant = _empreinte(ckpt)
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "Ma version")
    doc.poser_traduction(1, "Autre chose")
    doc.poser_mise_en_page(0, {"rect": [10, 10, 100, 60], "taille": 18})

    assert doc.modifie
    assert _empreinte(ckpt) == avant, "le disque ne doit pas avoir bougé"


def test_enregistrer_ecrit_tout_d_un_coup(ckpt):
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "Ma version")
    doc.poser_traduction(1, "Autre chose")
    doc.poser_mise_en_page(0, {"rect": [10, 10, 100, 60], "taille": 18})
    doc.enregistrer()

    assert checkpoints.load_traduction_manuelle(ckpt)[0] == "Ma version"
    assert checkpoints.load_traduction(ckpt)[1] == "Autre chose"
    assert checkpoints.load_mise_en_page(ckpt)[0]["taille"] == 18
    assert not doc.modifie


def test_enregistrer_supprime_le_qa(ckpt):
    """`qa.json` décrit le rendu PRÉCÉDENT : après une édition il ne décrit plus rien."""
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "Ma version")
    doc.enregistrer()
    assert not (ckpt / checkpoints.QA_FILENAME).exists()


def test_abandonner_jette_tout_et_relit_le_disque(ckpt):
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "Ma version")
    doc.abandonner()

    assert not doc.modifie
    assert doc.etat.manuelles == {2: "Trois, à la main"}
    assert not doc.peut_annuler


def test_une_correction_vide_reste_une_decision(ckpt):
    """Une chaîne vide est un choix éditorial valable — une bulle de silence — et se distingue
    de `None`, qui rend la bulle au modèle."""
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "")
    doc.enregistrer()
    assert checkpoints.load_traduction_manuelle(ckpt) == {0: "", 2: "Trois, à la main"}

    doc.poser_correction(0, None)
    doc.enregistrer()
    assert 0 not in checkpoints.load_traduction_manuelle(ckpt)


# --------------------------------------------------------------------------- #
# Historique
# --------------------------------------------------------------------------- #

def test_annuler_et_refaire(ckpt):
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "Version A")
    doc.poser_correction(0, "Version B")

    assert doc.etat.manuelles[0] == "Version B"
    assert doc.annuler() and doc.etat.manuelles[0] == "Version A"
    assert doc.annuler() and 0 not in doc.etat.manuelles
    assert not doc.annuler(), "on ne remonte pas au-delà de l'ouverture"
    assert doc.refaire() and doc.etat.manuelles[0] == "Version A"
    assert doc.refaire() and doc.etat.manuelles[0] == "Version B"
    assert not doc.refaire()


def test_une_nouvelle_operation_efface_le_futur(ckpt):
    """La règle de tous les éditeurs : repartir dans une autre direction rend le « refaire »
    incompatible, et le rejouer corromprait l'état."""
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_correction(0, "A")
    doc.annuler()
    assert doc.peut_refaire

    doc.poser_correction(1, "B")
    assert not doc.peut_refaire


def test_l_historique_est_borne(ckpt):
    doc = document.DocumentPlanche.ouvrir(ckpt)
    for n in range(document.PROFONDEUR_HISTORIQUE + 20):
        doc.poser_correction(0, f"v{n}")
    assert len(doc._passe) == document.PROFONDEUR_HISTORIQUE


def test_un_instantane_ne_partage_pas_ses_listes(ckpt):
    """Le point délicat du choix « instantanés plutôt qu'inverses » : les MASQUES sont
    partagés (jamais mutés en place), mais les listes et dictionnaires doivent être copiés,
    sinon une opération ultérieure corromprait un état passé."""
    doc = document.DocumentPlanche.ouvrir(ckpt)
    doc.poser_traduction(0, "Neuf")
    doc.poser_correction(1, "Manuel")

    passe = doc._passe[0]
    assert passe.traduction[0] == "Un", "l'état d'origine est intact"
    assert 1 not in passe.manuelles


def test_les_masques_sont_partages_et_non_copies(ckpt):
    """L'autre moitié du choix : copier les masques coûterait ~30 Mo par pas d'historique sur
    une planche de 1440×2048. C'est sûr parce qu'aucune opération ne mute un masque en place."""
    etat = document.lire_etat(ckpt)
    copie = etat.instantane()
    assert copie.regions[0].mask is etat.regions[0].mask
    assert copie.regions is not etat.regions


# --------------------------------------------------------------------------- #
# Le contrôle de fraîcheur
# --------------------------------------------------------------------------- #

def test_une_revision_qui_a_bouge_fait_refuser_l_ecriture(ckpt):
    """Un run qui a retouché la planche pendant la session d'édition l'a fait avancer.
    Écraser serait perdre son travail sans le dire."""
    doc = document.DocumentPlanche.ouvrir(ckpt, revision=3)
    doc.poser_correction(0, "Ma version")

    with pytest.raises(document.ErreurDocument, match="révision"):
        doc.enregistrer(revision_actuelle=4)

    assert doc.modifie, "la modification est conservée, pas jetée"
    assert 0 not in checkpoints.load_traduction_manuelle(ckpt)


def test_une_revision_inchangee_laisse_ecrire(ckpt):
    doc = document.DocumentPlanche.ouvrir(ckpt, revision=3)
    doc.poser_correction(0, "Ma version")
    doc.enregistrer(revision_actuelle=3)
    assert checkpoints.load_traduction_manuelle(ckpt)[0] == "Ma version"


# --------------------------------------------------------------------------- #
# Le cœur pur — celui que `manga/edition.py` partage
# --------------------------------------------------------------------------- #

def test_poser_regions_conserve_les_textes_des_bulles_inchangees(ckpt):
    """LE test du cœur partagé. Ajouter une bulle oubliée ne doit pas jeter les trois
    traductions déjà payées : c'est l'appariement par IoU, pas `invalider_textes`."""
    etat = document.lire_etat(ckpt)
    neuve = BubbleRegion(bbox=(60, 790, 340, 880),
                         mask=_masque((60, 790, 340, 880)), score=1.0, cls=0)
    neuf, rapport = document.poser_regions(etat, list(etat.regions) + [neuve], {3})

    assert rapport["regions"] == 4
    assert neuf.traduction == ["Un", "Deux", "Trois", ""]
    assert rapport["indices_a_relire"] == [3]
    assert rapport["textes_conserves"] == 3
    assert neuf.manuelles == {2: "Trois, à la main"}


def test_poser_regions_remappe_les_cles_quand_l_ordre_change(ckpt):
    """Le cas qui casse un report naïf : la nouvelle bulle se lit EN PREMIER, donc toutes les
    autres changent d'index — y compris la clé de la correction manuelle et de la mise en page."""
    etat = document.lire_etat(ckpt)
    etat.mises_en_page = {2: {"rect": [1, 2, 3, 4], "taille": 20}}
    tete = BubbleRegion(bbox=(60, 5, 340, 35), mask=_masque((60, 5, 340, 35)),
                        score=1.0, cls=0)
    neuf, _rapport = document.poser_regions(etat, [tete] + list(etat.regions), {0})

    assert neuf.traduction == ["", "Un", "Deux", "Trois"]
    assert neuf.manuelles == {3: "Trois, à la main"}
    assert neuf.mises_en_page == {3: {"rect": [1, 2, 3, 4], "taille": 20}}


def test_poser_regions_est_pur(ckpt):
    """Il ne doit RIEN écrire : c'est ce qui permet au document de l'appeler sans s'engager."""
    avant = _empreinte(ckpt)
    etat = document.lire_etat(ckpt)
    neuve = BubbleRegion(bbox=(60, 790, 340, 880),
                         mask=_masque((60, 790, 340, 880)), score=1.0, cls=0)
    document.poser_regions(etat, list(etat.regions) + [neuve], {3})
    assert _empreinte(ckpt) == avant


def test_une_zone_entierement_contenue_est_refusee(ckpt):
    """Elle n'aurait aucun pixel à elle après la mise en disjonction. Le dire, plutôt que
    d'annoncer un succès et de ne rien faire."""
    etat = document.lire_etat(ckpt)
    dedans = (150, 100, 250, 180)
    interieure = BubbleRegion(bbox=dedans, mask=_masque(dedans), score=1.0, cls=0)
    with pytest.raises(document.ErreurDocument, match="entièrement contenue"):
        document.poser_regions(etat, list(etat.regions) + [interieure], {3})


def test_les_masques_restent_disjoints(ckpt):
    """`masks.png` est une image d'ÉTIQUETTES : deux masques qui se recouvrent verraient le
    second effacer le premier au rechargement, sans que rien ne le signale."""
    etat = document.lire_etat(ckpt)
    chevauchante = (60, 100, 340, 300)
    neuve = BubbleRegion(bbox=chevauchante, mask=_masque(chevauchante), score=1.0, cls=0)
    neuf, _r = document.poser_regions(etat, list(etat.regions) + [neuve], {3})

    masques = [r.mask for r in neuf.regions]
    for i in range(len(masques)):
        for j in range(i + 1, len(masques)):
            assert not (masques[i] & masques[j]).any()


def test_le_document_enchaine_regions_et_textes(ckpt):
    """Un scénario complet : ajouter une zone, la traduire, corriger une autre, annuler une
    fois, enregistrer. Rien ne doit toucher le disque avant la fin."""
    avant = _empreinte(ckpt)
    doc = document.DocumentPlanche.ouvrir(ckpt)
    neuve = BubbleRegion(bbox=(60, 790, 340, 880),
                         mask=_masque((60, 790, 340, 880)), score=1.0, cls=0)
    doc.poser_regions(list(doc.etat.regions) + [neuve], {3})
    doc.poser_traduction(3, "Quatre")
    doc.poser_correction(0, "Un, revu")
    doc.annuler()                                   # retire la correction, garde la zone

    assert _empreinte(ckpt) == avant
    doc.enregistrer()

    assert len(checkpoints.load_regions(ckpt)) == 4
    assert checkpoints.load_traduction(ckpt)[3] == "Quatre"
    assert checkpoints.load_traduction_manuelle(ckpt) == {2: "Trois, à la main"}
    assert checkpoints.load_origines(ckpt)[3] == checkpoints.ORIGINE_EDITEUR


def test_sans_changement_de_region_masks_png_n_est_pas_reecrit(ckpt):
    """Le seul écrit coûteux du lot est le PNG d'étiquettes pleine page. Corriger une réplique
    ne doit pas le payer."""
    doc = document.DocumentPlanche.ouvrir(ckpt)
    avant = (ckpt / "masks.png").stat().st_mtime_ns
    doc.poser_correction(0, "Ma version")
    doc.enregistrer()
    assert (ckpt / "masks.png").stat().st_mtime_ns == avant


def test_edition_et_document_donnent_le_meme_resultat(ckpt, tmp_path):
    """Les deux chemins partagent `poser_regions` — ce test tombe si l'un des deux regagne sa
    propre copie de la règle « qu'est-ce qui est conservé, qu'est-ce qui est perdu »."""
    from manga import edition

    jumeau = tmp_path / "page_0002"
    jumeau.mkdir()
    for p in ckpt.iterdir():
        (jumeau / p.name).write_bytes(p.read_bytes())

    edition.ajouter_zone(ckpt, (60, 790, 340, 880), forme="ellipse")

    etat = document.lire_etat(jumeau)
    neuve = BubbleRegion(bbox=(60, 790, 340, 880),
                         mask=edition.masque_de_forme("ellipse", (60, 790, 340, 880), TAILLE),
                         score=1.0, cls=0)
    doc = document.DocumentPlanche(jumeau, etat)
    doc.poser_regions(list(etat.regions) + [neuve], {3})
    doc.enregistrer()

    assert checkpoints.load_traduction(ckpt) == checkpoints.load_traduction(jumeau)
    assert checkpoints.load_ocr(ckpt) == checkpoints.load_ocr(jumeau)
    assert (checkpoints.load_traduction_manuelle(ckpt)
            == checkpoints.load_traduction_manuelle(jumeau))
    assert len(checkpoints.load_regions(ckpt)) == len(checkpoints.load_regions(jumeau))


# --------------------------------------------------------------------------- #
# `relire=False` — retailler sans jeter le texte
# --------------------------------------------------------------------------- #
#
# `touchees` portait DEUX rôles : marquer ce qui doit être relu, et garder contre une zone
# entièrement contenue dans une voisine. Conserver les textes en passant `touchees=set()`
# aurait donc désarmé la garde du même coup — d'où un paramètre séparé, et d'où ces tests.

def _decalee(region: BubbleRegion, dx: int, dy: int) -> BubbleRegion:
    """La même région, translatée. L'appariement par IoU doit continuer d'y voir la même
    bulle tant que le recouvrement reste franc."""
    x0, y0, x1, y1 = region.bbox
    return BubbleRegion(bbox=(x0 + dx, y0 + dy, x1 + dx, y1 + dy),
                        mask=np.roll(region.mask, (dy, dx), axis=(0, 1)),
                        score=region.score, cls=region.cls)


def test_relire_faux_conserve_les_textes_des_zones_touchees(ckpt):
    """Ce qui sépare « retailler » de « redessiner ». Ajuster une bulle de quelques pixels ne
    change pas ce qui y est écrit ; lui refaire payer OCR et traduction rendrait le
    redimensionnement par poignées inutilisable."""
    etat = document.lire_etat(ckpt)
    nouvelles = list(etat.regions)
    nouvelles[1] = _decalee(nouvelles[1], 6, 6)

    neuf, rapport = document.poser_regions(etat, nouvelles, {1}, relire=False)

    assert neuf.traduction == ["Un", "Deux", "Trois"]
    assert neuf.ocr == ["アアア", "イイイ", "ウウウ"]
    assert rapport["indices_a_relire"] == []
    assert rapport["textes_conserves"] == 3
    assert neuf.manuelles == {2: "Trois, à la main"}


def test_le_defaut_jette_toujours_le_texte_touche(ckpt):
    """L'additivité : sans le mot-clé, `poser_regions` se comporte exactement comme avant."""
    etat = document.lire_etat(ckpt)
    nouvelles = list(etat.regions)
    nouvelles[1] = _decalee(nouvelles[1], 6, 6)

    neuf, rapport = document.poser_regions(etat, nouvelles, {1})

    assert neuf.traduction[1] == "" and neuf.ocr[1] == ""
    assert rapport["indices_a_relire"] == [1]


def test_le_rapport_nomme_les_indices_touches(ckpt):
    """C'est de cette clé que `edition._reecrire` tire les zones à repeindre dans
    `pages_clean/`. Avec `relire=False`, `indices_a_relire` est vide alors que les pixels ont
    bel et bien bougé — s'y fier laisserait la planche nettoyée en désaccord avec son masque."""
    etat = document.lire_etat(ckpt)
    nouvelles = list(etat.regions)
    nouvelles[2] = _decalee(nouvelles[2], 5, 5)

    _neuf, rapport = document.poser_regions(etat, nouvelles, {2}, relire=False)
    assert rapport["indices_touches"] == [2]


def test_relire_faux_garde_la_garde_de_zone_contenue(ckpt):
    """**Le test qui justifie le paramètre séparé.**

    Si l'on avait conservé les textes en passant `touchees=set()`, cette garde aurait disparu
    du même coup et la zone avalée serait sortie sans un pixel à elle, en silence."""
    etat = document.lire_etat(ckpt)
    dedans = (150, 100, 250, 180)
    interieure = BubbleRegion(bbox=dedans, mask=_masque(dedans), score=1.0, cls=0)

    with pytest.raises(document.ErreurDocument, match="entièrement contenue"):
        document.poser_regions(etat, list(etat.regions) + [interieure], {3}, relire=False)


def test_relire_faux_perd_le_texte_d_une_zone_trop_deplacee(ckpt):
    """L'appariement par IoU reste seul juge : conserver le texte n'est pas le conserver
    inconditionnellement. Une zone traînée sur une autre bulle n'est plus la même bulle."""
    etat = document.lire_etat(ckpt)
    nouvelles = list(etat.regions)
    nouvelles[0] = _decalee(nouvelles[0], 0, 700)

    neuf, _rapport = document.poser_regions(etat, nouvelles, {0}, relire=False)
    assert "Un" not in neuf.traduction


# ─────────────────────────────────────────────────────────────────────────────
# Sens de lecture — l'édition ne doit JAMAIS re-trier une planche à l'envers
#
# `poser_regions` appelait `reading_order()` sans le sens, donc toujours droite→gauche. Sur un
# webtoon (`gauche_droite`), la moindre édition de zone re-triait toute la planche en ordre
# manga : un mélange massif des répliques, et silencieux — le nombre de bulles restait juste et
# `regions.json` continuait d'annoncer le bon sens.
# ─────────────────────────────────────────────────────────────────────────────

def _cote_a_cote() -> tuple[BubbleRegion, BubbleRegion]:
    """Deux bulles COTE À COTE — le seul cas où le sens de lecture change le résultat."""
    gauche = (20, 40, 180, 220)
    droite = (220, 40, 380, 220)
    return (BubbleRegion(bbox=gauche, mask=_masque(gauche), score=0.9, cls=0),
            BubbleRegion(bbox=droite, mask=_masque(droite), score=0.9, cls=0))


@pytest.mark.parametrize("sens, attendu", [
    ("droite_gauche", ["Droite", "Gauche"]),
    ("gauche_droite", ["Gauche", "Droite"]),
])
def test_poser_regions_trie_dans_le_sens_de_la_planche(sens, attendu):
    gauche, droite = _cote_a_cote()
    etat = document.EtatPlanche(
        regions=[gauche, droite], ocr=["G", "D"], traduction=["Gauche", "Droite"],
        taille=TAILLE, sens=sens)
    neuf, _rapport = document.poser_regions(etat, [gauche, droite], set(), relire=False)
    assert neuf.traduction == attendu
    assert neuf.sens == sens, "le sens doit survivre à l'opération"


def test_les_corrections_suivent_le_tri_dans_les_deux_sens():
    """Les dicts creux (`manuelles`) sont indexés par bulle : ils doivent suivre le tri."""
    gauche, droite = _cote_a_cote()
    for sens, index_attendu in (("droite_gauche", 1), ("gauche_droite", 0)):
        etat = document.EtatPlanche(
            regions=[gauche, droite], ocr=["G", "D"], traduction=["Gauche", "Droite"],
            manuelles={0: "ma correction sur la gauche"}, taille=TAILLE, sens=sens)
        neuf, _r = document.poser_regions(etat, [gauche, droite], set(), relire=False)
        assert neuf.manuelles == {index_attendu: "ma correction sur la gauche"}, sens


def test_lire_etat_remonte_le_sens_du_cache(tmp_path):
    d = tmp_path / "page_0001"
    checkpoints.save_regions(d, [_region(0)], TAILLE, sens="gauche_droite")
    assert document.lire_etat(d).sens == "gauche_droite"


def test_le_sens_par_defaut_reste_le_manga(tmp_path):
    """Un cache écrit avant que le champ n'existe : rien ne change pour lui."""
    d = tmp_path / "page_0001"
    checkpoints.save_regions(d, [_region(0)], TAILLE)
    assert document.lire_etat(d).sens == checkpoints.SENS_HISTORIQUE == "droite_gauche"


def test_ecrire_etat_conserve_le_sens(tmp_path):
    d = tmp_path / "page_0001"
    checkpoints.save_regions(d, [_region(0)], TAILLE, sens="gauche_droite")
    etat = document.lire_etat(d)
    document.ecrire_etat(d, etat)
    assert checkpoints.sens_enregistre(d) == "gauche_droite"


def test_ajouter_une_zone_ne_retourne_pas_un_webtoon(tmp_path):
    """Bout en bout par le chemin réel de l'éditeur : `edition.ajouter_zone`."""
    from manga import edition

    d = tmp_path / "page_0001"
    gauche, droite = _cote_a_cote()
    checkpoints.save_regions(d, [gauche, droite], TAILLE, sens="gauche_droite")
    checkpoints.save_ocr(d, ["G", "D"])
    checkpoints.save_traduction(d, ["Gauche", "Droite"])

    edition.ajouter_zone(d, (20, 500, 180, 660), forme="rectangle")

    etat = document.lire_etat(d)
    assert etat.sens == "gauche_droite"
    # Les deux premières gardent leur ordre gauche→droite et leur texte ; la neuve est en bas.
    assert etat.traduction[:2] == ["Gauche", "Droite"]
    assert len(etat.regions) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Masques disjoints — le correctif du « une bulle cache le texte de l'autre »
#
# `masks.png` est une image d'ÉTIQUETTES : un pixel partagé va à la dernière bulle écrite, et le
# masque de l'autre revient amputé au rechargement, en silence et définitivement. Mesuré sur
# *webtoon A* Chap.11 planche 3 : deux bulles se recouvraient sur 36 108 px.
# `rendre_disjoints` existait, mais n'était câblée que sur l'éditeur.
# ─────────────────────────────────────────────────────────────────────────────

def _bloc(x0, y0, x1, y1, score=0.9) -> BubbleRegion:
    m = np.zeros((TAILLE[1], TAILLE[0]), dtype=bool)
    m[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=score, cls=0)


def test_rendre_disjoints_attribue_le_recouvrement_au_premier():
    a = _bloc(0, 0, 200, 200)
    b = _bloc(100, 100, 300, 300)
    sorties, origines = document.rendre_disjoints([a, b])
    assert origines == [0, 1]
    assert int(sorties[0].mask.sum()) == int(a.mask.sum()), "le premier garde tout"
    chevauchement = 100 * 100
    assert int(sorties[1].mask.sum()) == int(b.mask.sum()) - chevauchement


def test_rendre_disjoints_recalcule_la_bbox_du_masque_rogne():
    """Sans ce recalcul, bbox et masque divergent — et le rayon d'érosion du nettoyeur, qui se
    calcule sur la bbox, serait surdimensionné pour la forme réelle."""
    a = _bloc(0, 0, 300, 100)
    b = _bloc(0, 0, 300, 300)          # entièrement recouverte sur sa partie haute
    sorties, _o = document.rendre_disjoints([a, b])
    assert sorties[1].bbox[1] == 100, "la bbox suit le masque rogné"


def test_une_region_entierement_recouverte_disparait_et_les_index_suivent():
    a = _bloc(0, 0, 300, 300)
    dedans = _bloc(50, 50, 150, 150)
    c = _bloc(0, 400, 100, 500)
    sorties, origines = document.rendre_disjoints([a, dedans, c])
    assert len(sorties) == 2
    assert origines == [0, 2], "l'index d'origine dit QUI a disparu"


def test_des_bulles_qui_ne_se_touchent_pas_sont_inchangees():
    a, b = _bloc(0, 0, 100, 100), _bloc(200, 200, 300, 300)
    sorties, origines = document.rendre_disjoints([a, b])
    assert origines == [0, 1]
    assert [int(r.mask.sum()) for r in sorties] == [int(a.mask.sum()), int(b.mask.sum())]


def test_le_tri_par_score_decide_qui_garde_les_pixels():
    """C'est l'arbitrage retenu dans le pipeline : la bulle la mieux notée garde son masque."""
    faible = _bloc(0, 0, 200, 200, score=0.40)
    forte = _bloc(100, 100, 300, 300, score=0.95)
    tries = sorted([faible, forte], key=lambda r: -r.score)
    sorties, origines = document.rendre_disjoints(tries)
    gagnante = sorties[origines.index(0)]
    assert gagnante.score == 0.95
    assert int(gagnante.mask.sum()) == int(forte.mask.sum())
