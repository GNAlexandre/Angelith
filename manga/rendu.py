# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le lettrage d'UNE planche — le chemin unique, partagé par l'orchestrateur et l'éditeur.

## Pourquoi ce module existe

L'éditeur graphique doit pouvoir redessiner une planche après un déplacement de texte sans
relancer `process_volume` : un aller-retour complet pour bouger un bloc de dix pixels serait
inutilisable. Mais écrire un **second** chemin de rendu serait pire encore — deux moteurs
libres de diverger sur la seule chose que l'utilisateur regarde vraiment, les pixels.

D'où l'extraction. Il n'y a toujours qu'un seul chemin ; il a simplement deux appelants. La
promesse « ce qui sort de l'interface est ce que produirait `run_manga.py` » cesse d'être une
intention et devient une propriété du code, verrouillée par
`tests/test_manga_rendu.py::test_les_deux_chemins_donnent_la_meme_image`.

## Ce que la fonction fait, et dans quel ordre

Exactement ce que faisait le bloc de rendu de l'orchestrateur, sans rien réordonner :

0. l'**effacement** du texte hors bulle, quand il est demandé (lot 22) — voir ci-dessous ;
1. `typeset_page` sur la planche NETTOYÉE, avec les mises en page enregistrées ;
2. les gloses d'onomatopées, en passe séparée **posée sur la planche déjà lettrée** — séparée
   parce que rien de tout cela ne doit pouvoir déranger le chemin des bulles.

## L'effacement est un ÉTAGE, pas une modification du nettoyage (lot 22, L22.6 voie 1)

`manga.effacement.effacer_zones` **ne mute jamais** la planche : il rend un calque. C'est ce
qui permet trois choses à la fois, et aucune n'est un détail.

· `sfx` reste dans `checkpoints.CACHE_NON_BLOQUANT` — l'effacement ne change pas `nettoyage`,
  donc **aucun rendu existant n'est périmé** et la relance de 17 projets n'a pas lieu. Les deux
  autres voies que le plan de lot envisageait (faire entrer `sfx` dans le graphe, ou sortir le
  mode dans un outil séparé) coûtaient l'une des heures de GPU, l'autre l'intégration.
· le mode `"calque"` produit le calque PSD **sans toucher `pages_out/`** : un utilisateur qui
  l'active obtient exactement les mêmes planches aplaties qu'avant, plus un calque masquable.
· le mode `"aplati"` compose, et c'est le seul qui change un pixel de sortie.

Elle ne décide de rien : ni du forçage du glossaire, ni des corrections manuelles, ni de la
dérive terminologique. Ces trois-là s'appliquent au TEXTE, en amont, et restent chez l'appelant
— l'orchestrateur les fait pour un tome, l'éditeur les a déjà sur disque.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from . import effacement as effacement_mod
from . import gloss as gloss_mod
from . import typeset


@dataclass
class ResultatRendu:
    """Ce que le rendu a produit, au-delà de l'image.

    `qa` et `fits` étaient déjà collectés par l'orchestrateur (`report_out`, `fits_out`) ; les
    nommer ici évite que l'éditeur ait à les redécouvrir."""

    image: Image.Image
    qa: list[dict] = field(default_factory=list)
    fits: list[dict] = field(default_factory=list)
    gloses: list = field(default_factory=list)
    refus_gloses: list[str] = field(default_factory=list)
    #: Index des régions dont les pixels d'origine ont été recollés faute de tout texte
    #: (cf. `restaurer_sans_texte`). Ce sont des fausses détections probables.
    restaurees: list[int] = field(default_factory=list)
    #: Le calque d'effacement du texte hors bulle (`manga.effacement.Effacement`), ou `None`.
    #: Il porte AUSSI le journal des décisions, y compris celles de ne rien peindre : c'est
    #: par lui que `RAPPORT.md` sait dire pourquoi une zone n'a pas été effacée.
    effacement: object | None = None
    #: Les recettes de lettrage des zones hors bulle, même forme que `fits`. Vide sauf en
    #: mode `relettrage`.
    fits_sfx: list[dict] = field(default_factory=list)


