#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Banc du texte HORS BULLE — l'instrument de mesure du lot 21.

## Pourquoi un banc séparé de `tools/banc.py`

`banc.py` mesure la **bulle** : combien, à quel score, avec quel remplissage, contrôlée ou
non. Il ne dit rien de ce qui est écrit à côté d'elle, et pour une raison qui n'est pas un
oubli : jusqu'ici, la seule chose qu'on savait dire d'une zone hors bulle était son
existence. Le lot 21 en mesure quatre autres — son aire, son fond, sa polarité et sa forme —
et aucune n'a sa place dans un tableau dont chaque ligne est un tome de bulles.

## La discipline, héritée de `_banc_commun`

Ce banc lit **le cache et les planches rendues**, dans cet ordre :

  · `.checkpoints/page_XXXX/sfx.json` — les boîtes, les textes lus, le drapeau `mobilier` ;
  · `pages_out/page_XXXX.png` — les pixels.

⚠ **`pages_out/` est légitime ici, et ce n'est pas un raccourci.** Le pipeline ne repeint
que l'intérieur des bulles (`clean.clean_bubbles`, invariant pixel-exact testé) et n'écrit
du texte que dedans. Une zone hors bulle y est donc **bit-à-bit** celle de la planche
d'origine — c'est la même propriété dont `_banc_commun.porte_de_l_encre` se sert déjà pour
son test d'encre. Le banc reste ainsi jouable sur une machine dont `sources/` a été purgé.

⚠ Cela cesse d'être vrai si le tome a été rendu en `manga.onomatopees.mode: "glose"` : la
glose est dessinée **à côté** de la zone, donc dans le pourtour que ce banc échantillonne.
`--source` permet alors de pointer les planches d'origine.

## Ce que ce banc ne mesure pas

Il ne charge **aucun modèle**. Il ne relance ni la détection de texte, ni `manga-ocr`, ni le
moindre appel LLM : il agrège ce que le pipeline a déjà écrit. Les zones qu'il compte sont
donc celles qu'un run a trouvées, pas celles qui existent sur la planche — un faux négatif
de détection lui est invisible par construction, et c'est à dire, pas à cacher.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools import _banc_commun as banc  # noqa: E402
from tools.banc import charger_config, configurer_stdout  # noqa: E402

#: Graine du tirage de l'échantillon de vérité terrain. **Écrite dans le dépôt**, comme le
#: demande L21 étape 0.2 : un échantillon dont personne ne peut refaire le tirage n'est pas
#: une référence, c'est une anecdote. 21 est le numéro du lot.
GRAINE_ECHANTILLON = 21

#: Taille de l'échantillon de vérité terrain (L21, étape 0.2).
TAILLE_ECHANTILLON = 60


@dataclass
class Zone:
    """Une zone hors bulle, telle que le cache la porte — plus ce que le banc en mesure."""

    projet: str
    tome: str
    page: int
    index: int
    bbox: tuple[int, int, int, int]
    texte: str
    mobilier: bool
    tri: str
    aire_bbox: int
    aire_page: int
    # Rempli seulement quand les pixels sont lus (`--sans-pixels` l'éteint).
    style: dict | None = field(default=None)

    @property
    def frac(self) -> float:
        return self.aire_bbox / self.aire_page if self.aire_page else 0.0

    @property
    def cle(self) -> str:
        """Identifiant stable d'une zone, indépendant de l'ordre d'énumération."""
        return f"{self.projet}/{self.tome}/p{self.page:04d}/z{self.index:02d}"


def _langue_du_volume(volume: banc.Volume, config: dict) -> str:
    """Langue SOURCE du tome, dont dépend l'heuristique de `trier_zone`.

    ⚠ Elle s'INVERSE avec la langue : sur une source japonaise, du latin signale une
    hallucination ; sur une source latine, c'est le CJK qui est l'intrus. Se tromper de
    langue ici retourne tout le tableau de triage, silencieusement."""
    projet = banc.charger_json(volume.build_dir / "projet.json")
    if isinstance(projet, dict):
        code = projet.get("code_langue") or projet.get("langue")
        if code:
            return str(code).lower()
    from manga import sources_manga
    return sources_manga.langue_defaut(config)


def _planche_rendue(volume: banc.Volume, page: int, source: Path | None) -> Path | None:
    """Où lire les pixels d'une planche. `pages_out/` d'abord (cf. l'en-tête du module)."""
    if source is not None:
        candidats = sorted(source.glob(f"page_{page:04d}.*"))
        if candidats:
            return candidats[0]
    for dossier in ("pages_out", "pages_clean", "pages_src"):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = volume.build_dir / dossier / f"page_{page:04d}{ext}"
            if p.exists():
                return p
    return None


