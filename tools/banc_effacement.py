#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Banc de l'EFFACEMENT du texte hors bulle — l'instrument de mesure du lot 22.

## Ce qu'il mesure, et pourquoi ces trois chiffres-là

`tools/banc_sfx.py` (lot 21) dit ce qu'une zone **est** : son aire, son fond, sa polarité,
l'uniformité du fond local. Il ne dit rien de ce qu'un effacement en **ferait**, et c'est
précisément la question de `PLAN-22`. Trois mesures y répondent, et aucune n'est un avis :

| mesure | ce qu'elle dit | ce qu'on en attend |
|---|---|---|
| **empreinte** | part de la boîte réellement repeinte | le coût : ce qu'on accepte de perdre du dessin |
| **résidu** | part de la boîte encore en fort contraste avec le fond, après | l'efficacité : un effacement qui laisse le glyphe n'a rien effacé |
| **couture** | écart moyen de luminance à la frontière du repeint | la visibilité : un raccord franc se voit plus que le texte |

Un effacement réussi a une **empreinte modérée**, un **résidu proche de zéro** et une
**couture faible**. Les trois ensemble, sinon rien : une empreinte de 100 % rend un résidu
nul et une couture nulle, et repeint toute la case.

## ⚠ Ce banc IGNORE délibérément le garde-fou de lecture, et le pipeline non

`manga/effacement.py` refuse d'effacer une zone dont la lecture n'est pas concordante
(critère 10 du plan de lot), et **aucune clé ne le désarme**. Le taux de `lecture_sure` étant
de 0 % sur le corpus (`docs/mesures/sfx-2026-08-28.md`), un banc qui respecterait cette règle
mesurerait exactement zéro zone et ne dirait rien.

Ce banc mesure donc **ce que le remplissage ferait**, zone par zone, sans autorisation de
lecture. C'est légitime parce qu'il n'écrit rien dans `build/` et ne touche aucune planche :
c'est un instrument, pas un chemin de rendu. Les deux propriétés sont indépendantes et
doivent le rester — celle-ci répond à « le déterministe suffit-il ? », l'autre à
« a-t-on le droit de s'en servir ici ? ».

## La discipline de lecture, héritée de `_banc_commun`

Les boîtes, les masques et les styles viennent des caches
(`.checkpoints/page_XXXX/sfx.json` + `sfx_masks.png`) ; les pixels viennent de `pages_out/`,
qui est **bit-à-bit** la planche d'origine hors des bulles — c'est un invariant testé de
`clean.py`. Aucun modèle n'est chargé, aucune inférence n'est relancée.

⚠ Cela cesse d'être vrai si le tome a été rendu en `mode: "glose"` ou avec un effacement
aplati : `--source` permet alors de pointer les planches d'origine.
"""
from __future__ import annotations

import argparse
import json
import statistics as stat
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools import _banc_commun as banc  # noqa: E402
from tools.banc import charger_config, configurer_stdout  # noqa: E402
from tools.banc_sfx import _planche_rendue  # noqa: E402

#: Les trois paliers de `clean_bubbles`, transposés au fond local. Ce sont eux qui découpent
#: le tableau : `PLAN-22` demande la part de chaque tranche, pas une moyenne.
PALIERS = (("≥0,60", 0.60, 1.01), ("0,35–0,60", 0.35, 0.60), ("<0,35", -0.01, 0.35))

COLONNES = ["volume", "zones", "peintes", "empreinte méd.", "résidu avant", "résidu après",
            "couture méd.", "grain méd.", "couture/grain méd.", "couture/grain p90"]


@dataclass
class Mesure:
    """Ce qu'un effacement ferait d'UNE zone. Aucun pixel n'est écrit sur disque."""

    projet: str
    tome: str
    page: int
    index: int
    tri: str
    motif: str
    uniformite: float
    aire_boite: int
    empreinte: float = 0.0
    residu_avant: float = 0.0
    residu_apres: float = 0.0
    couture: float = 0.0
    grain: float = 0.0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def rapport(self) -> float:
        """Couture rapportée au grain du fond intact. 1 = se raccorde comme le fond."""
        return self.couture / self.grain if self.grain > 0 else 0.0

    @property
    def palier(self) -> str:
        for nom, bas, haut in PALIERS:
            if bas <= self.uniformite < haut:
                return nom
        return "<0,35"

    @property
    def cle(self) -> str:
        return f"{self.projet}/{self.tome}/p{self.page:04d}/z{self.index:02d}"


