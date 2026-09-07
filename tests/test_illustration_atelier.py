# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L'atelier** — qui est illustrable, avec quelles images, et qui l'a décidé.

Le test central du fichier est `test_un_personnage_A_RELIRE_est_proposé_quand_même` : c'est
la raison d'être de l'atelier. Une œuvre neuve n'a **aucune** référence validée — la revue
humaine n'a pas encore eu lieu — et un atelier qui n'accepterait que le validé ne proposerait
rien du tout sur ce qui est justement le cas normal.

Le second est `test_promouvoir_n_ecrit_QUE_ce_qu_on_lui_donne` : la revue humaine se persiste,
mais jamais par effet de bord. Une bible modifiée sans qu'on l'ait demandé serait une revue
fabriquée.
"""
import pytest
from PIL import Image

from core import bible as bible_mod
from illustration import atelier as atelier_mod
from illustration import identite as ident_mod
from illustration import selection as selection_mod


def _image(chemin, taille=(700, 1000), teinte=(120, 120, 120)):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", taille, teinte).save(chemin)
    return chemin


@pytest.fixture
def oeuvre(tmp_path):
    """Une œuvre à DEUX tomes — le cas que la portée par tome ne savait pas traiter."""
    ident_mod._CLASSES.clear()
    racine = tmp_path / "build" / "Œuvre"
    for tome, teintes in (("Vol.1", ((30, 30, 30), (90, 90, 90))),
                          ("Vol.2", ((150, 150, 150), (200, 200, 200)))):
        for nom, teinte in zip(("p1_couv.png", "p40_illus.png"), teintes):
            _image(racine / tome / "media" / nom, teinte=teinte)

    pret = bible_mod.personnage("Tory")
    pret["apparence"]["cheveux"] = "gris"
    pret["citations"] = [{"attribut": "cheveux", "source": "c.md", "texte": "gris"}]
    pret["references"] = [{"fichier": "Vol.1/media/p40_illus.png", "role": "identite",
                           "confiance": "humaine"}]

    a_relire = bible_mod.personnage("Gale")
    a_relire["apparence"]["yeux"] = "clairs"
    a_relire["citations"] = [{"attribut": "yeux", "source": "c.md", "texte": "clairs"}]
    a_relire["references"] = [{"fichier": "Vol.2/media/p40_illus.png", "role": "identite",
                               "confiance": "llm"}]

    sans_image = bible_mod.personnage("Salsa")
    sans_image["apparence"]["cheveux"] = "noirs"
    sans_image["citations"] = [{"attribut": "cheveux", "source": "c.md", "texte": "noirs"}]

    muet = bible_mod.personnage("Bear")
    muet["references"] = [{"fichier": "Vol.1/media/p40_illus.png", "role": "identite",
                           "confiance": "humaine"}]

    bible = {"personnages": [pret, a_relire, sans_image, muet]}
    glossaire = {"personnages": [{"nom": "Tory", "genre": "féminin"}]}
    return bible, glossaire, racine


# ══════════════════════════  Le catalogue : trois états, pas deux  ══════════════════════════

def test_les_trois_etats_sont_distincts(oeuvre):
    bible, glossaire, racine = oeuvre
    par_nom = {f.nom: f for f in atelier_mod.catalogue(bible, glossaire, racine)}
    assert par_nom["Tory"].etat == atelier_mod.PRET
    assert par_nom["Gale"].etat == atelier_mod.A_RELIRE
    assert par_nom["Salsa"].etat == atelier_mod.HORS_ATTEINTE   # aucune image
    assert par_nom["Bear"].etat == atelier_mod.HORS_ATTEINTE    # aucun attribut cité


def test_un_personnage_A_RELIRE_est_propose_quand_meme(oeuvre):
    """**La raison d'être de l'atelier.** Une œuvre neuve n'a AUCUNE référence validée : la
    revue humaine n'a pas encore eu lieu. Un atelier qui n'accepterait que le validé ne
    proposerait rien sur ce qui est justement le cas normal — et pousserait à contourner la
    revue plutôt qu'à la faire."""
    bible, glossaire, racine = oeuvre
    par_nom = {f.nom: f for f in atelier_mod.catalogue(bible, glossaire, racine)}
    gale = par_nom["Gale"]
    assert gale.illustrable is True
    assert gale.validees == 0 and len(gale.candidates) == 1
    assert "sans_validee" in gale.motifs


