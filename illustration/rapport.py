# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le rapport et le journal de la brique — **dans son dossier, pas dans ceux du tome**.

Le `PLAN-24` L24.6 demandait une section « Illustrations générées » dans le `RAPPORT.md` du
tome et des lignes dans son `perf.log`. Son critère 1 bis interdit d'ouvrir en écriture un
fichier préexistant, et le run complet doit laisser **toutes** les empreintes SHA-256
préexistantes inchangées. Les deux demandes ne tiennent pas ensemble ; c'est la frontière qui
gagne, parce qu'elle est la raison d'être du lot.

Donc : `build/<Projet>/<Tome>/illustrations/RAPPORT.md` et `.../perf.log`. Le contenu est
celui que le plan demande — combien d'images, avec quel modèle, quelle graine, et le rappel
qu'elles ne font pas partie de l'œuvre — au fichier près.

## La règle des chiffres s'applique ici comme ailleurs

Chaque nombre publié porte son dénominateur. « 12 s par image » ne veut rien dire sans « sur
n images » ; « bascule 4 s » ne veut rien dire sans le prix d'une image en face. C'est
exactement ce que `verdict_bascule` calcule, et le seuil de huit images vient du plan : si la
bascule coûte plus que huit images, c'est la bascule qu'il faut optimiser, pas le modèle.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.version import __version__

#: Au-delà de ce nombre d'images-équivalent, la bascule de modèle est le vrai coût du run.
#: Vient du `PLAN-24` L24.1 bis, point 2.
SEUIL_BASCULE_IMAGES = 8

_ENTETE = """\
# Illustrations générées — {oeuvre}

> **Ces images ne font pas partie de l'œuvre.** Elles ont été produites par un modèle
> génératif, à la demande, après validation humaine du prompt. Chacune porte son marquage
> dans le PNG (`AIGenerated=true`) et un manifeste `.provenance.json` à côté. Les supprimer
> ne casse rien : aucun autre fichier n'en dépend.

Écrit par Angelith {version} le {date}.
"""


def ecrire(recap: dict, destination) -> Path:
    """`RAPPORT.md` de la brique. Rend le chemin écrit."""
    destination = Path(destination)
    cible = destination / "RAPPORT.md"
    images = recap.get("images") or []
    # ⚠ L'identifiant LOCAL, jamais le titre — ce rapport vit dans le dossier qu'on partage
    # avec les images, et une image partagée par erreur emporterait son voisinage. C'est le
    # même arbitrage que pour les métadonnées du PNG. `requete.yaml`, lui, nomme le projet :
    # c'est un document de TRAVAIL, il porte la commande à retaper, et il ne se partage pas.
    lignes = [_ENTETE.format(oeuvre=recap.get("identifiant") or "(œuvre non identifiée)",
                             version=__version__,
                             date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))]
    lignes.append("\n## Ce qui a été produit\n")
    lignes.append(f"- **{len(images)} image(s)**")
    lignes.append(f"- modèle : `{recap.get('modele') or '(non renseigné)'}`")
    lignes.append(f"- moteur : `{recap.get('moteur') or '?'}`")
    lignes.append(f"- identifiant local de l'œuvre : `{recap.get('identifiant') or ''}` "
                  f"— le titre n'apparaît nulle part, ni ici ni dans les métadonnées")
    validation = recap.get("validation") or {}
    lignes.append(f"- prompt validé par : **{validation.get('par') or '(inconnu)'}**"
                  + (f" le {validation['date']}" if validation.get("date") else ""))
    empreintes = recap.get("empreintes") or {}
    lignes.append(f"- empreinte `config.yaml` : `{empreintes.get('config') or '(absente)'}`")
    lignes.append(f"- empreinte des poids : `{empreintes.get('poids') or '(absente)'}`")

    lignes.append("\n## Le détail, image par image\n")
    lignes.append("| Image | Graine | Secondes | Empreinte de requête |")
    lignes.append("|---|---:|---:|---|")
    for entree in images:
        lignes.append(f"| `{Path(entree['image']).name}` | {entree.get('graine', 0)} | "
                      f"{float(entree.get('secondes') or 0):.1f} | "
                      f"`{str(entree.get('empreinte_requete') or '')[:16]}…` |")

    lignes += _section_provenance(recap)
    lignes += _section_identite(recap)

    lignes += _section_arret(recap)

    lignes.append("\n## Le coût de la bascule de modèle\n")
    lignes.append(verdict_phases(recap))
    lignes.append("")
    lignes.append(verdict_bascule(recap))
    lignes += _section_vram(recap)
    lignes.append("\n## Ce que ce rapport ne dit pas\n")
    lignes.append(
        _phrase_identite(recap) + "\n"
        "- il ne dit rien du **pic de VRAM** quand le moteur ne le rapporte pas — une "
        "colonne vide vaut mieux qu'un chiffre inventé ;\n"
        "- il ne dit rien de la **reproductibilité** : elle se vérifie par "
        "`run_illustration.py --rejouer`, et son résultat s'écrit dans un document de "
        "mesure, pas ici.")
    for plafond in (recap.get("plafonds_atteints") or []):
        # ⚠ Un plafond qui mord SANS LE DIRE ferait croire à un corpus plus petit qu'il n'est.
        lignes.append(f"\n⚠ **{plafond}**")
    cible.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return cible