def _residu(arr: np.ndarray, bbox, fond_luma: float, seuil: float) -> float:
    """Part de la boîte dont la luminance s'écarte du fond de plus de `seuil`.

    C'est la définition d'encre de `clean.analyser_zone_hors_bulle`, réemployée telle quelle :
    mesurer l'effacement avec une autre définition que celle qui l'a décidé rendrait le
    chiffre incomparable à lui-même."""
    from manga.clean import _luma
    x0, y0, x1, y1 = bbox
    boite = arr[y0:y1, x0:x1]
    if boite.size == 0:
        return 0.0
    return float((np.abs(_luma(boite.astype(np.float64)) - fond_luma) > seuil).mean())


def _paires_frontiere(luma: np.ndarray, peint: np.ndarray) -> list[np.ndarray]:
    """Écarts absolus de luminance entre chaque pixel peint et son voisin NON peint.

    Quatre directions, appariées par décalage d'un pixel : c'est le seul appariement qui a
    un sens ici, le masque ne portant aucune correspondance entre les deux côtés."""
    out = []
    for axe, sens in ((0, 1), (0, -1), (1, 1), (1, -1)):
        voisin = np.roll(peint, sens, axis=axe)
        valeur = np.roll(luma, sens, axis=axe)
        if axe == 0:
            bord = slice(0, 1) if sens == 1 else slice(-1, None)
            voisin[bord, :] = peint[bord, :]
        else:
            bord = slice(0, 1) if sens == 1 else slice(-1, None)
            voisin[:, bord] = peint[:, bord]
        paires = peint & ~voisin
        if paires.any():
            out.append(np.abs(luma[paires] - valeur[paires]))
    return out


def _couture(apres: np.ndarray, peint: np.ndarray,
             anneau: np.ndarray) -> tuple[float, float]:
    """`(couture, grain)` — l'écart de luminance **à la frontière** du repeint, et l'écart
    que le fond intact porte naturellement à la même échelle.

    Un effacement se voit par sa **discontinuité**, pas par sa couleur : un aplat gris posé au
    milieu d'une trame a un résidu nul et une empreinte modeste, et la planche est abîmée. La
    couture mesure la marche à la frontière ; le grain mesure la marche que le voisinage
    intact porte déjà, et sans lui la couture n'a pas d'échelle — 12 niveaux de luminance sont
    invisibles sur une trame et voyants sur un aplat de ciel.

    C'est **le rapport des deux** qui se lit : à 1, l'effacement se raccorde comme le fond se
    raccorde à lui-même ; au-dessus, il introduit une arête que le dessin n'a pas."""
    from manga.clean import _luma
    if not peint.any():
        return 0.0, 0.0
    la = _luma(apres.astype(np.float64))
    ecarts = _paires_frontiere(la, peint)
    couture = float(np.concatenate(ecarts).mean()) if ecarts else 0.0
    grain = 0.0
    if anneau.any():
        # Le grain se mesure sur les paires horizontales du seul fond intact.
        voisin = np.roll(la, 1, axis=1)
        valides = anneau & np.roll(anneau, 1, axis=1)
        valides[:, 0] = False
        if valides.any():
            grain = float(np.abs(la[valides] - voisin[valides]).mean())
    return couture, grain