def restaurer_sans_texte(cleaned: Image.Image, originale: Image.Image, regions: list,
                         textes: list[str], sources: list[str] | None,
                         styles: list | None) -> list[int]:
    """Recolle les pixels d'origine des régions qui n'ont NI source NI réplique. **Mute
    `cleaned`.** Renvoie les index restaurés.

    ## Le défaut que cela corrige

    Une fausse détection sur du dessin est nettoyée comme une vraie bulle : `clean.py` choisit
    le mode d'après l'UNIFORMITÉ de la zone, et plus une zone est plate, plus il est confiant
    qu'il peut la repeindre — alors qu'une zone plate est justement une zone sans texte. Mesuré
    sur *webtoon A* Chap.11 planche 4 : le visage d'un personnage repeint à 45,6 % en
    `[252, 215, 175]`, la couleur de peau échantillonnée dans ses propres pixels.

    ## Pourquoi ici, et pas au nettoyage

    Aucune statistique de pixels ne distingue une fausse bulle d'une vraie — c'est **mesuré**,
    pas supposé : sur ce corpus les faux positifs ont plus d'encre (0,16–0,28) que de vraies
    bulles (0,03), parce qu'un dessin est plein de contrastes, et une bulle légitimement rose
    est plus saturée (0,355) que le visage (0,306). Le seul séparateur fiable est le TEXTE, et
    il n'existe pas encore à l'étape de nettoyage : `nettoyage` et `ocr` sont des frères
    indépendants dans le graphe de cache.

    Au rendu, en revanche, tout est connu. Et comme le rendu est la dernière étape, un
    `--from rendu` suffit à réparer une planche **sans un seul appel LLM**.

    ## Pourquoi la double condition

    `sources` vide seule ne suffit pas : une bulle dont l'OCR a échoué mais qu'on a corrigée à
    la main a une réplique. Restaurer celle-là redessinerait le texte d'origine SOUS la
    traduction française."""
    if originale is None:
        return []
    import numpy as np

    restaurees = [
        k for k, region in enumerate(regions)
        if not ((sources[k] if sources and k < len(sources) else "") or "").strip()
        and not ((textes[k] if k < len(textes) else "") or "").strip()
        and getattr(styles[k] if styles and k < len(styles) else None, "ok", False)
        and getattr(styles[k], "mode", "aucun") != "aucun"
    ]
    if not restaurees:
        return []
    # Le masque de la région, pas seulement l'intérieur érodé : on recolle des pixels
    # d'ORIGINE, donc en remettre un peu plus que ce qui avait été repeint ne peut rien abîmer.
    # Les masques étant disjoints, cela ne déborde jamais sur une voisine.
    arr = np.asarray(cleaned.convert("RGB")).copy()
    src = np.asarray(originale.convert("RGB"))
    for k in restaurees:
        arr[regions[k].mask] = src[regions[k].mask]
    cleaned.paste(Image.fromarray(arr))
    return restaurees


def rendre_planche(cleaned: Image.Image, regions: list, textes: list[str], *,
                   styles: list | None = None, font_path: str | None = None,
                   cfg_typeset: dict | None = None, sources: list[str] | None = None,
                   layouts: dict | None = None, avec_fits: bool = False,
                   zones_sfx: list | None = None, traductions_sfx: list[str] | None = None,
                   mode_sfx: str = "", originale: Image.Image | None = None,
                   styles_sfx: list | None = None, verdicts_sfx: list[str] | None = None,
                   cfg_effacement: dict | None = None) -> ResultatRendu:
    """Lettre une planche sur son fond nettoyé. **Mute `cleaned`** — comme `typeset_page`.

    ⚠ La mutation est conservée telle quelle, et documentée plutôt que corrigée : l'export PSD
    a besoin de la planche nettoyée INTACTE en plus de la planche finale, et c'est l'appelant
    qui en garde une copie (`fond_propre`). Changer ce contrat ici ferait diverger les deux
    chemins sur un détail invisible en test et très visible en PSD.

    `avec_fits` alloue la recette de lettrage par bulle (position, taille, police, calque) :
    l'export PSD en a besoin, l'éditeur aussi pour son aperçu. C'était jusqu'ici conditionné à
    l'activation du PSD, si bien que l'information n'existait pas quand elle n'était pas
    exportée."""
    qa: list[dict] = []
    # La liste existe toujours ; c'est `fits_out` plus bas qui décide si `typeset_page` la
    # remplit. L'ancienne écriture `[] if avec_fits else []` rendait la même valeur dans les
    # deux branches — un reste de l'époque où le second cas valait `None`.
    fits: list[dict] = []
    # AVANT le lettrage : une zone restaurée doit retrouver son dessin, pas recevoir du texte
    # par-dessus. Elle n'en recevra pas non plus, puisqu'elle n'a aucune réplique.
    restaurees = restaurer_sans_texte(cleaned, originale, regions, textes, sources, styles)

    # ── Étage 0 : l'effacement du texte hors bulle (lot 22) ─────────────────────────────
    #
    # ⚠ Il est calculé sur la planche d'ORIGINE quand elle est là, et jamais sur la planche
    # nettoyée. La raison est celle que `clean.BubbleStyle` écrit déjà : « ces informations ne
    # peuvent pas être redécouvertes après le nettoyage ». Le fond local qu'il faut
    # reconstruire est celui d'avant — et hors des bulles les deux images sont bit-à-bit
    # identiques, donc le choix ne change rien tant que la détection ne s'est pas trompée.
    effacement = None
    mode_eff = str((cfg_effacement or {}).get("mode") or "aucun").lower()
    if mode_eff != "aucun" and zones_sfx:
        effacement = effacement_mod.effacer_zones(
            originale or cleaned, zones_sfx, styles_sfx, verdicts_sfx, cfg_effacement)
        if mode_eff == "aplati" and effacement.rgba is not None:
            # `cleaned` est muté, comme partout ailleurs dans cette fonction : l'appelant en
            # garde une copie (`fond_propre`) pour le PSD, et c'est un contrat existant.
            cleaned.paste(Image.fromarray(effacement.rgba, mode="RGBA"),
                          (effacement.x, effacement.y),
                          Image.fromarray(effacement.rgba, mode="RGBA"))

    image = typeset.typeset_page(
        cleaned, regions, textes, font_path=font_path, styles=styles, cfg=cfg_typeset,
        report_out=qa, fits_out=fits if avec_fits else None,
        sources=sources, layouts=layouts)

    gloses: list = []
    refus: list[str] = []
    if mode_sfx == "glose" and zones_sfx and any((t or "").strip()
                                                 for t in (traductions_sfx or [])):
        gloses, refus = gloss_mod.placer(image, zones_sfx, traductions_sfx or [],
                                         bulles=regions, cfg=cfg_typeset, font_path=font_path)
        image = gloss_mod.dessiner(image, gloses, cfg=cfg_typeset, font_path=font_path)

    fits_sfx: list[dict] = []
    if mode_sfx == "relettrage" and zones_sfx and mode_eff != "aucun":
        # ⚠ Le relettrage suit l'effacement, et la MÊME décision d'aplatissement. En mode
        # « calque », rien n'est composé : la planche de `pages_out/` reste celle d'avant, et
        # le PSD reçoit l'effacement et le lettrage comme deux piles masquables. Dessiner le
        # français sans avoir composé l'effacement poserait la traduction PAR-DESSUS le
        # japonais intact — la bouillie exacte que ce mode existe pour éviter.
        #
        # ⚠ Et il exige un effacement : `mode_eff == "aucun"` le désactive, plutôt que de
        # produire deux textes pour un son.
        fits_sfx = _lettrer_zones(image, zones_sfx, traductions_sfx or [], styles_sfx,
                                  verdicts_sfx, cfg_typeset, font_path,
                                  dessiner=(mode_eff == "aplati"))

    return ResultatRendu(image=image, qa=qa, fits=fits, gloses=gloses, refus_gloses=refus,
                         restaurees=restaurees, effacement=effacement, fits_sfx=fits_sfx)


