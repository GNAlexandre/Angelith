# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Version du projet — SOURCE UNIQUE DE VÉRITÉ.
Toute autre mention (CHANGELOG, tag git, en-tête de run, métadonnées de sortie) en découle.

Pas de pyproject.toml : le projet n'est pas empaqueté, il se lance par `python run.py`. Un
littéral Python évite donc une lecture disque relative à __file__ (fichier VERSION) ou un
parseur TOML au démarrage.

⚠ MISE À JOUR 2.31.0 (2026-09-06), lot 37 : **la première phrase ci-dessus est LEVÉE**, la
seconde TIENT. Le projet EST empaqueté depuis ce lot — `pyproject.toml`, un `angelith.spec`
en un-dossier, un installeur Inno Setup —, et l'affirmation « il se lance par `python run.py` »
est devenue une demi-vérité : ce n'est plus que l'un des deux modes de distribution.

Ce qui ne change pas, et c'est l'argument technique de la seconde phrase : **le littéral
ci-dessous reste la source unique**. `pyproject.toml` le LIT — `[tool.setuptools.dynamic]
version = {attr = "core.version.__version__"}` —, il ne le recopie pas. Deux numéros de
version, ce serait un `tests/test_version.py` qui passe pendant qu'on livre le mauvais numéro ;
`tests/test_pyproject.py` compare donc la version des MÉTADONNÉES du paquet à celle-ci.

Aucun parseur TOML n'est chargé au démarrage : setuptools lit l'attribut à la CONSTRUCTION du
paquet, jamais à l'exécution."""

__version__ = "2.35.0"

