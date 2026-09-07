# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Brique **ILLUSTRATION** — produire des images neuves, jamais retoucher celles de l'œuvre.

Quatrième brique du dépôt, après `pipeline/` (light novel), `manga/` et `scan/`. Elle est
**expérimentale**, **désarmée par défaut** (`illustration.actif: false`), et elle n'a aucun
point de contact avec le chemin nominal : un utilisateur qui ne touche à rien ne télécharge
aucun poids et ne perd aucune seconde au démarrage.

## La frontière, et elle est testée et non affirmée

Le principe directeur du dépôt — « l'IA ne dessine jamais » (`docs/README.fr.md` §12) — porte
sur les **pixels de l'œuvre** : aucune écriture non déterministe dans une planche, une page ou
un fichier source. Cette brique ne modifie **aucun** fichier existant. Elle lit `media/`, elle
écrit des fichiers qui n'existaient pas, dans **deux** dossiers qui lui sont propres, marqués
comme générés, et supprimables sans rien casser :

    build/<Projet>/illustrations/            les candidates, et `rejetees/` sous elles
    sources/<Projet>/illustrations/          ce qu'un humain a décidé de GARDER (lot 27)

⚠ **Le second est un sous-dossier NEUF de `sources/<Projet>/`, jamais le dossier lui-même.**
`frontiere.perimetre` ne laisse donc toujours pas approcher `bible.yaml`, `glossaire.yaml` ni
un fichier de l'œuvre. Il existe parce que `build/` est régénérable par contrat — le dépôt
recommande lui-même un `rm -r build/` après un MAJEUR — alors qu'une image produite en 103,7 s
de GPU et retenue par un humain ne l'est pas.

⚠ **Cette portée ne préjuge pas de ce que le `PLAN-22` a décidé** pour l'effacement de pixels
existants : c'est un autre sujet, tranché ailleurs (`manga/effacement.py`, déterministe et
désarmé), et la phrase ci-dessus ne lui sert pas de précédent.

Le dépôt ne se contente jamais d'un raisonnement là où un test existe — `clean.py` garde son
`paint &= region.mask` « parce que l'invariant ne doit pas dépendre d'un raisonnement ». Même
exigence ici, et à deux niveaux :

1. `illustration/frontiere.py` installe un **périmètre d'écriture** en vrai, pendant le run :
   toute écriture hors du dossier de la brique lève. Ce n'est pas un mode de test, c'est le
   chemin nominal.
2. `tests/test_illustration_frontiere.py` prouve les trois propriétés du `PLAN-24` :
   `illustration/` n'importe rien de `manga/`, `pipeline/`, `scan/` ni `gui/` ; aucune
   fonction n'ouvre en écriture un chemin préexistant hors de son dossier ; un run complet
   sur un tome témoin laisse **toutes** les empreintes SHA-256 préexistantes inchangées.

## Le run a deux phases, et un humain au milieu

    phase 1 — prompt   → `requete.yaml`, lisible, éditable, `valide: false`
    ──────── porte humaine : l'utilisateur relit, corrige, valide, ou annule ────────
    phase 2 — image    → les PNG marqués + leur sidecar de provenance

⚠ **La phase 2 refuse de démarrer sur `valide: false`**, et le motif est nommé. C'est le seul
garde-fou qui garantisse qu'aucun PNG n'existe sans qu'un humain ait validé le prompt qui l'a
produit — la ligne exacte que la politique IA du dossier NLnet exige de pouvoir montrer.

⚠ **Depuis le lot 26, la porte a un SECOND battant** : on ne peut pas décocher **toutes** les
références d'un personnage qui en avait. Sans référence, la phase 2 retombe sur de la
génération pure — le modèle invente un visage au lieu de suivre celui de l'œuvre. Le refus
tombe **à la lecture du fichier**, avant la bascule VRAM et avant le chargement de 12 Go de
poids.

## D'où vient chaque mot du prompt, et pourquoi ça se vérifie

