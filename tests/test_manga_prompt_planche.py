# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que le traducteur reçoit RÉELLEMENT — l'énoncé assemblé (lot 15).

Le pipeline ne fait pas un appel par bulle : l'unité est la planche entière, une liste
numérotée, un appel. Le problème n'était donc pas la découpe, c'était le **contenu du
message** : glossaire, dernières répliques, place en pixels, liste numérotée. Et c'est tout.

Ces tests portent sur les quatre choses que ce lot y ajoute ou y répare :

· le **contexte inter-planches**, réparti par planche et étiqueté (L7.1) ;
· l'**appariement image ↔ planche** en mode lot, qui était positionnel et faux (L7.6 §3) ;
· le **rééquilibrage** de la consigne de place — contrainte, pas objectif (L7.8) ;
· l'**iso-comportement** sans les nouvelles clés, qui est le critère d'acceptation du lot.

Aucun appel LLM : on lit les messages assemblés, sans jamais en envoyer un.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from manga import checkpoints, consignes
from manga import orchestrator_manga as orch


# --------------------------------------------------------------------------- #
# L7.1 — le contexte inter-planches
# --------------------------------------------------------------------------- #

@pytest.fixture()
def tome(tmp_path: Path) -> Path:
    """Trois planches déjà traduites, la première VOLUBILE.

    C'est le cas qui révélait le défaut : la troncature globale `[-max:]` gardait la fin de
    N−1 et jetait entièrement N−3 et N−2."""
    for page, textes in ((1, [f"P1-{k}" for k in range(20)]),
                         (2, ["P2-a", "P2-b"]),
                         (3, ["P3-a", "P3-b"])):
        checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, page), textes)
    return tmp_path


def test_le_budget_est_reparti_entre_les_planches(tome):
    """Le défaut : sur une planche bavarde, `[-6:]` gardait six répliques de N−1 et **aucune**
    de N−3 ni de N−2. Silencieusement."""
    lignes = orch._contexte_precedent(tome, page=4, planches=3, max_repliques=6)

    assert len(lignes) == 6
    for planche in ("N−1", "N−2", "N−3"):
        assert any(planche in ligne for ligne in lignes), f"{planche} absente : {lignes}"


def test_chaque_ligne_dit_de_quelle_planche_elle_vient(tome):
    """Quelques tokens, et une liste plate redevient une séquence : le modèle sait laquelle
    une phrase en cours peut prolonger."""
    lignes = orch._contexte_precedent(tome, page=4, planches=3, max_repliques=6)

    assert lignes[-1].startswith("- Planche N−1 : ")
    assert lignes[-1].endswith("P3-b")


def test_le_reste_du_budget_va_aux_planches_les_plus_recentes(tome):
    """À budget non divisible, c'est N−1 qui mérite la réplique supplémentaire."""
    lignes = orch._contexte_precedent(tome, page=4, planches=3, max_repliques=5)

    assert sum(1 for ligne in lignes if "N−1" in ligne) == 2
    assert sum(1 for ligne in lignes if "N−3" in ligne) == 1


def test_un_contexte_desactive_ne_rend_rien(tome):
    assert orch._contexte_precedent(tome, page=4, planches=0, max_repliques=6) == []
    assert orch._contexte_precedent(tome, page=1, planches=3, max_repliques=6) == []


def test_le_forcage_terminologique_est_rejoue_sur_le_contexte(tome):
    """⚠ Propriété à ne pas casser : le cache garde la sortie BRUTE du modèle, le forçage
    s'applique à l'USAGE et non à l'écriture — c'est ce qui permet de corriger le glossaire et
    de relancer `--from rendu` sans un seul appel LLM. Sans ce rejeu, le contexte
    transmettrait au modèle les orthographes que le glossaire interdit."""
    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tome, 3), ["Kataphrakto ici"])
    gloss = {"objets": [{"nom": "Kataphract", "interdits": ["Kataphrakto"],
                         "force": True, "genre": "m"}]}

    lignes = orch._contexte_precedent(tome, page=4, planches=1, max_repliques=4, gloss=gloss)

    assert lignes and "Kataphract " in lignes[0]
    assert "Kataphrakto" not in lignes[0]


# --------------------------------------------------------------------------- #
# L7.6 §3 — l'appariement image ↔ planche
# --------------------------------------------------------------------------- #

class _Traducteur:
    """Double : garde le message reçu et les images, et rend une liste numérotée complète."""

    temperature = 0.3
    llm = None

    def __init__(self):
        self.messages: list[str] = []
        self.images: list[list | None] = []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.messages.append(user)
        self.images.append(images)
        n = sum(1 for ligne in dry_payload.splitlines() if ligne.strip())
        return "\n".join(f"{i + 1}. FR{i + 1}" for i in range(n))


def _planches(images: dict[int, str | None]) -> list[orch.PlancheLot]:
    return [orch.PlancheLot(index=p, textes_jp=[f"jp{p}a", f"jp{p}b"], bboxes=[None, None],
                            image_b64=images.get(p))
            for p in sorted(images)]


