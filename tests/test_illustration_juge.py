# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le juge du `PLAN-25` : l'encodeur, les trois grandeurs, et les planchers.

Aucun test de ce fichier ne charge le modèle ONNX : ils portent sur ce qui décide — le
prétraitement, la définition des trois grandeurs, la dégénérescence à une seule référence, et
le verdict d'utilisabilité. Le modèle réel est mesuré par `tools/banc_identite.py`, sous
marqueurs `modeles` et `lent`.

Le test central est `test_une_seule_reference_rend_les_deux_grandeurs_identiques` : c'est le
fait que le corpus réel impose, et le publier vaut mieux que d'afficher deux colonnes qui se
recopient.
"""
import io
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from illustration import juge as juge_mod


class EncodeurFactice:
    """Un encodeur déterministe sans ONNX : le vecteur dérive du contenu de l'image.

    ⚠ Il n'imite pas DINOv2 et ne prétend rien de la qualité du juge réel. Il rend testable la
    **plomberie** — les trois grandeurs, la dégénérescence, les verdicts — en CI, sans poids
    et sans GPU, exactement comme `MoteurFactice` le fait pour le moteur d'image."""

    def __init__(self, vecteurs=None) -> None:
        self.vecteurs = dict(vecteurs or {})
        self.appels = []

    def encoder(self, image):
        self.appels.append(image)
        cle = self._cle(image)
        if cle in self.vecteurs:
            return juge_mod.normaliser(np.asarray(self.vecteurs[cle], dtype=np.float64))
        return juge_mod.normaliser(np.asarray([len(cle) % 7 + 1.0, 1.0, 0.5]))

    @staticmethod
    def _cle(image):
        if isinstance(image, (bytes, bytearray)):
            return "octets"
        return str(image)


def _png(couleur=(120, 130, 140), taille=(40, 60)) -> bytes:
    tampon = io.BytesIO()
    Image.new("RGB", taille, couleur).save(tampon, format="PNG")
    return tampon.getvalue()


# ────────────────────────────  Le prétraitement  ────────────────────────────

def test_les_deux_cadrages_rendent_le_meme_format(tmp_path):
    chemin = tmp_path / "a.png"
    chemin.write_bytes(_png(taille=(300, 900)))
    for cadrage in juge_mod.CADRAGES:
        tenseur = juge_mod.pretraiter(chemin, cadrage=cadrage, cote=224)
        assert tenseur.shape == (1, 3, 224, 224)
        assert tenseur.dtype == np.float32


def test_le_cadrage_plein_garde_toute_l_image_et_le_centre_la_coupe(tmp_path):
    """Le fait qui a décidé le défaut : sur une page haute, le recadrage central jette le
    haut et le bas — donc le personnage, quand il n'est pas au milieu."""
    from PIL import ImageDraw
    image = Image.new("RGB", (200, 800), (255, 255, 255))
    ImageDraw.Draw(image).rectangle([0, 0, 199, 40], fill=(0, 0, 0))   # bandeau tout en haut
    chemin = tmp_path / "haute.png"
    image.save(chemin)

    plein = juge_mod.pretraiter(chemin, cadrage="plein", cote=224)
    centre = juge_mod.pretraiter(chemin, cadrage="centre", cote=224)
    # Le bandeau noir survit dans « plein » (écart-type élevé) et disparaît dans « centre ».
    assert float(plein.std()) > float(centre.std())


def test_un_cadrage_ou_une_agregation_inconnus_levent(tmp_path):
    with pytest.raises(ValueError, match="cadrage"):
        juge_mod.Encodeur(tmp_path / "x.onnx", cadrage="oblique")
    with pytest.raises(ValueError, match="agrégation"):
        juge_mod.Encodeur(tmp_path / "x.onnx", agregation="moyenne")


