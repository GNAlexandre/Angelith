#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La bible visuelle en ligne de commande — inventorier, proposer, relire, publier.

    python tools/bible.py "<Projet>" --inventaire         # L23.1, tableau des classes
    python tools/bible.py --tous --inventaire             # tout le corpus, par tome
    python tools/bible.py "<Projet>" --signature          # L23.7, la signature de style
    python tools/bible.py "<Projet>" --proposer           # L23.3 + L23.4 → propositions
    python tools/bible.py "<Projet>" --proposer --sans-images   # L23.4 seul, aucun appel vision
    python tools/bible.py "<Projet>" --revue              # relit et écrit bible.yaml
    python tools/bible.py "<Projet>" --revue --ecrire-genre     # + genre dans le glossaire
    python tools/bible.py --tous --rapport --markdown > docs/mesures/bible-visuelle-<date>.md

## Ce que cet outil est, et ce qu'il n'est pas

Il **lit** `build/` et `sources/`, et n'écrit que deux fichiers, tous deux sous
`sources/<Projet>/` : `bible.propositions.yaml` (la passe automatique) et `bible.yaml` (la
revue humaine). Il ne charge aucun modèle d'image, n'en installe aucun, ne touche à aucun
pixel d'une planche et n'entre dans aucun cache — `manga/checkpoints.py:STAGES` et
`.checkpoints/` ne le connaissent pas et n'ont pas à le connaître.

## Le seul geste qui change une SORTIE, et il est explicite

`--revue --ecrire-genre` écrit `genre` dans `glossaire.yaml`. Ce n'est **pas** un changement
de schéma — le champ existe et il est vide — mais c'est un **changement de sortie** : les
accords d'un tome relancé changeront, parce que `core/glossary.py` étiquette lui-même cette
catégorie « Personnages (le genre commande les accords) ». D'où l'option explicite, jamais un
défaut, et l'avertissement à l'écran avant la première écriture.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core import bible as bible_mod                          # noqa: E402
from core import bible_texte, glossary, illustrations         # noqa: E402
from core.cli import charger_config, configurer_stdout        # noqa: E402
from tools import _banc_commun as banc                        # noqa: E402

COLONNES_INVENTAIRE = ["tome", "fichiers", illustrations.COUVERTURE,
                       illustrations.PLEINE_PAGE, illustrations.DOUBLE_PAGE,
                       illustrations.VIGNETTE, illustrations.INDETERMINEE,
                       illustrations.ILLISIBLE, "exploitables", "en chapitre",
                       "tête de volume", "non référencées"]

COLONNES_SIGNATURE = ["tome", "échantillon", "couleur", "saturation", "contraste",
                      "densité trait", "part aplats", "palette"]

COLONNES_RAPPORT = ["projet", "personnages", "couverture de référence",
                    "couverture d'attributs", "genre avant", "genre après",
                    "illustrations exploitées", "abstentions LLM"]


# ────────────────────────────────  Découverte  ────────────────────────────────

def _projets(config: dict, demande: str | None, tous: bool) -> list[str]:
    racine = banc.racine_build(config)
    if demande:
        return [demande]
    if not tous or not racine.is_dir():
        return []
    return sorted(p.name for p in racine.iterdir() if p.is_dir())


def _tomes(config: dict, projet: str) -> list[Path]:
    racine = banc.racine_build(config) / projet
    if not racine.is_dir():
        return []
    return sorted(t for t in racine.iterdir() if t.is_dir() and (t / "media").is_dir())


def _dossier_projet(config: dict, projet: str) -> Path:
    return banc.racine_sources(config) / projet


def _personnages(config: dict, projet: str) -> list[dict]:
    chemin = _dossier_projet(config, projet) / "glossaire.yaml"
    return (glossary.load(chemin).get("personnages") or []) if chemin.is_file() else []


# ────────────────────────────────  L23.1 — inventaire  ────────────────────────────────

def _ligne_inventaire(tome: Path) -> dict:
    images = illustrations.inventaire_rattache(tome)
    compte = {c: sum(1 for i in images if i.classe == c) for c in illustrations.CLASSES}
    en_chapitre = sum(1 for i in images
                      if i.contexte and i.contexte not in (illustrations.TETE_DE_VOLUME,
                                                           illustrations.NON_REFERENCEE))
    return {
        "tome": f"{tome.parent.name} {tome.name}",
        "fichiers": len(images),
        **compte,
        "exploitables": sum(1 for i in images if illustrations.exploitable(i)),
        "en chapitre": en_chapitre,
        "tête de volume": sum(1 for i in images
                              if i.contexte == illustrations.TETE_DE_VOLUME),
        "non référencées": sum(1 for i in images
                               if i.contexte == illustrations.NON_REFERENCEE),
    }