def test_les_plus_prets_sont_proposes_en_PREMIER(oeuvre):
    """Le personnage le mieux documenté donnera la meilleure image : c'est celui qu'on
    propose d'abord. Les hors d'atteinte ferment la liste."""
    bible, glossaire, racine = oeuvre
    ordre = [f.nom for f in atelier_mod.catalogue(bible, glossaire, racine)]
    assert ordre[0] == "Tory"
    assert ordre[1] == "Gale"
    assert set(ordre[2:]) == {"Salsa", "Bear"}


def test_un_hors_atteinte_porte_son_MOTIF(oeuvre):
    """« Ce n'est pas un échec de l'atelier, c'est ce que la bible contient » — encore
    faut-il le dire, et dire lequel des deux manque."""
    bible, glossaire, racine = oeuvre
    par_nom = {f.nom: f for f in atelier_mod.catalogue(bible, glossaire, racine)}
    assert par_nom["Salsa"].motifs == ("sans_image",)
    assert par_nom["Bear"].motifs == ("sans_attribut_cite",)
    assert all(m in atelier_mod.MOTIFS for f in par_nom.values() for m in f.motifs)


def test_le_catalogue_n_appelle_AUCUN_modele(oeuvre, monkeypatch):
    """Il doit s'afficher instantanément au démarrage, avant que l'utilisateur ait choisi.
    Un catalogue qui coûterait un appel de vision par image ferait attendre une minute pour
    une liste de noms."""
    def _interdit(*_a, **_k):
        raise AssertionError("le catalogue ne doit appeler aucun modèle")

    monkeypatch.setattr(selection_mod, "choisir_avec_llm", _interdit)
    bible, glossaire, racine = oeuvre
    assert atelier_mod.catalogue(bible, glossaire, racine)


# ══════════════════════════  La sélection humaine  ══════════════════════════

def test_toutes_les_candidates_ressortent_retenues_ou_non(oeuvre):
    """Règle 3 du `PLAN-26` L26.0 : « un utilisateur qui retire une image doit voir pourquoi
    elle avait été prise ». Ne rendre que les retenues laisserait croire qu'il n'y avait pas
    d'autre choix."""
    bible, _, racine = oeuvre
    candidates = selection_mod.candidates_identite(bible, "Tory", racine)
    choix = atelier_mod.selection_humaine([], candidates)
    assert len(choix) == len(candidates)
    assert all(not c.retenue for c in choix)
    assert all(c.par == "humain" for c in choix)
    assert all(c.motif.strip() for c in choix)


def test_le_motif_dit_QUI_a_decide_et_reprend_l_avis_du_modele(oeuvre):
    """Les deux tiennent dans la même ligne, et le lecteur voit s'ils étaient d'accord."""
    bible, _, racine = oeuvre
    candidates = selection_mod.candidates_identite(bible, "Tory", racine)
    fichier = candidates[0].fichier
    choix = atelier_mod.selection_humaine(
        [fichier], candidates, motifs_du_modele={fichier: "visage de face net"})
    retenu = next(c for c in choix if c.fichier == fichier)
    assert "humain" in retenu.motif
    assert "visage de face net" in retenu.motif


# ══════════════════════════  La promotion dans la bible  ══════════════════════════

def test_promouvoir_ecrit_confiance_humaine(oeuvre):
    bible, _, _ = oeuvre
    modifiee, promues = atelier_mod.promouvoir(bible, "Gale",
                                               ["Vol.2/media/p40_illus.png"])
    assert promues == 1
    gale = bible_mod.entree(modifiee, "Gale")
    assert gale["references"][0]["confiance"] == "humaine"