def _anneau_intact(peint: np.ndarray, bbox, forme: tuple[int, int],
                   marge: int = 24) -> np.ndarray:
    """Le fond **non repeint** autour de la boîte — l'échelle contre laquelle lire la couture.

    Le même anneau que celui sur lequel `clean.analyser_zone_hors_bulle` mesure l'uniformité,
    et pour la même raison : à l'intérieur de la boîte, l'encre restante fausserait la mesure
    de tout ce qu'on voudrait y lire."""
    h, w = forme
    x0, y0, x1, y1 = bbox
    anneau = np.zeros((h, w), dtype=bool)
    anneau[max(0, y0 - marge):min(h, y1 + marge),
           max(0, x0 - marge):min(w, x1 + marge)] = True
    anneau[y0:y1, x0:x1] = False
    return anneau & ~peint


def mesurer_planche(volume: banc.Volume, numero: int, langue: str, cfg_eff: dict,
                    source: Path | None, images: Path | None) -> list[Mesure]:
    """Toutes les zones d'une planche, mesurées. `[]` si la planche n'a rien ou manque."""
    from PIL import Image

    from manga import checkpoints, clean, effacement, sfx_lecture, text_detection as td

    ckpt = volume.build_dir / ".checkpoints" / f"page_{numero:04d}"
    charge = checkpoints.load_sfx_complet(ckpt)
    if not charge or not charge["regions"]:
        return []
    chemin = _planche_rendue(volume, numero, source)
    if chemin is None:
        return []
    regions, textes = charge["regions"], charge["textes"]
    styles = charge["styles"]
    mobilier = charge["mobilier"]
    seuil = float(cfg_eff.get("seuil_encre", 45))

    with Image.open(chemin) as im:
        image = im.convert("RGB")
        arr = np.asarray(image)
        # ⚠ Le style hors bulle n'est en cache que pour les planches dont la passe `sfx` a
        # tourné APRÈS le lot 21 — c'est-à-dire aucune du corpus, puisque ce lot n'a
        # volontairement invalidé aucun cache. Il est alors REMESURÉ ici, exactement comme
        # `tools/banc_sfx.py` le fait, et le résultat est le même : la mesure porte sur les
        # pixels hors bulle, qui sont bit-à-bit ceux de la planche d'origine.
        if not styles:
            styles = [
                {"fond": list(s.fond), "fond_luma": s.fond_luma,
                 "uniformite_fond": s.uniformite_fond, "encre": list(s.encre),
                 "inverted": s.inverted, "remplissage": s.remplissage,
                 "aire_frac": s.aire_frac, "orientation": s.orientation, "ok": s.ok}
                for s in clean.analyser_zones_hors_bulle(image, regions)]
        out: list[Mesure] = []
        for i, region in enumerate(regions):
            texte = textes[i] if i < len(textes) else ""
            tri = td.trier_zone(texte or "", langue=langue,
                                mobilier=(mobilier[i:i + 1] or [False])[0])
            style = styles[i] if i < len(styles) else None
            motif, uniformite = effacement.decider(style, sfx_lecture.LECTURE_SURE, cfg_eff)
            bbox = effacement._boite_saine(region.bbox, arr.shape[1], arr.shape[0])
            aire = max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
            fond_luma = float(effacement._valeur(style, "fond_luma", 255.0))
            m = Mesure(projet=volume.projet, tome=volume.tome, page=numero, index=i,
                       tri=tri, motif=motif, uniformite=uniformite, aire_boite=aire,
                       bbox=bbox,
                       residu_avant=_residu(arr, bbox, fond_luma, seuil))
            if motif in effacement.MOTIFS_PEINTS:
                eff = effacement.effacer_zones(image, [region], [style],
                                               [sfx_lecture.LECTURE_SURE], cfg_eff)
                apres = np.asarray(effacement.composer(image, eff))
                peint = np.zeros(arr.shape[:2], dtype=bool)
                if eff.rgba is not None:
                    ph, pw = eff.rgba.shape[:2]
                    peint[eff.y:eff.y + ph, eff.x:eff.x + pw] = eff.rgba[:, :, 3] > 0
                m.empreinte = float(peint.sum()) / aire
                m.residu_apres = _residu(apres, bbox, fond_luma, seuil)
                anneau = _anneau_intact(peint, bbox, arr.shape[:2])
                m.couture, m.grain = _couture(apres, peint, anneau)
                if images is not None:
                    _ecrire_avant_apres(images, m, arr, apres)
            else:
                m.residu_apres = m.residu_avant
            out.append(m)
    return out