def _inventaire(config: dict, args) -> int:
    lignes = [_ligne_inventaire(t)
              for projet in _projets(config, args.projet, args.tous)
              for t in _tomes(config, projet)]
    if not lignes:
        print("Aucun tome porteur d'un dossier media/.")
        return 1
    sommables = set(COLONNES_INVENTAIRE) - {"tome"}
    total = {"tome": f"**TOTAL ({len(lignes)} tome(s))**",
             **{c: sum(ligne.get(c, 0) for ligne in lignes) for c in sommables}}
    # ⚠ *Pride and Prejudice* Vol.1 pèse à lui seul 164 des 446 fichiers, soit 36,8 %. Une
    # moyenne calculée sur tous les tomes sans le dire est fausse : on publie donc TOUJOURS
    # les deux totaux, avec et sans.
    sans_pp = [ligne for ligne in lignes if not ligne["tome"].startswith("Pride and Prejudice")]
    lignes_finales = [*lignes, total]
    if len(sans_pp) != len(lignes):
        lignes_finales.append({"tome": f"**TOTAL sans Pride and Prejudice ({len(sans_pp)})**",
                               **{c: sum(ligne.get(c, 0) for ligne in sans_pp)
                                  for c in sommables}})
    print(banc.tableau_markdown(COLONNES_INVENTAIRE, lignes_finales))
    return 0


# ────────────────────────────────  L23.7 — signature  ────────────────────────────────

def _signature_du_tome(tome: Path) -> dict:
    return illustrations.signature(illustrations.inventaire_rattache(tome))


def _ligne_signature(tome: Path, sig: dict) -> dict:
    palette = ", ".join(f"{t['hex']} {t['part']:.0%}" for t in (sig.get("palette") or [])[:3])
    return {
        "tome": f"{tome.parent.name} {tome.name}",
        "échantillon": sig.get("echantillon"),
        "couleur": "oui" if sig.get("couleur") else "non",
        "saturation": sig.get("saturation_moyenne"),
        "contraste": sig.get("contraste"),
        "densité trait": sig.get("densite_trait"),
        "part aplats": sig.get("part_aplats"),
        "palette": palette or "—",
    }


def _signatures(config: dict, args) -> int:
    lignes: list[dict] = []
    ecarts: list[str] = []
    for projet in _projets(config, args.projet, args.tous):
        tomes = _tomes(config, projet)
        signatures = [(t, _signature_du_tome(t)) for t in tomes]
        lignes.extend(_ligne_signature(t, s) for t, s in signatures)
        mesurees = [(t, s) for t, s in signatures if s.get("echantillon")]
        # ⚠ L'écart entre deux tomes d'une même œuvre est le chiffre qui décide si une
        # signature « par œuvre » a un sens. S'ils sont très écartés, elle n'en a pas.
        for (ta, sa), (tb, sb) in zip(mesurees, mesurees[1:]):
            e = illustrations.ecart_signature(sa, sb)
            ecarts.append(f"- **{projet}** {ta.name} ↔ {tb.name} : "
                          + ", ".join(f"{d} {e[d]}" for d in illustrations.DESCRIPTEURS
                                      if e.get(d) is not None)
                          + f" — moyenne **{e['moyenne']}**, échantillons {e['echantillons']}"
                          + ("" if e["meme_regime_couleur"]
                             else ", ⚠ **régimes de couleur différents**"))
    if not lignes:
        print("Aucun tome mesurable.")
        return 1
    print(banc.tableau_markdown(COLONNES_SIGNATURE, lignes))
    if ecarts:
        print("\n### Écart de signature entre tomes consécutifs d'une même œuvre\n")
        print("\n".join(ecarts))
        print("\n> ⚠ Cet écart n'a pas encore d'échelle : il dit que deux tomes diffèrent, "
              "pas si c'est beaucoup. Poser l'échelle est l'étape 0.2 du `PLAN-25`.")
    return 0


# ────────────────────────────────  L23.3 + L23.4 — proposer  ────────────────────────────────

def _references_candidates(config: dict, projet: str) -> dict:
    """Les illustrations exploitables du projet, par tome, prêtes pour la passe vision."""
    sortie = {}
    for tome in _tomes(config, projet):
        sortie[tome] = [i for i in illustrations.inventaire_rattache(tome)
                        if illustrations.exploitable(i)]
    return sortie