def _section_arret(recap: dict) -> list[str]:
    """**L27.2** — un run arrêté à la demande le DIT, en tête, et dit ce qui a été gardé.

    ⚠ Un rapport qui ne distingue pas « huit images demandées, huit produites » de « huit
    demandées, deux produites, arrêt à la demande » laisserait croire à un échec silencieux
    du moteur. Le motif d'arrêt est nommé, comme tous les plafonds de ce dépôt."""
    arret = str(recap.get("arret") or "")
    if not arret:
        return []
    return ["\n## ⚠ Ce run a été ARRÊTÉ avant la fin\n",
            arret,
            "\nL'arrêt a lieu **entre deux images**, jamais au milieu de l'une : un modèle "
            "interrompu en plein pas de débruitage laisse le pilote dans l'état que "
            "`docs/README.fr.md` a mesuré — 25 à 18 tok/s sur la traduction suivante. Les "
            "images ci-dessus sont écrites, marquées et complètes ; relancer la phase image "
            "reprendra la requête telle quelle."]


def _section_vram(recap: dict) -> list[str]:
    """**L27.2** — ce que la bascule a réellement fait en se fermant, et ce qu'elle n'a pas
    fait.

    ⚠ « Le LLM n'est pas rechargé parce que le moteur d'image tient encore la carte » est une
    information, pas un silence : sans elle, un utilisateur qui enchaîne une traduction ne
    comprend pas pourquoi elle paie un chargement."""
    vram = recap.get("vram") or {}
    journal = vram.get("journal") or []
    if not journal:
        return []
    lignes = ["\n### La carte, en fin de run\n"]
    lignes += [f"- {message}" for _cle, message in journal]
    return lignes


def _section_provenance(recap: dict) -> list[str]:
    """**L26.5** — d'où vient ce visage ? La réponse, sans ouvrir un `.json`.

    Le `PLAN-26` L26.5 le demande mot pour mot : « un lecteur doit pouvoir répondre à *d'où
    vient ce visage ?* sans ouvrir un `.json` ». C'est la même exigence que la bible visuelle,
    dont chaque attribut porte sa citation — un attribut dont on ne peut pas remonter la
    source n'est pas une observation, c'est une affirmation.

    ⚠ La colonne **origine** compte autant que la colonne source : `bible` et `glossaire` ne
    se valent pas. Le genre pris au glossaire est établi sur le TEXTE, pas sur un dessin ;
    dire lequel des deux a parlé est ce qui permet de contester le résultat."""
    blocs = recap.get("blocs") or {}
    images = recap.get("images") or []
    if not blocs or not images:
        return []
    lignes = ["\n## D'où vient ce visage (lot 26)\n",
              "| Image | Personnage | Cadrage | Attribut | Valeur | Source | Origine |",
              "|---|---|---|---|---|---|---|"]
    vides = 0
    for entree in images:
        bloc = blocs.get(entree.get("origine") or entree["nom"]) or {}
        sources = bloc.get("attributs_sources") or []
        if not sources:
            vides += 1
            continue
        nom = Path(entree["image"]).name
        for i, attribut in enumerate(sources):
            lignes.append(
                f"| {'`' + nom + '`' if i == 0 else ''} "
                f"| {bloc.get('personnage', '') if i == 0 else ''} "
                f"| {bloc.get('cadrage', '') if i == 0 else ''} "
                f"| `{attribut.get('attribut', '')}` | {attribut.get('valeur', '')} "
                f"| `{attribut.get('source') or '(non citée)'}` "
                f"| {attribut.get('origine', 'bible')} |")
    if vides:
        lignes.append(f"\n⚠ **{vides} image(s) sans traçabilité d'attribut** : leur bloc de "
                      f"requête ne porte pas `attributs_sources`. C'est le cas d'un "
                      f"`requete.yaml` écrit avant le lot 26 — le champ n'existait pas, et "
                      f"personne ne peut le reconstituer après coup.")
    lignes += _section_images_choisies(recap)
    return lignes


