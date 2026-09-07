# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lot 11 — les sept mécanismes qui étaient écrits, documentés, et inertes.

Le fil commun de ces défauts : **le pipeline a plusieurs chemins et les garde-fous n'ont pas
suivi.** Chaque cas ci-dessous est un chemin qui avait divergé de son jumeau — la fiche de
contexte qui n'arrivait qu'au chemin par lots, le pack de langue qui n'arrivait pas au
rattrapage, le budget de caractères borné d'un côté et pas de l'autre, deux classes CJK selon
la porte d'entrée.

D'où la forme de ce fichier : chaque test compare **les deux chemins**, plutôt que de vérifier
qu'un seul fonctionne. Un test qui n'aurait regardé que `_translate_lot` serait passé au vert
pendant tout le temps où `_translate_page` perdait la fiche.

⚠ Aucun marqueur, aucun appel LLM, aucun modèle : le traducteur est un double qui rend la
liste numérotée qu'on lui demande.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from manga import quality_manga, traduction_unitaire          # noqa: E402
from manga import orchestrator_manga as orch                  # noqa: E402
from manga._config import fusion                              # noqa: E402


class _Agent:
    """Traducteur factice : retient le dernier message reçu, rend N lignes numérotées.

    C'est le message qui est l'objet du test — ce que le modèle en ferait ne nous regarde
    pas."""

    temperature = 0.2
    llm = None

    def __init__(self):
        self.vu: list[str] = []

    def run(self, user, *, dry_payload="", max_tokens=0, temperature=None, images=None):
        self.vu.append(user)
        n = len([ligne for ligne in dry_payload.splitlines() if ligne.strip()])
        return "\n".join(f"{i + 1}. Réplique {i + 1}" for i in range(n))


FICHE = ("## Fiche de l'œuvre\n"
         "- Adresse : Inaho vouvoie Slaine ; Slaine tutoie Inaho.\n"
         "- Registre : militaire, sec.")


# ═══ L3.1 — la fiche de registre atteint les DEUX chemins ════════════════════════════════

def test_la_fiche_de_contexte_atteint_le_chemin_par_defaut():
    """LE défaut du lot. `contexte_oeuvre` était déclaré au paramètre de `_translate_page` et
    jamais lu dans son corps — sur le chemin par défaut (`manga.lot.planches: 1`), qui est
    celui que tout le monde emprunte. `_passe_contexte` dépensait donc un appel LLM par tome
    pour écrire un `contexte.txt` que personne ne lisait."""
    agent = _Agent()
    orch._translate_page(agent, None, ["アアア", "イイイ"], mode_vision=False,
                         gloss_text="", contexte_oeuvre=FICHE)
    assert FICHE in agent.vu[0]


def test_la_fiche_precede_les_repliques_precedentes():
    """L'ordre n'est pas cosmétique : la fiche est une consigne de VOIX, les répliques
    précédentes en sont des exemples. Une consigne qui suit ses exemples se lit comme un
    commentaire sur eux."""
    agent = _Agent()
    orch._translate_page(agent, None, ["アアア"], mode_vision=False, gloss_text="GLOSSAIRE",
                         contexte_oeuvre=FICHE, precedentes=["Réplique d'avant"])
    message = agent.vu[0]
    assert message.index("GLOSSAIRE") < message.index(FICHE) < message.index("Réplique d'avant")


def test_une_fiche_vide_n_ajoute_rien():
    """Sans agent `manga_contexte`, la fiche est vide — et le prompt doit être exactement
    celui d'avant, pas celui-ci plus une section vide."""
    agent = _Agent()
    orch._translate_page(agent, None, ["アアア"], mode_vision=False, gloss_text="",
                         contexte_oeuvre="")
    assert "\n\n\n" not in agent.vu[0]


def test_le_surcout_de_prefill_de_la_fiche_est_borne_par_la_config():
    """`manga.contexte_oeuvre.max_tokens` est ce qui rend le surcoût prévisible : la fiche est
    payée UNE FOIS PAR PLANCHE. Mesuré sur les huit `contexte.txt` de `build/` : 174 à 261
    tokens, soit +10,5 % du prefill d'un tome de 131 planches — et non les +16 % estimés au
    plafond, qui n'avaient jamais été payés."""
    from core import tokens
    assert tokens.estimate(FICHE) < 400


