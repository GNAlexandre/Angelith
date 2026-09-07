# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Chercher une réplique dans tout un tome — **sans Qt**.

## Pourquoi ce module existe

Retrouver « où ai-je traduit ce nom ? » obligeait à ouvrir les planches une par une. Ce
n'était pas un arbitrage de performance mais un oubli : une recherche sur **tout** un tome de
150 planches coûte **~210 ms** (mesuré sur *manga A* Vol.1, 300 fichiers JSON relus à
chaque appel).

⚠ 210 ms, ce n'est pas gratuit : c'est confortable pour une recherche **validée**, et trop
cher pour une recherche à chaque touche frappée. L'appelant déclenche donc sur `Entrée`, ou
temporise. Le coût brut de lecture des fichiers n'est que de 49 ms — le reste est la
validation faite par `checkpoints.load_*`, qu'on ne contourne pas : un cache de traduction
tronqué se lit différemment selon qu'on le valide ou non, et une recherche qui verrait autre
chose que l'éditeur serait pire que pas de recherche du tout.

## Ce qu'on cherche, et dans quel ordre

Trois champs, et ils ne se valent pas :

- la **réplique affichée** — ce que le lecteur verra, donc la correction manuelle si elle
  existe, sinon la traduction du modèle ;
- la **traduction d'origine** — utile pour retrouver ce qu'on a corrigé, et *seulement*
  quand elle diffère de l'affichée (sinon chaque bulle sortirait deux fois) ;
- l'**OCR japonais** — c'est là qu'on cherche un terme du glossaire dans sa langue source.

⚠ La correction manuelle **l'emporte** : afficher la traduction du modèle pour une bulle
qu'on a corrigée à la main enverrait l'utilisateur vérifier un texte qui n'existe plus.

Insensible à la casse **et aux accents** : chercher « leo » doit trouver « Léo ».

⚠ Mais **sur du latin seulement**. `NFD` décompose bel et bien les kana — « ガ » devient
« カ » + dakuten — et une purge aveugle des signes combinants faisait donc trouver « カキク »
en cherchant « ガギグ ». Le dakuten n'est pas un ornement : il change le son, donc le mot.
Voir `normaliser`.
"""
from __future__ import annotations

import unicodedata

from . import checkpoints, etat_planches

#: Nom des champs dans un résultat, pour que l'appelant n'ait pas à connaître nos chaînes.
CHAMP_AFFICHEE = "réplique"
CHAMP_TRADUCTION = "traduction d'origine"
CHAMP_OCR = "japonais"


def normaliser(texte: str) -> str:
    """Repli de comparaison : sans casse ni accents, **mais seulement sur du latin**.

    `NFD` sépare « é » en « e » + accent, qu'on retire ; `casefold` va plus loin que `lower`
    (il traite « ß » comme « ss »), ce qui ne coûte rien et évite une surprise.

    ⚠ Retirer *tous* les signes combinants était un défaut, trouvé par le test des kana : le
    **dakuten** japonais en est un. `NFD` décompose « ガ » en « カ » + dakuten, et une purge
    aveugle rendait donc « カ » — la recherche transformait chaque son voisé en son sourd, et
    « ガギグ » trouvait « カキク ». On ne dépouille donc que ce dont la base est latine, et on
    recompose en `NFC` pour rendre les kana intacts."""
    sortie: list[str] = []
    base_latine = False
    for caractere in unicodedata.normalize("NFD", texte or ""):
        if unicodedata.combining(caractere):
            if not base_latine:
                sortie.append(caractere)      # dakuten & consorts : ils PORTENT le sens
            continue
        base_latine = (caractere.isascii()
                       or "LATIN" in unicodedata.name(caractere, ""))
        sortie.append(caractere)
    return unicodedata.normalize("NFC", "".join(sortie)).casefold()


def repliques(build_dir, index: int) -> list[dict]:
    """Les bulles d'une planche : `{bulle, affichee, traduction, ocr, manuelle}`.

    Tolérant de bout en bout — une planche jamais traduite rend une liste vide plutôt qu'une
    exception. Une recherche qui échoue sur une planche ne rendrait aucun résultat sur les
    149 autres."""
    ckpt = checkpoints.page_checkpoint_dir(build_dir, index)
    traduction = checkpoints.load_traduction(ckpt) or []
    ocr = checkpoints.load_ocr(ckpt) or []
    manuelles = checkpoints.load_traduction_manuelle(ckpt) or {}
    total = max(len(traduction), len(ocr), len(manuelles) and max(manuelles) + 1 or 0)
    sortie = []
    for bulle in range(total):
        origine = traduction[bulle] if bulle < len(traduction) else ""
        manuelle = manuelles.get(bulle)
        sortie.append({
            "bulle": bulle,
            "affichee": manuelle if manuelle is not None else origine,
            "traduction": origine,
            "ocr": ocr[bulle] if bulle < len(ocr) else "",
            "manuelle": manuelle is not None,
        })
    return sortie


def chercher(build_dir, motif: str, indices=None, *, limite: int = 500) -> list[dict]:
    """Toutes les occurrences de `motif`, dans l'ordre de lecture.

    Un résultat : `{planche, bulle, champ, texte, extrait}`. `champ` dit *où* ça a été
    trouvé — sans lui, un résultat japonais et un résultat français se ressembleraient à
    l'écran alors qu'ils n'appellent pas le même geste.

    ⚠ Une chaîne vide ne rend **rien** plutôt que tout : « tout » serait le tome entier, ce
    qui n'est pas une réponse."""
    aiguille = normaliser(motif).strip()
    if not aiguille:
        return []
    resultats: list[dict] = []
    for planche in etat_planches.indices_de(build_dir, indices):
        for bulle in repliques(build_dir, planche):
            for champ, texte in ((CHAMP_AFFICHEE, bulle["affichee"]),
                                 (CHAMP_TRADUCTION, bulle["traduction"]),
                                 (CHAMP_OCR, bulle["ocr"])):
                # La traduction d'origine ne ressort que si la correction l'a changée :
                # sinon chaque bulle sortirait deux fois pour le même texte.
                if champ == CHAMP_TRADUCTION and not bulle["manuelle"]:
                    continue
                if not texte or aiguille not in normaliser(texte):
                    continue
                resultats.append({
                    "planche": planche, "bulle": bulle["bulle"], "champ": champ,
                    "texte": texte, "extrait": extrait(texte, motif),
                })
                if len(resultats) >= limite:
                    return resultats
    return resultats


