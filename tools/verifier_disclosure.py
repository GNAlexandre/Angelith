# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fou de la disclosure IA — `CONTRIBUTING.md`, section « Commit convention ».

## Pourquoi ce garde-fou avant les autres

Ce n'est pas une préférence de style. Le dossier de financement du projet repose sur une
politique d'IA générative qui exige la traçabilité : les livrables purement générés par IA
ne sont pas éligibles au paiement, et le code généré doit voir ses prompts figurer dans les
messages de commit ou dans une documentation accessible. **Un historique de douze mois ne se
documente pas rétroactivement** — d'où l'urgence relative de celui-ci sur tous les autres.

## Le format attendu

    Assisté par : <outil> (<modèle>), <date ISO>
    Prompt : « … »
    Revu et testé manuellement : oui|non

Trois précautions, sans lesquelles le garde-fou devient un obstacle qu'on désarme :

1. **Un commit non assisté est légitime.** Une correction de coquille écrite à la main n'a
   pas de prompt. `Assisté par : aucun` est accepté — explicitement, plutôt qu'en laissant
   passer l'absence, qui ne distingue pas « écrit à la main » de « oublié ».
2. **`Revu et testé manuellement : non` PASSE le job et BLOQUE la fusion.** C'est une
   information honnête, pas une faute : `CONTRIBUTING.md` dit que les contributions que
   personne n'a lues ne sont pas acceptées, pas qu'il est interdit de le dire. Les deux
   verdicts sont donc rendus séparément (`conforme` / `fusionnable`), et deux drapeaux
   distincts (`--bloquant`, `--exiger-relecture`) décident lequel casse un job.
3. **Les commits de fusion et les commits de robots sont exemptés.** Un message de fusion est
   écrit par GitHub ; une montée de version proposée par Dependabot n'a ni prompt ni modèle.
   Exiger d'eux une disclosure reviendrait à demander la traçabilité d'un texte qui n'a
   produit aucun code — et, concrètement, à rendre rouge chaque PR de dépendance dès le jour
   où ce garde-fou devient bloquant. L'exemption est nommée ici plutôt que découverte là.

## La tolérance sur les accents, et pourquoi elle est écrite

`Assiste par` (sans accent) est accepté au même titre que `Assisté par`. Ce dépôt a déjà
mesuré qu'une console Windows en cp1252 fait tomber un caractère non-ASCII au passage
(cf. la note `configurer_stdout()` de `.github/workflows/ci.yml`, où le job échouait avant
d'avoir écrit un octet à cause d'une flèche « → »). Refuser un commit pour un accent perdu
serait refuser sur un défaut d'encodage, pas sur un défaut de traçabilité.

## Usage

    python tools/verifier_disclosure.py --base origin/main       # les commits d'une branche
    python tools/verifier_disclosure.py --historique 100         # le taux sur l'historique
    python tools/verifier_disclosure.py --base origin/main --markdown  # pour un résumé de job
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: `Assisté par :` ou `Assiste par :`, en tête de ligne. Le reste de la ligne est la valeur.
_ASSISTE = re.compile(r"^Assist[ée] par\s*:\s*(.*)$", re.MULTILINE)
_PROMPT = re.compile(r"^Prompt\s*:\s*(.*)$", re.MULTILINE)
_REVU = re.compile(r"^Revu et test[ée] manuellement\s*:\s*(.*)$", re.MULTILINE)

#: La valeur qui déclare un commit écrit à la main. Elle doit être ÉCRITE : l'absence de
#: ligne ne vaut pas déclaration, elle ne distingue pas « à la main » de « oublié ».
_AUCUN = re.compile(r"^aucun(e)?\b", re.IGNORECASE)

#: `<outil> (<modèle>), <date ISO>`. Le modèle entre parenthèses et la date sont exigés :
#: « Claude Code » seul ne permet ni de rejouer ni de dater une génération.
_OUTIL_MODELE_DATE = re.compile(r"^.+\(.+\)\s*,\s*(\d{4}-\d{2}-\d{2})\b")

#: `oui` ou `non` en tête de valeur. Le reste de la ligne est libre — une explication après
#: le verdict est utile ; ce qui ne l'est pas, c'est un verdict qu'on ne peut pas lire.
_OUI = re.compile(r"^oui\b", re.IGNORECASE)
_NON = re.compile(r"^non\b", re.IGNORECASE)