def test_promouvoir_n_ecrit_QUE_ce_qu_on_lui_donne(oeuvre):
    """⚠ **Jamais par effet de bord.** Une bible modifiée sans qu'on l'ait demandé serait une
    revue humaine fabriquée — exactement ce que `confiance: humaine` existe pour interdire."""
    bible, _, _ = oeuvre
    inchangee, promues = atelier_mod.promouvoir(bible, "Gale", [])
    assert promues == 0
    assert bible_mod.entree(inchangee, "Gale")["references"][0]["confiance"] == "llm"

    # Et la promotion d'un personnage ne touche pas les autres.
    modifiee, _ = atelier_mod.promouvoir(bible, "Gale", ["Vol.2/media/p40_illus.png"])
    assert bible_mod.entree(modifiee, "Tory")["references"][0]["confiance"] == "humaine"


def test_promouvoir_ne_leve_PAS_valide_par_humain(oeuvre):
    """`valide_par_humain` porte sur les ATTRIBUTS, que l'atelier ne relit pas. Le lever ici
    ferait passer pour relus des attributs que personne n'a regardés."""
    bible, _, _ = oeuvre
    modifiee, _ = atelier_mod.promouvoir(bible, "Gale", ["Vol.2/media/p40_illus.png"])
    assert bible_mod.entree(modifiee, "Gale")["valide_par_humain"] is False


# ══════════════════════════  Le choix personnalisé  ══════════════════════════

def test_un_bloc_libre_porte_la_charpente_du_gabarit():
    """Ce que l'humain écrit remplace les ATTRIBUTS, pas la grammaire du modèle d'image :
    sans la charpente, une description libre perdrait le prompt négatif et la désignation des
    références — les deux choses qu'il ne sait pas qu'il doit écrire."""
    bloc = atelier_mod.bloc_libre("une silhouette de dos sous la pluie", cadrage="pied")
    assert "en pied" in bloc["prompt"]
    assert "une silhouette de dos sous la pluie" in bloc["prompt"]
    assert "texte" in bloc["prompt_negatif"] and "filigrane" in bloc["prompt_negatif"]


def test_un_bloc_libre_dit_que_les_mots_viennent_de_L_HUMAIN():
    """⚠ Un lecteur du sidecar doit pouvoir distinguer, sans ambiguïté, une image dont chaque
    mot vient de l'œuvre d'une image dont les mots viennent de son auteur. Les confondre
    viderait de son sens toute la traçabilité du lot 26."""
    bloc = atelier_mod.bloc_libre("une silhouette de dos", cadrage="buste")
    sources = bloc["attributs_sources"]
    assert len(sources) == 1
    assert sources[0]["origine"] == "humain"
    assert sources[0]["source"] == "saisie à l'écran par l'humain"
    assert bloc["personnage"] == ""


def test_une_description_VIDE_est_refusee():
    """« L'atelier refuse plutôt que de produire une image au hasard » — même politique que
    partout ailleurs dans la brique."""
    with pytest.raises(ValueError) as echec:
        atelier_mod.bloc_libre("   ", cadrage="buste")
    assert "vide" in str(echec.value)


def test_un_bloc_libre_designe_les_references_qu_on_lui_attache():
    """Une référence branchée mais jamais citée dans le texte est une référence à moitié
    utilisée, et rien ne le signalerait."""
    choix = [selection_mod.Choix("Vol.1/media/a.png", "retenue", True, par="humain")]
    bloc = atelier_mod.bloc_libre("une silhouette", cadrage="buste", references=choix)
    assert "image 1" in bloc["prompt"]
    assert [c["fichier"] for c in bloc["references"]] == ["Vol.1/media/a.png"]

# ══════════════════  La revue attribut par attribut  ══════════════════