Le lot 26 pose une règle qui prolonge celle de la bible visuelle — « un attribut sans citation
n'est pas une observation » :

    bible.apparence + citations[]     →  les ATTRIBUTS, mot pour mot
    glossaire.personnages[].genre     →  le SUJET, accordé
    bible.style.signature (mesurée)   →  le REGISTRE, mis en mots
    illustration/gabarits/*.yaml      →  la CHARPENTE : ordre, ponctuation, prompt négatif
    bible.references[] + style.ancrages[]  →  les IMAGES, avec un motif chacune

Aucun texte produit par un modèle ne devient un fragment d'attribut : ce n'est pas une
vérification, c'est une **absence de branche** dans `illustration/prompt.py`. Le seul texte
qu'un modèle peut ajouter est une **clause de scène** — une pose, un geste —, et elle traverse
un filtre qui la rejette **en entier** si elle décrit une apparence.

⚠ Ce filtre est un vocabulaire fermé, donc **franchissable par périphrase**, et c'est écrit
dans le gabarit à côté de la liste. Ce qui n'est pas franchissable, c'est la charpente.

## L'écran de relecture est le SEUL chemin vers la génération (lot 27)

`illustration/relecture.py` porte une `Porte` à usage unique : elle construit ce qu'il faut
montrer, elle reçoit ce que l'humain a corrigé, et elle délivre un laissez-passer que la
phase 2 exige. **L'atelier console et l'onglet graphique franchissent la même** — deux portes,
c'est une porte de moins qu'on croit avoir.

    atelier.py       qui est illustrable, et pourquoi pas
    relecture.py     l'écran, les corrections, la PORTE
    galerie.py       garder / jeter / purger, l'inventaire, images_generees[]
    progression.py   préparation (LLM) · bascule de modèle · génération (image)
    attente.py       le chiffre de l'étape 0.1, et la tranche d'interface qu'il impose
    vram.py          la bascule : elle s'ouvre une fois, elle se ferme TOUJOURS, une seule fois

## Voir ce que le projet envoie, et refuser avant le GPU (lot 28)

Deux modules en lecture seule, et un outil qui les expose (`tools/comfy.py`) :

    sonde.py         ce que le serveur ComfyUI expose RÉELLEMENT — /object_info, /system_stats
    validation.py    les cinq vérifications d'un graphe, AVANT la première seconde de GPU

⚠ **Ni l'un ni l'autre ne sait générer.** Ils n'appellent que des routes en lecture ; générer
reste le travail de `run_illustration.py`, qui porte la porte humaine et le marquage. Un
second chemin capable d'envoyer un `/prompt` serait une seconde porte, non gardée, et
`tests/test_tools_comfy.py` compte les requêtes plutôt que de relire les sources.

⚠ **Un serveur injoignable produit « non fait », jamais « passé ».** C'est toute la discipline
de ces deux modules : un validateur qui refuserait un nœud parce que ComfyUI est éteint
refuserait tous les graphes du dépôt à chaque diagnostic hors ligne, et un avertissement faux
cesse d'être lu.

## Juger, et savoir qu'on ne sait pas (lot 29)

    aveugle.py       le protocole HUMAIN en aveugle : paires, seuil, réponses, accord

⚠ **Son produit n'est pas un verdict, c'est un ÉTALON.** Le juge automatique de `juge.py` ne
sépare « même personnage » de « personnages différents » que **68 fois sur 100** — et personne
ne sait, **au 2026-09-03**, si 68 est un mauvais score, parce que personne n'a mesuré ce qu'un
humain fait sur les mêmes paires. C'est l'accord humain / automatique qui le dira, et il n'a
pas encore été mesuré : le protocole est écrit depuis le `PLAN-25`, outillé depuis le lot 29,
et **jamais exécuté**. Tant que ce chiffre n'existe pas, toute colonne « ressemblance » du
dépôt reste **non opposable** (`docs/mesures/identite-2026-09-03.md`).

⚠ **`aveugle.py` ne charge aucun modèle et n'écrit aucune image.** Les scores du juge
automatique lui sont **passés** ; c'est `tools/juge_humain.py` qui possède l'encodeur. Règle
de couche : tout ce qui décide se teste sans modèle.

## Ce que la brique n'importe pas

`core/` et rien d'autre, et personne ne l'importe **sauf `gui/atelier.py`**, tardivement.

Le graphe d'imports internes du dépôt est sans cycle — `core` n'importe rien d'interne,
`pipeline`→core, `manga`→core+pipeline, `scan`→core+manga, `gui`→core+manga+pipeline — et
`illustration`→core. `tests/test_imports_briques.py` le vérifie pour les **six** paquets.

⚠ **La propriété de feuille a été affaiblie au lot 27, et c'est écrit.** Le `PLAN-27` demande
« un onglet, à côté de Planches et de Runs » : il n'existe aucune façon d'écrire cet onglet
sans que `gui/` connaisse la brique. Ce qui est conservé, et testé pour de bon :

1. `pipeline/`, `manga/`, `scan/` et `core/` ne l'importent **toujours pas** — le light novel
   rend un tome sans elle, et l'insertion du lot 27 passe par `core/insertion.py` pour ça ;
2. **aucun import de niveau module** dans `gui/`, donc la fenêtre démarre sans le paquet — un
   test rend `illustration` inimportable puis construit la fenêtre entière, qui affiche alors
   un état vide disant pourquoi l'onglet l'est.
"""