#: Séparateurs de `git log --format` : `\x1f` entre champs, `\x1e` entre commits. Choisis
#: parce qu'aucun message de commit ne les contient — contrairement à `\n\n`, qui sépare
#: aussi deux paragraphes d'un corps de commit et découperait un message en son milieu.
_CHAMP = "\x1f"
_ENREGISTREMENT = "\x1e"


@dataclass
class Verdict:
    """Le résultat pour UN commit. Deux booléens distincts, et c'est le point du fichier :
    un commit peut être parfaitement conforme ET ne pas devoir être fusionné."""
    sha: str
    sujet: str
    fusion: bool = False
    conforme: bool = True
    fusionnable: bool = True
    motifs: list[str] = field(default_factory=list)

    def refuser(self, motif: str) -> None:
        self.conforme = False
        self.motifs.append(motif)


def est_un_robot(auteur: str) -> bool:
    """GitHub nomme ses robots `dependabot[bot]`, `github-actions[bot]`… Le suffixe `[bot]`
    est la convention, et c'est aussi ce que l'API expose."""
    return auteur.strip().endswith("[bot]")


def analyser(sha: str, sujet: str, message: str, *, fusion: bool = False,
             auteur: str = "") -> Verdict:
    """Le cœur testable : aucun appel à git, aucun accès disque."""
    v = Verdict(sha=sha, sujet=sujet, fusion=fusion or est_un_robot(auteur))
    if v.fusion:
        v.motifs.append("commit de fusion" if fusion else f"commit de robot ({auteur})")
        v.motifs[-1] += " — aucun code généré par un modèle, exempté"
        return v

    m_assiste = _ASSISTE.search(message)
    if m_assiste is None:
        v.refuser("ligne « Assisté par : » absente — écrire « Assisté par : aucun » si le "
                  "commit est écrit à la main")
        # On rend le verdict ici plutôt que d'empiler trois motifs pour une seule cause :
        # sans cette ligne, on ne sait pas si un prompt DEVRAIT exister.
        return v

    valeur = m_assiste.group(1).strip()
    assiste_par_un_modele = not _AUCUN.match(valeur)

    if not valeur:
        v.refuser("« Assisté par : » sans valeur")
    elif assiste_par_un_modele and not _OUTIL_MODELE_DATE.match(valeur):
        v.refuser(f"« Assisté par : {valeur} » n'a pas la forme « <outil> (<modèle>), "
                  f"<date ISO> » — sans modèle ni date, la génération ne se rejoue pas")

    m_prompt = _PROMPT.search(message)
    if assiste_par_un_modele:
        if m_prompt is None:
            v.refuser("ligne « Prompt : » absente alors que le commit déclare une assistance")
        elif not m_prompt.group(1).strip():
            v.refuser("« Prompt : » sans contenu")
    elif m_prompt is not None and m_prompt.group(1).strip():
        # Contradictoire, mais pas bloquant : on le dit sans refuser.
        v.motifs.append("« Assisté par : aucun » mais un prompt est cité")

    m_revu = _REVU.search(message)
    if m_revu is None:
        v.refuser("ligne « Revu et testé manuellement : » absente")
    else:
        revu = m_revu.group(1).strip()
        if _OUI.match(revu):
            pass
        elif _NON.match(revu):
            v.fusionnable = False
            v.motifs.append("« Revu et testé manuellement : non » — déclaration honnête, et "
                            "la fusion attend une relecture humaine (CONTRIBUTING.md)")
        else:
            v.refuser(f"« Revu et testé manuellement : {revu} » ne commence ni par « oui » "
                      f"ni par « non » — un verdict qui ne se lit pas n'en est pas un")
    return v


# ---------------------------------------------------------------------------
# La couche git. Séparée du jugement, pour que celui-ci se teste sans dépôt.

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def commits(plage: list[str]) -> list[Verdict]:
    """Les verdicts sur `plage`, telle qu'on la passerait à `git log`."""
    format_ = f"%H{_CHAMP}%P{_CHAMP}%an{_CHAMP}%s{_CHAMP}%B{_ENREGISTREMENT}"
    brut = _git("log", f"--format={format_}", *plage)
    verdicts = []
    for bloc in brut.split(_ENREGISTREMENT):
        bloc = bloc.strip("\n")
        if not bloc:
            continue
        sha, parents, auteur, sujet, message = bloc.split(_CHAMP, 4)
        verdicts.append(analyser(sha[:8], sujet, message, auteur=auteur,
                                 fusion=len(parents.split()) > 1))
    return verdicts