def _ecrire_avant_apres(dossier: Path, m: Mesure, avant: np.ndarray,
                        apres: np.ndarray) -> None:
    """Écrit un avant/après côte à côte. **Hors dépôt, toujours** : les planches du corpus ne
    sont pas redistribuables, et le lot 21 a déjà tranché ce point par écrit."""
    from PIL import Image
    x0, y0, x1, y1 = m.bbox
    marge = 24
    ax0, ay0 = max(0, x0 - marge), max(0, y0 - marge)
    ax1, ay1 = min(avant.shape[1], x1 + marge), min(avant.shape[0], y1 + marge)
    a = avant[ay0:ay1, ax0:ax1]
    b = apres[ay0:ay1, ax0:ax1]
    if a.size == 0:
        return
    sep = np.full((a.shape[0], 4, 3), 255, dtype=np.uint8)
    dossier.mkdir(parents=True, exist_ok=True)
    nom = f"{m.cle.replace('/', '_')}_{m.motif}_u{m.uniformite:.2f}.png"
    Image.fromarray(np.hstack([a, sep, b])).save(dossier / nom)


# ---------------------------------------------------------------------------
# La figure SYNTHÉTIQUE — le seul avant/après que ce dépôt puisse publier
# ---------------------------------------------------------------------------
#
# ⚠ Les planches du corpus ne sont pas redistribuables : le lot 21 a tranché ce point par
# écrit, et le lot 22 ne le rouvre pas. `--images` écrit donc les avant/après réels HORS du
# dépôt, et `--synthetique` fabrique une figure qui, elle, peut y vivre.
#
# Elle n'est pas une illustration : les trois fonds reproduisent les trois situations que la
# distribution d'uniformité du corpus désigne — un aplat (53,3 % des zones), une trame
# régulière (36,1 %), une structure franche (10,6 %, le palier du gratte-ciel de la page 44).
# Le troisième existe pour montrer ce que le module **ne fait pas**.

FONDS_SYNTHETIQUES = ("aplat", "trame", "structure")