def _section_images_choisies(recap: dict) -> list[str]:
    """Les images de référence, retenues **et écartées**, avec leur motif.

    ⚠ Montrer les écartées est le point : « un utilisateur qui retire une image doit voir
    pourquoi elle avait été prise » (`PLAN-26` L26.0, règle 3). Un rapport qui ne montrerait
    que les retenues laisserait croire qu'il n'y avait pas d'autre choix."""
    blocs = recap.get("blocs") or {}
    lignes: list[str] = []
    for nom, bloc in blocs.items():
        choisies = list(bloc.get("references") or []) + list(bloc.get("ancrages_style") or [])
        if not choisies:
            continue
        if not lignes:
            lignes = ["\n### Les images montrées au modèle, et celles qui ne l'ont pas été\n",
                      "| Bloc | Image | Usage | Retenue | Décidée par | Motif |",
                      "|---|---|---|---|---|---|"]
        ancres = {c["fichier"] for c in (bloc.get("ancrages_style") or [])}
        for i, choix in enumerate(choisies):
            usage = "style" if choix["fichier"] in ancres else "identité"
            lignes.append(
                f"| {'`' + nom + '`' if i == 0 else ''} | `{Path(choix['fichier']).name}` "
                f"| {usage} | {'oui' if choix.get('retenue') else 'non'} "
                f"| {choix.get('par', 'deterministe')} | {choix.get('motif', '')} |")
    return lignes


def verdict_phases(recap: dict) -> str:
    """**L26 critère 1 quater** — le temps de la phase 1 face à celui de la phase 2.

    ⚠ Le plan le demande explicitement : « si elle dure plus longtemps que la phase 2, c'est
    un fait à publier, pas un détail ». Une phase 1 qui coûterait plus cher que la génération
    déplacerait le problème sans que personne le voie, puisque seule la phase 2 charge un
    modèle d'image et qu'on la regarde donc davantage."""
    phase1 = float(recap.get("phase1_secondes") or 0.0)
    images = recap.get("images") or []
    phase2 = sum(float(e.get("secondes") or 0.0) for e in images)
    appels = int(recap.get("phase1_appels_llm") or 0)
    if not phase1 and not phase2:
        return ""
    detail = (f"Phase 1 (choix des images et rédaction du prompt) : **{phase1:.1f} s**, "
              f"{appels} appel(s) au modèle de vision.\n"
              f"Phase 2 (génération) : **{phase2:.1f} s** sur {len(images)} image(s).")
    if phase2 <= 0:
        return detail
    part = 100.0 * phase1 / (phase1 + phase2)
    if phase1 > phase2:
        return (f"{detail}\n\n⚠ **La phase 1 a coûté plus cher que la phase 2** "
                f"({part:.0f} % du run). C'est un fait publié, pas un détail : le plan "
                f"demande de le dire. Le levier est le nombre d'appels de vision, pas le "
                f"modèle d'image.")
    return f"{detail}\n\nLa phase 1 pèse **{part:.1f} %** du temps total du run."


def _phrase_identite(recap: dict) -> str:
    """Ce que le rapport dit de la ressemblance — et il en dit deux choses opposées selon que
    la voie A est armée ou non. La phrase du lot 24 (« il ne dit RIEN de la ressemblance »)
    resterait fausse une fois le lot 25 armé, et une phrase fausse dans un rapport est pire
    qu'une absence de phrase."""
    if not recap.get("identite_active"):
        return ("- il ne dit **rien** de la ressemblance des personnages : la voie A du "
                "`PLAN-25` est désarmée (`illustration.identite.actif: false`), donc aucune "
                "grandeur d'identité n'a été mesurée ;")
    return ("- les grandeurs d'identité sont mesurées, mais leur **plancher est propre à ce "
            "corpus** : un cosinus n'a de sens que rapporté à l'étalonnage publié dans "
            "`docs/mesures/`, et le sidecar de chaque image porte les deux ;")