def test_le_cote_est_ramene_a_un_multiple_de_quatorze(tmp_path):
    """DINOv2 découpe en parcelles de 14 : un côté qui n'en est pas un multiple se ferait
    rogner en silence par le réseau, et deux mesures ne se compareraient plus."""
    assert juge_mod.Encodeur(tmp_path / "x.onnx", cote=225).cote == 224
    assert juge_mod.Encodeur(tmp_path / "x.onnx", cote=450).cote == 448


def test_l_encodeur_absent_le_dit_avant_de_mesurer(tmp_path):
    """⚠ **Ce test était vert POUR LA MAUVAISE RAISON, et le lot 43 le corrige.**

    Il cherchait « introuvable ». Or `encoder` commençait par un `stat()` sur l'IMAGE et
    rendait « image illisible : … ([WinError 2] Le fichier spécifié est introuvable) » : le mot
    attendu venait du message d'erreur du SYSTÈME, en français, et pas du dépôt. Sur un runner
    de langue anglaise le même code rend « The system cannot find the file specified » — le
    test échouait donc en intégration continue et nulle part ailleurs, ce qui l'a rendu
    invisible jusqu'à la première publication sur un dépôt public.

    Deux leçons, et la seconde compte plus : la propriété annoncée par le nom du test — dire
    l'absence du modèle AVANT de mesurer — **n'était pas tenue du tout**, et l'accident de
    langue le cachait. On vérifie donc le texte que le dépôt écrit, jamais celui que le
    système traduit."""
    encodeur = juge_mod.Encodeur(tmp_path / "absent.onnx")
    assert encodeur.disponible() is False
    with pytest.raises(juge_mod.JugeIndisponible, match="encodeur du juge introuvable"):
        encodeur.encoder(tmp_path / "peu importe")


def test_le_modele_absent_l_emporte_sur_une_image_pourtant_lisible(tmp_path):
    """Un encodeur absent se signale lui-même, même quand l'image est parfaitement lisible.

    ⚠ **Ce test ne garde PAS l'ordre**, contrairement à ce qu'on pourrait attendre de son
    nom — vérifié en retirant le correctif : il reste vert. Avec une image lisible, le
    `stat()` réussit et l'on atteint `_ouvrir()`, qui rend le bon message dans les deux ordres.

    C'est le test précédent — modèle absent ET image absente — qui garde l'ordre, et lui seul.
    Celui-ci garde autre chose, qui vaut aussi : l'absence de repli silencieux vers une mesure
    dégradée quand tout le reste est en place."""
    image = tmp_path / "vraie.png"
    Image.new("RGB", (32, 32), "white").save(image)
    with pytest.raises(juge_mod.JugeIndisponible, match="encodeur du juge introuvable"):
        juge_mod.Encodeur(tmp_path / "absent.onnx").encoder(image)


def test_aucun_test_de_ce_fichier_ne_lit_un_message_du_systeme(tmp_path):
    """⚠ Le garde-fou de la leçon ci-dessus : un `match=` qui viserait un mot des messages
    d'erreur de l'OS serait de nouveau vert en français et rouge en anglais. On refuse donc
    que le fichier attende un mot qui n'apparaît pas dans le code du dépôt."""
    source = Path(__file__).read_text(encoding="utf-8")
    racine = Path(__file__).resolve().parent.parent
    code = (racine / "illustration" / "juge.py").read_text(encoding="utf-8")
    # ⚠ Restreint aux `pytest.raises`, sinon l'expression ci-dessous se capture elle-même.
    for attendu in re.findall(r'pytest\.raises\([^)]*match="([^"]+)"', source):
        premier = attendu.split()[0]
        assert premier in code, (
            f"« {attendu} » n'apparaît pas dans illustration/juge.py : ce test attend "
            f"probablement un message du système, qui change avec la langue de la machine.")


# ──────────────────────────  Les trois grandeurs  ──────────────────────────