def _fond_synthetique(nom: str, largeur: int, hauteur: int) -> np.ndarray:
    """Un des trois fonds de la figure, fabriqué sans police ni ressource externe."""
    y, x = np.mgrid[0:hauteur, 0:largeur]
    if nom == "aplat":
        fond = np.full((hauteur, largeur), 236.0)
        fond += 6.0 * np.sin(x / 37.0)          # le grain d'un scan, pas un aplat parfait
    elif nom == "trame":
        # Trame mécanique + dégradé : le fond « faiblement structuré » de L22.1.
        fond = 150.0 + 60.0 * (x / largeur)
        fond -= 26.0 * ((x // 4 + y // 4) % 2)
    else:
        # Le gratte-ciel de la page 44 : des façades de valeurs distinctes, des fenêtres
        # claires, et un ciel dégradé. C'est le cas exact que `clean.py` a appris à refuser —
        # non parce qu'il est « sombre », mais parce que sa luminance n'a PAS de mode
        # dominant, et qu'aucune couleur unique n'y est le fond de quoi que ce soit.
        fond = 96.0 + 104.0 * (y / hauteur)                   # le ciel, en dégradé
        facade = (x // 31) % 4
        batiment = x < int(largeur * 0.86)
        fond[batiment & (facade == 0)] = 26.0
        fond[batiment & (facade == 1)] = 140.0
        fond[batiment & (facade == 2)] = 68.0
        fond[batiment & (facade == 3)] = 196.0
        fenetres = batiment & ((y // 15) % 2 == 0) & ((x // 11) % 2 == 0)
        fond[fenetres] = 238.0
    return np.clip(fond, 0, 255).astype(np.uint8)


def _glyphe(masque: np.ndarray, x0: int, y0: int) -> None:
    """Trois traits épais, en place. Pas de police : la figure doit se refaire à l'identique
    sur n'importe quelle machine, et `tests/conftest.py` rappelle déjà ce que coûte une
    ressource système absente — la couverture saute en silence."""
    masque[y0:y0 + 14, x0:x0 + 96] = True                      # barre horizontale
    masque[y0:y0 + 78, x0 + 20:x0 + 34] = True                 # jambage
    masque[y0 + 64:y0 + 78, x0 + 20:x0 + 110] = True           # pied
    masque[y0 + 22:y0 + 36, x0 + 56:x0 + 118] = True           # traverse


def figure_synthetique(destination: Path, cfg_eff: dict) -> Path:
    """Écrit `avant | après` pour les trois fonds, l'un sous l'autre. Rend le chemin écrit."""
    from PIL import Image

    from manga import clean, effacement, sfx_lecture
    from manga.detection import BubbleRegion

    largeur, hauteur = 260, 150
    bandes = []
    for nom in FONDS_SYNTHETIQUES:
        fond = _fond_synthetique(nom, largeur, hauteur)
        encre = np.zeros((hauteur, largeur), dtype=bool)
        _glyphe(encre, 70, 36)
        arr = np.dstack([fond] * 3)
        # L'encre prend le pôle contrasté du fond : noire sur clair, blanche sur sombre.
        clair = float(fond.mean()) < 128.0
        arr[encre] = 245 if clair else 16
        image = Image.fromarray(arr)

        masque = np.zeros((hauteur, largeur), dtype=bool)
        masque[28:126, 62:196] = True
        zone = BubbleRegion(bbox=(62, 28, 196, 126), mask=masque, score=1.0, cls=0,
                            kind="onomatopee")
        style = clean.analyser_zone_hors_bulle(image, zone)
        eff = effacement.effacer_zones(image, [zone], [style],
                                       [sfx_lecture.LECTURE_SURE], cfg_eff)
        apres = np.asarray(effacement.composer(image, eff))
        sep = np.full((hauteur, 6, 3), 255, dtype=np.uint8)
        bandes.append(np.hstack([arr, sep, apres]))
        motif = eff.decisions[0].motif if eff.decisions else "?"
        print(f"  {nom:<9} uniformité {style.uniformite_fond:.3f} → {motif}")

    trait = np.full((6, bandes[0].shape[1], 3), 255, dtype=np.uint8)
    figure = np.vstack([b for paire in zip(bandes, [trait] * len(bandes))
                        for b in paire][:-1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(figure).save(destination)
    return destination


def _quantile(valeurs: list[float], p: float) -> float:
    if not valeurs:
        return 0.0
    v = sorted(valeurs)
    return v[min(len(v) - 1, int(p * len(v)))]


def resumer(mesures: list[Mesure]) -> dict:
    """Le résumé d'un lot de zones, découpé par palier d'uniformité."""
    peintes = [m for m in mesures if m.empreinte > 0]
    par_palier: dict[str, dict] = {}
    for nom, _bas, _haut in PALIERS:
        lot = [m for m in mesures if m.palier == nom]
        p = [m for m in lot if m.empreinte > 0]
        par_palier[nom] = {
            "zones": len(lot),
            "part": len(lot) / len(mesures) if mesures else 0.0,
            "empreinte_med": stat.median([m.empreinte for m in p]) if p else 0.0,
            "residu_avant": stat.median([m.residu_avant for m in lot]) if lot else 0.0,
            "residu_apres": stat.median([m.residu_apres for m in lot]) if lot else 0.0,
            "couture_med": stat.median([m.couture for m in p]) if p else 0.0,
            "grain_med": stat.median([m.grain for m in p]) if p else 0.0,
            "rapport_med": stat.median([m.rapport for m in p]) if p else 0.0,
            "rapport_p90": _quantile([m.rapport for m in p], 0.90),
        }
    motifs: dict[str, int] = {}
    for m in mesures:
        motifs[m.motif] = motifs.get(m.motif, 0) + 1
    return {
        "zones": len(mesures),
        "peintes": len(peintes),
        "motifs": motifs,
        "empreinte_med": stat.median([m.empreinte for m in peintes]) if peintes else 0.0,
        "empreinte_p90": _quantile([m.empreinte for m in peintes], 0.90),
        "residu_avant": stat.median([m.residu_avant for m in mesures]) if mesures else 0.0,
        "residu_apres": stat.median([m.residu_apres for m in mesures]) if mesures else 0.0,
        "couture_med": stat.median([m.couture for m in peintes]) if peintes else 0.0,
        "grain_med": stat.median([m.grain for m in peintes]) if peintes else 0.0,
        "rapport_med": stat.median([m.rapport for m in peintes]) if peintes else 0.0,
        "rapport_p90": _quantile([m.rapport for m in peintes], 0.90),
        "paliers": par_palier,
    }


def ligne_volume(nom: str, r: dict) -> dict:
    return {
        "volume": nom, "zones": r["zones"], "peintes": r["peintes"],
        "empreinte méd.": f"{r['empreinte_med']:.3f}",
        "résidu avant": f"{r['residu_avant']:.3f}",
        "résidu après": f"{r['residu_apres']:.3f}",
        "couture méd.": f"{r['couture_med']:.1f}",
        "grain méd.": f"{r['grain_med']:.1f}",
        "couture/grain méd.": f"{r['rapport_med']:.2f}",
        "couture/grain p90": f"{r['rapport_p90']:.2f}",
    }


def tableau_paliers(r: dict) -> str:
    """Le tableau que `PLAN-22` réclame à l'étape 0.2 : la part de chaque tranche, et ce que
    le déterministe y fait."""
    lignes = [{"palier": nom, "zones": d["zones"], "part": f"{100 * d['part']:.1f} %",
               "empreinte méd.": f"{d['empreinte_med']:.3f}",
               "résidu avant": f"{d['residu_avant']:.3f}",
               "résidu après": f"{d['residu_apres']:.3f}",
               "couture méd.": f"{d['couture_med']:.1f}",
               "grain méd.": f"{d['grain_med']:.1f}",
               "couture/grain méd.": f"{d['rapport_med']:.2f}",
               "couture/grain p90": f"{d['rapport_p90']:.2f}"}
              for nom, d in r["paliers"].items()]
    return banc.tableau_markdown(
        ["palier", "zones", "part", "empreinte méd.", "résidu avant", "résidu après",
         "couture méd.", "grain méd.", "couture/grain méd.", "couture/grain p90"], lignes)


def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Mesure ce qu'un effacement déterministe ferait du texte hors bulle "
                    "des tomes de build/ (lot 22).")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--tous", action="store_true", help="tous les volumes de build/")
    ap.add_argument("--markdown", action="store_true",
                    help="tableaux précédés de leur en-tête de publication")
    ap.add_argument("--json", metavar="FICHIER", default=None,
                    help="écrit toutes les zones mesurées, une par entrée")
    ap.add_argument("--images", metavar="DOSSIER", default=None,
                    help="écrit un avant/après par zone effacée (HORS DÉPÔT : le corpus "
                         "n'est pas redistribuable)")
    ap.add_argument("--synthetique", metavar="FICHIER", default=None,
                    help="écrit la figure avant/après sur les trois fonds synthétiques "
                         "(la seule que le dépôt puisse publier) et s'arrête")
    ap.add_argument("--texte-seul", action="store_true",
                    help="ne mesure que les zones que le triage classe « texte »")
    ap.add_argument("--dilatation", type=float, default=None,
                    help="surcharge `manga.onomatopees.effacement.dilatation` (balayage)")
    ap.add_argument("--passes", type=int, default=None,
                    help="surcharge `passes_diffusion` (balayage)")
    ap.add_argument("--seuil-uniformite", type=float, default=None,
                    help="surcharge `seuil_uniformite` (0 = tout en diffusion)")
    ap.add_argument("--source", metavar="DOSSIER", default=None)
    ap.add_argument("--build", metavar="DOSSIER", default=None)
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    if not (args.tous or (args.projet and args.tome)):
        ap.error("indique « projet tome », ou --tous pour tous les volumes de build/.")

    from manga import text_detection as td
    from tools.banc_sfx import _langue_du_volume

    config = charger_config(args.config)
    build_root = Path(args.build) if args.build else banc.racine_build(config)
    if args.tous:
        volumes = banc.enumerer_volumes(build_root)
    else:
        build_dir = banc.build_dir_de(build_root, args.projet, args.tome)
        volumes = ([banc.Volume(args.projet, args.tome, build_dir)]
                   if (build_dir / ".checkpoints").is_dir() else [])
    source = Path(args.source) if args.source else None
    images = Path(args.images) if args.images else None
    cfg_eff = dict(((config.get("manga") or {}).get("onomatopees") or {})
                   .get("effacement") or {})
    # Le balayage est une SURCHARGE de ligne de commande, pas une clé de plus : un réglage
    # qu'on cherche n'a rien à faire dans un fichier qui documente ses valeurs par un chiffre.
    if args.dilatation is not None:
        cfg_eff["dilatation"] = args.dilatation
    if args.passes is not None:
        cfg_eff["passes_diffusion"] = args.passes
    if args.seuil_uniformite is not None:
        cfg_eff["seuil_uniformite"] = args.seuil_uniformite

    if args.synthetique:
        chemin = figure_synthetique(Path(args.synthetique), cfg_eff)
        print(f"Figure écrite : {chemin}")
        return 0

    toutes: list[Mesure] = []
    lignes: list[dict] = []
    porteurs: list[banc.Volume] = []
    for v in volumes:
        langue = _langue_du_volume(v, config)
        mesures: list[Mesure] = []
        for numero in banc.numeros_de_planches(v.build_dir):
            mesures += mesurer_planche(v, numero, langue, cfg_eff, source, images)
        if args.texte_seul:
            mesures = [m for m in mesures if m.tri == td.TRI_TEXTE]
        if not mesures:
            continue
        porteurs.append(v)
        toutes += mesures
        lignes.append(ligne_volume(v.nom, resumer(mesures)))

    if not toutes:
        print("❌ Aucune zone hors bulle en cache : la passe onomatopées n'a jamais tourné.")
        return 1

    total = resumer(toutes)
    lignes.append(ligne_volume("**TOTAL**", total))

    sortie: list[str] = []
    if args.markdown:
        sortie += banc.entete_publication(
            args.config, porteurs, titre="Banc de l'effacement du texte hors bulle",
            commande="python tools/banc_effacement.py --tous --markdown")
    sortie.append(banc.tableau_markdown(COLONNES, lignes))
    sortie.append("")
    sortie.append("### Par palier d'uniformité du fond local")
    sortie.append("")
    sortie.append(tableau_paliers(total))
    sortie.append("")
    sortie.append("### Décisions, par motif")
    sortie.append("")
    for motif, n in sorted(total["motifs"].items(), key=lambda kv: -kv[1]):
        from manga import effacement as eff_mod
        sortie.append(f"- `{motif}` — {n} zone(s) · "
                      f"{eff_mod.LIBELLES.get(motif, motif)}")
    print("\n".join(sortie))

    if args.json:
        Path(args.json).write_text(
            json.dumps([{**vars(m), "palier": m.palier, "cle": m.cle} for m in toutes],
                       ensure_ascii=False, indent=1), encoding="utf-8")
    if images is not None:
        print(f"\nAvant/après écrits dans {images} — hors dépôt, non redistribuables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
