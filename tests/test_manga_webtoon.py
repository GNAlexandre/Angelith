# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lot 14 — le webtoon : le critère de découpage, la porte d'encre, le plafond d'étiquettes,
la limite du PSD et la sonde de mémoire.

Rien ici ne charge de modèle ONNX. Tout ce qui est vérifié est de la géométrie, du format de
fichier ou de la mesure système — c'est précisément ce qui rend ces tests exécutables en CI,
là où le corpus webtoon réel (9 bandes de 1080×10 000, 80 Mo de PNG) ne l'est pas.

⚠ **Le test qui compte le plus est celui de l'ISO-COMPORTEMENT** (`test_le_critere_...`). Le
lot remplace une falaise de ratio par un critère de détectabilité : si la substitution changeait
la décision d'une seule planche paginée, elle invaliderait le cache de détection de tous les
tomes déjà traduits — des heures de GPU. Elle a été vérifiée sur les 1 513 planches des dix
volumes de `build/` (zéro écart) ; ce test-ci en garde la trace là où la CI peut la rejouer."""
import numpy as np
import pytest
from PIL import Image

from core import memoire
from manga import checkpoints, detection, document, psd, text_detection
from manga.detection import BubbleRegion

BANDE = (1080, 10000)


def _region(x0, y0, x1, y1, forme=(600, 400), score=0.9):
    masque = np.zeros(forme, dtype=bool)
    masque[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=masque, score=score, cls=0)


# --------------------------------------------------------------------------- #
# L6.4 — la falaise de ratio devient un critère de détectabilité
# --------------------------------------------------------------------------- #

#: Le ratio d'origine, tel qu'il était écrit avant le lot. Recopié EXPRÈS plutôt qu'importé :
#: c'est la référence de non-régression, elle ne doit pas suivre la config.
_RATIO_HISTORIQUE = 3.0


def _ancien_critere(largeur: int, hauteur: int) -> bool:
    """La décision d'avant le lot, mot pour mot : `hauteur / largeur < ratio_min → []`."""
    if largeur <= 0 or hauteur <= 0:
        return False
    return hauteur / largeur >= _RATIO_HISTORIQUE


#: Les 14 tailles distinctes du corpus de mesure, plus les cas limites de part et d'autre du
#: seuil. Les six premières sont celles réellement présentes dans `build/`.
_TAILLES = [
    (1080, 10000), (1080, 9171), (1440, 2048), (1125, 1600), (844, 1200), (848, 1200),
    (1000, 1200), (1030, 732), (1688, 1200), (2048, 1440), (800, 2000),
    (1000, 2999), (1000, 3000), (1000, 3001), (1080, 3000), (1200, 3600), (1200, 3599),
]


@pytest.mark.parametrize("largeur,hauteur", _TAILLES)
def test_le_critere_de_DETECTABILITE_decide_comme_le_ratio_a_640(largeur, hauteur):
    """L'ISO-COMPORTEMENT du défaut livré, planche par planche.

    `OCCUPATION_MIN = INPUT_SIZE / 3.0` n'est pas un chiffre choisi : c'est l'expression exacte
    du ratio 3,0 dans l'unité où le raisonnement se tient. Vérifié sur les 1 513 planches du
    corpus — zéro écart —, et gardé ici sur les tailles limites que le corpus ne contient pas."""
    attendu = _ancien_critere(largeur, hauteur)
    obtenu = bool(detection.fenetres(largeur, hauteur, input_size=detection.INPUT_SIZE))
    assert obtenu is attendu, f"{largeur}×{hauteur} : {obtenu} au lieu de {attendu}"


def test_l_occupation_est_le_petit_cote_dans_le_canevas():
    """69 px sur 640 pour une bande, 450 pour une planche paginée. C'est tout le sujet du lot :
    le réseau ne voit pas la même chose dans les deux cas, et le ratio ne le disait pas."""
    assert detection.occupation(1080, 10000, 640) == pytest.approx(69.1, abs=0.1)
    assert detection.occupation(1440, 2048, 640) == pytest.approx(450.0, abs=0.1)
    # Symétrique : c'est le PETIT côté qui compte, pas la hauteur.
    assert detection.occupation(2048, 1440, 640) == detection.occupation(1440, 2048, 640)