def zones_du_volume(volume: banc.Volume, config: dict, *, pixels: bool = True,
                    source: Path | None = None) -> list[Zone]:
    """Toutes les zones hors bulle d'un tome, mesurées.

    Une planche est ouverte **au plus une fois**, et seulement si elle porte au moins une
    zone : sur les tomes du corpus, la moitié des planches n'en portent aucune."""
    from manga import text_detection as td
    langue = _langue_du_volume(volume, config)
    ckpt = volume.build_dir / ".checkpoints"
    zones: list[Zone] = []
    for numero in banc.numeros_de_planches(volume.build_dir):
        data = banc.charger_json(ckpt / f"page_{numero:04d}" / "sfx.json")
        if not isinstance(data, dict):
            continue
        regions = data.get("regions") or []
        if not regions:
            continue
        textes = data.get("textes") or []
        taille = data.get("image_size") or (0, 0)
        aire_page = max(1, int(taille[0]) * int(taille[1]))
        styles = None
        if pixels:
            styles = _styles_de_la_planche(volume, numero, regions, source)
        for i, r in enumerate(regions):
            bbox = tuple(int(v) for v in r.get("bbox") or (0, 0, 0, 0))
            texte = textes[i] if i < len(textes) else ""
            mobilier = bool(r.get("mobilier"))
            zones.append(Zone(
                projet=volume.projet, tome=volume.tome, page=numero, index=i,
                bbox=bbox, texte=texte or "", mobilier=mobilier,
                tri=td.trier_zone(texte or "", mobilier=mobilier, langue=langue),
                aire_bbox=max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1]),
                aire_page=aire_page,
                style=styles[i] if styles and i < len(styles) else None))
    return zones


def _styles_de_la_planche(volume: banc.Volume, numero: int, regions: list[dict],
                          source: Path | None) -> list[dict] | None:
    """Le style hors bulle de chaque zone d'une planche, ou `None` si l'image manque.

    ⚠ Les MASQUES ne sont pas relus. `sfx.json` ne persiste que les boîtes — c'est un choix
    du cache, pas un manque de ce banc — et `analyser_zone_hors_bulle` sait travailler sans :
    l'encre y est alors définie par son contraste au fond local, ce qui est de toute façon le
    juge quand le masque existe. Ce que le banc perd est le `remplissage` du masque, remplacé
    par celui de l'encre ; il est nommé ainsi dans le tableau."""
    chemin = _planche_rendue(volume, numero, source)
    if chemin is None:
        return None
    from PIL import Image

    from manga.clean import analyser_zone_hors_bulle
    from manga.detection import BubbleRegion
    with Image.open(chemin) as im:
        im = im.convert("RGB")
        out = []
        for r in regions:
            bbox = tuple(int(v) for v in r.get("bbox") or (0, 0, 0, 0))
            region = BubbleRegion(bbox=bbox, mask=None, score=1.0, cls=0,
                                  kind="onomatopee")
            st = analyser_zone_hors_bulle(im, region)
            out.append({
                "fond": list(st.fond), "fond_luma": round(st.fond_luma, 1),
                "uniformite_fond": round(st.uniformite_fond, 4),
                "encre": list(st.encre), "encre_luma": round(st.encre_luma, 1),
                "inverted": st.inverted,
                "part_encre": round(st.part_encre, 4),
                "remplissage": round(st.remplissage, 4),
                "aire_frac": round(st.aire_frac, 5),
                "orientation": st.orientation, "ok": st.ok,
            })
    return out


# ---------------------------------------------------------------------------
# Agrégation
# ---------------------------------------------------------------------------

def _quantiles(valeurs: list[float]) -> dict:
    """Cinq nombres qui décrivent une distribution, ou des `None` si elle est vide.

    ⚠ Une moyenne seule ne dit rien ici : ce qu'on cherche est la **queue haute** des aires
    (le dessin pris pour du texte) et le **creux** de la distribution d'uniformité (le seuil
    de `PLAN-22`). Ni l'une ni l'autre n'apparaît dans une moyenne."""
    if not valeurs:
        return {"n": 0, "min": None, "med": None, "p90": None, "p99": None, "max": None}
    v = sorted(valeurs)
    def q(p: float):
        return v[min(len(v) - 1, int(p * len(v)))]
    return {"n": len(v), "min": v[0], "med": stat.median(v), "p90": q(0.90),
            "p99": q(0.99), "max": v[-1]}


