# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L29.2** — le protocole en aveugle : la discipline, pas le code.

    des images produites  →  des paires (référence, A, B), étiquettes CACHÉES
    un humain              →  une réponse par paire, horodatée, ajoutée à un journal
    le juge automatique    →  le même classement sur les mêmes paires
                           →  l'ACCORD des deux, et c'est le livrable

## Pourquoi ce module est délibérément bête

Sa valeur n'est pas dans son algorithme — mélanger deux images et compter des voix ne
demande rien. Elle est dans **trois règles**, et la première est celle qu'on viole toujours :

1. **le seuil de succès est fixé AVANT de voir les résultats.** Il est écrit dans le fichier
   de protocole au moment où celui-ci est créé, et `rapport` le lit **de là** — jamais d'un
   argument de ligne de commande. Un seuil qu'on peut passer en option est un seuil qu'on
   ajuste après coup, et un seuil ajusté après coup ne mesure rien. Le `PLAN-25` proposait
   14 sur 20 ; c'est le défaut, et il se change à la création, pas à la lecture ;
2. **l'ordre A/B est tiré au sort et l'étiquette est cachée**, y compris dans le nom du
   fichier présenté et dans **l'ordre d'écriture sur le disque** — « un dossier trié par date
   suffit à trahir la configuration » ;
3. **les réponses sont horodatées et conservées**, dans un journal en **ajout seul**. Une
   réponse ne se corrige pas en place : on en ajoute une nouvelle, et les deux restent. Un
   protocole en aveugle non archivé n'est pas reproductible, et c'est le seul juge opposable
   du dossier.

## Ce que le produit de l'étape EST, et ce qu'il n'est pas

**Ce n'est pas un verdict sur la voie A**, c'est un **étalon**. Le lot 25 a livré un juge
automatique dont la probabilité de séparation vaut **0,68** sur 100 paires
(`docs/mesures/prompt-illustration-2026-08-30.md` §11) — mais personne ne sait si 0,68 est
un mauvais score, parce que personne n'a mesuré ce qu'un humain fait sur les mêmes paires.
C'est **l'accord humain / automatique** qui le dira, et c'est le seul chiffre que ce module
existe pour produire.

⚠ **Aucune fonction d'ici ne charge de modèle, n'ouvre de réseau ni n'écrit d'image.** Les
scores du juge automatique lui sont **passés** ; c'est l'appelant qui possède l'encodeur.
C'est ce qui rend tout ce fichier testable en CI, sans poids et sans GPU — et c'est la règle
de couche du dépôt : tout ce qui décide se teste sans modèle.

## L'état, au 2026-09-03

⚠ **Le protocole n'a JAMAIS été exécuté.** Il est écrit depuis le `PLAN-25` étape 0.3, il est
outillé depuis ici, et il attend la seule chose qu'aucun code ne remplace : une demi-journée
d'un humain devant des images, sur la machine qui sait générer. Tant que ce chiffre n'existe
pas, toute colonne « ressemblance » du dépôt reste **non opposable**, et le dire fait partie
de la mesure.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

#: Version du fichier de protocole. Sans rapport avec `checkpoints.FORMAT_VERSION` : ce
#: fichier n'est pas un cache et n'invalide rien (interdit n° 1).
VERSION = 1

#: Le seuil du `PLAN-25` étape 0.3, repris tel quel par le `PLAN-29` L29.2 : « préférée dans
#: au moins 14 cas sur 20 ». Le plan autorise à le changer — **maintenant, pas après**.
SEUIL_DEFAUT = 14
PAIRES_DEFAUT = 20

#: Les réponses acceptées. `=` et `?` ne sont PAS la même chose et les confondre coûterait le
#: sens de la mesure : `=` est un jugement (« les deux se valent »), `?` est une abstention
#: (« je ne sais pas », « l'image est illisible »). Une égalité compte pour une demi-voix de
#: chaque côté ; une abstention ne compte pour rien et **sort du dénominateur**.
REPONSES = ("A", "B", "=", "?")