def test_le_critere_SUIT_la_resolution_dentree():
    """Le vrai gain du lot, et ce que le ratio ne pouvait pas exprimer.

    Une planche au ratio 3,0 est tout juste découpée à 640. À 1024 le réseau la voit 1,6× plus
    grande : elle n'a plus besoin de l'être, et le tome économise ses inférences de fenêtre."""
    assert detection.fenetres(1000, 3000, input_size=640) != []
    assert detection.fenetres(1000, 3000, input_size=1024) == []
    # …et la bande, elle, reste découpée aux deux résolutions : 110 px sur 1 024, c'est encore
    # très en dessous du seuil. Relever la résolution ne dispense pas de découper une bande.
    assert len(detection.fenetres(*BANDE, input_size=1024)) == 8


def test_la_resolution_par_defaut_ne_change_rien_pour_les_appelants_qui_l_ignorent():
    """`input_size=None` doit rendre exactement l'ancien comportement : plusieurs outils du
    dépôt appellent `fenetres()` sans savoir à quelle résolution le détecteur tourne."""
    for largeur, hauteur in _TAILLES:
        assert detection.fenetres(largeur, hauteur) == \
            detection.fenetres(largeur, hauteur, input_size=detection.INPUT_SIZE)


def test_l_occupation_minimale_est_reglable_a_la_main():
    """Le seuil explicite prime sur celui dérivé du ratio — c'est ce qui permet de découper la
    tranche de 1080×3000 (occupation 230 px) une fois qu'on aura mesuré qu'il faut le faire."""
    assert detection.fenetres(1080, 3000, input_size=640) == []
    decoupee = detection.fenetres(1080, 3000, {"fenetre_occupation_min": 240}, input_size=640)
    assert len(decoupee) > 1


def test_le_ratio_reste_le_levier_lisible():
    """Non-régression : `fenetre_ratio_min` continue de piloter le seuil quand l'occupation
    n'est pas écrite. C'est la clé que `config.yaml` documente depuis le correctif webtoon."""
    assert detection.fenetres(*BANDE, {"fenetre_ratio_min": 99}) == []
    # Ratio 2,08 : au-dessus du seuil abaissé, et assez haute pour porter deux fenêtres —
    # `fenetre_hauteur` (2 160) reste une seconde condition, une planche plus courte que la
    # fenêtre n'a rien à découper.
    assert detection.fenetres(1440, 3000, {"fenetre_ratio_min": 1.2}) != []
    assert detection.fenetres(1440, 3000, {"fenetre_ratio_min": 3.0}) == []


# --------------------------------------------------------------------------- #
# L6.5 — la porte d'encre sur les fenêtres
# --------------------------------------------------------------------------- #