def _lettrer_zones(image: Image.Image, zones: list, traductions: list[str],
                   styles_sfx: list | None, verdicts_sfx: list[str] | None,
                   cfg_typeset: dict | None, font_path: str | None, *,
                   dessiner: bool = True) -> list[dict]:
    """Lettre les zones hors bulle EFFAÇABLES, et rend leurs recettes. **Mute `image`** —
    sauf si `dessiner=False`, qui calcule les recettes pour le seul PSD.

    ⚠ Le même garde-fou que l'effacement, et pour la même raison : on ne relettre que ce
    qu'on a le droit d'effacer. Écrire une traduction française à côté d'une onomatopée
    japonaise qu'on n'a pas effacée donne deux textes pour un son ; l'écrire **par-dessus**
    sans avoir effacé donne une bouillie. La glose reste le mode qui pose à côté, et il n'est
    pas touché.

    Une zone dont le lettrage ne tient pas est **sautée**, pas dessinée en débordement :
    `best_fit` rend alors un `Fit` marqué `overflow`, et une onomatopée découpée par son
    propre masque est illisible. C'est la règle de la brique — une absence signalée vaut mieux
    qu'un lettrage abîmé."""
    from .sfx_lecture import LECTURE_SURE

    out: list[dict] = []
    for i, zone in enumerate(zones):
        texte = (traductions[i] if i < len(traductions) else "") or ""
        verdict = verdicts_sfx[i] if verdicts_sfx and i < len(verdicts_sfx) else ""
        if not texte.strip() or verdict != LECTURE_SURE:
            continue
        style_hb = styles_sfx[i] if styles_sfx and i < len(styles_sfx) else None
        style = typeset.style_pour_zone(style_hb, zone.bbox, image.size[::-1])
        if not style.ok:
            continue
        contenu, police, _subs, _supp = typeset.preparer_contenu(texte, cfg_typeset or {},
                                                                 font_path)
        if not contenu.strip():
            continue
        angle = typeset.angle_pour_zone(
            str(effacement_mod._valeur(style_hb, "orientation", "carree")), cfg_typeset)
        fit = typeset.fit_zone(contenu, style, cfg_typeset or {}, police, angle=angle)
        if fit.overflow or not fit.lines:
            continue
        if dessiner:
            typeset._draw_fit(image, fit, style, police)
        out.append({"index": i, "fit": fit, "style": style, "police": police,
                    "region": zone})
    return out