#: Nom des deux fichiers, sous le dossier du protocole.
NOM_PROTOCOLE = "protocole.json"
NOM_REPONSES = "reponses.jsonl"

#: Nom des copies présentées à l'humain. `{n:02d}` puis `A`/`B` — et **rien d'autre** : ni la
#: configuration, ni le nom d'origine, ni la graine. Le nom d'un fichier est une étiquette.
GABARIT_COPIE = "paire-{n:02d}-{cote}.png"


class ProtocoleInvalide(RuntimeError):
    """Le fichier de protocole manque, ou ne dit pas ce dont le rapport a besoin.

    ⚠ Pas de repli sur des valeurs par défaut : un rapport calculé contre un seuil que le
    protocole ne portait pas serait exactement le seuil ajusté après coup que la règle 1
    interdit."""


# ──────────────────────────────  Construire les paires  ──────────────────────────────

def paires(candidats: list[dict], *, nombre: int = PAIRES_DEFAUT,
           graine: int = 20260903) -> list[dict]:
    """`nombre` paires tirées des `candidats`, **ordre A/B tiré au sort**.

    Un candidat est `{"image": <chemin>, "configuration": "<étiquette>"}`. La paire rendue
    porte `gauche` / `droite` (les chemins) et `_config_gauche` / `_config_droite` — le
    tiret bas dit ce que le dépôt fait déjà de `_interdits` dans un manifeste : **une clé
    qu'on n'affiche pas**.

    ⚠ **Les paires qui opposent DEUX CONFIGURATIONS DIFFÉRENTES passent en premier.** Deux
    images de la même configuration ne disent rien sur la configuration ; elles restent
    utilisables pour l'accord humain/automatique — qui, lui, ne demande que deux images —
    et c'est pourquoi elles ne sont pas jetées, seulement repoussées."""
    import random

    alea = random.Random(int(graine))
    valides = [c for c in candidats if c.get("image")]
    couples = list(itertools.combinations(valides, 2))
    alea.shuffle(couples)
    # ⚠ Le tri est STABLE : à l'intérieur de chaque groupe l'ordre reste celui du mélange,
    # donc le tirage garde son hasard. Trier n'ordonne pas, il regroupe.
    couples.sort(key=lambda c: c[0].get("configuration") == c[1].get("configuration"))

    sortie = []
    for index, (un, deux) in enumerate(couples[:max(0, int(nombre))], start=1):
        gauche, droite = (un, deux) if alea.random() < 0.5 else (deux, un)
        sortie.append({
            "n": index,
            "gauche": str(gauche["image"]),
            "droite": str(droite["image"]),
            "_config_gauche": str(gauche.get("configuration") or ""),
            "_config_droite": str(droite.get("configuration") or ""),
        })
    return sortie


def protocole(liste: list[dict], *, reference: str = "", seuil: int = SEUIL_DEFAUT,
              graine: int = 20260903, juge: dict | None = None) -> dict:
    """Le document de protocole, **seuil compris**, prêt à être écrit avant la première
    réponse.

    `reference` est l'image de référence montrée à côté de chaque paire ; elle peut être vide
    — on demande alors « laquelle préfères-tu », ce qui est une autre question et le rapport
    le dit. `juge` décrit l'encodeur qui servira à l'accord (nom, empreinte, cadrage), pour
    qu'un rapport relu dans six mois sache **quel** juge automatique a été comparé."""
    return {
        "version": VERSION,
        "cree": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graine": int(graine),
        "seuil": int(seuil),
        "sur": len(liste),
        "reference": str(reference or ""),
        "juge": dict(juge or {}),
        "paires": list(liste),
    }