def test_les_trois_grandeurs_sont_mesurees_separement(tmp_path):
    image = tmp_path / "generee.png"
    image.write_bytes(_png())
    refs = [tmp_path / f"ref{i}.png" for i in range(2)]
    for chemin in refs:
        chemin.write_bytes(_png())
    encodeur = EncodeurFactice({str(image): [1.0, 0.0, 0.0],
                                str(refs[0]): [1.0, 0.0, 0.0],
                                str(refs[1]): [0.0, 1.0, 0.0]})
    grandeurs = juge_mod.mesurer(encodeur, image, references=refs)
    assert grandeurs.ressemblance == pytest.approx(0.5, abs=1e-9)   # moyenne de 1,0 et 0,0
    assert grandeurs.nouveaute == pytest.approx(0.0, abs=1e-9)      # 1 − le MAXIMUM
    assert grandeurs.references == 2
    assert grandeurs.degeneree is False


def test_une_seule_reference_rend_les_deux_grandeurs_identiques(tmp_path):
    """**Le fait que le corpus réel impose.** Avec une référence, moyenne = maximum, donc
    `nouveauté = 1 − ressemblance` : les deux grandeurs sont une seule, et il devient
    impossible d'être à la fois ressemblant et inédit au sens de ces définitions."""
    image, ref = tmp_path / "g.png", tmp_path / "r.png"
    image.write_bytes(_png())
    ref.write_bytes(_png())
    encodeur = EncodeurFactice({str(image): [1.0, 1.0, 0.0], str(ref): [1.0, 0.0, 0.0]})
    grandeurs = juge_mod.mesurer(encodeur, image, references=[ref])
    assert grandeurs.degeneree is True
    assert grandeurs.nouveaute == pytest.approx(1.0 - grandeurs.ressemblance)


def test_sans_reference_les_grandeurs_restent_None(tmp_path):
    """`None` et non 0 : un cosinus de 0 est une mesure, une absence de référence n'en est
    pas une. Les confondre ferait passer un personnage sans référence pour un échec."""
    image = tmp_path / "g.png"
    image.write_bytes(_png())
    grandeurs = juge_mod.mesurer(EncodeurFactice(), image)
    assert grandeurs.ressemblance is None and grandeurs.nouveaute is None
    assert grandeurs.style_embedding is None and grandeurs.style_descripteurs is None


def test_le_style_nomme_le_descripteur_qui_decroche(tmp_path):
    """Un motif nommé vaut mieux qu'un score : « saturation 4,9× la signature » dit quoi
    corriger dans la requête, « style 0,21 » ne dit rien."""
    image = tmp_path / "coloree.png"
    image.write_bytes(_png(couleur=(250, 20, 20), taille=(120, 120)))
    signature = {"saturation_moyenne": 0.02, "contraste": 0.24, "densite_trait": 0.26,
                 "part_aplats": 0.36, "couleur": False, "echantillon": 16}
    grandeurs = juge_mod.mesurer(EncodeurFactice(), image, signature_tome=signature)
    assert grandeurs.style_descripteurs is not None
    assert grandeurs.descripteur_decroche[0] in ("saturation_moyenne", "part_aplats",
                                                 "contraste", "densite_trait")
    assert grandeurs.meme_regime_couleur is False


def test_le_juge_mesure_des_octets_avant_toute_ecriture(tmp_path):
    """Le plan demande qu'une image trop proche de sa référence soit REJETÉE : ne pas
    l'écrire est plus net que l'écrire puis l'effacer."""
    octets = _png(taille=(80, 80))
    signature = {"saturation_moyenne": 0.02, "contraste": 0.24, "densite_trait": 0.26,
                 "part_aplats": 0.36, "couleur": False, "echantillon": 16}
    grandeurs = juge_mod.mesurer(EncodeurFactice(), octets, signature_tome=signature)
    assert grandeurs.style_descripteurs is not None
    assert not list(tmp_path.iterdir())