def test_une_planche_sans_image_ne_decale_plus_les_autres():
    """Le défaut : `[p.image_b64 for p in utiles if p.image_b64]` RETIRE des éléments de la
    liste. Une seule planche à `image_b64` nul décalait donc toutes les suivantes — l'image k
    ne correspondait plus à la planche k, et rien dans le texte ne les reliait. En vision, le
    lot est écrêté à quatre planches : le désalignement portait sur au plus quatre planches,
    ce qui suffit à mettre les répliques dans les mauvaises bulles."""
    agent = _Traducteur()

    orch._translate_lot(_planches({1: None, 2: "IMG2", 3: "IMG3"}), agent,
                        replier=lambda p: ([], None, "vide"))

    message = agent.messages[0]
    assert agent.images[0] == ["IMG2", "IMG3"]
    assert "L'image jointe n° 1 est la planche 2." in message
    assert "L'image jointe n° 2 est la planche 3." in message
    assert "planche 1." not in message.split("L'image")[-1]


def test_un_lot_sans_image_n_annonce_aucune_image():
    agent = _Traducteur()

    orch._translate_lot(_planches({1: None, 2: None}), agent,
                        replier=lambda p: ([], None, "vide"))

    assert agent.images[0] is None
    assert "L'image jointe" not in agent.messages[0]


# --------------------------------------------------------------------------- #
# L7.8 — la place est une contrainte, pas un objectif
# --------------------------------------------------------------------------- #

def test_la_consigne_de_place_interdit_d_abreger_le_sens():
    """L'ancienne formule (« dépasser force une police illisible ») ne disait que la moitié
    qui pousse à couper, et rien ne mesurait l'autre : le registre de `quality_manga` ne
    bornait que par le haut."""
    entete = consignes.GABARITS_ENTETE.lower()

    assert "contrainte" in entete and "objectif" in entete
    assert "abréger" in entete or "abreger" in entete


def test_le_gabarit_reste_une_ligne_numerotee_par_bulle():
    lignes = orch._lignes_gabarits([(0, 0, 100, 100), None, (0, 0, 200, 200)],
                                   depart=5, sources=["", "", ""], langue="jp")

    assert [ligne.split(".")[0] for ligne in lignes] == ["5", "7"]


# --------------------------------------------------------------------------- #
# Iso-comportement — le critère d'acceptation du lot
# --------------------------------------------------------------------------- #

def test_sans_structure_l_enonce_de_planche_est_celui_d_avant():
    """« Le mode texte SANS les nouvelles clés produit un résultat inchangé », vérifiable par
    diff de `traduction.json` sur un tome entier. Ici on vérifie l'énoncé lui-même : ni
    séparateur de groupe, ni mention de forme, ni étiquette de locuteur."""
    agent = _Traducteur()

    orch._translate_page(agent, None, ["jp1", "jp2"], mode_vision=False, gloss_text="")

    message = agent.messages[0]
    assert "1. jp1\n2. jp2" in message
    assert "Groupe" not in message
    assert "[A]" not in message
    assert consignes.STRUCTURE_NOTE not in message


def test_avec_une_structure_l_enonce_porte_groupes_types_et_locuteurs():
    from manga import planche as planche_mod

    agent = _Traducteur()
    structure = planche_mod.Structure(groupes=[1, 2], types=[planche_mod.DIALOGUE,
                                                             planche_mod.CRI],
                                      locuteurs=["A", "B"])

    orch._translate_page(agent, None, ["jp1", "jp2"], mode_vision=False, gloss_text="",
                         structure=structure)

    message = agent.messages[0]
    assert "— Groupe 1 —" in message and "— Groupe 2 —" in message
    assert "1. [A] jp1" in message
    assert "2. [B] (cri) jp2" in message
    assert consignes.STRUCTURE_NOTE in message


def test_le_plafond_de_sortie_ignore_les_annotations():
    """Elles décrivent l'ÉNONCÉ ; le plafond mesure ce que la RÉPONSE va peser, et la réponse
    ne reprend ni les groupes ni les étiquettes. Le `dry_payload` suit la même règle — c'est
    lui que l'agent renvoie en dry-run, et `analyser_numerotation` traiterait une ligne non
    numérotée comme la continuation de la précédente."""
    from manga import planche as planche_mod

    charges: list[str] = []

    class _Espion(_Traducteur):
        def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
            charges.append(dry_payload)
            return super().run(user, dry_payload, max_tokens, temperature, images)

    structure = planche_mod.Structure(groupes=[1, 2], types=[planche_mod.CRI] * 2,
                                      locuteurs=["A", "B"])
    orch._translate_page(_Espion(), None, ["jp1", "jp2"], mode_vision=False, gloss_text="",
                         structure=structure)

    assert charges[0] == "1. jp1\n2. jp2"
