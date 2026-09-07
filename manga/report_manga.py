# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`RAPPORT.md` de la brique manga — miroir de celui du light novel.

**Point de conception essentiel.** Les pages déjà générées sont sautées par
`process_volume` et ne produisent donc **aucune statistique fraîche**. Construire le rapport
à partir du seul run en cours donnerait, sur une reprise, un rapport quasi vide — donc
mensonger : « 3 pages traitées, 0 problème » alors que le tome en compte 150 et 14
débordements.

D'où le `qa.json` **par page**, persisté sous `.checkpoints/page_XXXX/` au moment où la page
est calculée, et relu pour TOUTES les pages à la construction du rapport — y compris celles
réutilisées du cache. Le rapport décrit ainsi l'état du **tome**, pas celui du run.

C'est l'application directe du principe du pipeline LN : « un échec non compté est un échec
invisible » (`pipeline/orchestrator.py`).
"""
from __future__ import annotations

import json
from pathlib import Path

from core import report
from core.version import __version__

from ._config import fusion
from . import bubbles_split, checkpoints, effacement, geometry

# Le nom vit dans `checkpoints` : c'est lui qui doit pouvoir le supprimer quand une
# scission change le nombre de bulles (cf. `checkpoints.migrate_page`).
QA_FILENAME = checkpoints.QA_FILENAME

# Sous ce remplissage de masque, une région non scindée est signalée : c'est là que le
# lettrage peut souffrir (texte de deux ballons dans une géométrie fusionnée) sans qu'aucun
# autre compteur ne s'en aperçoive.
#
# ⚠ REPLI seulement : la valeur effective est lue dans `manga.detection.scission.seuil_suspect`
# (cf. `_seuil_bilobee`). En dur, changer le seuil modifiait ce qui est SCINDÉ sans changer ce
# que le rapport ANNONCE — deux chiffres qui se contredisent dans le même run.
# `tools/mesurer_bulles.py` lisait déjà la config, lui.
_SEUIL_BILOBEE = bubbles_split.SEUIL_SUSPECT


def _seuil_bilobee(mcfg: dict) -> float:
    scission = (mcfg.get("detection") or {}).get("scission") or {}
    return float(scission.get("seuil_suspect", _SEUIL_BILOBEE))

_DEFAUTS_RAPPORT = {
    "seuil_confiance": 0.50,
    "max_lignes_section": 40,
}


def _extrait(texte: str | None, maxi: int = 60) -> str:
    """Un extrait de réplique, avec une ellipse **seulement s'il y a une suite**.

    Le rapport écrivait `« Dok...… »` sur des répliques de trois mots : l'ellipse était
    concaténée en dur après une coupe qui n'avait rien coupé. Un lecteur y voit une troncature
    du LETTRAGE — donc un défaut à corriger — là où la réplique est entière."""
    t = (texte or "").strip()
    return t if len(t) <= maxi else t[:maxi].rstrip() + "…"


def save_page_qa(ckpt_dir: Path, donnees: dict) -> None:
    """Enregistre le contrôle qualité d'UNE page, à côté de ses autres checkpoints."""
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    (ckpt_dir / QA_FILENAME).write_text(
        json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def load_page_qa(ckpt_dir: Path) -> dict | None:
    p = Path(ckpt_dir) / QA_FILENAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None      # un qa.json corrompu ne doit pas faire échouer un tome


def build_page_qa(*, page: int, nom_fichier: str, regions, styles, texts_jp, translated,
                  rendu_qa: list[dict], motif_traduction: str | None = None,
                  strategie_traduction: str = "",
                  rattrapees: list[int] | None = None,
                  polices_psd: list[str] | None = None,
                  sfx: list | None = None, sfx_textes: list[str] | None = None,
                  sfx_traductions: list[str] | None = None,
                  sfx_gloses: list | None = None, sfx_mode: str = "",
                  scission_cfg: dict | None = None, lot_taille: int = 1,
                  origines: dict | None = None, corrigees: list[int] | None = None,
                  think=None) -> dict:
    """Assemble le contrôle qualité d'une page à partir de ce que les étapes ont mesuré."""
    rattrapees = set(rattrapees or ())
    # Origine de chaque réplique. `manuelle` l'emporte sur `editeur` : une saisie au clavier
    # est la décision la plus forte, et c'est elle que le relecteur doit voir en premier.
    origines = dict(origines or {})
    for i in (corrigees or ()):
        origines[i] = "manuelle"
    # Forme des régions au remplissage bas : « suspecte » (un goulot existe, le découpage a
    # été refusé) ou « dentelee » (aucun goulot — ballon de cri, longue queue). Sans cette
    # distinction, le rapport rangeait 45 bulles parfaitement normales du Vol.2 sous
    # « bi-lobées SUSPECTES » et noyait les vrais doubles.
    formes = bubbles_split.classer_non_scindees(regions or [], scission_cfg)
    bulles = []
    for i, region in enumerate(regions or []):
        style = styles[i] if styles and i < len(styles) else None
        entree_rendu = next((e for e in rendu_qa
                             if e.get("type") == "bulle" and e.get("index") == i), {})
        bulles.append({
            "index": i,
            "bbox": list(region.bbox),
            "score": round(float(region.score), 4),
            "kind": region.kind,
            # Remplissage du masque : la métrique qui distingue un ballon (médiane 0,89) d'une
            # région bi-lobée (0,60). Elle n'était calculée nulle part avant le lot 4.2, ce qui
            # explique qu'aucun rapport n'ait jamais signalé les bulles doubles.
            "remplissage_masque": round(geometry.remplissage(region.mask), 3)
            if getattr(region, "mask", None) is not None else None,
            "scindee": bool(getattr(region, "scindee", False)),
            # Absent des qa.json d'avant ce lot : le rapport retombe alors sur l'ancien
            # classement, qui range tout remplissage bas sous « bi-lobée ».
            "forme": formes.get(i, ""),
            "mode_nettoyage": getattr(style, "mode", None),
            "inverse": bool(getattr(style, "inverted", False)),
            "uniformite": round(float(getattr(style, "uniformity", 0.0)), 4),
            "rayon_erosion": int(getattr(style, "erode_radius", 0)),
            "ocr": (texts_jp[i] if texts_jp and i < len(texts_jp) else ""),
            "traduction": (translated[i] if translated and i < len(translated) else ""),
            # Traduite par un appel UNITAIRE, après que la traduction de page l'a laissée
            # vide : elle n'a pas vu le contexte de la planche, et mérite donc un œil.
            "rattrapee": i in rattrapees,
            # Qui a produit cette réplique : `pipeline` (le run), `editeur` (retraduite bulle
            # par bulle depuis l'interface, donc SANS le contexte de planche) ou `manuelle`
            # (saisie au clavier). Jusqu'ici une réplique reprise à la main était
            # indistinguable des 943 autres — `rattrapee: false` comme tout le monde.
            "origine": origines.get(i, "pipeline"),
            "taille_police": entree_rendu.get("taille"),
            "lignes": entree_rendu.get("lignes"),
            "debordement": bool(entree_rendu.get("overflow", False)),
            "repli": entree_rendu.get("repli", ""),
            # POURQUOI la bulle a été difficile : `bulle_degeneree` · `bulle_etroite` ·
            # `texte_trop_long`. Les deux premières désignent la DÉTECTION ; seule la
            # troisième justifie de raccourcir la réplique.
            "cause": entree_rendu.get("cause", ""),
        })
    return {
        "page": page,
        "fichier": nom_fichier,
        "version": __version__,
        "bulles": bulles,
        "ecarts": [e for e in rendu_qa if e.get("type") == "ecart_comptage"],
        "glyphes_manquants": [e for e in rendu_qa if e.get("type") == "glyphes_manquants"],
        "bulles_vides": [e for e in rendu_qa if e.get("type") == "bulle_vide"],
        # Le seul incident du rendu où du TEXTE DISPARAÎT de la planche : la région a été
        # nettoyée (source effacée) mais rien n'a été dessiné dessus, ou le nettoyage a
        # renoncé et la traduction n'est nulle part. Une bulle blanche est indistinguable
        # d'un choix éditorial — sans cette liste, la perte ne se voit sur aucun compte.
        "non_dessinees": [e for e in rendu_qa
                          if e.get("type") == "replique_non_dessinee"],
        # Zones dont le dessin d'origine a été recollé faute de tout texte : le nettoyage les
        # avait repeintes, l'OCR et la traduction n'y ont rien trouvé. Fausses détections
        # probables (cf. `rendu.restaurer_sans_texte`).
        "restaurees": [e for e in rendu_qa if e.get("type") == "restauree"],
        "motif_traduction": motif_traduction,
        # COMMENT les répliques ont été rattachées à leurs bulles (cf.
        # `quality_manga.STRATEGIES`). Une planche reconstituée positionnellement peut avoir
        # ses répliques dans les mauvaises bulles ; une planche numérotée, non. Rien ne
        # distinguait les deux jusqu'ici, et le rendu a exactement la même allure.
        "strategie_traduction": strategie_traduction,
        # Nombre de planches qui partageaient l'appel de traduction (1 = une planche, un
        # appel). Une planche traduite au sein d'un lot de 20 n'a pas la même valeur de preuve
        # qu'une planche traduite seule : elle a disposé de moins d'attention par bulle et
        # d'un contexte plus dilué. Sans ce champ, un tome traduit par lots et un tome traduit
        # planche par planche seraient indistinguables au rapport — y compris pour comparer
        # deux runs, ce qui est exactement la mesure qu'on voudra faire.
        "lot_taille": int(lot_taille),
        # Niveau de raisonnement du traducteur pour cette planche. `--think` ne laissait
        # AUCUNE trace nulle part : deux runs d'un même tome, l'un raisonné et l'autre non,
        # produisaient des `qa.json` indiscernables — donc incomparables.
        "think": think,
        # Noms PostScript des calques de type du PSD : Photoshop substitue en silence une police
        # qu'il ne trouve pas, et le lettrage change sans que rien ne l'explique.
        "polices_psd": list(polices_psd or []),
        # Texte SUR LE DESSIN (lot 9). Compté à part des bulles, parce que c'en est autre
        # chose : on ne l'efface pas, on le glose. `posee: false` distingue « le modèle n'a
        # rien voulu en faire » (filigrane) de « aucune zone libre » — la première n'est pas
        # un incident, la seconde en est un.
        # Le MODE décide de la lecture des `posee: false` : en "rapport" aucune glose n'est
        # tentée, donc aucune ne peut être « refusée faute de place ». Sans ce champ, le
        # rapport annonçait 7 échecs de placement sur un run qui n'avait rien tenté.
        "sfx_mode": sfx_mode,
        "sfx": [
            {
                "index": k,
                "bbox": list(z.bbox),
                "source": (sfx_textes[k] if sfx_textes and k < len(sfx_textes) else ""),
                "traduction": (sfx_traductions[k]
                               if sfx_traductions and k < len(sfx_traductions) else ""),
                "posee": bool(sfx_gloses and k < len(sfx_gloses) and sfx_gloses[k] is not None),
            }
            for k, z in enumerate(sfx or [])
        ],
    }


# Sections tronquées : déplacé dans le socle au lot 2.6 (`core/report.py`), partagé avec le
# light novel qui appliquait la même troncature à la main sur ses forçages refusés.
_section = report.section


def _sections_detection(detections: list[tuple[int, dict]], maxi: int) -> list[str]:
    """Ce que la DÉTECTION a écarté, relancé, ou perdu — relu dans les `regions.json`.

    Trois faits, trois sections, et aucun des trois n'apparaissait nulle part avant le lot 12 :

    · **les rejets du post-traitement**, comptés par motif. Le seul filtre qui existait —
      « moins de 2 px de côté » — était muet : personne n'a jamais su combien de détections il
      mangeait. Un filtre muet est la façon dont on perd les treize planches suivantes ;
    · **les escalades**, avec leur réglage et le verdict de l'arbitre. Une escalade refusée est
      une information sur la planche, pas un non-événement : c'est elle qui dit qu'on a
      cherché et qu'il n'y avait rien ;
    · **les bulles rognées par une voisine**. Elles étaient signalées en `warn` — donc dans
      `perf.log`, où personne ne les relit — **après** que `save_regions` avait déjà écrit, et
      elles n'étaient ni dans `provenance`, ni dans `qa.json`. Mesuré sur la planche 3 du
      Chap.11 : deux bulles partageaient 36 108 px.

    ⚠ La cause n'est pas la qualité de la détection, c'est le FORMAT DE CACHE : `masks.png` est
    une image d'ÉTIQUETTES, donc un pixel ne peut appartenir qu'à une région — et **élargir
    l'étiquette n'y change rien**. Le lot 14 a mesuré la question et tranché : la largeur du
    tableau (lot 14, L6.3) borne le NOMBRE de régions, pas le partage des pixels. Réparer
    vraiment demanderait un masque par région, donc un format de cache entièrement différent,
    pour un défaut qui touche 15 planches sur 125 mesurées. Ici on cesse seulement de perdre
    l'information en silence."""
    from .detection import MOTIFS_REJET, MOTIFS_SAUT
    from .detection_retry import MOTIFS_ESCALADE

    sections: list[str] = []
    rejets: dict[str, int] = {}
    sauts: dict[str, int] = {}
    planches_saut: dict[str, list[int]] = {}
    planches_rejet: dict[str, list[int]] = {}
    escalades: list[str] = []
    n_escalades = n_acceptees = bulles_gagnees = 0
    rognees: list[str] = []
    absorbees: list[str] = []
    troncatures: list[str] = []
    traits: list[str] = []
    par_encre: list[str] = []
    creux: list[str] = []
    for page, meta in detections:
        for motif, n in (meta.get("rejets") or {}).items():
            rejets[motif] = rejets.get(motif, 0) + int(n)
            planches_rejet.setdefault(motif, []).append(page)
        for motif, n in (meta.get("fenetres_sautees") or {}).items():
            sauts[motif] = sauts.get(motif, 0) + int(n)
            planches_saut.setdefault(motif, []).append(page)
        esc = meta.get("escalade") or {}
        if esc:
            n_escalades += 1
            gagnees = int(esc.get("apres", 0)) - int(esc.get("avant", 0))
            if esc.get("accepte"):
                n_acceptees += 1
                bulles_gagnees += max(0, gagnees)
            escalades.append(
                f"page {page} — {MOTIFS_ESCALADE.get(esc.get('motif'), esc.get('motif', '?'))}"
                f" · input_size {esc.get('input_size')} · conf "
                f"{float(esc.get('conf_threshold', 0)):.2f} · {esc.get('avant')} → "
                f"{esc.get('apres')} bulle(s) · {esc.get('verdict', '')}")
        for c in (meta.get("chevauchements") or []):
            x0, y0, x1, y1 = (c.get("bbox") or [0, 0, 0, 0])
            rognees.append(f"page {page} — bulle ({x0}, {y0})–({x1}, {y1}), score "
                           f"{float(c.get('score', 0)):.2f} : {c.get('perdus', 0)} px cédés à "
                           f"une voisine")
        if meta.get("absorbees"):
            absorbees.append(f"page {page} — {meta['absorbees']} région(s) entièrement "
                             f"recouverte(s) par une voisine, écartée(s)")
        for t in (meta.get("germes_tronques") or []):
            x0, y0, x1, y1 = (t.get("bbox") or [0, 0, 0, 0])
            troncatures.append(
                f"page {page} — région ({x0}, {y0})–({x1}, {y1}) : {t.get('germes', 0)} "
                f"germe(s) de lobe au-delà de `scission.max_lobes`"
                + (f", découpée en {t['lobes']}" if t.get("lobes") else ", non découpée"))
        for t in (meta.get("trait_sans_goulot") or []):
            x0, y0, x1, y1 = (t.get("bbox") or [0, 0, 0, 0])
            traits.append(f"page {page} — région ({x0}, {y0})–({x1}, {y1}), remplissage "
                          f"{float(t.get('remplissage', 0)):.2f}")
        for t in (meta.get("lobes_creux") or []):
            x0, y0, x1, y1 = (t.get("bbox") or [0, 0, 0, 0])
            creux.append(f"page {page} — lobe ({x0}, {y0})–({x1}, {y1}), remplissage "
                         f"{float(t.get('remplissage', 0)):.2f} sur {t.get('aire', 0)} px")
        for t in (meta.get("scindees_par_encre") or []):
            x0, y0, x1, y1 = (t.get("bbox") or [0, 0, 0, 0])
            par_encre.append(
                f"page {page} — région ({x0}, {y0})–({x1}, {y1}) → {t.get('lobes', 0)} lobe(s)"
                + (f", couture encrée à {float(t['encre']):.0%}"
                   if t.get("encre") is not None else ""))

    if rejets:
        lignes = [f"{MOTIFS_REJET.get(m, m)} — {n} détection(s) sur "
                  f"{len(set(planches_rejet.get(m, ())))} planche(s) "
                  f"(`{m}`)" for m, n in sorted(rejets.items(), key=lambda kv: -kv[1])]
        sections += _section("Détections REJETÉES au post-traitement (par motif)", lignes, maxi)
    # ⚠ Section SÉPARÉE des rejets, et ce n'est pas de la cosmétique : une détection écartée
    # après examen et une portion de planche à laquelle on n'a jamais payé d'inférence ne se
    # lisent pas de la même façon. La seconde est un pari, et un pari se publie.
    if sauts:
        sections += _section(
            "Fenêtres SAUTÉES sans inférence (porte d'encre)",
            [f"{MOTIFS_SAUT.get(m, m)} — {n} fenêtre(s) sur "
             f"{len(set(planches_saut.get(m, ())))} planche(s) (`{m}`)"
             for m, n in sorted(sauts.items(), key=lambda kv: -kv[1])], maxi)
    if escalades:
        sections += _section(
            f"Escalades de détection — {n_acceptees} acceptée(s) sur {n_escalades}, "
            f"+{bulles_gagnees} bulle(s)", escalades, maxi)
    # ⚠ Pas de troncature à six ici, contrairement au `warn` du run : le rapport décrit le
    # tome. C'est précisément la septième bulle rognée qu'on perdait.
    sections += _section("Bulles ROGNÉES par une voisine (masques rendus disjoints — "
                         "`masks.png` est une image d'étiquettes, un pixel ne peut "
                         "appartenir qu'à une région)", rognees, maxi)
    sections += _section("Régions entièrement RECOUVERTES par une voisine, écartées",
                         absorbees, maxi)
    # ⚠ Ce n'est pas un rejet, c'est une TRONCATURE : une grappe de cinq ballons est ramenée à
    # quatre et les pixels du cinquième repartent au lobe le plus proche. Silencieusement,
    # jusqu'au lot 13 — d'où la mention explicite de la clé, qui est le seul levier.
    sections += _section("Germes de lobe TRONQUÉS par `scission.max_lobes` (les pixels "
                         "concernés sont repartis au lobe le plus proche, pas perdus)",
                         troncatures, maxi)
    sections += _section("Régions traversées par un TRAIT sans goulot d'érosion "
                         "(signalées, jamais scindées d'autorité — à regarder sur la planche)",
                         traits, maxi)
    sections += _section("Régions scindées sur CONFIRMATION DU TRAIT de contour "
                         "(garde-fou de forme relâché jusqu'au plancher)", par_encre, maxi)
    # ⚠ Ces lobes-là ne viennent PAS d'un garde-fou de scission trop lâche : celui-ci exige
    # 0,72 de remplissage et ne peut pas produire 0,01. Ils sont le résidu de
    # `rendre_disjoints`, quand le détecteur a émis à la fois une région fusionnée et les
    # ballons qui la composent. La cause est le format de `masks.png` (image d'étiquettes,
    # un pixel ne peut appartenir qu'à une région), et elle est structurelle : cf.
    # `_sections_detection`. Ici on cesse de le perdre.
    sections += _section("Lobes VIDÉS par le rendu disjoint (une voisine mieux notée a pris "
                         "leurs pixels — la scission n'y est pour rien)", creux, maxi)
    return sections


LIBELLES_ORIGINE = {
    "pipeline": "produite(s) par un run",
    "editeur": "reprise(s) bulle par bulle depuis l'éditeur (sans le contexte de planche)",
    "manuelle": "saisie(s) à la main",
}

#: Motifs de rejet d'une zone hors bulle, tels que `text_detection.hors_des_bulles` les
#: compte (lot 21, L21.1). Les nommer au rapport est la contrepartie exigée de tout filtre :
#: `aire_max` et `remplissage_max` sont désarmés par défaut, mais quiconque les arme doit
#: voir sur-le-champ ce qu'ils lui coûtent.
LIBELLES_REJET_SFX = {
    "aire_min": "sous l'aire minimale (bruit de trame)",
    "aire_max": "au-dessus de la borne haute d'aire",
    "remplissage_max": "trop pleine pour un tracé de lettrage",
    "dans_bulle": "déjà dans une bulle (traitée par le chemin nominal)",
}

#: Nom du dossier de crops de la voie C. Repris de `orchestrator_manga.DOSSIER_CROPS_SFX`
#: par valeur et non par import : `report_manga` est importé par l'orchestrateur, l'inverse
#: ferait un cycle. Un test vérifie que les deux ne divergent pas.
DOSSIER_CROPS_SFX = "sfx_illisibles"


def _compter_origines(pages_qa: list[dict]) -> dict:
    """Répartition des répliques par origine, sur tout le tome.

    Ne compte pas `pipeline` seul : quand tout vient du pipeline, la ligne n'apprend rien et
    le rapport a déjà bien assez de chiffres."""
    compte: dict[str, int] = {}
    for qa in pages_qa:
        for b in qa.get("bulles") or []:
            origine = b.get("origine") or "pipeline"
            compte[origine] = compte.get(origine, 0) + 1
    return compte if set(compte) - {"pipeline"} else {}


def _ligne_traduction(pages_qa: list[dict]) -> str:
    """Taille de lot et raisonnement RÉELLEMENT employés, relus depuis les `qa.json`.

    ⚠ Par planche, et non d'après la configuration du run en cours : sur un tome repris, la
    config décrit ce qu'on vient de lancer, pas ce qui a produit les 147 autres planches."""
    lots: dict[int, int] = {}
    pensees: dict[str, int] = {}
    for qa in pages_qa:
        taille = int(qa.get("lot_taille") or 1)
        lots[taille] = lots.get(taille, 0) + 1
        think = qa.get("think")
        if think not in (None, False, "none"):
            cle = "medium" if think is True else str(think)
            pensees[cle] = pensees.get(cle, 0) + 1
    if not lots or (len(lots) == 1 and 1 in lots and not pensees):
        return ""          # une planche, un appel, aucun raisonnement : rien à signaler
    bouts = ["- Traduction : "
             + ", ".join(f"{n} planche(s) par lot(s) de {t}" for t, n in sorted(lots.items()))]
    if pensees:
        bouts.append(" · raisonnement : "
                     + ", ".join(f"{n} en « {k} »" for k, n in sorted(pensees.items())))
    return "".join(bouts)


def _compter_tri(pages_qa: list[dict]) -> dict:
    """Recompte le triage du texte hors bulle sur TOUT le tome, depuis les `qa.json`.

    ⚠ `stats_sfx["tri"]` n'existe que pour les planches du RUN en cours. Sur une reprise à
    trois planches, il annonçait « 3 traduite(s) » en se présentant comme un bilan de tome —
    un chiffre exact et complètement trompeur. Le rapport décrit l'état du tome ; c'est
    exactement pourquoi `qa.json` est persisté par planche.

    Renvoie `{}` si aucune planche ne porte de zone hors bulle : l'appelant retombe alors sur
    les statistiques du run, qui restent la seule source pour un tome d'avant ce champ."""
    tri: dict[str, int] = {}
    for qa in pages_qa:
        for zone in qa.get("sfx") or []:
            source = (zone.get("source") or "").strip()
            trad = (zone.get("traduction") or "").strip()
            cle = "japonais" if trad else ("ponctuation" if source else "bruit")
            tri[cle] = tri.get(cle, 0) + 1
    return tri


def _lignes_structure(structures: dict | None, registre_par_planche: dict | None,
                      stats_relecture: dict | None) -> list[str]:
    """Ce que le lot 15 a mesuré : structure de planche, registre, relecture.

    Les trois tiennent ensemble parce qu'ils répondent à la même question — *est-ce que ce
    qu'on a ajouté au prompt sert à quelque chose ?* — et qu'aucun des trois ne se mesure sans
    être publié.

    ⚠ **Le taux d'« indéterminé » est en premier, et il est là pour être regardé.** Un
    classifieur qui type tout est un classifieur suspect ; celui-ci laisse 86,2 % des bulles
    sans type sur les dix volumes de `build/`, et c'est la propriété qu'il faut surveiller quand on
    touche à `manga.structure.*`."""
    from . import planche as planche_mod
    from . import registre as registre_mod

    lignes: list[str] = []
    if structures:
        t = planche_mod.taux(list(structures.values()))
        total = max(1, t["bulles"])
        types = t["types"]
        lignes.append(
            f"- Structure de planche : {t['planches_annotees']} planche(s) annotée(s) · "
            f"types — "
            + ", ".join(f"{types.get(nom, 0)} {nom}" for nom in planche_mod.TYPES)
            + f" ({100 * types.get(planche_mod.INDETERMINE, 0) / total:.0f} % indéterminés) · "
            + f"{t['etiquetees']} bulle(s) avec étiquette de locuteur"
            + (f" · {t['planches_repli']} planche(s) ordonnée(s) par repli diagonal"
               if t["planches_repli"] else ""))
    if registre_par_planche:
        r = registre_mod.relever_tome(registre_par_planche)
        if r.total:
            lignes.append(
                f"- Registre de 2ᵉ personne : {r.tutoiement} tutoiement(s), "
                f"{r.vouvoiement} vouvoiement(s)"
                + (f" · dominante « {r.dominant()} »" if r.dominant() else " · aucune dominante")
                + (f" · {len(r.basculements)} basculement(s) entre planches consécutives"
                   f" (planches {', '.join(str(p) for p in r.basculements[:8])})"
                   if r.basculements else "")
                + (f" · {len(r.planches_mixtes)} planche(s) mêlant les deux"
                   if r.planches_mixtes else "")
                + " — signalé, jamais corrigé : un changement de registre peut être une scène")
    if stats_relecture:
        manques = stats_relecture.get("glossaire_manque", 0)
        if manques:
            lignes.append(
                f"- Glossaire absent du rendu : {manques} terme(s) présent(s) dans la source "
                f"et absent(s) de la traduction (contrôle lexical, aucun appel LLM)")
        if stats_relecture.get("actif"):
            refus = {k[len("relecture_refus_"):]: v for k, v in stats_relecture.items()
                     if k.startswith("relecture_refus_") and v}
            lignes.append(
                f"- Relecture à mandat étroit : "
                f"{stats_relecture.get('relecture_appels', 0)} appel(s) · "
                f"{stats_relecture.get('relecture_proposees', 0)} proposition(s) · "
                f"{stats_relecture.get('relecture_appliquees', 0)} appliquée(s)"
                + (" · rejets : " + ", ".join(f"{v} × {k}" for k, v in sorted(refus.items()))
                   if refus else ""))
    return lignes


def build_report(build_dir: Path, project: str, volume: str, *, total_pages: int,
                 mcfg: dict, duree_s: float | None = None,
                 stats_llm: dict | None = None,
                 stats_traduction: dict | None = None,
                 stats_glossaire: dict | None = None,
                 force_refus: list[str] | None = None,
                 derives: list | None = None,
                 pluriels: list | None = None,
                 rattrapage_refus: list[str] | None = None,
                 # ⚠ Ce paramètre manquait, et l'orchestrateur accumulait `sfx_refus` depuis
                 # le lot 13 dans une liste que PERSONNE ne lisait : les gloses non plaçables
                 # étaient comptées, formatées, et jetées. Le lot 21 le branche, et y ajoute
                 # ses propres refus de traduction brodée.
                 sfx_refus: list[str] | None = None,
                 stats_sfx: dict | None = None,
                 stats_manuelles: dict | None = None,
                 # Lot 39 — ce que le mode SANS LLM a laissé vide. ⚠ Un tome qui sort sans
                 # texte doit le DIRE : sinon c'est un rendu qu'on prendra pour une sortie.
                 stats_sans_llm: dict | None = None,
                 structures: dict | None = None,
                 registre_par_planche: dict | None = None,
                 stats_relecture: dict | None = None,
                 planches_en_echec: list[dict] | None = None,
                 psd_refuses: list[str] | None = None,
                 pic_memoire: int | None = None,
                 format_planche: str = "manga", langue: str = "jp",
                 sens: str | None = None) -> str:
    """Construit le texte du rapport en relisant les `qa.json` de **toutes** les pages."""
    from . import quality_manga

    cfg = fusion(_DEFAUTS_RAPPORT, mcfg.get("rapport"))
    maxi = int(cfg["max_lignes_section"])
    seuil = float(cfg["seuil_confiance"])
    seuil_bilobee = _seuil_bilobee(mcfg)
    build_dir = Path(build_dir)

    pages_qa = []
    # ⚠ Les planches SANS `qa.json` sont retenues et NOMMÉES. Le rapport se contentait
    # d'annoncer « 149 analysée(s) sur 150 » : la planche manquante n'était citée nulle part,
    # donc ses bulles échappaient à tout contrôle qualité sans que rien ne le signale. Une
    # planche non analysée est une anomalie, pas une soustraction.
    sans_qa: list[int] = []
    # ⚠ La provenance de DÉTECTION est relue depuis `regions.json`, pas depuis `qa.json`.
    # Ce n'est pas un détail d'implémentation : sur le corpus de mesure, **423 planches sur
    # 1 513 n'ont pas de `qa.json`** — les deux premiers volumes de *manga D* n'en ont
    # aucun. Un rejet de post-traitement ou une bulle rognée par sa voisine y serait invisible.
    # `regions.json`, lui, existe dès que la planche a été détectée.
    detections: list[tuple[int, dict]] = []
    for i in range(1, total_pages + 1):
        ckpt = checkpoints.page_checkpoint_dir(build_dir, i)
        meta = checkpoints.load_detection_meta(ckpt)
        if meta:
            detections.append((i, meta))
        qa = load_page_qa(ckpt)
        if qa is not None:
            pages_qa.append(qa)
        else:
            sans_qa.append(i)

    sans_bulle, sans_ocr, trad_vides, debordements = [], [], [], []
    faible_confiance, replis, abandons, ecarts, glyphes = [], [], [], [], []
    scindees, bilobees, dentelees, instables = [], [], [], []
    positionnelles, partielles = [], []
    degenerees, etroites, sous_minimum, marquees, substitues = [], [], [], [], []
    restaurees: list[str] = []
    non_dessinees: list[str] = []
    rattrapees = []
    tailles, modes = [], {"masque": 0, "texte": 0, "aucun": 0}
    polices_psd: set[str] = set()
    n_bulles = n_inverses = 0
    sans_bulle_avec_texte: list[str] = []
    gloses_refusees: list[str] = []
    sfx_lignes: list[str] = []
    motifs_residuels: list[str] = []
    n_sfx = n_sfx_traduits = n_sfx_glosees = 0

    for qa in pages_qa:
        p = qa.get("page")
        polices_psd.update(qa.get("polices_psd") or ())
        # Texte SUR LE DESSIN — relevé AVANT le `continue` des planches sans bulle, parce que
        # c'est précisément là qu'il compte le plus : les pages d'action pleine page n'ont
        # aucun ballon et sont couvertes d'onomatopées.
        zones = qa.get("sfx") or []
        n_sfx += len(zones)
        for z in zones:
            src = (z.get("source") or "").strip()
            trad = (z.get("traduction") or "").strip()
            if trad:
                n_sfx_traduits += 1
                if qa.get("sfx_mode") == "glose" and not z.get("posee"):
                    gloses_refusees.append(
                        f"page {p} zone {z.get('index', 0) + 1} — « {trad[:32]} »")
            if z.get("posee"):
                n_sfx_glosees += 1
            if src or trad:
                x0, y0, _x1, _y1 = z.get("bbox") or (0, 0, 0, 0)
                # Le japonais ET sa lecture : c'est ce qui rend la ligne utilisable pour
                # lettrer à la main dans Photoshop — et ce qui permet de voir d'un coup d'œil
                # qu'une lecture est fantaisiste.
                sfx_lignes.append(f"page {p} zone {z.get('index', 0) + 1} "
                                  f"({x0}, {y0}) — « {_extrait(src, 24)} » → "
                                  f"« {_extrait(trad, 40)} »")
        bulles = qa.get("bulles", [])
        if not bulles:
            # Distinguer la planche BLANCHE (page de garde, séparateur) de la planche pleine
            # d'action : le rapport comptait les deux ensemble, et une pleine page couverte de
            # katakana s'y lisait comme une page vide.
            if zones:
                sans_bulle_avec_texte.append(
                    f"page {p} (`{qa.get('fichier', '?')}`) — {len(zones)} zone(s) hors bulle")
            else:
                sans_bulle.append(f"page {p} (`{qa.get('fichier', '?')}`)")
            continue
        # Comment les répliques ont été rattachées à leurs bulles. Le rendu d'une planche
        # reconstituée positionnellement est indiscernable à l'œil de celui d'une planche
        # numérotée — sauf que ses répliques peuvent être dans les mauvaises bulles.
        # Motif d'échec RÉSIDUEL — celui qui a survécu aux retries. Il était persisté dans le
        # `qa.json` et n'apparaissait dans AUCUNE section : sur manga B, les pages 58 et 59
        # portaient `repetition` sans qu'une seule ligne du rapport ne le dise.
        motif_page = qa.get("motif_traduction")
        if motif_page:
            motifs_residuels.append(
                f"page {p} — {quality_manga.libelle(motif_page, langue)} "
                f"(`{motif_page}`), sortie conservée")
        strategie = qa.get("strategie_traduction") or ""
        if strategie in ("positionnelle", "numerotee_partielle"):
            attendues = sum(1 for b in bulles if b.get("kind") == "bulle")
            rendues = sum(1 for b in bulles if b.get("kind") == "bulle"
                          and (b.get("traduction") or "").strip())
            libelle = f"page {p} — {rendues} réplique(s) rendue(s) pour {attendues} bulle(s)"
            if strategie == "positionnelle":
                positionnelles.append(libelle)
            else:
                partielles.append(libelle)
        for b in bulles:
            if b.get("kind") != "bulle":
                continue
            n_bulles += 1
            mode = b.get("mode_nettoyage")
            if mode in modes:
                modes[mode] += 1
            if b.get("inverse"):
                n_inverses += 1
            if b.get("taille_police"):
                tailles.append(b["taille_police"])
            num = b["index"] + 1
            if b.get("rattrapee"):
                rattrapees.append(f"page {p} bulle {num} — « "
                                  f"{_extrait(b.get('traduction'))} »")
            if not (b.get("ocr") or "").strip():
                sans_ocr.append(f"page {p} bulle {num}")
            elif not (b.get("traduction") or "").strip():
                trad_vides.append(f"page {p} bulle {num}")
            # Un débordement n'a pas UNE cause mais trois, et deux d'entre elles n'ont rien à
            # voir avec le traducteur. Le rapport conseillait « raccourcir la traduction »
            # neuf fois sur ce tome et n'avait raison qu'une seule.
            trad = _extrait(b.get("traduction"))
            cause = b.get("cause") or ""
            if b.get("debordement") and cause == "bulle_degeneree":
                x0, y0, x1, y1 = b.get("bbox") or (0, 0, 0, 0)
                degenerees.append(
                    f"page {p} bulle {num} — {x1 - x0}×{y1 - y0} px, remplissage "
                    f"{b.get('remplissage_masque')} — NON lettrée · « {trad} »")
            elif b.get("debordement") and cause == "bulle_etroite":
                etroites.append(f"page {p} bulle {num} — « {trad} »")
            elif b.get("debordement"):
                debordements.append(f"page {p} bulle {num} — « {trad} »")
            if b.get("repli") == "taille_min_absolue":
                sous_minimum.append(
                    f"page {p} bulle {num} — lettrée à {b.get('taille_police')} px "
                    f"({'bulle étroite' if cause == 'bulle_etroite' else 'réplique longue'}) "
                    f"· « {trad} »")
            rempl = b.get("remplissage_masque")
            if b.get("scindee"):
                scindees.append(f"page {p} bulle {num}"
                                + (f" (remplissage {rempl:.2f})" if rempl else ""))
            elif rempl is not None and rempl < seuil_bilobee:
                trad = _extrait(b.get("traduction"), 50)
                ligne = (f"page {p} bulle {num} — remplissage {rempl:.2f}, "
                         f"police {b.get('taille_police')} px — « {trad} »")
                # Un remplissage bas ne fait pas un double ballon. `forme` vient d'une sonde
                # d'érosion : « dentelee » = aucun goulot, donc une bulle unique au contour en
                # étoile ou à longue queue — sa forme normale, pas un incident. Les 45 régions
                # que le Vol.2 rangeait ici sont TOUTES dans ce cas.
                if b.get("forme") == "dentelee":
                    dentelees.append(ligne)
                elif b.get("forme") == "instable":
                    # Un goulot s'ouvre, mais jamais sur assez d'échelons d'érosion consécutifs
                    # pour être autre chose que du bruit. Le ranger avec les vrais doubles
                    # reproduirait exactement le défaut que le lot 4.2 a corrigé pour les
                    # ballons de cri : noyer les cas actionnables sous les cas normaux.
                    instables.append(ligne)
                else:
                    bilobees.append(ligne)
            if b.get("score", 1.0) < seuil:
                faible_confiance.append(f"page {p} bulle {num} (score {b['score']:.2f})")
            if mode == "aucun":
                abandons.append(f"page {p} bulle {num} "
                                f"(uniformité {b.get('uniformite', 0):.2f})")
            elif b.get("rayon_erosion") == 0:
                replis.append(f"page {p} bulle {num}")
        for e in qa.get("ecarts", []):
            ecarts.append(f"page {p} — {e.get('bulles')} bulle(s) pour "
                          f"{e.get('traductions')} traduction(s) (écart {e.get('ecart')})")
        for g in qa.get("glyphes_manquants", []):
            # Deux sorts distincts, et l'ancien rapport signalait comme « absent » un
            # caractère qu'il venait pourtant de peindre en carré tofu.
            if g.get("substitues"):
                substitues.append(f"page {p} bulle {g.get('index', 0) + 1} — « "
                                  f"{g['substitues']} » remplacé(s) par un équivalent latin")
            if g.get("caracteres"):
                glyphes.append(f"page {p} bulle {g.get('index', 0) + 1} — « "
                               f"{g.get('caracteres')} » SUPPRIMÉ(s) : aucune police de la "
                               f"chaîne ne les couvre et aucun équivalent n'est connu")
        for v in qa.get("bulles_vides", []):
            marquees.append(f"page {p} bulle {v.get('index', 0) + 1} — source non vide, "
                            f"traduction vide : marquée « {v.get('marqueur')} »")
        for n in qa.get("non_dessinees", []):
            # Les deux causes ne donnent pas la même planche : une région dégénérée a été
            # nettoyée, donc la bulle sort BLANCHE ; une bulle non nettoyée a gardé son
            # japonais. Dans les deux cas le français manque, mais on ne les corrige pas au
            # même endroit.
            motif = {"bulle_degeneree": "région jugée dégénérée — bulle BLANCHE",
                     "bulle_non_nettoyee": "nettoyage abandonné — le JAPONAIS est resté"
                     }.get(n.get("cause", ""), n.get("cause", ""))
            non_dessinees.append(f"page {p} bulle {n.get('index', 0) + 1} — {motif} — "
                                 f"« {_extrait(n.get('texte'))} »")
        for r in qa.get("restaurees", []):
            restaurees.append(f"page {p} bulle {r.get('index', 0) + 1} — ni texte source ni "
                              f"réplique : dessin d'origine recollé")

    mediane = sorted(tailles)[len(tailles) // 2] if tailles else 0
    resume = ["## Résumé du run"] + report.entete_run(duree_s) + [
        f"- Pages : {len(pages_qa)} analysée(s) sur {total_pages}"
        + (" · ⚠ SANS contrôle qualité : "
           + ", ".join(str(n) for n in sans_qa[:12])
           + (f" (+{len(sans_qa) - 12})" if len(sans_qa) > 12 else "")
           if sans_qa else "")
        + (f" · {len(sans_bulle)} sans bulle" if sans_bulle else "")
        + (f" · {len(sans_bulle_avec_texte)} sans bulle MAIS avec du texte hors bulle"
           if sans_bulle_avec_texte else ""),
        f"- Bulles : {n_bulles} · taille de police médiane : {mediane} px"
        + (f" (de {min(tailles)} à {max(tailles)})" if tailles else ""),
        f"- Nettoyage : {modes['masque']} en mode masque · {modes['texte']} en mode texte · "
        f"{modes['aucun']} abandonnée(s) · {n_inverses} bulle(s) inversée(s)",
    ]
    # ⚠ **Le seul chiffre du rapport qui décrit la MACHINE et non le tome**, et c'est
    # exactement pourquoi il y a sa place (lot 14, L6.0). Un contributeur qui ouvre une issue
    # « ça se fait tuer sur les webtoons » n'avait rien à y joindre ; `perf.log` porte le
    # détail par passe, cette ligne-ci porte le maximum du run, qui est ce qu'on compare à la
    # RAM installée. `?` quand le système ne sait pas répondre — jamais un zéro inventé.
    if pic_memoire is not None:
        from core import memoire
        resume.append(f"- Mémoire : pic de {memoire.format_octets(pic_memoire)} "
                      f"(maximum du processus sur tout le run)")
    # COMMENT le tome a été traduit — taille de lot et raisonnement, relus depuis les
    # `qa.json` donc à l'échelle du tome. Deux runs d'un même tome, l'un par lots de 20 avec
    # raisonnement et l'autre planche par planche sans, produisaient jusqu'ici des rapports
    # indiscernables : la comparaison qu'on veut faire était impossible.
    ligne_lot = _ligne_traduction(pages_qa)
    if ligne_lot:
        resume.append(ligne_lot)
    origines = _compter_origines(pages_qa)
    if origines:
        resume.append(
            "- Provenance des répliques : "
            + " · ".join(f"{v} {LIBELLES_ORIGINE.get(k, k)}"
                         for k, v in sorted(origines.items(), key=lambda kv: -kv[1])))
    mobilier = (stats_sfx or {}).get("mobilier", 0)
    groupes_mobilier = (stats_sfx or {}).get("groupes_mobilier") or []
    if mobilier:
        # Le dire au résumé ET lister les groupes : un filtre qui écarte un cinquième des
        # zones (92 sur 448, mesure du lot 21) doit pouvoir être vérifié d'un coup d'œil,
        # sinon c'est un trou noir.
        resume.append(
            f"- Mobilier de page : {mobilier} zone(s) écartée(s) en {len(groupes_mobilier)} "
            f"groupe(s) récurrent(s) (filigranes de scan) — ni lues, ni traduites")
    masques_ecartes = (stats_sfx or {}).get("masques_ecartes", 0)
    if masques_ecartes:
        # Un `if` qui avale une incohérence est une dette qui se paie une fois par tome, au
        # pire moment : l'union des bulles sort vide, et TOUTES les répliques déjà prises en
        # charge sont re-détectées comme texte hors bulle, relues et retraduites en glose.
        resume.append(
            f"- ⚠ Appariement texte↔bulle : {masques_ecartes} masque(s) de bulle de forme "
            f"inattendue écarté(s) — cache probablement écrit avant un changement de "
            f"découpage. Relancer `--from detection` sur ce tome.")
    if (stats_sans_llm or {}).get("actif"):
        # ⚠ **En TÊTE de la section, et en toutes lettres.** C'est la ligne qui distingue un
        # tome délibérément non traduit d'un tome dont la traduction a échoué — et les deux
        # produisent exactement les mêmes planches à l'œil.
        resume.append(
            f"- ⚠ **MODE SANS LLM** : aucun appel au serveur. "
            f"{stats_sans_llm.get('bulles', 0)} bulle(s) sur "
            f"{stats_sans_llm.get('pages', 0)} planche(s) sont sorties **VIDES** et attendent "
            f"une saisie. Ouvre la Retouche : ce que tu tapes va dans "
            f"`traduction_manuelle.json`, que le pipeline ne réécrit jamais.")
    if (stats_manuelles or {}).get("bulles"):
        resume.append(
            f"- Reprises À LA MAIN : {stats_manuelles['bulles']} réplique(s) sur "
            f"{stats_manuelles['pages']} planche(s) — lues depuis "
            f"`traduction_manuelle.json`, jamais réécrites par le pipeline")
    # Triage du texte hors bulle. Recompté depuis TOUS les `qa.json`, et non plus repris des
    # statistiques du run : celles-ci ne décrivent que les planches RETRAITÉES, si bien qu'une
    # reprise à trois planches annonçait « 3 traduite(s) » pour un tome qui en compte 338. Le
    # rapport décrit l'état du TOME, pas celui du run — c'est le principe même de `qa.json`.
    tri = _compter_tri(pages_qa) or ((stats_sfx or {}).get("tri") or {})
    if tri:
        # Le triage est ce qui retire 42 % des zones de la charge LLM (Vol.1) sans rien perdre
        # de traduisible. Le publier permet de vérifier qu'il ne dérape pas.
        resume.append(
            f"- Triage du texte hors bulle : {tri.get('japonais', 0)} traduite(s) par le LLM · "
            f"{tri.get('ponctuation', 0)} rendue(s) sans appel (ponctuation seule) · "
            f"{tri.get('bruit', 0)} écartée(s) (lecture hallucinée sur du dessin) · "
            f"{tri.get('mobilier', 0)} mobilier de page")
    if n_sfx:
        # Le texte posé sur le dessin n'est pas EFFACÉ — le principe « l'IA ne dessine
        # jamais » l'interdit —, il est glosé à côté. Le dire ici évite qu'on lise le
        # japonais resté visible comme un échec de traduction : il est intact par
        # construction, et sa traduction est à côté.
        resume.append(
            f"- Texte hors bulle : {n_sfx} zone(s) détectée(s) · {n_sfx_traduits} traduite(s)"
            + (f" · {n_sfx_glosees} glosée(s) sur la planche" if n_sfx_glosees
               else " · aucune dessinée sur la planche (mode `rapport`)")
            + " — le texte d'origine est CONSERVÉ (jamais effacé). ⚠ Lectures à relire :"
              " l'OCR de dialogue invente sur une onomatopée stylisée.")
    # --- Lot 21 : ce que la LECTURE vaut, et ce que les filtres ont écarté ------------
    #
    # Trois lignes, et chacune répond à une question que le rapport ne savait pas poser.
    rejets = (stats_sfx or {}).get("rejets") or {}
    if rejets:
        # ⚠ Un filtre MUET est la façon dont on perd les zones suivantes sans le voir. Les
        # deux bornes hautes du lot 21 sont désarmées par défaut ; si quelqu'un les arme,
        # il doit voir immédiatement ce qu'elles coûtent.
        resume.append(
            "- Zones écartées à la détection : "
            + " · ".join(f"{v} {LIBELLES_REJET_SFX.get(k, k)}"
                         for k, v in sorted(rejets.items(), key=lambda kv: -kv[1]) if v))
    sures = (stats_sfx or {}).get("lecture_sure", 0)
    douteuses = (stats_sfx or {}).get("lecture_douteuse", 0)
    if sures or douteuses:
        total_lectures = sures + douteuses
        # ⚠ Ce compte est celui du RUN, pas celui du tome — contrairement au triage, qui est
        # recompté depuis tous les `qa.json`. Le verdict de concordance n'est pas persisté
        # (il dépend d'un appel LLM qu'on ne rejoue pas), donc une reprise à trois planches
        # n'annonce que ces trois-là. Le dire plutôt que de laisser lire un total de tome :
        # c'est exactement la méprise que `_compter_tri` a dû corriger une fois déjà.
        resume.append(
            f"- Fiabilité de la lecture (sur les planches de CE run) : "
            f"{sures}/{total_lectures} zone(s) "
            f"`lecture_sure` ({100 * sures / max(1, total_lectures):.0f} %) — deux voies de "
            f"lecture indépendantes qui s'accordent"
            + ("" if (stats_sfx or {}).get("concordance") else
               " · ⚠ seconde voie DÉSARMÉE (`manga.onomatopees.concordance`) : une seule "
               "voie ne concorde avec rien, toutes les zones sont donc douteuses par "
               "défaut, ce qui est l'état réel du dépôt et non une sévérité"))
    if (stats_sfx or {}).get("broderie"):
        resume.append(
            f"- Traductions d'onomatopée REFUSÉES : {stats_sfx['broderie']} — une phrase "
            f"inventée là où une onomatopée était attendue. La zone reste sans glose : une "
            f"absence signalée vaut mieux qu'une mauvaise réplique posée.")
    # --- Lot 22 : l'effacement du texte hors bulle -------------------------------------
    #
    # Deux lignes, et la seconde est celle qui compte : elle dit ce qui n'a PAS été effacé et
    # pourquoi. Un effacement muet serait le pire des deux mondes — on ne saurait ni ce qui a
    # été repeint, ni ce qui a été épargné.
    eff_mode = (stats_sfx or {}).get("effacement_mode", "aucun")
    eff_motifs = (stats_sfx or {}).get("effacement") or {}
    if eff_mode != "aucun" and eff_motifs:
        effacees = (stats_sfx or {}).get("effacees", 0)
        relettrees = (stats_sfx or {}).get("relettrees", 0)
        resume.append(
            f"- Effacement du texte hors bulle (mode « {eff_mode} ») : {effacees} zone(s) "
            f"reconstruite(s)"
            + (f" · {relettrees} relettrée(s)" if relettrees else "")
            + (" — calque `Effacement SFX` dans le PSD, **la planche aplatie n'est pas "
               "touchée** : masquer le calque rétablit le japonais"
               if eff_mode == "calque" else
               " — composé sur la planche finale ; le PSD porte le calque `Effacement SFX`, "
               "masquable pour revenir en arrière")
            + ". Aucun modèle génératif : remplissage de la couleur de fond mesurée ou "
              "diffusion en numpy pur.")
        resume.append(
            "- Effacement — décisions par motif : "
            + " · ".join(f"{n} {effacement.LIBELLES.get(motif, motif)}"
                         for motif, n in sorted(eff_motifs.items(), key=lambda kv: -kv[1])))
        if eff_motifs.get(effacement.MOTIF_LECTURE_DOUTEUSE):
            resume.append(
                f"  - ⚠ {eff_motifs[effacement.MOTIF_LECTURE_DOUTEUSE]} zone(s) épargnée(s) "
                f"faute de lecture concordante, et c'est la garantie qui rend ce mode "
                f"défendable : effacer sur une lecture douteuse produit une erreur DESSINÉE "
                f"à la place d'une erreur SIGNALÉE. Aucune clé ne désarme cette règle ; ce "
                f"qui la lève est `manga.onomatopees.concordance`, qui exige un modèle "
                f"`manga_onomatopees` capable de vision.")
    if (stats_sfx or {}).get("crops"):
        resume.append(
            f"- Zones à transcrire à la main : {stats_sfx['crops']} crop(s) exporté(s) dans "
            f"`{DOSSIER_CROPS_SFX}/`. Le rapport listait les onomatopées sans fournir "
            f"l'image ; une planche-contact se traite en dix secondes par zone, une liste de "
            f"boîtes ne se traite pas.")
    if polices_psd:
        # Photoshop substitue en silence une police absente du système : le calque reste
        # éditable, mais le lettrage change et rien à l'écran n'en donne la raison.
        resume.append(
            "- PSD — police(s) à installer côté système pour retrouver le lettrage exact : "
            + ", ".join(f"`{p}`" for p in sorted(polices_psd))
            + " · `powershell -File tools/installer_polices.ps1` (aucun droit "
              "administrateur, réversible)")
    if stats_traduction:
        motifs = {k: v for k, v in stats_traduction.items()
                  if k in quality_manga.LIBELLES and v}
        retries = (stats_traduction.get("retry_temp_reduite", 0)
                   + stats_traduction.get("retry_temp_relevee", 0))
        ligne = (f"- Traduction : {stats_traduction.get('pages_ok', 0)} page(s) ok"
                 + (f" (dont {stats_traduction['recupere_par_retry']} récupérée(s) après "
                    f"retry à température corrigée)"
                    if stats_traduction.get("recupere_par_retry") else ""))
        if motifs:
            ligne += " · échecs : " + ", ".join(
                f"{v} × {quality_manga.libelle(k, langue)}" for k, v in sorted(motifs.items()))
        if retries:
            ligne += f" · {retries} retry(s) tenté(s)"
        resume.append(ligne)
        # Traduction par LOTS : ce qui a été groupé, et ce que le groupage a coûté. Un lot
        # abandonné ou une planche repliée n'est pas un échec — c'est le filet qui a joué —
        # mais leur nombre dit si la taille de lot choisie est tenable pour ce tome.
        if stats_traduction.get("lots") or stats_traduction.get("lots_abandonnes"):
            resume.append(
                f"- Traduction par lots : {stats_traduction.get('lots', 0)} lot(s) exploité(s)"
                + (f" · {stats_traduction['lots_abandonnes']} lot(s) abandonné(s) "
                   f"(reconstruction non numérotée)"
                   if stats_traduction.get("lots_abandonnes") else "")
                + (f" · {stats_traduction['planches_repliees']} planche(s) reprise(s) seule(s)"
                   if stats_traduction.get("planches_repliees") else "")
                # Un lot coupé en deux n'est pas un échec : c'est le garde-fou de prefill qui
                # a joué AVANT qu'Ollama ne tronque le prompt en silence. Son nombre dit que
                # `manga.lot.planches` est trop haut pour ce num_ctx.
                + (f" · {stats_traduction['lots_coupes']} lot(s) coupé(s) en deux "
                   f"(prefill au-dessus du num_ctx déclaré)"
                   if stats_traduction.get("lots_coupes") else ""))
        # Vision CIBLÉE (lot 15, L7.6) : combien de planches ont mérité une seconde tentative
        # avec image, et combien y ont été récupérées. C'est le seul chiffre qui dise si le
        # mode « cible » achète quelque chose — sans lui, la vision reste un pari.
        if stats_traduction.get("vision_ciblee"):
            resume.append(
                f"- Vision ciblée : {stats_traduction['vision_ciblee']} planche(s) reprise(s) "
                f"avec les crops de leurs groupes · "
                f"{stats_traduction.get('vision_ciblee_recuperee', 0)} récupérée(s)")
        appels_r = stats_traduction.get("rattrapage_appels", 0)
        if appels_r or rattrapees or rattrapage_refus:
            resume.append(
                f"- Rattrapage unitaire : {len(rattrapees)} bulle(s) récupérée(s) · "
                f"{stats_traduction.get('rattrapage_refuse', 0)} réponse(s) refusée(s) · "
                f"{appels_r} appel(s) court(s)"
                + (f" · {stats_traduction['rattrapage_abandonne']} planche(s) trop trouée(s) "
                   f"pour être reprises bulle par bulle"
                   if stats_traduction.get("rattrapage_abandonne") else ""))
    if positionnelles or partielles:
        resume.append(
            f"- Rattachement des répliques : {len(partielles)} planche(s) en numérotation "
            f"incomplète (bulles laissées vides) · {len(positionnelles)} en repli positionnel "
            f"(alignement NON garanti)")
    resume += _lignes_structure(structures, registre_par_planche, stats_relecture)
    if stats_glossaire:
        n_forcees = stats_glossaire.get("entrees_forcees", 0)
        # Distinguer « rien à forcer » de « rien n'a eu besoin de l'être » : le second est un
        # succès (tout était déjà canonique), le premier veut dire que le glossaire n'impose
        # rien du tout — et donc que la cohérence des noms n'est pas garantie.
        if not n_forcees:
            resume.append("- Glossaire : aucune entrée `force: true` — les orthographes de "
                          "noms propres ne sont pas garanties (cf. §12 du README)")
        else:
            # « 0 remplacement » se lit comme une panne alors que c'est le plus souvent un
            # succès : rien à corriger. Le dire, sinon le rapport accuse le mécanisme.
            n_rempl = stats_glossaire.get('remplacements', 0)
            resume.append(
                f"- Glossaire : {n_forcees} entrée(s) `force: true` · "
                f"{n_rempl} remplacement(s) appliqué(s) aux bulles"
                + ("" if n_rempl else
                   " — aucune forme bannie n'était présente dans le texte ; les `interdits` "
                   "listent les fautes des runs PRÉCÉDENTS, pas celles de celui-ci")
                + (f" · {len(force_refus)} refusé(s) par les garde-fous d'accord"
                   if force_refus else ""))
        # Trois états, et deux d'entre eux affichaient les mêmes zéros : « désactivée » n'est
        # pas « active et sans travail ». C'est ce qui a fait croire, sur le run v0.21.0, que
        # la passe s'était cassée alors qu'elle n'avait jamais été branchée.
        if not stats_glossaire.get("terminologue_actif", True):
            resume.append(
                "- Terminologie : passe **DÉSACTIVÉE** — aucun nom propre n'a été relevé "
                "depuis le japonais. Pour l'activer : décommenter `manga.modeles.terminologue` "
                "dans `config.yaml`, puis relancer avec `--from traduction` (un appel LLM par "
                "planche).")
        elif stats_glossaire.get("pages_relevees") or stats_glossaire.get("pages_reprises"):
            resume.append(
                f"- Terminologie : {stats_glossaire.get('pages_relevees', 0)} planche(s) "
                f"relevée(s)"
                + (f" ({stats_glossaire['pages_reprises']} reprise(s) du cache)"
                   if stats_glossaire.get("pages_reprises") else "")
                + f" · +{stats_glossaire.get('ajouts', 0)} entrée(s), "
                f"{stats_glossaire.get('fusions', 0)} fusion(s)"
                + (f", {stats_glossaire['conflits']} conflit(s)"
                   if stats_glossaire.get("conflits") else ""))
        else:
            resume.append("- Terminologie : passe active, mais aucune planche à relever "
                          "(tout est en cache) — `--from terminologie` pour un nouveau relevé.")
        if derives or stats_glossaire.get("derives_bannies"):
            n_t = {n: sum(1 for d in (derives or []) if d.niveau == n)
                   for n in ("T1", "T2", "T3")}
            resume.append(
                f"- Dérives d'orthographe : {n_t['T1']} ancrée(s) sur le japonais · "
                f"{n_t['T2']} par dominance · {n_t['T3']} lexicale(s) non tranchée(s) · "
                f"{stats_glossaire.get('derives_bannies', 0)} forme(s) écrite(s) en "
                f"`interdits` (aucun appel LLM)")
    resume += report.lignes_llm(stats_llm)

    sections: list[str] = []
    # EN TÊTE de toutes les sections, et c'est délibéré : une planche qui a levé n'a produit
    # ni bulle, ni traduction, ni `qa.json`. Elle est donc absente de tout ce qui suit — et
    # sans cette section, un tome amputé de trois planches se lit comme un tome réussi. Un
    # échec non compté est un échec invisible.
    sections += _section(
        "Planches en ÉCHEC (exception pendant le run — le tome a continué sans elles)",
        [f"page {e.get('page')} · étape « {e.get('phase')} » — {e.get('type')} : "
         f"{e.get('message')} · reprendre avec `--page {e.get('page')}`"
         for e in (planches_en_echec or [])], maxi)
    # Juste après les échecs, et pour la même raison : c'est une sortie MANQUANTE. Une planche
    # refusée par le format PSD garde ses pages rendues, son CBZ et son PDF — mais
    # `pages_psd/` en compte une de moins, et sans cette ligne rien ne dit laquelle ni
    # pourquoi.
    sections += _section("PSD REFUSÉ (planche au-delà des limites du format)",
                         list(psd_refuses or []), maxi)
    if derives:
        lignes = []
        for d in sorted(derives, key=lambda x: (x.niveau, x.nom.lower(), x.candidat.lower())):
            if d.niveau == "T1":
                preuve = (f"ancrée sur `{d.source}` dans l'OCR de la MÊME bulle "
                          f"(page {d.page}, bulle {d.bulle}) — corrigée dès ce run")
            elif d.niveau == "T2":
                preuve = (f"dominance sur le tome : {d.nom} ×{d.occurrences_nom} contre "
                          f"{d.candidat} ×{d.occurrences_candidat} — `--from rendu` pour "
                          f"l'appliquer")
            else:
                preuve = ("proximité lexicale seule — **non bannie**, à trancher à la main "
                          "(ajouter à `interdits` si c'en est une)")
            # Ne vaut que pour ce qui est RÉELLEMENT écrit : une T3 n'ajoute aucun interdit,
            # dire qu'il serait inerte n'aurait aucun sens.
            inerte = ("" if d.forcee or not d.ecrit_interdit else
                      " ⚠ l'entrée n'a pas `force: true` : l'interdit restera sans effet")
            lignes.append(f"[{d.niveau}] « {d.candidat} » → « {d.nom} » — {preuve}{inerte}")
        sections += _section("Dérives d'orthographe détectées (T1 et T2 écrites en "
                             "`interdits`, T3 non)", lignes, maxi)
    if pluriels:
        sections += _section(
            "Pluriels observés sans champ `pluriel:` au glossaire",
            [f"« {pl} » ×{n} — ajouter `pluriel: {pl}` à l'entrée « {nom} » ; ce n'est PAS "
             f"une dérive, la bannir remplacerait le pluriel par le singulier"
             for nom, pl, n in pluriels], maxi)
    if force_refus:
        # Dédoublonné : le même couple revient à chaque occurrence dans le tome.
        sections += _section(
            "Formes canoniques NON forcées (accord/élision impossible à garantir)",
            list(dict.fromkeys(force_refus)), maxi)
    sections += _section("Pages sans aucune bulle détectée", sans_bulle, maxi)
    # LA section qui manquait. Une planche à zéro bulle était rangée avec les pages de garde,
    # alors qu'une pleine page d'action couverte de katakana est tout l'inverse d'une page
    # vide : c'est là que le japonais reste le plus visible.
    sections += _section("Pages sans bulle MAIS porteuses de texte (pleines pages d'action)",
                         sans_bulle_avec_texte, maxi)
    sections += _section("Gloses NON posées faute de zone libre "
                         "(le japonais reste, sa traduction n'a pas pu être placée)",
                         gloses_refusees, maxi)
    # ⚠ À RELIRE, et le titre le dit. `manga-ocr` est un modèle de DIALOGUE : sur une
    # onomatopée stylisée il rend toujours une phrase plausible, donc il invente. Ces lignes
    # servent à lettrer à la main — pas à être crues sur parole.
    sections += _section(
        "Groupes ÉCARTÉS comme mobilier de page (même position sur de nombreuses planches)",
        [f"boîte ({g['boite'][0]}, {g['boite'][1]})–({g['boite'][2]}, {g['boite'][3]}) — "
         f"{g['planches']} planche(s), {g['zones']} zone(s)" for g in groupes_mobilier], maxi)
    sections += _section("Texte hors bulle — lecture À RELIRE "
                         "(l'OCR de dialogue invente sur une onomatopée stylisée)",
                         sfx_lignes, maxi)
    # En tête des incidents de traduction : c'est le seul cas où une réplique peut être
    # dessinée dans la MAUVAISE bulle, et rien dans l'image ne le laisse voir.
    sections += _section("Planches rattachées SANS numérotation (répliques dans l'ordre des "
                         "lignes — alignement non garanti)", positionnelles, maxi)
    sections += _section(
        "Planches dont le motif d'échec a SURVÉCU aux relances (sortie conservée, à relire)",
        motifs_residuels, maxi)
    sections += _section("Planches à numérotation incomplète (bulles laissées vides plutôt "
                         "que décalées)", partielles, maxi)
    sections += _section("Écarts de comptage bulles / traductions", ecarts, maxi)
    # ⚠ En TÊTE des incidents, avant les débordements : c'est le seul où du texte a
    # DISPARU. Un débordement laisse des lettres rognées, qui se voient sur la planche ;
    # une bulle blanche ne se voit pas, elle se lit comme un silence voulu.
    sections += _section("RÉPLIQUES NON DESSINÉES — la traduction n'est nulle part sur la "
                         "planche (perte de texte)", non_dessinees, maxi)
    sections += _section("Régions DÉGÉNÉRÉES, non lettrées (corriger la DÉTECTION, pas la "
                         "traduction — la région ne peut pas porter un seul mot)",
                         degenerees, maxi)
    sections += _section("Bulles trop ÉTROITES en débordement (la largeur manque, pas la "
                         "concision)", etroites, maxi)
    sections += _section("Bulles en débordement (là, raccourcir la traduction est le bon "
                         "correctif)", debordements, maxi)
    sections += _section("Bulles lettrées SOUS la taille minimale (plutôt que de déborder)",
                         sous_minimum, maxi)
    sections += _section("Bulles RATTRAPÉES bulle à bulle (traduites hors du contexte de leur "
                         "planche — à relire)", rattrapees, maxi)
    sections += _section("Rattrapages REFUSÉS (la bulle reste vide, ce qui est moins grave "
                         "qu'une mauvaise réplique dessinée)", list(rattrapage_refus or []),
                         maxi)
    sections += _section("Texte hors bulle — glose NON POSÉE ou traduction REFUSÉE (le "
                         "japonais reste visible et intact, donc corrigible à la main)",
                         list(sfx_refus or []), maxi)
    sections += _section("Traductions vides", trad_vides, maxi)
    sections += _section("Bulles vides MARQUÉES (source non traduite)", marquees, maxi)
    sections += _section(
        "Zones RESTAURÉES — fausse détection probable, dessin d'origine recollé", restaurees,
        maxi)
    sections += _section("Bulles sans texte OCR", sans_ocr, maxi)
    sections += _section("Bulles issues d'une région bi-lobée scindée", scindees, maxi)
    sections += _section(f"Régions bi-lobées SUSPECTES, non scindées "
                         f"(goulot trouvé, découpage refusé — remplissage "
                         f"< {seuil_bilobee:.2f})", bilobees, maxi)
    # Section SÉPARÉE, et volontairement descriptive plutôt qu'alarmante : ces bulles ne
    # demandent aucune action. Les lister quand même sert au lettrage — un ballon de cri
    # laisse peu de place utile — mais les ranger avec les vrais doubles noyait ces derniers.
    sections += _section("Bulles au contour DENTELÉ ou à longue queue "
                         "(remplissage bas par nature, aucune action requise)",
                         dentelees, maxi)
    # Section séparée elle aussi, et pour la même raison : « instable » ne veut PAS dire
    # « double manqué ». Un découpage qui n'existe qu'à un seul échelon d'érosion est la
    # signature d'un artefact ; le lister à part permet de vérifier que le critère de
    # stabilité écarte bien ce qu'il prétend écarter, sans polluer la liste de travail.
    sections += _section("Régions à goulot INSTABLE (un découpage s'ouvre puis disparaît "
                         "d'un échelon d'érosion à l'autre — artefact, pas un double)",
                         instables, maxi)
    sections += _section(f"Détections à faible confiance (< {seuil:.2f})",
                         faible_confiance, maxi)
    sections += _sections_detection(detections, maxi)
    sections += _section("Bulles NON nettoyées (probable fausse détection sur du dessin)",
                         abandons, maxi)
    sections += _section("Bulles nettoyées en mode repli (érosion abandonnée)", replis, maxi)
    sections += _section("Glyphes SUBSTITUÉS par un équivalent latin", substitues, maxi)
    sections += _section("Glyphes absents de la police, SUPPRIMÉS", glyphes, maxi)

    # Format, langue et sens en TÊTE du rapport. Le run raté du Chap.11 n'en disait rien : on
    # pouvait lire les neuf pages du rapport sans jamais apprendre que la chaîne avait traité
    # un webtoon anglais comme du manga japonais.
    from core import glossary_lang
    entete = (f"# Rapport {format_planche} — {project} / {volume}\n\n"
              f"Pages : {total_pages} · bulles : {n_bulles} · "
              f"langue source : {glossary_lang.nom_langue(langue)} · "
              f"sens de lecture : "
              f"{sens or (mcfg.get('rendu') or {}).get('sens_lecture', 'droite_gauche')}\n\n")
    corps = "\n".join(resume) + "\n\n" + "\n".join(sections)
    pied = ("\nPages nettoyées : `pages_clean/` · pages finales : `pages_out/` · "
            "contrôle qualité par page : `.checkpoints/page_XXXX/qa.json`\n")
    return entete + corps + pied


def write_report(build_dir: Path, project: str, volume: str, **kwargs) -> Path:
    """Écrit `RAPPORT.md` sous `build/<Projet>/<Tome>/manga/` et renvoie son chemin."""
    chemin = Path(build_dir) / "RAPPORT.md"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(build_report(build_dir, project, volume, **kwargs), encoding="utf-8")
    return chemin