def resumer(zones: list[Zone]) -> dict:
    """Le résumé d'un lot de zones : triage, aires, uniformité, polarité, forme."""
    tri: dict[str, int] = {}
    for z in zones:
        tri[z.tri] = tri.get(z.tri, 0) + 1
    styles = [z.style for z in zones if z.style]
    mesures = [s for s in styles if s.get("ok")]
    uniformites = [s["uniformite_fond"] for s in mesures]
    return {
        "zones": len(zones),
        "pages_porteuses": len({(z.projet, z.tome, z.page) for z in zones}),
        "tri": tri,
        "aire_px": _quantiles([float(z.aire_bbox) for z in zones]),
        "aire_frac": _quantiles([z.frac for z in zones]),
        "mesurees": len(mesures),
        "uniformite": _quantiles(uniformites),
        # Les trois paliers de `clean_bubbles`, transposés au fond local. C'est CE tableau
        # qui décide de `PLAN-22` (cf. L21.2).
        "uniformite_paliers": {
            "≥0.60": sum(1 for u in uniformites if u >= 0.60),
            "0.35–0.60": sum(1 for u in uniformites if 0.35 <= u < 0.60),
            "<0.35": sum(1 for u in uniformites if u < 0.35),
        },
        "polarite": {
            "encre_sombre": sum(1 for s in mesures if not s["inverted"]),
            "encre_claire": sum(1 for s in mesures if s["inverted"]),
        },
        "remplissage": _quantiles([s["remplissage"] for s in mesures]),
        "orientation": {
            o: sum(1 for s in mesures if s["orientation"] == o)
            for o in ("verticale", "horizontale", "carree")
        },
    }


def echantillon(zones: list[Zone], taille: int = TAILLE_ECHANTILLON,
                graine: int = GRAINE_ECHANTILLON) -> list[Zone]:
    """Tirage SANS REMISE et reproductible de `taille` zones.

    Trié par clé avant tirage : l'ordre d'énumération de `build/` dépend du système de
    fichiers, et un tirage qui en dépendrait ne serait pas reproductible malgré sa graine.

    ⚠ Le tirage porte sur **toutes** les zones, mobilier compris. Écarter le mobilier avant
    de tirer ferait mesurer le triage par l'échantillon qu'il a lui-même filtré."""
    ordonnees = sorted(zones, key=lambda z: z.cle)
    if len(ordonnees) <= taille:
        return ordonnees
    return sorted(random.Random(graine).sample(ordonnees, taille), key=lambda z: z.cle)


def exporter_crops(zones: list[Zone], volumes: dict, destination: Path,
                   source: Path | None = None) -> list[str]:
    """Écrit le crop rectangulaire de chaque zone dans `destination`. Renvoie les noms.

    ⚠ **Le crop est RECTANGULAIRE BRUT**, jamais l'encre isolée, et c'est une mesure du
    dépôt : sur une zone hors bulle, l'encre nue donne une lecture inventée là où le crop
    brut donne la bonne, « parce que le masque retire justement les demi-teintes dont
    l'encodeur se sert » (`ocr.region_rectangulaire`).

    ⚠ **Ces images ne vont pas dans le dépôt.** Les planches du corpus ne sont pas
    redistribuables ; L21 étape 0.2 le dit et tranche : les MESURES restent, les images
    sortent. La destination par défaut est donc hors de l'arbre suivi."""
    from PIL import Image
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    noms: list[str] = []
    par_planche: dict[tuple, list[Zone]] = {}
    for z in zones:
        par_planche.setdefault((z.projet, z.tome, z.page), []).append(z)
    for (projet, tome, page), lot in sorted(par_planche.items()):
        volume = volumes[(projet, tome)]
        chemin = _planche_rendue(volume, page, source)
        if chemin is None:
            continue
        with Image.open(chemin) as im:
            im = im.convert("RGB")
            for z in lot:
                nom = z.cle.replace("/", "_") + ".png"
                im.crop(z.bbox).save(destination / nom)
                noms.append(nom)
    return noms


# ---------------------------------------------------------------------------
# Sortie
# ---------------------------------------------------------------------------

def _n(valeur, chiffres: int = 3) -> str:
    if valeur is None:
        return "—"
    if isinstance(valeur, float):
        return f"{valeur:.{chiffres}f}"
    return f"{valeur:,}".replace(",", " ")


def ligne_volume(nom: str, resume: dict) -> dict:
    tri = resume["tri"]
    return {
        "volume": nom,
        "planches porteuses": resume["pages_porteuses"],
        "zones": resume["zones"],
        "mobilier": tri.get("mobilier", 0),
        "bruit": tri.get("bruit", 0),
        "ponctuation": tri.get("ponctuation", 0),
        "texte": tri.get("japonais", 0),
        "aire méd. px²": _n(resume["aire_px"]["med"], 0),
        "aire p99 px²": _n(resume["aire_px"]["p99"], 0),
        "frac méd.": _n(resume["aire_frac"]["med"], 4),
        "frac p90": _n(resume["aire_frac"]["p90"], 4),
        "frac p99": _n(resume["aire_frac"]["p99"], 4),
        "unif. méd.": _n(resume["uniformite"]["med"]),
        "unif. ≥0,60": resume["uniformite_paliers"]["≥0.60"],
        "unif. <0,35": resume["uniformite_paliers"]["<0.35"],
        "encre claire": resume["polarite"]["encre_claire"],
        "rempl. méd.": _n(resume["remplissage"]["med"]),
    }