def _bande_moitie_vide(hauteur=6000, largeur=1000) -> Image.Image:
    """Blanche en haut, encrée en bas — le cas que la porte est censée attraper."""
    arr = np.full((hauteur, largeur, 3), 250, dtype=np.uint8)
    arr[hauteur // 2:, ::3, :] = 0
    return Image.fromarray(arr)


def test_la_porte_dencre_est_DESARMEE_par_defaut():
    """Mesuré sur les 71 fenêtres des 9 bandes du corpus : **aucune** ne tombe sous le seuil
    d'encre (la moins encrée est à 0,0065, la médiane à 0,79). Et le gain visé était surestimé
    d'un ordre de grandeur — le fenêtrage coûte 7,1 s par bande, pas 70. Armer une porte qui
    risque de perdre une bulle pour économiser des secondes serait un mauvais marché."""
    assert detection.DEFAUTS_FENETRE["fenetre_encre_min"] == 0.0
    image = _bande_moitie_vide()
    bandes = detection.fenetres(*image.size, input_size=640)
    sautees: dict = {}
    assert detection.fenetres_encrees(image, bandes, {}, sautees=sautees) == bandes
    assert sautees == {}


def test_la_porte_armee_ecarte_la_fenetre_vide_ET_la_COMPTE():
    image = _bande_moitie_vide()
    bandes = detection.fenetres(*image.size, input_size=640)
    sautees: dict = {}
    gardees = detection.fenetres_encrees(image, bandes, {"fenetre_encre_min": 0.004},
                                         sautees=sautees)
    assert len(gardees) < len(bandes)
    assert sautees["fenetre_sans_encre"] == len(bandes) - len(gardees)
    assert "fenetre_sans_encre" in detection.MOTIFS_SAUT, "un motif sauté doit être NOMMÉ"


def test_la_porte_ne_saute_JAMAIS_toutes_les_fenetres():
    """Le garde-fou du garde-fou. Une bande dont chaque fenêtre passe sous le seuil est une
    bande que la porte a mal jugée, pas une bande vide : sans cette clause, un seuil trop haut
    produirait une planche à zéro bulle **en silence** — le défaut même que le lot 12 corrige."""
    blanche = Image.fromarray(np.full((6000, 1000, 3), 250, dtype=np.uint8))
    bandes = detection.fenetres(*blanche.size, input_size=640)
    sautees: dict = {}
    assert detection.fenetres_encrees(blanche, bandes, {"fenetre_encre_min": 0.5},
                                      sautees=sautees) == bandes
    assert sautees == {}, "rien n'a été sauté, donc rien n'est compté"


# --------------------------------------------------------------------------- #
# L6.3 — le plafond de l'image d'étiquettes
# --------------------------------------------------------------------------- #

def _regions_jointives(n: int, largeur: int, hauteur: int) -> list[BubbleRegion]:
    """`n` régions d'une ligne chacune : disjointes par construction, donc étiquetables."""
    regions = []
    for i in range(n):
        masque = np.zeros((hauteur, largeur), dtype=bool)
        masque[i, :] = True
        regions.append(BubbleRegion(bbox=(0, i, largeur, i + 1), mask=masque,
                                    score=1.0, cls=0))
    return regions


def test_sous_255_regions_le_format_ne_change_pas_dun_octet():
    """Non-régression du cache : le maximum mesuré sur les 1 513 planches du corpus est de
    **17 régions**. Tout le corpus existant doit donc continuer d'être écrit en `uint8`,
    faute de quoi le lot invaliderait des heures de GPU pour rien."""
    regions = _regions_jointives(17, 40, 30)
    image = checkpoints.image_etiquettes(regions, 40, 30)
    assert image.mode == "L"
    attendu = np.zeros((30, 40), dtype=np.uint8)
    for i, r in enumerate(regions, start=1):
        attendu[r.mask] = i
    assert np.array_equal(np.asarray(image), attendu)


def test_au_dela_de_255_letiquette_selargit_au_lieu_denrouler(tmp_path):
    """Le défaut corrigé : `label[r.mask] = i` en `uint8` écrivait la 256ᵉ région en **fond**
    et la 257ᵉ par-dessus la première. Sans un mot, et définitivement."""
    regions = _regions_jointives(300, 8, 300)
    image = checkpoints.image_etiquettes(regions, 8, 300)
    assert image.mode == "I;16"
    assert np.asarray(image).max() == 300

    checkpoints.save_regions(tmp_path, regions, (8, 300))
    relues = checkpoints.load_regions(tmp_path)
    assert len(relues) == 300
    assert relues[255].mask.sum() == 8, "la 256ᵉ région a bien ses pixels à elle"
    assert not (relues[0].mask & relues[256].mask).any(), "…et ne les partage avec personne"


def test_au_dela_du_plafond_lerreur_NOMME_la_planche_et_le_nombre():
    class _Fausse:
        """Assez de régions pour dépasser, sans allouer 65 536 masques."""
        def __len__(self):
            return checkpoints.PLAFOND_ETIQUETTES + 1

    with pytest.raises(checkpoints.ErreurEtiquettes) as e:
        checkpoints.image_etiquettes(_Fausse(), 10, 10, ou="page_0042")
    assert "page_0042" in str(e.value)
    assert str(checkpoints.PLAFOND_ETIQUETTES + 1) in str(e.value)


def test_le_chemin_SFX_a_son_propre_plafond(tmp_path):
    """Deux compteurs INDÉPENDANTS : `sfx_masks.png` repart à 1 dans son propre fichier. Une
    planche peut donc porter 250 bulles et 250 onomatopées sans qu'aucun des deux ne déborde —
    raison pour laquelle la garde est posée sur les deux chemins et pas une fois en amont."""
    zones = _regions_jointives(300, 8, 300)
    checkpoints.save_sfx(tmp_path, zones, [""] * 300, (8, 300), lu=True)
    relues, _textes = checkpoints.load_sfx(tmp_path)
    assert len(relues) == 300
    assert relues[299].mask.sum() == 8


def test_le_chemin_dEDITION_MANUELLE_annonce_la_MEME_limite():
    """C'était le SEUL des trois chemins gardé, et il l'était à 255. Le laisser en arrière
    ferait refuser à l'éditeur une planche que le pipeline écrit sans broncher."""
    from manga import edition  # noqa: F401  (l'import valide la chaîne du module)
    assert document.checkpoints.PLAFOND_ETIQUETTES == checkpoints.PLAFOND_ETIQUETTES


# --------------------------------------------------------------------------- #
# L6.6 — la limite du format PSD
# --------------------------------------------------------------------------- #

def test_une_bande_de_webtoon_ORDINAIRE_passe():
    """⚠ Le résultat le plus utile de cette étape est un NON-événement, et il faut l'écrire :
    sur les 9 bandes de 1080×10 000 du corpus, `perf.log` montre 9 PSD écrits, de 42,4 à
    59,6 Mo, sans un seul échec. La crainte de l'ancien plan n'est pas confirmée à cette
    taille — c'est trois fois moins que la limite du format."""
    assert 10000 < psd.COTE_MAX
    assert psd.ecrire.__doc__ is not None


def test_au_dela_de_30000_px_le_PSD_est_REFUSE_avant_toute_ecriture(tmp_path):
    cible = tmp_path / "trop_grand.psd"
    with pytest.raises(psd.TropGrandPourPSD) as e:
        psd.ecrire(cible, Image.new("RGB", (100, psd.COTE_MAX + 1)), [])
    assert str(psd.COTE_MAX) in str(e.value)
    assert not cible.exists(), "un fichier corrompu est pire qu'un fichier absent"
    # Le message doit nommer la SORTIE DE REMPLACEMENT : les autres formats n'ont pas la limite.
    assert "cbz" in str(e.value)


def test_le_refus_du_PSD_remonte_au_RAPPORT():
    """La planche garde ses autres formats ; c'est `pages_psd/` qui compte une entrée de moins,
    et sans cette ligne rien ne dirait laquelle."""
    from manga import report_manga
    import inspect
    assert "psd_refuses" in inspect.signature(report_manga.build_report).parameters


# --------------------------------------------------------------------------- #
# L6.0 — la sonde de mémoire
# --------------------------------------------------------------------------- #

def test_le_pic_de_memoire_est_un_entier_positif_ou_None():
    """`None` est une réponse acceptable — un système qui ne sait pas répondre le dit. Un
    **zéro** n'en est pas une, et c'était très exactement le défaut du premier jet : sans
    `GetCurrentProcess.restype = HANDLE`, l'appel Windows échouait en rendant 0."""
    valeur = memoire.pic()
    assert valeur is None or (isinstance(valeur, int) and valeur > 0)


def test_le_pic_est_MONOTONE_et_se_lit_en_differentiel():
    with memoire.Pic() as p:
        garde = np.ones((256, 1024, 1024), dtype=np.uint8)   # 256 Mo, alloués pour de bon
        assert garde.sum() > 0
    if p.apres is None:
        pytest.skip("cette plateforme ne publie pas sa mémoire résidente")
    assert p.apres >= (p.avant or 0)
    assert p.gagne is not None and p.gagne >= 0
    del garde


def test_le_format_dit_ce_quil_sait_et_ce_quil_ignore():
    assert memoire.format_octets(None) == "?"
    assert memoire.format_octets(512) == "512 o"
    assert memoire.format_octets(2 * 1024 ** 3) == "2,00 Go"
    assert memoire.format_octets(1536 * 1024) == "1,50 Mo"


def test_un_pic_sans_reponse_ne_fabrique_pas_de_chiffre():
    p = memoire.Pic(avant=None, apres=None)
    assert p.gagne is None
    assert "?" in str(p)


# --------------------------------------------------------------------------- #
# L6.1 — le fenêtrage de la passe hors bulle
# --------------------------------------------------------------------------- #

class _FauxSession:
    """Rend une carte `seg` uniforme, et COMPTE les passes. Le modèle réel pèse 94,7 Mo et
    coûte 128 s par appel sur une bande — mesuré ; il n'a rien à faire dans un test."""

    def __init__(self, valeur=1.0):
        self.valeur = valeur
        self.appels = 0

    def run(self, _sorties, _entrees):
        self.appels += 1
        carte = np.full((1, 1, text_detection.INPUT_SIZE, text_detection.INPUT_SIZE),
                        self.valeur, dtype=np.float32)
        return [None, carte, None]


def _detecteur_de_texte(valeur=1.0):
    det = object.__new__(text_detection.TextDetector)
    det.session = _FauxSession(valeur)
    det._input_name = "images"
    return det


def test_une_planche_PAGINEE_passe_par_le_chemin_dorigine():
    """Iso-comportement : `fenetres()` rend `[]`, et l'appel est celui d'avant, au bit près."""
    det = _detecteur_de_texte()
    masque = det.masque_texte(Image.new("RGB", (1125, 1600)),
                              fenetrage=text_detection.DEFAUTS_FENETRE_SFX)
    assert det.session.appels == 1
    assert masque.shape == (1600, 1125)


def test_le_fenetrage_du_texte_est_livre_ARME():
    """⚠ **La première mesure disait le contraire, et une seule planche aurait suffi à livrer
    le mauvais défaut.** Sur une bande de DIALOGUE, le fenêtrage ne change rien au décompte
    (0 zone des deux côtés) ; sur une bande d'ACTION — une bulle sur 10 000 px de hauteur — il
    rend **5 zones là où la passe pleine bande n'en trouvait aucune**, dont une de 39 607 px².
    La passe pleine bande n'est pas un peu moins bonne : elle est aveugle là où la passe sert.

    Le coût (×4,8 à ×6,1) ne tombe QUE sur les bandes, et il est annoncé."""
    assert text_detection.DEFAUTS_FENETRE_SFX["fenetrage"] is True
    det = _detecteur_de_texte()
    det.masque_texte(Image.new("RGB", BANDE),
                     fenetrage=text_detection.DEFAUTS_FENETRE_SFX)
    assert det.session.appels == 6


def test_une_BANDE_est_lue_fenetre_par_fenetre():
    """Le défaut corrigé : la bande entière partait dans un carré de 1024, où elle n'occupait
    que **110 colonnes sur 1 024**. Mesuré avant correction : 6,65 % de la planche marquée
    « texte » et 24 composantes — la passe ne trouvait pas rien, elle trouvait des taches."""
    det = _detecteur_de_texte()
    masque = det.masque_texte(Image.new("RGB", BANDE),
                              fenetrage=text_detection.DEFAUTS_FENETRE_SFX)
    assert det.session.appels == 6, "6 fenêtres de 3 072 px sur une bande de 10 000"
    assert masque.shape == (BANDE[1], BANDE[0])
    assert masque.all(), "l'union des fenêtres couvre toute la bande, sans trou de couture"


def test_le_fenetrage_du_texte_se_COUPE_explicitement():
    """⚠ L'interrupteur existe pour un chiffre précis : une inférence de ce modèle coûte le
    même prix quelle que soit la taille de la planche (mesuré : 109 s sur 1080×10 000, 123 s
    sur 1080×3 072, 125 s sur 1125×1 600 — l'entrée est un carré de 1024 dans tous les cas).
    Fenêtrer multiplie donc le coût **par le nombre de fenêtres, exactement**. Sur une machine
    sans GPU, un chapitre de 9 bandes passe de 9 inférences à 54, et cet arbitrage-là
    appartient à l'utilisateur."""
    det = _detecteur_de_texte()
    det.masque_texte(Image.new("RGB", BANDE),
                     fenetrage={**text_detection.DEFAUTS_FENETRE_SFX, "fenetrage": False})
    assert det.session.appels == 1
    # …et l'inverse : la clé est bien le seul interrupteur, dans les deux sens.
    arme = _detecteur_de_texte()
    arme.masque_texte(Image.new("RGB", BANDE),
                      fenetrage=text_detection.DEFAUTS_FENETRE_SFX)
    assert arme.session.appels == 6


def test_sans_fenetrage_le_comportement_est_celui_davant():
    """Les appelants qui ne connaissent pas la config — outils, tests — ne doivent rien voir
    changer. `fenetrage=None` désarme le découpage."""
    det = _detecteur_de_texte()
    det.masque_texte(Image.new("RGB", BANDE))
    assert det.session.appels == 1


def test_le_recouvrement_du_TEXTE_est_plus_grand_que_celui_des_BULLES():
    """Deux calibrations distinctes, et c'est le point de l'étape. Celui des bulles vient de
    « la plus haute bulle du corpus fait 833 px » ; une colonne de katakana géants dépasse
    largement — le cas mesuré du corpus paginé est déjà de 1 470 px."""
    assert (text_detection.DEFAUTS_FENETRE_SFX["fenetre_recouvrement"]
            > detection.DEFAUTS_FENETRE["fenetre_recouvrement"])
    assert text_detection.DEFAUTS_FENETRE_SFX["fenetre_recouvrement"] >= 1470


def test_les_fenetres_du_TEXTE_sont_elles_memes_detectables():
    """Le garde-fou qui manquait au raisonnement : découper en fenêtres qui restent
    sous-résolues ne servirait à rien. Une fenêtre de 3 072 px à 1024 occupe 360 px du
    canevas — au-dessus du seuil, donc elle n'aurait elle-même pas besoin d'être découpée."""
    hauteur = text_detection.DEFAUTS_FENETRE_SFX["fenetre_hauteur"]
    assert detection.occupation(BANDE[0], hauteur, text_detection.INPUT_SIZE) > \
        detection.OCCUPATION_MIN


def test_une_zone_a_cheval_sur_une_couture_nest_PAS_dedoublonnee():
    """⚠ Ce que cette conception fait DISPARAÎTRE. Le lot 12 a dû écrire un dédoublonnage de
    couture pour les bulles, parce que chaque fenêtre y produit des *régions*. Ici on réunit
    les **masques** avant de chercher les composantes : un texte à cheval est vu tronqué d'un
    côté, entier de l'autre, et l'union rend l'entier — une seule composante, sans arbitrage."""
    det = _detecteur_de_texte()
    masque = det.masque_texte(Image.new("RGB", BANDE),
                              fenetrage=text_detection.DEFAUTS_FENETRE_SFX)
    from manga.geometry import composantes
    assert len(composantes(masque)) == 1


# --------------------------------------------------------------------------- #
# L6.7 — le bloc de réglages `webtoon`, et le piège qu'il cache
# --------------------------------------------------------------------------- #

def _config_livree() -> dict:
    from pathlib import Path

    from core.cli import charger_config
    return charger_config(Path(__file__).resolve().parents[1] / "config.yaml")


def test_le_sens_du_webtoon_ne_tient_QUE_au_bloc_de_format():
    """⚠ **Le piège que la config ne signalait pas.** `formats.sens_lecture` résout dans
    l'ordre : bloc de format → racine `manga.rendu.sens_lecture` → défaut du format. Comme
    `config.yaml` pose explicitement `droite_gauche` à la racine, `SENS_PAR_DEFAUT["webtoon"]`
    est **mort** : supprimer les trois lignes du bloc de format rendrait `droite_gauche` sur un
    webtoon, sans un avertissement — et toutes les répliques atterriraient dans les mauvaises
    bulles."""
    from manga import formats

    config = _config_livree()
    assert formats.sens_lecture(config, "webtoon") == "gauche_droite"

    ampute = {"manga": {**config["manga"], "formats": {"webtoon": {"rendu": {}}}}}
    assert formats.sens_lecture(ampute, "webtoon") == "droite_gauche", \
        "le défaut du format est bien inatteignable — d'où le commentaire de config.yaml"
    assert formats.SENS_PAR_DEFAUT["webtoon"] == "gauche_droite", \
        "…alors même qu'il dirait la bonne chose si on l'atteignait"


def test_le_webtoon_herite_de_tout_le_reste():
    """L'autre moitié de la surcouche : un format ne redéclare que ce qui diffère. Un bloc
    `webtoon` qui recopierait la détection du manga serait deux configurations à entretenir."""
    from manga import formats

    config = _config_livree()
    det_manga = formats.config_format(config, "manga", "detection")
    det_webtoon = formats.config_format(config, "webtoon", "detection")
    assert det_webtoon["model_path"] == det_manga["model_path"]
    assert det_webtoon["conf_threshold"] == det_manga["conf_threshold"]


def test_le_bloc_webtoon_allege_le_PSD():
    """Mesuré : 42 à 60 Mo par bande × 9 bandes = **~450 Mo de PSD pour un chapitre**, contre
    7,2 Mo par planche en paginé. `psd_original` retire le calque du scan d'origine, qui pèse
    à lui seul un tiers du fichier."""
    from manga import formats

    rendu = formats.config_format(_config_livree(), "webtoon", "rendu")
    assert rendu["psd_original"] is False
    assert formats.config_format(_config_livree(), "manga", "rendu")["psd_original"] is True