# ═══ L3.9 — le prompt annonçait UNE planche et en recevait trois ═════════════════════════

def test_le_prompt_annonce_des_planches_precedentes_au_pluriel():
    """`manga.contexte.planches_precedentes` vaut 3 par défaut. Le prompt de planche disait
    « la planche précédente » : le modèle recevait N−3, N−2 et N−1 en croyant qu'elles
    venaient toutes de N−1. Le chemin par lots avait le pluriel juste."""
    agent = _Agent()
    orch._translate_page(agent, None, ["アアア"], mode_vision=False, gloss_text="",
                         precedentes=["A", "B", "C"])
    assert "Répliques des planches précédentes" in agent.vu[0]
    assert "de la planche précédente" not in agent.vu[0]


# ═══ L3.2 — le pack de langue atteint le rattrapage unitaire ═════════════════════════════

class _PackFactice:
    """Un pack minimal : il ne sait que surcharger une consigne, ce qui suffit ici."""

    def __init__(self, consigne: str):
        self._consigne = consigne

    def consigne(self, cle: str, defaut: str) -> str:
        return self._consigne if cle == traduction_unitaire.CLE_CONSIGNE else defaut


def test_le_pack_surcharge_la_consigne_du_prompt_unitaire():
    """C'est le SEUL point d'externalisation de consigne du chemin manga. Sans le pack, un run
    `cible: en` réclame une traduction FRANÇAISE par une consigne codée en dur."""
    pack = _PackFactice("Translate the SINGLE line below into English.")
    prompt = traduction_unitaire.prompt_bulle("Hello", langue="en", pack=pack)
    assert "into English" in prompt
    assert traduction_unitaire.CONSIGNE not in prompt


def test_sans_pack_la_consigne_francaise_reste_le_defaut():
    """Le texte français reste à son site d'appel : le recopier dans le pack `fr` en ferait
    une seconde source libre de diverger."""
    assert traduction_unitaire.CONSIGNE in traduction_unitaire.prompt_bulle("アアア")


def test_le_pack_suit_jusqu_au_rattrapage_du_chemin_de_planche(monkeypatch):
    """`_rattraper_bulles` jetait le pack : `resoudre_pack(config).accorder()` ne retenait que
    les règles d'accord. Les deux voies — planche seule et lot — doivent le transmettre."""
    recus = []
    monkeypatch.setattr(orch.traduction_unitaire, "traduire_bulle",
                        lambda *a, pack=None, **k: (recus.append(pack), ("Rendu", None))[1])
    sentinelle = object()
    orch._rattraper_bulles(_Agent(), ["アアア"], [""], page=1, pack=sentinelle)
    assert recus == [sentinelle]


# ═══ L3.3 — le défaut du code est celui de la config livrée ══════════════════════════════

def test_la_passe_onomatopees_est_eteinte_quand_la_cle_est_absente():
    """Le code lisait `sfx_cfg.get("actif", True)` : un `config.yaml` amputé du bloc
    `onomatopees` — fichier antérieur au lot 9, configuration minimale, fixture — activait
    donc **en silence** une passe qui télécharge 94,7 Mo de poids et ajoute une passe OCR
    complète sur tout le tome.

    ⚠ Ce défaut de REPLI est `False` alors que la config livrée est à `true`, et les deux ne
    se contredisent pas : la config livrée dit ce que le projet recommande à qui la lit, ce
    défaut-ci dit quoi faire quand personne n'a rien choisi. Un défaut de repli se juge sur ce
    qu'il coûte quand on se trompe.

    ⚠ Le test lit le CODE et **pas** `config.yaml`, délibérément : ce fichier est fait pour
    être édité, et l'asserter ferait échouer la suite sur toute machine réglée autrement."""
    source = (RACINE / "manga" / "orchestrator_manga.py").read_text(encoding="utf-8")
    assert 'sfx_cfg.get("actif", False)' in source
    assert 'sfx_cfg.get("actif", True)' not in source


# ═══ L3.5 — une seule définition du CJK, quel que soit le chemin ═════════════════════════