def _section_identite(recap: dict) -> list[str]:
    """La section « ressemblance, nouveauté, style » — **les trois grandeurs côte à côte**.

    ⚠ Elles ne sont jamais moyennées entre elles : « une configuration qui gagne en
    ressemblance et perd en style est un fait à montrer, pas à moyenner » (`PLAN-25`
    critère 4 ter)."""
    if not recap.get("identite_active"):
        return []
    images = recap.get("images") or []
    lignes = ["\n## Identité, nouveauté, style (lot 25)\n",
              "| Image | Réf. | Ressemblance | Nouveauté | Style (embed.) | "
              "Style (descr.) | Descripteur qui décroche | Marques |",
              "|---|---:|---:|---:|---:|---:|---|---|"]
    for entree in images:
        g = entree.get("grandeurs") or {}
        marques = ", ".join(f"{c}: {v}" for c, v in (entree.get("marques") or {}).items())
        lignes.append(
            f"| `{Path(entree['image']).name}` | {g.get('references', 0)} | "
            f"{_nombre(g.get('ressemblance'))} | {_nombre(g.get('nouveaute'))} | "
            f"{_nombre(g.get('style_embedding'))} | {_nombre(g.get('style_descripteurs'))} | "
            f"{(g.get('descripteur_decroche') or ['—'])[0] or '—'} | {marques or '—'} |")

    refus = recap.get("refus") or []
    if refus:
        lignes.append(f"\n**{len(refus)} personnage(s) REFUSÉ(S)** avant toute génération — "
                      f"aucune référence validée par un humain. C'est le critère 5 du "
                      f"`PLAN-25`, et il n'a pas de nuance :")
        for entree in refus:
            lignes.append(f"- « {entree['personnage']} » ;")

    rejetees = recap.get("rejetees") or []
    lignes.append(f"\n**{len(rejetees)} image(s) rejetée(s)** — produites puis non écrites, et "
                  f"le motif est nommé. Le rejet de nouveauté n'est pas négociable "
                  f"(`PLAN-25` L25.2).")
    for rejet in rejetees:
        lignes.append(f"- `{rejet['nom']}` : {' · '.join(rejet['motifs'])} ;")
    motifs = recap.get("motifs") or {}
    if motifs:
        lignes.append("\nMotifs, nommés et comptés :\n")
        lignes += [f"- `{motif}` × {n} ;" for motif, n in motifs.items()]
    if any((e.get("grandeurs") or {}).get("degeneree") for e in images):
        lignes.append(
            "\n⚠ Au moins une image n'a qu'**une seule** référence. Dans ce cas "
            "`nouveauté = 1 − ressemblance` **exactement** : les deux colonnes sont la même "
            "mesure et ne s'optimisent pas séparément.")
    return lignes


def _nombre(valeur) -> str:
    return "—" if valeur is None else f"{float(valeur):.4f}"


def verdict_bascule(recap: dict) -> str:
    """La phrase qui compare le coût de la bascule à celui des images — avec dénominateur."""
    images = recap.get("images") or []
    bascule = float(recap.get("bascule_secondes") or 0.0)
    if not images:
        return f"Bascule de modèle : {bascule:.1f} s. Aucune image produite : rien à comparer."
    total = sum(float(i.get("secondes") or 0.0) for i in images)
    moyenne = total / len(images)
    if moyenne <= 0:
        return (f"Bascule de modèle : {bascule:.1f} s pour {len(images)} image(s) "
                f"instantanée(s) — le moteur n'a rien coûté, la comparaison n'a pas de sens.")
    equivalent = bascule / moyenne
    verdict = ("⚠ **c'est la bascule qu'il faut optimiser, pas le modèle**"
               if equivalent > SEUIL_BASCULE_IMAGES else
               "elle reste sous le seuil : le coût du run est bien celui de la génération")
    return (f"Bascule de modèle : **{bascule:.1f} s**, soit **{equivalent:.1f} image(s)** au "
            f"prix moyen de ce run ({moyenne:.1f} s/image sur {len(images)} image(s), "
            f"{total:.1f} s au total) — {verdict}. "
            f"Le seuil est de {SEUIL_BASCULE_IMAGES} images (`PLAN-24` L24.1 bis).")


def perf(recap: dict, destination) -> Path:
    """Le journal de performance de la brique. Une ligne par image, plus la bascule.

    Format volontairement proche de celui du `perf.log` du dépôt — des lignes préfixées,
    lisibles à l'œil et grepables — sans être le même fichier."""
    destination = Path(destination)
    cible = destination / "perf.log"
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lignes = [f"{horodatage} [illustration] run moteur={recap.get('moteur')} "
              f"modele={recap.get('modele')} images={len(recap.get('images') or [])}",
              f"{horodatage} [illustration] bascule_vram {float(recap.get('bascule_secondes') or 0):.3f} s"]
    for entree in recap.get("images") or []:
        vram = entree.get("vram_pic_octets")
        lignes.append(
            f"{horodatage} [illustration] image {Path(entree['image']).name} "
            f"{float(entree.get('secondes') or 0):.3f} s graine={entree.get('graine')} "
            + (f"vram_pic={vram}" if vram else "vram_pic=non rapporté"))
    # Le fichier est propre à la brique et vit dans son dossier : l'ajout en fin (`a`) ne
    # touche donc jamais un fichier de l'œuvre, et le périmètre d'écriture le vérifie.
    with open(cible, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lignes) + "\n")
    return cible
