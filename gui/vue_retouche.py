# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la destination « Retouche » **dit** — sans Qt, donc testable sans écran.

Même partage que `gui/vue_oeuvres.py` porte pour la bibliothèque et `gui/pellicule.py` pour
la pellicule : ici vivent les phrases et les seuils, dans `gui/retouche.py` il ne reste que
des widgets. C'est la règle de couche de `gui/__init__.py`, et c'est ce qui permet au job de
CI qui n'installe pas PySide6 de vérifier ces décisions.

Trois sujets, et ils viennent tous d'une mesure du lot 35 :

1. **pourquoi un tome n'est pas dans la liste** — la retouche édite des planches, donc elle
   ne montre que les tomes manga et webtoon (`PLAN-35` L35.1 point 1) ;
2. **ce que le verrou de run protège** — un motif, une étape, un avancement, plutôt qu'un
   panneau gris (L35.5) ;
3. **ce que le cache d'aperçus coûte** — la mémoire mesurée, affichée, parce que la mesure
   de l'étape 0.1 a montré qu'elle n'est pas celle que le dépôt annonçait (L35.3 point 3).
"""
from __future__ import annotations

#: Combien de tomes non éditables on nomme avant de passer à « et N autres ». Trois tient
#: sur une ligne d'infobulle ; au-delà, la phrase devient un paragraphe qu'on ne lit plus.
NOMMES = 3


def phrase_tomes_absents(absents: list[str]) -> str:
    """Pourquoi tel tome de ce projet ne figure pas dans la liste. `""` s'ils y sont tous.

    ⚠ **Une liste qui filtre sans le dire est une liste qu'on croit complète.** Un projet
    peut porter à la fois un roman et son manga — `manga C/Vol.1` porte même
    165 planches manga *et* 271 images de scan (`docs/mesures/bibliotheque-2026-09-05.md`
    §1) — et quelqu'un qui a lancé un run light novel puis cherche son tome ici doit lire
    pourquoi il n'y est pas, pas conclure que le dossier a disparu.

    ⚠ Le chiffre porte son dénominateur, comme tout chiffre du dépôt : « 4 des 6 tomes »,
    jamais « 4 tomes »."""
    if not absents:
        return ""
    noms = ", ".join(f"« {nom} »" for nom in absents[:NOMMES])
    reste = len(absents) - NOMMES
    if reste > 0:
        noms += f" et {reste} autre{'s' if reste > 1 else ''}"
    pluriel = len(absents) > 1
    return (f"{noms} n'{'apparaissent' if pluriel else 'apparaît'} pas ici : la retouche "
            f"édite des PLANCHES, donc elle ne liste que les tomes manga et webtoon. Un tome "
            f"light novel se traite depuis « Light novel » — il n'a pas de bulles à corriger.")


def motif_de_verrou(etat: dict | None, cible: str = "") -> str:
    """La ligne du verrou de run global : le motif, l'étape, l'avancement — L35.5.

    Avant ce lot, `marquer_verrou(None, libelle, True)` affichait le libellé de la tâche suivi
    de « — affichage seul ». C'est vrai et c'est insuffisant : cela ne dit ni quel tome le run
    touche, ni où il en est, donc pas *combien de temps* le panneau va rester gris. Le bandeau
    du `PLAN-32` porte déjà ces chiffres ; il n'y avait qu'à les faire descendre.

    `etat` est le dictionnaire de `core/progression.Progression.etat()`. Il peut être vide —
    une tâche sans phases déclarées, un import, une copie de sources — et la phrase se réduit
    alors au motif, **sans inventer un avancement**."""
    if not cible:
        return ""
    bouts = [f"Verrouillé : run en cours sur {cible}"]
    etape = str((etat or {}).get("phase_libelle") or "")
    if etape:
        rang, phases = int(etat.get("rang") or 0), int(etat.get("phases") or 0)
        bouts.append(f"{etape} ({rang}/{phases})" if phases else etape)
    total = int((etat or {}).get("total") or 0)
    if total > 0:
        unite = str(etat.get("unite") or "").strip()
        courant = int(etat.get("courant") or 0)
        bouts.append(f"{unite + ' ' if unite else ''}{courant}/{total}")
    return " — ".join(bouts) + " — affichage seul"


#: En dessous, on ne dit rien du coût mémoire : une moyenne tirée d'un seul aperçu décrirait
#: la planche qu'on regarde, pas le tome. Même règle que `gui/avancement.MINIMUM`, et pour la
#: même raison — « une estimation fausse est pire que pas d'estimation ».
MINIMUM_APERCUS = 2


def ligne_de_cache(entrees: int, octets: int, plafond: int, voulues: int) -> str:
    """« aperçus 3/9 en cache — 105,6 Mo sur 120, ~35,2 Mo pièce ». `""` si on n'a rien à dire.

    ⚠ **C'est le point 3 de L35.3, et c'est celui que la mesure a rendu obligatoire.** Le
    dépôt annonçait « 1,04 Mo de calques » par aperçu et « la fenêtre ±10 pèse ~21 Mo ;
    le plafond par défaut (120 Mo) la contient largement ». Mesuré le 2026-09-05 : **9,35 Mo**
    par aperçu sur un tome paginé et **35,2 Mo** sur une bande webtoon. Une fenêtre de 21
    planches demande donc ~196 Mo là où le plafond en tient 120, et le cache s'emballait —
    136 compositions pour 12 aperçus gardés en 120 s. Un utilisateur n'avait aucun moyen de
    le savoir : ce chiffre-là ne s'affichait nulle part.

    `voulues` est la taille de la fenêtre glissante RÉELLEMENT retenue, pas la marge réglée :
    c'est le nombre qui, comparé aux entrées, dit s'il reste du préchargement à faire."""
    if entrees < MINIMUM_APERCUS:
        return ""
    mo = octets / (1024 * 1024)
    piece = mo / entrees
    return (f"aperçus {entrees}/{max(entrees, voulues)} en cache — "
            f"{mo:.1f} Mo sur {plafond / (1024 * 1024):.0f}, ~{piece:.1f} Mo pièce")


def infobulle_de_cache(entrees: int, octets: int, plafond: int, tenable: int,
                       demandee: int) -> str:
    """Ce que la ligne ne tient pas : pourquoi la fenêtre est bridée, et par quoi.

    ⚠ Elle nomme le réglage (`gui.apercu.plafond_mo`) plutôt que de dire « augmente la
    mémoire » : un conseil qu'on ne peut pas appliquer sans chercher où est le bouton est un
    conseil qui coûte plus qu'il ne rend."""
    if entrees < MINIMUM_APERCUS:
        return ""
    piece = octets / entrees / (1024 * 1024)
    base = (f"Un aperçu composé pèse ~{piece:.1f} Mo sur ce tome. Le plafond du cache vaut "
            f"{plafond / (1024 * 1024):.0f} Mo (`gui.apercu.plafond_mo`), il en tient donc "
            f"{tenable}.")
    if tenable < demandee:
        return (base + f"\nLa fenêtre de préchargement demandait {demandee} planches : elle "
                       f"est ramenée à {tenable}. Sans ce frein, le cache évincerait puis "
                       f"recomposerait sans fin — mesuré à 136 compositions pour 12 aperçus "
                       f"gardés en 120 s (docs/mesures/retouche-2026-09-05.md).")
    return base + "\nLa fenêtre de préchargement tient entièrement dedans."