# La version du dépôt est UNIQUE, mais les deux briques n'ont pas le même degré de
# confiance. Affiché par `--version`.
#
# `manga` passe de « bêta » à « stable » en 1.0.0, et les mesures le portent : sur les
# 258 planches à bulles des deux tomes du *manga A*, 257 sont en numérotation
# complète, 0 en repli positionnel, et 0 des 1 593 bulles ne porte de kanji résiduel.
#
# ⚠ La réserve est nommée plutôt que masquée : la LECTURE du texte hors bulle reste peu fiable
# (`manga-ocr` est un modèle de dialogue et hallucine sur une onomatopée stylisée), d'où
# `manga.onomatopees.mode: "rapport"` par défaut — on détecte et on rapporte, on ne dessine
# pas. Cela ne touche pas les bulles, qui sont ce que « stable » qualifie.
#
# ⚠ **La réserve a un chiffre depuis la 2.12.0**, et il est pire que la phrase : sur 60 zones
# hors bulle tirées au sort (graine 21) et transcrites à l'œil, `manga-ocr` est exact
# **6 fois sur les 41** dont la lecture nourrit le LLM — **14,6 %** — et il est « plausible
# mais faux » 21 fois. Il lit la NARRATION imprimée (4 sur 9) et presque jamais l'onomatopée
# stylisée (2 sur 14). Et la DÉTECTION n'est pas fiable non plus : 14 des 60 zones seulement
# sont une onomatopée, 16 ne portent aucun texte, 14 sont des agrégats. Tout est dans
# `docs/mesures/sfx-2026-08-28.md`.
#
# ⚠ **Le lot 22 n'a pas levé cette réserve, il l'a rendue opérante.** Un effacement
# déterministe du texte hors bulle existe (`manga/effacement.py`, remplissage ou diffusion en
# numpy pur, aucun modèle génératif — la décision est écrite dans README §12), mais il n'efface
# **jamais** une zone dont la lecture n'est pas concordante. Ce taux valant 0 %, le mode
# n'efface aujourd'hui **aucune zone** : le chemin est complet, sa condition d'entrée ne l'est
# pas. Tout est dans `docs/mesures/relettrage-2026-08-28.md`.
#
# L'interface graphique n'apparaît PAS ici, et ne fait pas non plus passer la version à 2.0.0
# tant qu'elle n'est pas jugée mûre à l'usage. Deux raisons distinctes :
#
# · ce n'est pas une troisième brique de traitement mais une FAÇADE — elle n'a aucun chemin
#   propre, elle appelle les deux `process_volume` et `manga/edition.py`, et son degré de
#   confiance est donc celui des briques qu'elle pilote ;
# · la 2.0.0 est une promesse écrite au README (« interface graphique et édition directe ») :
#   la poser demande d'avoir retouché de vraies planches, pas seulement d'avoir livré le code.
#   Elle vit donc sous « [Non publié] » au CHANGELOG en attendant ce verdict.
#
# ⚠ MISE À JOUR 2.25.0 (2026-09-04) : la première raison **tient toujours** — l'interface reste
# une façade sans chemin de traitement propre, et le lot 31 n'en ajoute aucun. Ce qui change est
# ce qu'elle coûte : elle n'ouvre plus de tome au démarrage. Mesuré sur le corpus réel
# (18 dossiers sous `sources/`, 6 avec des planches) : **1,89 s → 0,13 s** avant le
# premier pixel, **692 → 1**
# ouverture de fichier, **311 → 106 Mo** de pic mémoire, et zéro `Services`, zéro glossaire,
# zéro aperçu. Tout est dans `docs/mesures/coquille-2026-09-04.md`.
#
# ⚠ MISE À JOUR 2.29.0 (2026-09-05) : la première raison **tient encore**, et le lot 35 ne
# lui ajoute toujours aucun chemin de traitement. Ce qu'il change est ce que coûte le geste
# qui RESTE après le lot 31 — ouvrir un tome dans la retouche —, et ce coût n'était pas celui
# que le dépôt annonçait. Mesuré sur le corpus réel, à mi-tome, avec les réglages par défaut :
# la fenêtre de préchargement demandait **21 aperçus à 9,35 Mo pièce** contre un plafond de
# 120 Mo qui en tient 12, si bien que le cache évinçait ce que la voie de lecture venait de
# composer — **137 compositions pour 12 aperçus gardés en 120 s, indéfiniment, sur un panneau
# que personne ne touchait**. Après le lot : **13 pour 12**. Le chiffre de 1,04 Mo par aperçu
# écrit dans `gui/cache_apercu.py` était faux d'un facteur 9 sur un tome paginé et d'un
# facteur 34 sur une bande webtoon. Tout est dans `docs/mesures/retouche-2026-09-05.md`.
#
# `scan` (1.4.0) arrive en BÊTA, et la réserve est nommée : l'analyse de mise en page est
# mesurée sur un seul tirage — les scans de *manga C* — et ses seuils, quoique
# tous relatifs et non absolus, n'ont pas encore vu d'autre imprimeur. Le garde-fou de la
# brique (la grille prédit ce que la lecture devrait rendre) et `run_ocr.py --apercu` existent
# précisément pour que le prochain tirage se règle en une minute au lieu de se découvrir après
# deux heures d'OCR. La lecture elle-même est celle de `manga-ocr`, déjà éprouvée.
# ⚠ MISE À JOUR 2.16.0 : la première réserve ci-dessous est LEVÉE — le moteur réel a tourné le
# 2026-08-29 sur la RX 7900 XT (ComfyUI 0.34.2, Qwen-Image-2512 GGUF Q4_1) : 11 images sur 11
# sur un corpus réel, 0 échec sur 25 générations, 103,7 s par image, pic VRAM 14 421 Mio sur
# 20 464. Tout est dans `docs/mesures/connecteur-qwen-2026-08-29.md`.
#
# ⚠ L'état reste `experimental`, et la SECONDE réserve est la raison : les images produites sont
# **hors du registre graphique** du tome, et c'est mesuré — écart moyen 0,200 sur les quatre
# descripteurs de `core/illustrations.py`, cinq fois moins de densité de trait, et un régime de
# couleur opposé (le tome est en noir et blanc). Passer à `beta` demanderait de savoir produire
# une image qui ressemble au tome, ce que le `PLAN-25` a à décider — pas seulement de savoir
# produire une image.
#
# `illustration` (2.15.0) arrive en EXPÉRIMENTAL — un mot plus bas que « bêta », et il est
# neuf dans ce dépôt parce qu'aucun des trois autres états ne dirait la vérité. La réserve est
# double, et aucune des deux moitiés n'est un défaut d'écriture :
#
# · **le moteur réel n'a jamais tourné.** Les trois chemins d'exécution que le `PLAN-24`
#   demandait de mesurer sur la 7900XT — ComfyUI, `stable-diffusion.cpp`, `diffusers` — n'ont
#   pas été mesurés : la session qui a livré la brique n'avait ni le GPU ni le réseau. Le
#   défaut de `illustration.moteur` est donc `"factice"`, qui rend un carré uni : la CHAÎNE
#   est vérifiée de bout en bout, la GÉNÉRATION ne l'est pas.
# · **la brique ne prétend rien sur la ressemblance.** Aucune grandeur d'identité, de
#   nouveauté ou de distance de style n'est mesurée ici ; c'est le `PLAN-25`, et l'annoncer
#   maintenant serait le genre d'affirmation que `docs/mesures/webtoon-2026-08-26.md` a dû
#   venir démentir.
#
# Ce qui EST tenu, en revanche, se teste sans GPU : la frontière d'écriture (la brique ne peut
# pas toucher un pixel de l'œuvre, `illustration/frontiere.py` le refuse à l'exécution), la
# porte humaine (`valide: false` bloque la phase image), et le marquage AI Act (aucun chemin
# de code ne sait écrire un PNG sans son bloc tEXt ni son sidecar de provenance).
#
# ⚠ MISE À JOUR 2.17.0 : la SECONDE réserve est **entamée, pas levée**, et l'état reste
# `experimental` pour trois raisons qui se comptent.
#
# · Le registre graphique s'est nettement rapproché : conditionner par les références de la
#   bible fait passer l'écart moyen aux quatre descripteurs de **0,200 à 0,1224** (−39 %) à
#   nombre de pas identique, là où 12,5 fois plus de calcul n'achetait que −24 %. Mais le
#   **régime de couleur reste faux** — le tome est en noir et blanc, les générations non.
# · La RESSEMBLANCE, elle, n'est toujours pas mesurable : le juge automatique du lot 25 ne
#   sépare « même personnage » de « personnages différents de la même œuvre » que **68 fois
#   sur 100** (contre 91 entre deux œuvres). Ses verdicts sont livrés marqués
#   « non opposables », et le protocole en aveugle du plan **n'a pas été exécuté**.
# · Le corpus de références s'est révélé impropre : les trois références d'identité validées
#   du tome de référence sont des **couvertures**. Voir `docs/mesures/identite-2026-08-29.md`.
#
# Passer à `beta` demanderait un verdict humain sur la ressemblance, et des recadrages de
# personnage à la place des couvertures. Ni l'un ni l'autre ne s'écrit en Python.
#
# ⚠ MISE À JOUR 2.18.0 : la TROISIÈME réserve ci-dessus — « le corpus de références s'est
# révélé impropre » — a maintenant un correctif MESURÉ, et il ne vient pas d'un modèle
# d'image.
#
# · Le modèle de VISION du dépôt (`yume-27b`, capacité vision confirmée) sait lire ce que le
#   classifieur déterministe du lot 23 ne voit pas. Sur les 10 références validées du corpus,
#   il désigne « couverture avec titre, nom d'auteur, numéro de tome » sur des fichiers que
#   `core/illustrations.py` range en `pleine_page` — dont la page « Afterword », qui porte le
#   texte de l'illustrateur et sa signature. Quatre motifs sur quatre vérifiés à l'œil sont
#   exacts.
# · Conséquence directe sur le registre graphique : la sélection retenue change, donc les
#   pixels envoyés au conditionnement changent, donc le régime de couleur change. C'est le
#   mécanisme que le lot 25 avait nommé sans pouvoir le corriger — « le conditionnement
#   rapproche l'image du registre des RÉFÉRENCES, pas du registre du TOME ».
#
# L'état reste `experimental`, et pour la raison qui n'a pas bougé : la RESSEMBLANCE n'est
# toujours pas mesurable — le juge du lot 25 ne sépare que 68 fois sur 100 —, et le protocole
# humain en aveugle n'a toujours pas été exécuté. Tout est dans
# `docs/mesures/prompt-illustration-2026-08-30.md`.
#
# ⚠ MISE À JOUR 2.19.0 : la brique a **une commande**, et elle a été mise à l'épreuve sur une
# œuvre de 4 tomes et 80 illustrations exploitables — cinq fois le corpus qui avait servi
# jusque-là. Ce que l'usage a montré, et qu'aucune mesure hors contexte n'aurait montré :
#
# · **la portée par TOME était fausse.** Les références d'un personnage vivent où l'éditeur
#   les a mises, et une œuvre à plusieurs volumes réutilise les mêmes noms de fichier : deux
#   tomes portaient tous deux un `image1`, et la résolution rendait le premier venu — donc,
#   potentiellement, le personnage d'un autre volume.
# · **le classifieur de couvertures en manquait au moins trois sur cinq.** Une couverture
#   republiée en fin de volume était rangée en `pleine_page`, et le mécanisme du lot 25 qui
#   repousse les couvertures ne se déclenchait donc pas sur celles qui en avaient le plus
#   besoin. Corrigé par détection de sosie, seuil posé dans un vide mesuré.
# · **une revue en bloc ne vaut rien.** Sur le premier personnage relu, la passe automatique
#   proposait cinq attributs dont **trois faux** — dont des cheveux « bleu céleste » là où le
#   dessin les montre verts, la phrase citée décrivant un autre personnage. La revue se fait
#   désormais attribut par attribut, avec la phrase sous les yeux.
#
# Et un résultat qui tient en une image : sur ce personnage, les trois attributs faux ont été
# REJETÉS, le prompt ne portait plus que « yeux verts, porte manteau sobre » — et l'image
# produite a les bons cheveux. Ce sont les RÉFÉRENCES qui portent l'identité, pas les mots.
#
# Tout est dans `docs/mesures/atelier-2026-08-31.md`.
# ⚠ MISE À JOUR 2.21.0 : la brique a une INTERFACE, une porte partagée par les deux
# interfaces, et une sortie qui sait entrer dans un tome. L'état reste `experimental`, et la
# raison n'a **toujours** pas bougé depuis la 2.17.0 : la RESSEMBLANCE n'est pas mesurable —
# le juge du lot 25 ne sépare que 68 fois sur 100 — et le protocole humain en aveugle n'a
# toujours pas été exécuté. Un atelier ne mesure rien ; il rend seulement la mesure plus
# facile à demander.
#
# Ce que le lot 27 tient, et qui se teste sans GPU :
#
# · **l'écran de relecture est le seul chemin vers la génération.** `illustration/relecture.py`
#   porte une `Porte` à usage unique, la console et l'onglet graphique la franchissent tous
#   les deux, et deux tests l'attestent — l'un à l'exécution, l'autre en lisant les sources de
#   l'interface avec `ast` pour qu'un second chemin ajouté demain échoue le jour même.
# · **la bascule VRAM se ferme sur tous les chemins de sortie**, y compris l'erreur et
#   l'annulation. Elle ne se fermait qu'en cas de succès jusqu'ici, et le coût d'un abandon
#   sale est mesuré : 25 → 18 tok/s sur la traduction suivante.
# · **une image produite ne peut pas devenir une référence** : clé `images_generees[]`
#   distincte de `references[]`, plus deux refus indépendants (le dossier, le marquage AI
#   Act). Le test fait l'aller-retour complet et vérifie que la liste des candidates est
#   inchangée.
# · **l'insertion dans les sorties du light novel est opt-in et étiquetée**, et sa légende n'a
#   pas d'interrupteur : `core/insertion.py` lève sur une légende vide, et elle sort dans les
#   trois formats — vérifié avec le vrai Pandoc, DOCX, EPUB et PDF.
#
# ⚠ Et un défaut du dépôt lui-même, corrigé ici : **le `config.yaml` PUBLIÉ armait la brique
# depuis la 2.20.0**. Six valeurs de travail d'une machine étaient entrées dans un commit qui
# parlait de polices de manga. `test_le_defaut_du_depot_est_bien_desarme` échouait donc sur
# `git show HEAD:config.yaml` depuis ce jour-là. Tout est dans
# `docs/mesures/atelier-illustration-2026-09-02.md`.
#
# ⚠ MISE À JOUR 2.23.0 : la brique porte l'OUTILLAGE du jugement, et **aucune mesure de plus**.
# L'état reste `experimental`, et la raison n'a pas bougé depuis la 2.17.0 : au **2026-09-03**,
# le juge du lot 25 sépare toujours 68 fois sur 100, et le protocole humain en aveugle n'a
# toujours pas été exécuté. Le lot 29 a tourné sur le PC SECONDAIRE — ni bible, ni encodeur,
# ni GPU — et **sept de ses neuf critères ne sont donc pas tenus**, tous pour cette raison.
#
# Ce que le lot 29 livre quand même, et qui se teste sans carte :
#
# · **le protocole en aveugle est OUTILLÉ** (`illustration/aveugle.py`, `tools/juge_humain.py`) :
#   seuil fixé à la création du protocole et relu de là, ordre A/B tiré au sort, étiquettes
#   absentes du nom des fichiers ET de leur date, réponses horodatées en ajout seul. Le
#   livrable qu'il produira est un ACCORD humain / automatique, pas un verdict ;
# · **le corpus se compte** (`tools/bible.py --corpus`, et le tableau s'affiche à chaque
#   revue) : 0 / 1 / 2 / ≥3 références d'identité par personnage, avec et sans les
#   couvertures. C'est l'écart entre ces deux comptes qui a fait passer, au lot 25, trois
#   couvertures pour un corpus prêt ;
# · **deux défauts silencieux sont corrigés.** Le champ de recadrage était ÉCRIT sous un nom
#   (`recadrage`) et LU sous un autre (`cadre`) depuis la 2.14.0 — il n'a donc jamais pu être
#   rempli, ce qui explique en partie deux lots d'axe « nature du recadrage » non mesuré. Et
#   `tools/banc_identite.py --balayage` levait un `AttributeError` depuis la 2.18.0, sur le
#   seul chemin de ce banc qu'aucun test sans GPU ne pouvait atteindre ;
# · **le levier du décor est livré DÉSARMÉ.** « Sur fond neutre » est soupçonné d'être une
#   régression que le dépôt s'est infligée (part d'aplats 0,6300 contre 0,3669 pour le tome) ;
#   les trois variantes existent, le défaut ne bouge pas, et un test vérifie que le prompt
#   produit sans rien demander est celui d'avant le lot, mot pour mot.
#
# Tout est dans `docs/mesures/identite-2026-09-03.md`, qui reprend les neuf critères un par un.
ETAT_BRIQUES = {"ln": "stable", "manga": "stable", "scan": "beta",
                "illustration": "experimental"}