COLONNES = ["volume", "planches porteuses", "zones", "mobilier", "bruit", "ponctuation",
            "texte", "aire méd. px²", "aire p99 px²", "frac méd.", "frac p90", "frac p99",
            "unif. méd.", "unif. ≥0,60", "unif. <0,35", "encre claire", "rempl. méd."]


def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Mesure le texte HORS BULLE des tomes de build/ (lot 21).")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--tous", action="store_true", help="tous les volumes de build/")
    ap.add_argument("--markdown", action="store_true",
                    help="tableau précédé de son en-tête de publication")
    ap.add_argument("--json", metavar="FICHIER", default=None,
                    help="écrit toutes les zones mesurées, une par entrée")
    ap.add_argument("--sans-pixels", action="store_true",
                    help="n'ouvre aucune planche : aires et triage seulement")
    ap.add_argument("--source", metavar="DOSSIER", default=None,
                    help="dossier de planches d'origine (obligatoire si le tome a été "
                         "rendu en mode « glose »)")
    ap.add_argument("--echantillon", type=int, metavar="N", default=0,
                    help=f"tire N zones au sort (graine {GRAINE_ECHANTILLON}) et les liste")
    ap.add_argument("--graine", type=int, default=GRAINE_ECHANTILLON)
    ap.add_argument("--crops", metavar="DOSSIER", default=None,
                    help="exporte le crop de chaque zone de l'échantillon (hors dépôt)")
    ap.add_argument("--build", metavar="DOSSIER", default=None)
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    if not (args.tous or (args.projet and args.tome)):
        ap.error("indique « projet tome », ou --tous pour tous les volumes de build/.")

    config = charger_config(args.config)
    build_root = Path(args.build) if args.build else banc.racine_build(config)
    if args.tous:
        volumes = banc.enumerer_volumes(build_root)
    else:
        build_dir = banc.build_dir_de(build_root, args.projet, args.tome)
        volumes = ([banc.Volume(args.projet, args.tome, build_dir)]
                   if (build_dir / ".checkpoints").is_dir() else [])
    source = Path(args.source) if args.source else None

    toutes: list[Zone] = []
    lignes: list[dict] = []
    porteurs: list[banc.Volume] = []
    index = {}
    for v in volumes:
        zones = zones_du_volume(v, config, pixels=not args.sans_pixels, source=source)
        if not zones:
            continue          # un tome sans passe onomatopées n'est pas un tome à zéro zone
        porteurs.append(v)
        index[(v.projet, v.tome)] = v
        toutes.extend(zones)
        lignes.append(ligne_volume(v.nom, resumer(zones)))
    if not toutes:
        print("❌ Aucune zone hors bulle en cache : la passe onomatopées n'a jamais tourné.")
        return 1

    lignes.append(ligne_volume("**TOTAL**", resumer(toutes)))

    sortie: list[str] = []
    if args.markdown:
        sortie += banc.entete_publication(
            args.config, porteurs, titre="Banc du texte hors bulle",
            commande="python tools/banc_sfx.py --tous --markdown")
    sortie.append(banc.tableau_markdown(COLONNES, lignes))

    if args.echantillon:
        tirage = echantillon(toutes, args.echantillon, args.graine)
        sortie += ["", f"## Échantillon — {len(tirage)} zones, graine {args.graine}", ""]
        sortie.append(banc.tableau_markdown(
            ["clé", "boîte", "aire px²", "frac", "tri", "unif. fond", "encre claire",
             "lecture manga-ocr"],
            [{"clé": z.cle, "boîte": "×".join(
                str(v) for v in (z.bbox[2] - z.bbox[0], z.bbox[3] - z.bbox[1])),
              "aire px²": _n(z.aire_bbox, 0), "frac": _n(z.frac, 4), "tri": z.tri,
              "unif. fond": _n((z.style or {}).get("uniformite_fond")),
              "encre claire": "oui" if (z.style or {}).get("inverted") else "non",
              "lecture manga-ocr": (z.texte or "—")[:32]} for z in tirage]))
        if args.crops:
            noms = exporter_crops(tirage, index, Path(args.crops), source)
            sortie += ["", f"> {len(noms)} crops écrits dans `{args.crops}` — "
                           f"**hors du dépôt** (planches non redistribuables)."]

    print("\n".join(sortie))

    if args.json:
        Path(args.json).write_text(json.dumps(
            [asdict(z) for z in toutes], ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