@pytest.mark.parametrize("rendu", ["Attends ！", "Vraiment ？", "（）"])
def test_le_rattrapage_accepte_ce_que_le_chemin_de_planche_accepte(rendu):
    """Le rattrapage utilisait la classe LARGE (`tokens._CJK`), qui englobe la ponctuation
    pleine chasse. Il rejetait donc des réponses que le chemin de planche acceptait — et la
    bulle restait vide, l'inverse exact de ce que le rattrapage existe pour faire."""
    assert quality_manga.diagnostiquer_rattrapage(rendu, source="アアア") != \
        quality_manga.MOTIF_SOURCE_RESIDUELLE


def test_le_rattrapage_rejette_toujours_du_vrai_japonais_residuel():
    """La correction ne doit pas ouvrir la porte : un kana rendu tel quel reste un refus."""
    assert quality_manga.diagnostiquer_rattrapage("アアア", source="アアア") == \
        quality_manga.MOTIF_SOURCE_RESIDUELLE


def test_aucun_module_manga_n_appelle_l_alias_prive_du_socle():
    """`tokens._CJK` est l'alias privé de `tokens.CJK`. L'appeler depuis `manga/` liait la
    brique à un nom que `core/` ne doit à personne."""
    fautifs = [p.name for p in (RACINE / "manga").glob("*.py")
               if "tokens._CJK" in p.read_text(encoding="utf-8").replace(
                   "`tokens._CJK`", "")]
    assert fautifs == []


# ═══ L3.6 — une clé à `null` ne fait plus disparaître son défaut ═════════════════════════

DEFAUTS = {"a": 1, "b": "deux"}


@pytest.mark.parametrize("cfg", [None, {}, {"a": None}, {"a": None, "b": None},
                                 {"inconnue": 99}, {"a": None, "inconnue": 99}])
def test_fusion_preserve_les_defauts(cfg):
    """`{**defauts, **cfg}` recouvrait le défaut par `None` — et `null` est la façon normale
    d'écrire « laisse le défaut » en YAML. Le premier `int()` levait alors."""
    assert fusion(DEFAUTS, cfg) == DEFAUTS


def test_fusion_honore_une_valeur_donnee():
    assert fusion(DEFAUTS, {"a": 7}) == {"a": 7, "b": "deux"}


def test_fusion_ne_mute_pas_les_defauts():
    """Les appelants en gardent un au niveau module ; le muter contaminerait tout le run."""
    fusion(DEFAUTS, {"a": 7})
    assert DEFAUTS == {"a": 1, "b": "deux"}


@pytest.mark.parametrize("module,nom", [
    ("manga.detection", "DEFAUTS_FENETRE"),
    ("manga.ocr", "_DEFAUTS_OCR"),
    ("manga.terminology", "_DEFAUTS_DERIVE"),
    ("manga.orchestrator_manga", "_DEFAUTS_RATTRAPAGE"),
    ("manga.report_manga", "_DEFAUTS_RAPPORT"),
])
def test_chaque_bloc_de_defauts_survit_a_une_cle_nulle(module, nom):
    """Site par site, comme le demande le critère : une clé à `null` dans `config.yaml` ne
    doit faire disparaître aucun défaut, où qu'elle soit écrite."""
    import importlib
    defauts = getattr(importlib.import_module(module), nom)
    nulle = dict.fromkeys(defauts)
    assert fusion(defauts, nulle) == defauts


def _code_seul(chemin: Path) -> str:
    """Le fichier SANS ses commentaires ni ses chaînes.

    Sans ça, ces deux gardes accuseraient les docstrings qui *documentent* le motif fautif —
    et le seul moyen de les faire taire serait de cesser d'expliquer pourquoi il est fautif."""
    import io
    import tokenize
    morceaux = []
    with open(chemin, "rb") as fh:
        for jeton in tokenize.tokenize(io.BytesIO(fh.read()).readline):
            if jeton.type not in (tokenize.COMMENT, tokenize.STRING):
                morceaux.append(jeton.string)
    return " ".join(morceaux)