def rendre(verdicts: list[Verdict], *, markdown: bool = False) -> str:
    juges = [v for v in verdicts if not v.fusion]
    conformes = [v for v in juges if v.conforme]
    bloquants = [v for v in juges if v.conforme and not v.fusionnable]
    exemptes = len(verdicts) - len(juges)  # fusions et robots
    taux = f"{len(conformes)}/{len(juges)}"
    pourcent = (100 * len(conformes) / len(juges)) if juges else 100.0

    lignes: list[str] = []
    if markdown:
        lignes += ["### Disclosure IA", "",
                   f"**{taux} commits conformes** ({pourcent:.0f} %), "
                   f"{exemptes} commit(s) exempté(s) (fusions, robots).", ""]
        if juges:
            lignes += ["| commit | sujet | verdict |", "|---|---|---|"]
            for v in juges:
                if not v.conforme:
                    etat = "❌ " + " ; ".join(v.motifs)
                elif not v.fusionnable:
                    etat = "⚠ conforme, fusion bloquée : non relu"
                else:
                    etat = "✅"
                lignes.append(f"| `{v.sha}` | {v.sujet.replace('|', '-')[:60]} | {etat} |")
    else:
        for v in juges:
            if v.conforme and v.fusionnable:
                continue
            lignes.append(f"{'REFUS' if not v.conforme else 'FUSION BLOQUEE'} "
                          f"{v.sha} {v.sujet}")
            lignes += [f"    · {m}" for m in v.motifs]
        lignes.append(f"\n{taux} commits conformes ({pourcent:.0f} %), "
                      f"{exemptes} commit(s) exempté(s) (fusions, robots).")
    if bloquants:
        lignes += ["", f"⚠ {len(bloquants)} commit(s) déclarent « Revu et testé "
                       f"manuellement : non ». Le job passe — la déclaration est honnête "
                       f"— mais la fusion attend une relecture humaine."]
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`, et ce n'est pas un oubli.** Ce fichier
    # n'importe QUE la bibliothèque standard, et le job « Garde-fous » le lance sur un Python
    # nu — `.github/workflows/garde-fous.yml` ne fait aucun `pip install`. Importer
    # `core.cli` tirerait `yaml` et casserait le job. D'où ces quatre lignes, répétées dans
    # les outils sans dépendance et tenues en phase par `tests/test_outils_sortie.py`.
    #
    # Sans elles, une console Windows en cp1252 fait tomber l'outil sur le premier « ⚠ » —
    # mesuré le 2026-09-04 : `verifier_disclosure.py --historique 3` levait un
    # `UnicodeEncodeError` APRÈS avoir jugé les commits, donc en perdant son verdict.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description="Garde-fou de la disclosure IA (CONTRIBUTING.md).")
    ap.add_argument("--base", default=None,
                    help="référence de base ; les commits jugés sont <base>..<tête>")
    ap.add_argument("--tete", default="HEAD")
    ap.add_argument("--historique", type=int, default=None,
                    help="juger les N derniers commits (MESURE du taux, pas un garde-fou)")
    ap.add_argument("--markdown", action="store_true", help="sortie pour $GITHUB_STEP_SUMMARY")
    ap.add_argument("--bloquant", action="store_true",
                    help="sortir en erreur sur non-conformité (défaut : rapporter, sortir 0)")
    ap.add_argument("--exiger-relecture", action="store_true",
                    help="sortir en erreur si un commit déclare « Revu … : non » — la garde "
                         "de FUSION, distincte de celle de conformité")
    a = ap.parse_args(argv)

    if a.historique is not None:
        plage = [f"-{a.historique}", a.tete]
    elif a.base:
        plage = [f"{a.base}..{a.tete}"]
    else:
        ap.error("--base ou --historique est requis")

    verdicts = commits(plage)
    print(rendre(verdicts, markdown=a.markdown))

    juges = [v for v in verdicts if not v.fusion]
    if a.bloquant and any(not v.conforme for v in juges):
        return 1
    if a.exiger_relecture and any(not v.fusionnable for v in juges):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