def _proposer(config: dict, args) -> int:
    from core.bible_llm import (PromptAbsent, charger_prompt, compte_des_rejets, en_bible,
                                proposer_depuis_image, proposer_depuis_texte)
    from core.langues import resoudre_pack

    projet = args.projet
    personnages = _personnages(config, projet)
    if not personnages:
        print(f"❌ {projet} : aucun personnage dans le glossaire — rien à documenter.")
        return 1

    tomes = _tomes(config, projet)
    candidats = [c for t in tomes for c in bible_texte.candidats_du_tome(t, personnages)]
    mesure = bible_texte.denominateur(candidats, personnages)
    print(f"[lexique] {mesure['personnages_avec_candidat']}/{mesure['personnages']} "
          f"personnage(s) ont au moins un passage candidat — "
          f"{mesure['passages']} passage(s) : {mesure['par_attribut']}")

    try:
        systeme = charger_prompt(resoudre_pack(config))
    except PromptAbsent as erreur:
        print(f"❌ {erreur}")
        return 1

    llm, modele = _client(config, args)
    propositions = []
    rejets_totaux: dict[str, int] = {}
    if candidats:
        lots = [candidats[i:i + args.lot] for i in range(0, len(candidats), args.lot)]
        for numero, lot in enumerate(lots, 1):
            print(f"[texte] lot {numero}/{len(lots)} — {len(lot)} passage(s)…")
            trouvees, rejets = proposer_depuis_texte(llm, modele, systeme, personnages, lot)
            propositions.extend(trouvees)
            _cumuler(rejets_totaux, rejets)

    references: dict[str, list] = {}
    abstentions = appels = 0
    if not args.sans_images:
        for tome, images in _references_candidates(config, projet).items():
            for image in images:
                appels += 1
                print(f"[image] {tome.name} — {image.nom}")
                trouvees, rejets = proposer_depuis_image(
                    llm, modele, systeme, personnages, image.chemin,
                    f"{tome.name}/media/{image.nom}")
                _cumuler(rejets_totaux, rejets)
                if not trouvees or all(p.certitude == "indeterminee" for p in trouvees):
                    abstentions += 1
                propositions.extend(trouvees)
                for nom in {p.nom for p in trouvees}:
                    # ⚠ **La référence porte son TOME**, et ce n'est pas cosmétique. Elle
                    # s'écrivait `media/<nom>`, relative au tome, et `core/bible.py:
                    # reference_existe` la cherchait « sous n'importe quel tome du projet ».
                    # Sur une œuvre à un seul tome c'est équivalent ; sur roman N, dont les
                    # Vol.1 et Vol.2 portent tous deux un `image1`, c'était AMBIGU : le
                    # premier tome dans l'ordre gagnait, en silence, et le modèle d'image
                    # pouvait recevoir le personnage d'un autre volume.
                    references.setdefault(nom, []).append(
                        (f"{tome.name}/media/{image.nom}",
                         image.contexte or f"{tome.name}", image.classe))

    sortie = en_bible(propositions, references)
    sortie["mesure"] = {
        "date": date.today().isoformat(),
        "lexique": mesure,
        "appels_vision": appels,
        "abstentions_vision": abstentions,
        "rejets_du_code": rejets_totaux,
    }
    chemin = bible_mod.chemin_propositions(_dossier_projet(config, projet))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    chemin.write_text(
        "# Propositions AUTOMATIQUES — rien ici n'est vrai tant qu'un humain ne l'a pas lu.\n"
        "# `tools/bible.py \"<Projet>\" --revue` les fait entrer, une par une, dans bible.yaml.\n\n"
        + yaml.safe_dump(sortie, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")
    print(f"\n→ {chemin}")
    exemples = rejets_totaux.pop("exemples", [])
    print(f"   {len(propositions)} attribut(s) proposé(s), "
          f"{compte_des_rejets(rejets_totaux)} refusé(s) par le code : {rejets_totaux}")
    for exemple in exemples[:5]:
        print(f"     refusé — {exemple}")
    if appels:
        print(f"   vision : {abstentions}/{appels} abstention(s) — une abstention basse est "
              f"suspecte, pas rassurante.")
    return 0


def _cumuler(total: dict, ajout: dict) -> None:
    """Somme les compteurs et concatène les exemples. Les deux ne s'additionnent pas de la
    même façon, et confondre les deux ferait un total faux."""
    from core.bible_llm import EXEMPLES_MAX
    for cle, valeur in (ajout or {}).items():
        if isinstance(valeur, list):
            reste = total.setdefault(cle, [])
            reste.extend(valeur[:max(0, EXEMPLES_MAX - len(reste))])
        else:
            total[cle] = total.get(cle, 0) + valeur


def _client(config: dict, args):
    """Le client LLM et le modèle à employer. On réutilise le roster du light novel plutôt
    que d'inventer une clé de configuration : la bible n'est pas une étape de pipeline et
    n'a pas à faire grossir `config.yaml` d'un agent qui ne tourne jamais tout seul."""
    from core.agents import build_agents
    agents = build_agents(config)
    agent = agents.get(args.agent) or next((a for a in agents.values() if a), None)
    if agent is None:
        raise SystemExit("aucun agent configuré dans `modeles:` — impossible d'appeler un LLM.")
    return agent.llm, agent.modele


# ────────────────────────────────  L23.5 — revue  ────────────────────────────────

def _demander(question: str, choix: str = "o/n/?") -> str:
    """Une question fermée. `?` = passer, et c'est un choix légitime : une bible se remplit
    en plusieurs passes, et forcer une décision produirait des décisions au hasard."""
    while True:
        reponse = input(f"{question} [{choix}] ").strip().lower()
        if reponse in choix.split("/"):
            return reponse
        if reponse == "":
            return "?"


def _revue(config: dict, args) -> int:
    import yaml
    projet = args.projet
    dossier = _dossier_projet(config, projet)
    chemin_prop = bible_mod.chemin_propositions(dossier)
    if not chemin_prop.is_file():
        print(f"❌ {chemin_prop} n'existe pas — lance d'abord `--proposer`.")
        return 1
    propositions = bible_mod.fill_defaults(
        yaml.safe_load(chemin_prop.read_text(encoding="utf-8")) or {})
    courante = bible_mod.load(bible_mod.chemin(dossier))
    personnages = _personnages(config, projet)
    genres = {str(e.get("nom") or ""): str(e.get("genre") or "") for e in personnages}
    # ⚠ L'indice de genre est DÉTERMINISTE et mesuré : 26 confirmations sur 26 contre les
    # genres déjà déclarés du corpus (précision 100 %), pour un rappel de 24,8 %. Il ne décide
    # rien — il met la phrase sous l'œil de celui qui décide.
    indices = bible_texte.indices_de_genre(
        [t for tome in _tomes(config, projet) for t in bible_texte.textes_du_tome(tome)],
        personnages)

    acceptees = bible_mod.vide()
    a_ecrire_genre: dict[str, str] = {}
    entrees = [e for e in propositions["personnages"] if e["nom"]]
    classes = _classes_du_projet(config, projet)
    for ligne in _lignes_corpus(courante, classes, titre="AVANT cette revue"):
        print(ligne)
    print(f"\n{len(entrees)} personnage(s) à relire. « ? » ou Entrée = passer, "
          f"« O » = tout accepter pour ce personnage.\n")

    for numero, entree in enumerate(entrees, 1):
        deja = bible_mod.entree(courante, entree["nom"])
        if deja and deja.get("valide_par_humain") and not args.tout:
            continue
        print(f"── [{numero}/{len(entrees)}] {entree['nom']} "
              f"(genre au glossaire : « {genres.get(entree['nom'], '?') or '?'} »)")
        citations = {a: [c for c in entree["citations"] if c.get("attribut") == a]
                     for a in bible_mod.ATTRIBUTS}
        retenue = bible_mod.personnage(entree["nom"])
        tout = False
        for attribut in bible_mod.ATTRIBUTS:
            valeur = entree["apparence"][attribut]
            if not valeur or not citations[attribut]:
                continue
            source = citations[attribut][0]
            print(f"   {attribut:14} {valeur}")
            print(f"   {'':14} ↳ {source.get('source')} — « {source.get('texte', '')[:120]} »")
            reponse = "o" if tout else _demander("     retenir ?", "o/n/?/O")
            if reponse == "O":
                tout = True
                reponse = "o"
            if reponse != "o":
                continue
            retenue["apparence"][attribut] = valeur
            retenue["citations"].extend(citations[attribut])
        for reference in _references_a_relire(entree, args.role):
            couverture = str(reference.get("classe") or "") == illustrations.COUVERTURE
            print(f"   référence     {reference.get('fichier')} "
                  f"({reference.get('classe')}, {reference.get('contexte')})"
                  + ("  ⚠ COUVERTURE — mauvaise référence d'IDENTITÉ (titre peint dans les "
                     "pixels), bonne ancre de STYLE" if couverture else ""))
            if _demander("     retenir ?") != "o":
                continue
            gardee = {**reference, "confiance": "humaine"}
            if str(gardee.get("role") or "identite") == "identite":
                gardee = _recadrer(config, projet, gardee)
            retenue["references"].append(gardee)
        if any(retenue["apparence"][a] for a in bible_mod.ATTRIBUTS) or retenue["references"]:
            retenue["valide_par_humain"] = True
            acceptees["personnages"].append(retenue)
        # ⚠ Le gain qui justifie ce lot à lui seul : quand une illustration ou une citation
        # lève le genre, on le propose POUR LE GLOSSAIRE — le seul champ que le traducteur
        # lit déjà, et qui commande les accords français.
        if args.ecrire_genre and (genres.get(entree["nom"], "") in ("", "?")):
            indice = indices.get(entree["nom"])
            if indice is not None and (indice.feminin or indice.masculin):
                print(f"   indice de genre : féminin {indice.feminin} / masculin "
                      f"{indice.masculin}"
                      + (f" → propose « {indice.propose} »" if indice.propose else ""))
                for exemple in indice.exemples:
                    print(f"     {exemple}")
            choix = _demander(f"   → genre de {entree['nom']} ?", "f/m/?")
            if choix in ("f", "m"):
                a_ecrire_genre[entree["nom"]] = "féminin" if choix == "f" else "masculin"

    fusionnee = bible_mod.fusionner(courante, acceptees)
    print("")
    for ligne in _lignes_corpus(fusionnee, classes, titre="APRÈS cette revue"):
        print(ligne)
    fusionnee["style"] = _style_a_valider(config, projet, fusionnee["style"], args)
    chemin = bible_mod.chemin(dossier)
    retires = bible_mod.save(fusionnee, chemin)
    print(f"\n→ {chemin} — {len(acceptees['personnages'])} personnage(s) validé(s)")
    if retires:
        print(f"   ⚠ {len(retires)} attribut(s) retiré(s) faute de citation : {retires}")
    problemes = bible_mod.verifier_coherence(
        fusionnee, [str(e.get("nom") or "") for e in personnages],
        banc.racine_build(config) / projet)
    for p in problemes:
        print(f"   ⚠ {p}")
    if a_ecrire_genre:
        _ecrire_genre(config, projet, a_ecrire_genre)
    return 0


# ────────────────────  L29.1 — le rôle, le recadrage, et le compte  ────────────────────

def _corpus(config: dict, args) -> int:
    """`--corpus` — le tableau 0/1/2/≥3, sans rien relire ni rien écrire.

    ⚠ Il ne charge aucun modèle et n'appelle aucun LLM : il compte des champs d'un YAML et
    classe des images. C'est ce qui permet de le lancer **avant** de décider s'il vaut la
    peine d'ouvrir une session de revue."""
    projets = _projets(config, args.projet, args.tous)
    if not projets:
        print("❌ aucun projet — donne un nom, ou --tous.")
        return 1
    lignes: list[dict] = []
    for projet in projets:
        doc = bible_mod.load(bible_mod.chemin(_dossier_projet(config, projet)))
        if not doc.get("personnages"):
            print(f"— {projet} : aucune bible (`bible.yaml` absent ou vide)")
            continue
        classes = _classes_du_projet(config, projet)
        sans = bible_mod.couverture_identite(doc, sans_couverture=True, classes=classes)
        avec = bible_mod.couverture_identite(doc)
        lignes.append({
            "projet": projet,
            "personnages": len(doc["personnages"]),
            **{f"{t} (toutes)": avec["tranches"][t] for t in bible_mod.TRANCHES},
            **{f"{t} (hors couv.)": sans["tranches"][t] for t in bible_mod.TRANCHES},
            "cible du PLAN-29": "✅ atteinte" if sans["pret"] else f"⚠ {sans['manque']}",
        })
    if not lignes:
        return 1
    colonnes = (["projet", "personnages"]
                + [f"{t} (toutes)" for t in bible_mod.TRANCHES]
                + [f"{t} (hors couv.)" for t in bible_mod.TRANCHES]
                + ["cible du PLAN-29"])
    if args.markdown:
        print("\n".join(banc.entete_publication(
            args.config, [], titre="Corpus d'identité — PLAN-29 L29.1",
            commande="python " + " ".join(["tools/bible.py", *sys.argv[1:]]))))
    print(banc.tableau_markdown(colonnes, lignes))
    print("")
    print("⚠ Deux comptes, et l'écart entre eux EST le sujet du lot 29 : une couverture "
          "porte le titre de l'œuvre en grandes lettres, ce qui en fait une excellente "
          "ancre de STYLE et une mauvaise référence d'IDENTITÉ.")
    return 0


def _references_a_relire(entree: dict, role: str) -> list[dict]:
    """Les références proposées d'un personnage, dans l'ordre où la revue doit les voir.

    ⚠ **Les couvertures passent en DERNIER**, et c'est la règle que le lot 26 applique déjà à
    `illustration/identite.py:retenir` — appliquée ici aussi, parce qu'une règle qui ne vaut
    qu'au moment de générer arrive trop tard : c'est à la revue que le corpus se constitue.
    Une couverture est une excellente ancre de STYLE et une mauvaise référence d'IDENTITÉ
    (elle porte le titre de l'œuvre en grandes lettres, et ces pixels partent dans le
    conditionnement).

    `role` filtre : `identite` ne montre que ce qui peut porter une identité, `style` que le
    reste. ⚠ Une couverture n'est jamais **cachée** en rôle `identite`, seulement repoussée :
    un personnage dont la couverture est la seule référence n'a pas d'autre choix, et le lot
    25 l'a constaté sur le corpus réel."""
    references = [r for r in (entree.get("references") or []) if isinstance(r, dict)]
    if role:
        references = [r for r in references
                      if str(r.get("role") or "identite") == role]
    return sorted(references,
                  key=lambda r: str(r.get("classe") or "") == illustrations.COUVERTURE)


def _classes_du_projet(config: dict, projet: str) -> dict:
    """`{nom de fichier: classe}` pour tous les tomes du projet.

    ⚠ Sans mesure de couleur : le classement n'en a plus besoin depuis que le lot 23 a retiré
    le critère des « moins de 3 couleurs dominantes », et relire les pixels de tout un projet
    pour compter des références coûterait cent fois le prix du résultat."""
    table: dict = {}
    for tome in _tomes(config, projet):
        for illus in illustrations.inventaire_rattache(tome, avec_couleurs=False):
            table[illus.nom] = illus.classe
    return table


def _lignes_corpus(bible_doc: dict, classes: dict, *, titre: str = "") -> list[str]:
    """Le tableau 0 / 1 / 2 / ≥3 du `PLAN-29` L29.1, **affiché à chaque revue**.

    ⚠ Deux comptes, pas un, et l'écart entre les deux est le sujet du lot : celui de gauche
    prend toutes les références d'identité validées, celui de droite en retire les
    couvertures. Le lot 25 a étalonné son juge sur un corpus dont les trois premières
    références étaient trois couvertures, dont deux le même dessin ; publier le seul compte
    de gauche aurait dit « corpus prêt » ce jour-là."""
    avec = bible_mod.couverture_identite(bible_doc)
    sans = bible_mod.couverture_identite(bible_doc, sans_couverture=True, classes=classes)
    tete = f"── Corpus d'identité — {titre}" if titre else "── Corpus d'identité"
    lignes = [tete, "   références validées par personnage :"]
    for etiquette, mesure in (("toutes", avec), ("hors couverture", sans)):
        tranches = " · ".join(f"{t} → {mesure['tranches'][t]}" for t in bible_mod.TRANCHES)
        lignes.append(f"     {etiquette:16} {tranches}")
    lignes.append(f"   cible du PLAN-29 : {bible_mod.CIBLE_PERSONNAGES} personnages, dont "
                  f"{bible_mod.CIBLE_AVEC_TROIS} à {bible_mod.CIBLE_REFERENCES} références "
                  f"ou plus, aucune couverture parmi elles")
    lignes.append(f"   → {'✅ ' if sans['pret'] else '⚠ il manque '}{sans['manque']}")
    return lignes


def _recadrer(config: dict, projet: str, reference: dict) -> dict:
    """Propose un rectangle pour une référence d'identité, et laisse l'humain le corriger.

    ⚠ **Le rectangle est PROPOSÉ, jamais retenu tel quel sans un geste.** Il vient de
    `core/illustrations.py:cadre_propose`, qui mesure où est l'encre et applique une
    hypothèse — « le haut de l'encre est la tête » — vraie d'une figure debout et fausse
    d'une figure couchée. Le motif la dit à l'écran, en toutes lettres, parce qu'on ne
    corrige bien que ce dont on connaît la construction.

    ⚠ **Aucune détection de visage, aucun OpenCV** (interdit n° 4, et le `PLAN-29` L29.1 le
    redit). Aucun pixel n'est écrit ici : quatre fractions entrent dans `bible.yaml`, et
    c'est `illustration/identite.py:preparer` qui recadrera, plus tard, ailleurs."""
    fichier = str(reference.get("fichier") or "")
    chemins = bible_mod.chemins_de_reference(fichier, banc.racine_build(config) / projet)
    if not chemins:
        print("     (image introuvable sur le disque — pas de cadre proposé)")
        return reference
    cadrage = _demander("     cadrage ?", "/".join((*illustrations.CADRAGES_PROPOSES, "n")))
    # ⚠ `_demander` rend « ? » sur une entrée vide, y compris quand « ? » n'est pas dans les
    # choix : Entrée vaut donc « passer », et **tout ce qui n'est pas un cadrage connu passe
    # aussi**. Sans ce filtre, une touche Entrée envoyait « ? » à `cadre_propose`, qui lève.
    if cadrage not in illustrations.CADRAGES_PROPOSES:
        return reference
    propose = illustrations.cadre_propose(chemins[0], cadrage)
    if not propose:
        print("     (image non mesurable — pas de cadre proposé)")
        return reference
    x, y, largeur, hauteur = propose["cadre"]
    print(f"     cadre proposé [x={x} y={y} l={largeur} h={hauteur}] — "
          f"{propose['part_de_la_page']:.0%} de la page")
    print(f"     ↳ {propose['motif']}")
    saisie = input("     garde-le (Entrée), corrige-le (x y l h en fractions), "
                   "ou « n » pour la page entière : ").strip()
    if saisie.lower() == "n":
        return reference
    if saisie:
        morceaux = saisie.replace(",", " ").split()
        if len(morceaux) != 4 or not bible_mod.cadre_valide(morceaux):
            print("     ⚠ quatre fractions attendues dans [0, 1] — cadre proposé conservé")
        else:
            propose["cadre"] = [round(float(v), 4) for v in morceaux]
    return {**reference, "cadre": propose["cadre"]}


def _style_a_valider(config: dict, projet: str, style: dict, args) -> dict:
    """Mesure la signature du premier tome et propose ses ancrages, à valider à la main.

    ⚠ Les ancrages sont **proposés** par le déterministe (les plus proches du centre de la
    distribution) et **confirmés** par l'humain. Une couverture avec un logo d'éditeur et un
    bandeau de prix est une mauvaise ancre, et aucun descripteur ne le sait."""
    tomes = _tomes(config, projet)
    if not tomes:
        return style
    images = illustrations.inventaire_rattache(tomes[0])
    style["signature"] = illustrations.signature(images)
    connus = {a.get("fichier") for a in style["ancrages"]}
    propositions = [a for a in illustrations.ancrages_proposes(images, args.ancrages)
                    if a["fichier"] not in connus]
    if propositions:
        print(f"\n── Ancrages de style proposés pour {tomes[0].name} "
              f"(signature sur {style['signature']['echantillon']} image(s))")
        print("   ⚠ préfère une ancre SANS visage : une ancre qui montre un personnage "
              "contamine l'identité de l'image générée.")
    for ancrage in propositions:
        print(f"   {ancrage['fichier']} — {ancrage['classe']} — {ancrage['motif']}")
        if _demander("     retenir comme ancre ?") == "o":
            style["ancrages"].append({**ancrage, "valide_par_humain": True})
    return style


def _ecrire_genre(config: dict, projet: str, genres: dict[str, str]) -> None:
    """Écrit `genre` dans `glossaire.yaml`. **Le seul geste de cet outil qui change une
    sortie de traduction.**

    ⚠ Ce n'est pas un changement de schéma — le champ existe et il est vide sur 144 des 326
    personnages du corpus (mesuré le 2026-08-29). C'est un changement de SORTIE : les accords
    d'un tome relancé changeront. `glossary.save` préserve les rendus des autres langues et
    fusionne sans écrasement ; on ne touche donc qu'au champ demandé."""
    chemin = _dossier_projet(config, projet) / "glossaire.yaml"
    print(f"\n⚠ {len(genres)} genre(s) à écrire dans {chemin}.")
    print("  Ce champ commande les accords français : les tomes relancés changeront de "
          "sortie.")
    for nom, genre in sorted(genres.items()):
        print(f"    {nom} → {genre}")
    if _demander("  écrire ?") != "o":
        print("  → rien écrit.")
        return
    contenu = glossary.load(chemin)
    touches = 0
    for entree in contenu.get("personnages") or []:
        nouveau = genres.get(str(entree.get("nom") or ""))
        if nouveau and str(entree.get("genre") or "") in ("", "?"):
            entree["genre"] = nouveau
            touches += 1
    glossary.save(contenu, chemin)
    print(f"  → {touches} genre(s) écrit(s) dans {chemin}.")


# ────────────────────────────────  L23.6 — le banc  ────────────────────────────────

def _ligne_rapport(config: dict, projet: str) -> dict:
    import yaml
    dossier = _dossier_projet(config, projet)
    personnages = _personnages(config, projet)
    total = len(personnages)
    bible = bible_mod.load(bible_mod.chemin(dossier))
    entrees = bible.get("personnages") or []

    avec_reference = sum(1 for e in entrees
                         if any(r.get("confiance") == "humaine"
                                for r in e.get("references") or []))
    avec_attributs = sum(1 for e in entrees
                         if sum(1 for a in bible_mod.ATTRIBUTS
                                if e["apparence"].get(a)) >= 3)
    sans_genre = sum(1 for e in personnages
                     if str(e.get("genre") or "").strip() in ("", "?"))
    resolus = sum(1 for e in entrees if e.get("genre_confirme"))

    images = [i for t in _tomes(config, projet)
              for i in illustrations.inventaire_rattache(t)]
    exploitables = sum(1 for i in images if illustrations.exploitable(i))

    abstentions = "—"
    chemin_prop = bible_mod.chemin_propositions(dossier)
    if chemin_prop.is_file():
        mesure = ((yaml.safe_load(chemin_prop.read_text(encoding="utf-8")) or {})
                  .get("mesure") or {})
        appels = mesure.get("appels_vision") or 0
        if appels:
            abstentions = f"{mesure.get('abstentions_vision', 0)}/{appels}"

    return {
        "projet": projet,
        "personnages": total,
        "couverture de référence": f"{avec_reference}/{total}" if total else "—",
        "couverture d'attributs": f"{avec_attributs}/{total}" if total else "—",
        "genre avant": f"{total - sans_genre}/{total}" if total else "—",
        "genre après": f"{total - sans_genre + resolus}/{total}" if total else "—",
        "illustrations exploitées": f"{exploitables}/{len(images)}" if images else "—",
        "abstentions LLM": abstentions,
    }


def _rapport(config: dict, args) -> int:
    projets = _projets(config, args.projet, args.tous)
    if not projets:
        print("Aucun projet.")
        return 1
    lignes = [_ligne_rapport(config, p) for p in projets]
    tableau = banc.tableau_markdown(COLONNES_RAPPORT, lignes)
    if not args.markdown:
        print(tableau)
        return 0
    volumes = [banc.Volume(projet=p, tome=t.name, build_dir=t)
               for p in projets for t in _tomes(config, p)]
    entete = banc.entete_publication(
        args.config, volumes, titre="Banc de la bible visuelle",
        commande="python tools/bible.py --tous --rapport --markdown")
    print("\n".join([*entete, tableau, ""]))
    return 0


# ────────────────────────────────  Entrée  ────────────────────────────────

def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="La bible visuelle : inventorier, proposer, relire, publier.")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("--tous", action="store_true", help="tous les projets de build/")
    ap.add_argument("--inventaire", action="store_true",
                    help="L23.1 — classes d'illustrations par tome")
    ap.add_argument("--signature", action="store_true",
                    help="L23.7 — signature de style par tome, et écart entre tomes")
    ap.add_argument("--proposer", action="store_true",
                    help="L23.3 + L23.4 — écrit bible.propositions.yaml")
    ap.add_argument("--revue", action="store_true",
                    help="L23.5 — passe les propositions en revue et écrit bible.yaml")
    ap.add_argument("--rapport", action="store_true", help="L23.6 — le banc de la bible")
    ap.add_argument("--corpus", action="store_true",
                    help="L29.1 — le tableau 0/1/2/≥3 des références d'identité, "
                         "avec et sans les couvertures")
    ap.add_argument("--role", default="", choices=("", *bible_mod.ROLES_REFERENCE),
                    help="--revue : ne relit que les références de ce rôle. `identite` "
                         "repousse les couvertures en dernier sans les cacher")
    ap.add_argument("--markdown", action="store_true",
                    help="tableau précédé de son en-tête de publication (date, commit, config)")
    ap.add_argument("--sans-images", action="store_true",
                    help="--proposer sans la passe vision (L23.4 seul, aucun appel image)")
    ap.add_argument("--ecrire-genre", action="store_true",
                    help="⚠ --revue peut écrire `genre` dans glossaire.yaml. CHANGE LA "
                         "SORTIE d'un tome relancé. Jamais actif par défaut.")
    ap.add_argument("--tout", action="store_true",
                    help="--revue repasse aussi les personnages déjà validés")
    ap.add_argument("--lot", type=int, default=25,
                    help="passages par appel LLM en passe texte (défaut : 25)")
    ap.add_argument("--ancrages", type=int, default=3,
                    help="ancrages de style proposés à la revue (défaut : 3, plage 2 à 5)")
    # ⚠ `mise_en_page` et non `terminologue` : c'est le seul agent du roster livré avec le
    # raisonnement COUPÉ. Mesuré le 2026-08-29 sur roman D — avec `terminologue`, 8 des
    # 10 lots de la passe texte sortent « génération coupée net au plafond max_tokens », le
    # budget entier étant parti dans le <think>. Relever un attribut n'est pas un problème de
    # raisonnement : c'est une lecture.
    ap.add_argument("--agent", default="mise_en_page",
                    help="agent de `modeles:` dont le modèle et le client servent aux passes "
                         "(défaut : mise_en_page, le seul sans raisonnement)")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    modes = [args.inventaire, args.signature, args.proposer, args.revue, args.rapport,
             args.corpus]
    if sum(bool(m) for m in modes) != 1:
        ap.error("choisis exactement un mode : --inventaire, --signature, --proposer, "
                 "--revue, --rapport ou --corpus.")
    if (args.proposer or args.revue) and not args.projet:
        ap.error("--proposer et --revue portent sur UN projet : donne son nom.")
    if not (args.projet or args.tous):
        ap.error("donne un nom de projet, ou --tous.")

    config = charger_config(args.config)
    if args.inventaire:
        return _inventaire(config, args)
    if args.signature:
        return _signatures(config, args)
    if args.proposer:
        return _proposer(config, args)
    if args.revue:
        return _revue(config, args)
    if args.corpus:
        return _corpus(config, args)
    return _rapport(config, args)


if __name__ == "__main__":
    raise SystemExit(main())