def extrait(texte: str, motif: str, *, marge: int = 28) -> str:
    """Le voisinage de la trouvaille, pour une liste de résultats sur une ligne.

    Découper sur le texte **d'origine** et non sur sa forme normalisée : les deux ont la même
    longueur ici (on ne retire que des signes combinants, jamais de caractères de base), mais
    afficher la forme normalisée montrerait « Leo » là où la planche dit « Léo »."""
    plat = " ".join((texte or "").split())
    debut = normaliser(plat).find(normaliser(motif))
    if debut < 0:
        return plat[:2 * marge]
    gauche = max(0, debut - marge)
    droite = min(len(plat), debut + len(motif) + marge)
    return (("…" if gauche else "") + plat[gauche:droite]
            + ("…" if droite < len(plat) else ""))


# ─────────────────────────────────────────────────────────────────────────────
# REMPLACER
#
# Corriger un nom sur quarante planches demandait quarante ouvertures. La recherche savait
# déjà les trouver ; il ne manquait que le geste d'écriture.
#
# ⚠ On ne remplace que dans la **réplique affichée**, et c'est un choix, pas une limite.
# L'OCR est du texte SOURCE : y « corriger » un nom français n'a pas de sens, et le modifier
# périmerait la traduction qui en descend. La traduction d'origine, elle, est la sortie du
# modèle — un `--from traduction` la réécrirait, donc y écrire serait écrire dans le sable.
#
# Le remplacement atterrit dans `traduction_manuelle.json`, exactement comme une saisie au
# clavier, et pour la même raison : c'est le seul fichier que le pipeline ne réécrit jamais.
# Un nom corrigé ici survit à toute relance.
# ─────────────────────────────────────────────────────────────────────────────

def occurrences_remplacables(build_dir, motif: str, indices=None, *,
                             limite: int = 500) -> list[dict]:
    """Les résultats de `chercher` sur lesquels un remplacement a un sens.

    C'est-à-dire ceux de la réplique AFFICHÉE — cf. le commentaire ci-dessus. Séparé de
    `remplacer` pour que l'appelant puisse montrer ce qui va changer AVANT de l'écrire : un
    remplacement sur tout un tome n'est pas un geste qu'on lance à l'aveugle."""
    return [r for r in chercher(build_dir, motif, indices, limite=limite)
            if r["champ"] == CHAMP_AFFICHEE]