def test_une_entree_filtree_ne_garde_QUE_les_attributs_retenus():
    """⚠ **Une revue en bloc est trop grossière, et la mesure l'a montré.** Sur le premier
    personnage relu de l'œuvre de mesure, la passe automatique proposait cinq attributs dont
    **trois faux** : des cheveux « bleu céleste » là où le dessin les montre verts — la phrase
    citée décrivait un AUTRE personnage —, un âge « environ deux ans » pour une adolescente, et
    un « masque blanc » tiré d'une phrase qui décrit les passants de la rue.

    Un « ces attributs sont-ils bons ? o/n » n'aurait laissé que deux issues : écrire trois
    erreurs dans la bible, ou perdre les deux bons attributs."""
    entree = bible_mod.personnage("Tiat")
    entree["apparence"]["cheveux"] = "bleu céleste"        # faux : la phrase parle d'une autre
    entree["apparence"]["yeux"] = "verts"                  # juste
    entree["apparence"]["age_apparent"] = "environ deux ans"   # faux
    entree["citations"] = [
        {"attribut": "cheveux", "source": "chapters/ch04.md", "texte": "cheveux bleu céleste"},
        {"attribut": "yeux", "source": "Vol.1/media/image2.emf", "texte": "illustration"},
        {"attribut": "age_apparent", "source": "chapters/ch04.md", "texte": "deux ans"}]

    filtree = atelier_mod.entree_filtree(entree, ["yeux"])
    assert filtree["apparence"]["yeux"] == "verts"
    assert filtree["apparence"]["cheveux"] == ""
    assert filtree["apparence"]["age_apparent"] == ""
    assert [c["attribut"] for c in filtree["citations"]] == ["yeux"]


def test_chaque_attribut_sort_avec_SES_citations():
    """« Un attribut sans sa source n'est pas une observation. » Un écran de revue qui
    montrerait les valeurs sans les phrases demanderait de faire confiance, pas de vérifier —
    et c'est en LISANT la phrase qu'on voit qu'elle parle de quelqu'un d'autre."""
    entree = bible_mod.personnage("Tiat")
    entree["apparence"]["cheveux"] = "bleu céleste"
    entree["citations"] = [
        {"attribut": "cheveux", "source": "chapters/ch04.md", "texte": "premier"},
        {"attribut": "cheveux", "source": "chapters/ch08.md", "texte": "second"},
        {"attribut": "yeux", "source": "x.md", "texte": "orphelin"}]
    cites = atelier_mod.attributs_cites(entree)
    assert [a for a, _, _ in cites] == ["cheveux"]
    assert [c["texte"] for c in cites[0][2]] == ["premier", "second"]


def test_un_attribut_SANS_citation_ne_ressort_pas():
    """La bible le purgerait à l'écriture ; le montrer à la revue ferait croire qu'il compte."""
    entree = bible_mod.personnage("Tiat")
    entree["apparence"]["cheveux"] = "verts"
    assert atelier_mod.attributs_cites(entree) == []


def test_promouvoir_fait_ENTRER_un_personnage_venu_des_propositions(oeuvre):
    """Sans cette écriture, `prompt.construire` ne trouverait même pas le personnage : la
    bible est la seule source d'attributs, et une proposition n'y est pas."""
    bible, _, _ = oeuvre
    proposee = bible_mod.personnage("Nouvelle")
    proposee["apparence"]["cheveux"] = "vertes"
    proposee["citations"] = [{"attribut": "cheveux", "source": "c.md", "texte": "vertes"}]
    proposee["references"] = [{"fichier": "Vol.1/media/p40_illus.png", "role": "identite",
                               "confiance": "llm"}]

    modifiee, promues = atelier_mod.promouvoir(
        bible, "Nouvelle", ["Vol.1/media/p40_illus.png"], entree=proposee)
    entree = bible_mod.entree(modifiee, "Nouvelle")
    assert entree is not None
    assert entree["apparence"]["cheveux"] == "vertes"
    assert entree["references"][0]["confiance"] == "humaine"
    assert promues == 1
    # ⚠ `valide_par_humain` est levé ICI, et seulement ici : l'atelier a montré les attributs
    # et leurs citations à l'écran avant de demander.
    assert entree["valide_par_humain"] is True