# --------------------------------------------------------------------------- #
#  L35.2 — le chemin inverse : un run qui finit propose la retouche
# --------------------------------------------------------------------------- #

#: Les briques dont un tome se retouche. Ce sont les identifiants de `Fenetre.LANCEURS`,
#: c'est-à-dire ceux que `_cible_run["brique"]` porte : `"ln"` pour le light novel,
#: `"manga"` pour le manga **et pour le webtoon** — le webtoon n'est pas une brique, c'est
#: `--format webtoon` du même orchestrateur (`PLAN-31` L31.7).
#:
#: ⚠ `"webtoon"` y figure quand même, et ce n'est pas une redite : si le jour venait où le
#: format devenait une brique à part, l'oublier ici ne ferait disparaître qu'un bouton, en
#: silence. Une liste coûte moins cher qu'un `!= "ln"`, qui rendrait `True` sur tout ce
#: qu'on n'aurait pas prévu.
BRIQUES_RETOUCHABLES = ("manga", "webtoon")


def libelle_retouche(brique: str, planches) -> str:
    """Le bouton « Retoucher… » du bilan de run. `""` quand il n'y a rien à proposer.

    ⚠ **Le compte ou rien.** Le dépôt sait souvent exactement quelles planches un travail
    vient de réécrire — `Fenetre._planches_du_run` existe depuis le lot 18 pour ne pas jeter
    tout le cache d'aperçus après un relettrage de trois planches (« ~21 aperçus perdus, soit
    ~29 s de recomposition pour rien ») — et quand il le sait, le bouton le dit. Quand il ne
    le sait pas, il ne l'invente pas : un run lancé depuis « Manga » peut toucher n'importe
    quelle planche, et « Retoucher les 131 planches » serait un chiffre sans dénominateur.

    ⚠ Un run light novel (`brique="ln"`) ne rend rien : il n'y a pas d'éditeur light novel
    dans ce dépôt (L35.6), et proposer un bouton qui mène à une destination où le tome
    n'apparaîtra même pas dans la liste serait pire que de ne rien proposer."""
    if str(brique or "") not in BRIQUES_RETOUCHABLES:
        return ""
    nombre = len(planches or ())
    if nombre:
        return f"Retoucher {nombre} planche{'s' if nombre > 1 else ''}"
    return "Retoucher ce tome"