def _table_normalisee(texte: str) -> tuple[str, list[int]]:
    """`(forme normalisée, index d'origine de chacun de ses caractères)`.

    ⚠ On ne peut PAS se contenter de comparer les longueurs. `normaliser` ne les préserve pas
    en général : `casefold()` rend « ß » → « ss », les ligatures se décomposent, et un signe
    combinant disparaît. Un découpage par index nu écrirait donc au mauvais endroit sur ces
    textes-là — silencieusement, ce qui est le pire des défauts pour une opération qui touche
    quarante planches d'un coup.

    On normalise donc caractère par caractère en gardant la trace de l'origine de chacun, ce
    qui rend la transposition exacte quoi qu'il arrive à la longueur."""
    forme: list[str] = []
    origines: list[int] = []
    for i, caractere in enumerate(texte):
        morceau = normaliser(caractere)
        forme.append(morceau)
        origines.extend([i] * len(morceau))
    return "".join(forme), origines


def remplacer_dans(texte: str, motif: str, par: str) -> str:
    """Remplace toutes les occurrences, **insensible à la casse et aux accents** — la même
    comparaison que `chercher`, sinon on montrerait des résultats qu'on ne saurait pas
    remplacer.

    Écrit depuis le texte D'ORIGINE, jamais depuis sa forme normalisée : cette dernière
    rendrait « Cafe » là où la planche dit « Café » pour tout ce qui entoure la trouvaille.
    La correspondance entre les deux passe par `_table_normalisee`."""
    plat = texte or ""
    if not motif:
        return plat
    aiguille = normaliser(motif)
    if not aiguille:
        return plat
    reference, origines = _table_normalisee(plat)

    sortie: list[str] = []
    i = j = 0                       # `i` dans l'original, `j` dans la forme normalisée
    while True:
        k = reference.find(aiguille, j)
        if k < 0:
            sortie.append(plat[i:])
            return "".join(sortie)
        debut = origines[k]
        fin = origines[k + len(aiguille)] if k + len(aiguille) < len(origines) else len(plat)
        sortie.append(plat[i:debut])
        sortie.append(par)
        i, j = fin, k + len(aiguille)


def remplacer(build_dir, motif: str, par: str, occurrences: list[dict]) -> list[int]:
    """Applique le remplacement aux `occurrences` données. Rend les planches modifiées.

    ⚠ On prend une LISTE d'occurrences plutôt que de rechercher soi-même : c'est ce qui permet
    à l'appelant de n'en cocher qu'une partie. Remplacer « Leo » partout alors qu'une planche
    parle d'un autre Leo est précisément l'erreur qu'un remplacement global rend facile.

    Passe par `manga.document`, jamais par une écriture directe : c'est lui qui tient
    l'alignement par position et la distinction saisie / sortie du modèle."""
    from . import document as doc_mod

    par_planche: dict[int, set[int]] = {}
    for occ in occurrences:
        par_planche.setdefault(int(occ["planche"]), set()).add(int(occ["bulle"]))

    modifiees: list[int] = []
    for planche in sorted(par_planche):
        ckpt = checkpoints.page_checkpoint_dir(build_dir, planche)
        document = doc_mod.DocumentPlanche.ouvrir(ckpt)
        # On relit la planche APRÈS l'avoir ouverte, plutôt que de se fier aux textes que la
        # recherche a rapportés : entre les deux, un run a pu la retoucher. Remplacer sur un
        # texte périmé écrirait une réplique qui n'a jamais existé.
        courant = {b["bulle"]: b["affichee"] for b in repliques(build_dir, planche)}
        touchee = False
        for index in sorted(par_planche[planche]):
            if index >= len(document.etat.regions):
                continue      # la planche a changé depuis la recherche : on la saute
            avant_texte = courant.get(index, "")
            apres_texte = remplacer_dans(avant_texte, motif, par)
            if apres_texte == avant_texte:
                continue
            document.poser_correction(index, apres_texte)
            touchee = True
        if touchee:
            document.enregistrer()
            modifiees.append(planche)
    return modifiees