def verifier(doc: dict) -> dict:
    """Le protocole relu, ou `ProtocoleInvalide`. Rend le document tel quel."""
    if not isinstance(doc, dict) or not doc.get("paires"):
        raise ProtocoleInvalide(
            "protocole vide ou illisible — relance `python tools/juge_humain.py --paires N`.")
    if not isinstance(doc.get("seuil"), int) or doc["seuil"] <= 0:
        raise ProtocoleInvalide(
            "le protocole ne porte pas de seuil de succès entier.\n"
            "  Le seuil se fixe À LA CRÉATION, jamais à la lecture : un seuil qu'on passe en "
            "option après avoir vu les résultats ne mesure rien (PLAN-29 L29.2, règle 1).")
    return doc


# ────────────────────────────  Les réponses, en ajout seul  ────────────────────────────

def reponse(n: int, valeur: str, *, secondes: float | None = None) -> dict:
    """Une réponse horodatée. `valeur` est l'une de `REPONSES`, et rien d'autre.

    `secondes` est le temps de décision, s'il a été relevé. Il n'entre dans aucun verdict :
    il est là parce qu'une réponse rendue en une seconde et une réponse pesée trente secondes
    ne se lisent pas pareil, et qu'on ne peut pas le reconstituer après coup."""
    valeur = str(valeur or "").strip().upper()
    if valeur not in REPONSES:
        raise ValueError(f"réponse « {valeur} » hors de {REPONSES}")
    ligne = {"n": int(n), "reponse": valeur,
             "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if secondes is not None:
        ligne["secondes"] = round(float(secondes), 2)
    return ligne


def ajouter(chemin, ligne: dict) -> None:
    """Ajoute une réponse au journal. **Ajout seul, jamais réécriture.**

    ⚠ Une réponse qu'on corrige laisse les deux lignes dans le fichier, et `dernieres` retient
    la dernière. C'est la seule forme sous laquelle « je me suis repris à la paire 7 » reste
    lisible six mois plus tard — un fichier réécrit ne le dirait pas."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("a", encoding="utf-8") as flux:
        flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def lire_reponses(chemin) -> list[dict]:
    """Toutes les lignes du journal, dans l'ordre. Une ligne illisible est **sautée en le
    disant** — jamais devinée : une réponse reconstruite serait une réponse inventée."""
    chemin = Path(chemin)
    if not chemin.is_file():
        return []
    sorties = []
    for brute in chemin.read_text(encoding="utf-8").splitlines():
        brute = brute.strip()
        if not brute:
            continue
        try:
            ligne = json.loads(brute)
        except json.JSONDecodeError:
            continue
        if isinstance(ligne, dict) and ligne.get("reponse") in REPONSES:
            sorties.append(ligne)
    return sorties


def dernieres(lignes: list[dict]) -> dict:
    """`{n: dernière réponse}` — la dernière l'emporte, et les précédentes restent au journal."""
    table: dict = {}
    for ligne in lignes:
        table[int(ligne.get("n") or 0)] = ligne
    return table


# ──────────────────────────────────  Le rapport  ──────────────────────────────────

def rapport(doc: dict, lignes: list[dict], scores: dict | None = None) -> dict:
    """Le tableau du protocole : les voix par configuration, le verdict contre le seuil, et
    **l'accord avec le juge automatique**.

    `scores` est `{chemin d'image: ressemblance à la référence}`, calculé par l'appelant avec
    `illustration/juge.py`. Absent, la colonne d'accord est `None` — **pas 0** : un accord de
    zéro est une mesure (« ils ne sont jamais d'accord »), une absence d'encodeur n'en est pas
    une, et le dépôt distingue déjà les deux (`juge.mesurer`).

    ⚠ **Le verdict de configuration n'est rendu que si UNE SEULE opposition domine.** Vingt
    paires qui opposeraient six configurations deux à deux ne se résument pas par « 14 sur
    20 » : le seuil du plan compare DEUX configurations. Quand ce n'est pas le cas, le champ
    `verdict` le dit et ne tranche pas."""
    verifier(doc)
    table = dernieres(lignes)
    seuil, total = int(doc["seuil"]), len(doc["paires"])

    repondues = accord = comparables = 0
    voix: dict = {}
    duels: dict = {}
    detail = []
    for paire in doc["paires"]:
        n = int(paire.get("n") or 0)
        ligne = table.get(n)
        choix = str((ligne or {}).get("reponse") or "")
        cfg_g = str(paire.get("_config_gauche") or "")
        cfg_d = str(paire.get("_config_droite") or "")
        vainqueur_humain = ""
        if choix in ("A", "B", "="):
            repondues += 1
            if choix == "=":
                voix[cfg_g] = voix.get(cfg_g, 0.0) + 0.5
                voix[cfg_d] = voix.get(cfg_d, 0.0) + 0.5
            else:
                vainqueur_humain = "gauche" if choix == "A" else "droite"
                gagnante = cfg_g if choix == "A" else cfg_d
                voix[gagnante] = voix.get(gagnante, 0.0) + 1.0
            if cfg_g != cfg_d:
                duel = tuple(sorted((cfg_g, cfg_d)))
                compte = duels.setdefault(duel, {duel[0]: 0.0, duel[1]: 0.0})
                if choix == "=":
                    compte[duel[0]] += 0.5
                    compte[duel[1]] += 0.5
                else:
                    compte[cfg_g if choix == "A" else cfg_d] += 1.0

        vainqueur_auto = _vainqueur_auto(paire, scores)
        if vainqueur_humain and vainqueur_auto:
            comparables += 1
            accord += int(vainqueur_humain == vainqueur_auto)
        detail.append({"n": n, "réponse": choix or "(sans réponse)",
                       "humain": vainqueur_humain or "—",
                       "automatique": vainqueur_auto or "—",
                       "d'accord": ("oui" if vainqueur_humain == vainqueur_auto else "non")
                                   if (vainqueur_humain and vainqueur_auto) else "—"})

    verdict, motif = _verdict(duels, seuil, total)
    return {
        "paires": total, "repondues": repondues, "seuil": seuil,
        "voix": voix, "duels": duels,
        "verdict": verdict, "motif": motif,
        "accord": (accord / comparables) if comparables else None,
        "accord_n": comparables, "accord_oui": accord,
        "detail": detail,
    }


def _vainqueur_auto(paire: dict, scores: dict | None) -> str:
    """Laquelle des deux images le juge automatique classe le plus près de la référence.

    Rend `""` quand l'une des deux manque au tableau, ou quand les deux scores sont **égaux** :
    un ex æquo n'est pas un choix, et le compter comme un désaccord ferait baisser l'accord
    pour une raison qui n'est pas un désaccord."""
    if not scores:
        return ""
    a, b = scores.get(str(paire.get("gauche"))), scores.get(str(paire.get("droite")))
    if a is None or b is None or a == b:
        return ""
    return "gauche" if a > b else "droite"


def _verdict(duels: dict, seuil: int, total: int) -> tuple:
    """Le verdict contre le seuil fixé d'avance, ou l'aveu qu'il ne s'applique pas."""
    if not duels:
        return None, ("aucune paire répondue n'oppose deux configurations différentes — "
                      "le seuil du plan compare DEUX configurations, il ne s'applique pas ici")
    if len(duels) > 1:
        return None, (f"{len(duels)} oppositions de configurations différentes sur ces "
                      f"{total} paires : « {seuil} sur {total} » compare DEUX configurations, "
                      f"et n'en résume pas {len(duels)}. Les voix sont publiées duel par duel, "
                      f"sans verdict global")
    (duel, compte), = duels.items()
    gagnante = max(compte, key=lambda c: compte[c])
    voix = compte[gagnante]
    rendu = f"{voix:g} voix sur {sum(compte.values()):g} pour « {gagnante} » (seuil {seuil})"
    if voix >= seuil:
        return True, f"{rendu} — le seuil fixé AVANT la mesure est franchi"
    return False, (f"{rendu} — le seuil fixé AVANT la mesure n'est PAS franchi. "
                   f"Ce n'est pas un échec du protocole, c'est son résultat")