def test_aucun_module_manga_ne_refait_la_fusion_a_la_main():
    """Le motif fautif ne doit pas revenir par une neuvième porte.

    ⚠ Le relevé du lot annonçait sept sites ; il y en avait **dix**. `gloss.py` portait le
    même `{**_DEFAUTS, **(cfg or {})}` et n'était pas dans la liste, et les deux `_cfg`
    historiques (`clean`, `bubbles_split`) restaient deux copies de plus."""
    fautifs = [p.name for p in (RACINE / "manga").glob("*.py")
               if "** ( cfg or { } )" in _code_seul(p)]
    assert fautifs == []


# ═══ L3.6 bis — le recouvrement de fenêtre est borné, et le rabot est annoncé ════════════

def test_un_recouvrement_demesure_ne_fait_plus_exploser_le_nombre_de_fenetres():
    """La seule borne était `h - 1`, ce qui n'en est pas une : `fenetre_recouvrement: 2159`
    avec une fenêtre de 2160 donne `pas = 1`, donc **7 841 inférences ONNX** pour une seule
    bande de 1080×10 000, sans un avertissement."""
    from manga.detection import fenetres
    bandes = fenetres(1080, 10_000, {"fenetre_recouvrement": 2159})
    assert len(bandes) <= 25, f"{len(bandes)} fenêtres — le rabot n'a pas joué"


def test_le_rabot_du_recouvrement_est_annonce():
    """Un recouvrement démesuré ne produit pas un résultat faux mais un run qui n'en finit
    pas : c'est le genre de panne qu'on met deux heures à attribuer à une ligne de config."""
    from manga.detection import fenetres
    dits: list[str] = []
    fenetres(1080, 10_000, {"fenetre_recouvrement": 2159}, dire=dits.append)
    assert len(dits) == 1
    assert "fenetre_recouvrement" in dits[0] and "2159" in dits[0]


def test_le_reglage_livre_ne_declenche_aucun_rabot():
    """Le défaut livré (900 sur 2160, soit 42 %) est très en dessous de la borne : corriger un
    abus ne doit pas gêner l'usage normal."""
    from manga.detection import DEFAUTS_FENETRE, fenetres
    dits: list[str] = []
    bandes = fenetres(1080, 10_000, dict(DEFAUTS_FENETRE), dire=dits.append)
    assert dits == []
    assert len(bandes) == 8


# ═══ L3.7 — le budget de caractères est le même sur les deux chemins ═════════════════════

BOITE = (0, 0, 400, 300)


def test_le_budget_est_borne_par_la_source_sur_une_langue_latine():
    """`surface / 320` est calibré sur du japonais, qui est dense. D'une source latine vers le
    français, le gabarit de surface seul demande au modèle d'être trois fois plus bavard que
    l'original — et le seul webtoon du dépôt est à source anglaise."""
    large = traduction_unitaire.budget_caracteres(BOITE, "Hello", "jp")
    borne = traduction_unitaire.budget_caracteres(BOITE, "Hello", "en")
    assert borne < large
    assert borne == max(12, int(len("Hello") * 1.3))


def test_le_budget_du_japonais_reste_celui_de_la_surface():
    """La correction ne doit rien changer au chemin japonais, qui est le chemin nominal."""
    assert traduction_unitaire.budget_caracteres(BOITE, "アアア", "jp") == int(400 * 300 / 320)


def test_les_gabarits_de_planche_et_le_prompt_unitaire_donnent_le_meme_budget():
    """LE test du lot : les deux chemins posaient le calcul séparément et avaient divergé.
    S'ils redivergent, celui-ci tombe."""
    source, langue = "Hello there", "en"
    ligne = orch._lignes_gabarits([BOITE], sources=[source], langue=langue)[0]
    attendu = traduction_unitaire.budget_caracteres(BOITE, source, langue)
    assert f"≤ {attendu} caractères" in ligne


def test_les_gabarits_du_lot_recoivent_aussi_les_sources():
    """Le lot consomme la même fonction, avec `depart` décalé : la borne doit l'y suivre."""
    lignes = orch._lignes_gabarits([BOITE, BOITE], depart=5,
                                   sources=["Hi", "Hello there"], langue="en")
    assert lignes[0].startswith("5.") and lignes[1].startswith("6.")
    assert "≤ 12 caractères" in lignes[0]        # plancher : "Hi" est trop court
    assert "≤ 14 caractères" in lignes[1]