def test_le_libelle_de_decrochage_donne_un_rapport_lisible():
    texte = juge_mod.libelle_decrochage("saturation_moyenne", 0.3231, 0.0661)
    assert "4.89×" in texte and "0.3231" in texte and "0.0661" in texte


# ────────────────────────────  Les planchers  ────────────────────────────

def test_une_echelle_publie_son_denominateur():
    echelle = juge_mod.Echelle("identite_haut", [0.1, 0.5, 0.9])
    assert echelle.resume() == {"nom": "identite_haut", "n": 3, "mediane": 0.5,
                                "moyenne": pytest.approx(0.5), "ecart_type": pytest.approx(0.4),
                                "min": 0.1, "max": 0.9}


def test_une_echelle_vide_ne_ment_pas():
    vide = juge_mod.Echelle("x")
    assert vide.mediane is None and vide.ecart_type is None and vide.n == 0


def test_le_juge_est_declare_inutilisable_quand_l_ecart_ne_depasse_pas_le_bruit():
    """Le critère du plan, appliqué tel quel : « si l'écart entre "même personnage" et
    "personnages différents" est inférieur à ce que le bruit justifie, le juge automatique est
    inutilisable — dites-le et passez au seul juge humain »."""
    haut = juge_mod.Echelle("identite_haut", [0.46, 0.46, 0.46])
    confusion = juge_mod.Echelle("identite_confusion", [0.20, 0.40, 0.60])   # écart-type 0,20
    utilisable, motif = juge_mod.juge_utilisable(haut, confusion)
    assert utilisable is False
    assert "ne dépasse pas le bruit" in motif


def test_le_juge_est_utilisable_quand_l_ecart_depasse_le_bruit():
    haut = juge_mod.Echelle("identite_haut", [0.90, 0.90, 0.92])
    confusion = juge_mod.Echelle("identite_confusion", [0.30, 0.31, 0.32])
    utilisable, motif = juge_mod.juge_utilisable(haut, confusion)
    assert utilisable is True and "× le bruit" in motif


def test_un_plancher_haut_sous_la_confusion_est_un_juge_aveugle():
    haut = juge_mod.Echelle("identite_haut", [0.20, 0.21, 0.22])
    confusion = juge_mod.Echelle("identite_confusion", [0.50, 0.51, 0.52])
    utilisable, motif = juge_mod.juge_utilisable(haut, confusion)
    assert utilisable is False and "ne distingue rien" in motif


def test_le_seuil_du_plan_est_la_moitie_de_l_intervalle():
    haut = juge_mod.Echelle("identite_haut", [0.8])
    confusion = juge_mod.Echelle("identite_confusion", [0.4])
    assert juge_mod.seuil_median(haut, confusion) == pytest.approx(0.6)
    assert juge_mod.seuil_median(juge_mod.Echelle("x"), confusion) is None


def test_les_cinq_paires_du_plan_sont_declarees_et_reparties_en_deux_echelles():
    """Trois paires situent l'IDENTITÉ, deux le REGISTRE GRAPHIQUE. Une seule métrique, deux
    échelles distinctes : les mélanger est l'erreur que le plan nomme explicitement."""
    noms = [nom for nom, _ in juge_mod.PAIRES]
    assert len(noms) == 5
    assert set(juge_mod.ECHELLE_IDENTITE) | set(juge_mod.ECHELLE_STYLE) == set(noms)
    assert not set(juge_mod.ECHELLE_IDENTITE) & set(juge_mod.ECHELLE_STYLE)


def test_le_cosinus_reste_borne():
    """L'arithmétique flottante rend parfois 1,0000000000000002, et un banc qui le publierait
    perdrait un lecteur pour rien."""
    v = juge_mod.normaliser(np.asarray([3.0, 4.0]))
    assert juge_mod.cosinus(v, v) == 1.0
    assert juge_mod.cosinus(v, -v) == -1.0


def test_un_vecteur_nul_ne_rend_pas_nan():
    nul = juge_mod.normaliser(np.zeros(4))
    assert juge_mod.cosinus(nul, nul) == 0.0


# ────────────────────────  Le recouvrement, et non l'écart  ────────────────────────

def test_la_separation_vaut_un_quand_les_populations_sont_disjointes():
    a = juge_mod.Echelle("a", [0.7, 0.8, 0.9])
    b = juge_mod.Echelle("b", [0.1, 0.2, 0.3])
    assert juge_mod.separation(a, b) == pytest.approx(1.0)
    assert juge_mod.separation(b, a) == pytest.approx(0.0)


def test_la_separation_vaut_un_demi_sur_deux_populations_identiques():
    """0,50 est le tirage à pile ou face, et c'est le repère du tableau publié."""
    a = juge_mod.Echelle("a", [0.1, 0.2, 0.3])
    b = juge_mod.Echelle("b", [0.1, 0.2, 0.3])
    assert juge_mod.separation(a, b) == pytest.approx(0.5)


def test_les_ex_aequo_comptent_pour_moitie():
    """Sans rangs moyens, deux valeurs identiques compteraient l'une pour l'autre selon
    l'ordre de tri — la mesure dépendrait du hasard."""
    a = juge_mod.Echelle("a", [0.5])
    b = juge_mod.Echelle("b", [0.5])
    assert juge_mod.separation(a, b) == pytest.approx(0.5)


def test_une_echelle_vide_ne_rend_aucune_separation():
    assert juge_mod.separation(juge_mod.Echelle("a"), juge_mod.Echelle("b", [0.1])) is None


def test_l_ecart_des_medianes_peut_passer_pendant_que_les_populations_se_recouvrent():
    """**Le défaut de méthode que la mesure a trouvé**, reproduit en une ligne : le critère du
    plan — « l'écart doit dépasser le bruit » — est tenu, et pourtant le juge ne classe
    correctement qu'un peu plus d'une paire sur deux. C'est pour ça que le second critère
    existe, et pour ça que les deux verdicts sont publiés côte à côte."""
    haut = juge_mod.Echelle("identite_haut", [0.28, 0.30, 0.50, 0.90, 0.95])
    confusion = juge_mod.Echelle("identite_confusion", [0.30, 0.33, 0.36, 0.39, 0.42])
    assert haut.mediane - confusion.mediane > confusion.ecart_type      # le critère du plan
    aire = juge_mod.separation(haut, confusion)
    assert aire < juge_mod.SEUIL_SEPARATION
    utilisable, motif = juge_mod.juge_utilisable(haut, confusion)
    assert utilisable is False
    assert "le critère du plan est tenu" in motif and "MAIS la séparation" in motif


def test_un_bruit_nul_ne_fait_pas_un_juge_parfait():
    """Une population de confusion dont toutes les paires valent la même chose est trop pauvre
    pour qu'un rapport y veuille dire quelque chose — et le message le dit au lieu de diviser
    par zéro."""
    haut = juge_mod.Echelle("identite_haut", [0.9, 0.9, 0.9])
    confusion = juge_mod.Echelle("identite_confusion", [0.3, 0.3, 0.3])
    utilisable, motif = juge_mod.juge_utilisable(haut, confusion)
    assert utilisable is True and "bruit NUL" in motif


def test_les_libelles_du_verdict_suivent_l_echelle_mesuree():
    """L'échelle de STYLE ne parle pas de « personnage » : un message recopié d'une échelle à
    l'autre ferait lire un chiffre de style comme un chiffre d'identité."""
    haut = juge_mod.Echelle("style_haut", [0.28, 0.30, 0.50, 0.90, 0.95])
    bas = juge_mod.Echelle("style_bas", [0.30, 0.33, 0.36, 0.39, 0.42])
    _, motif = juge_mod.juge_utilisable(haut, bas, libelles=("deux illustrations du même tome",
                                                            "une illustration d'une autre œuvre"))
    assert "même tome" in motif and "personnage" not in motif
