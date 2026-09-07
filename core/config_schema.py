# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les cles que `config.yaml` reconnait — la reference contre laquelle on detecte une faute.

## Pourquoi une liste et non le fichier lui-meme

`config.yaml` EST le fichier que l'utilisateur edite : le comparer a lui-meme ne trouverait
jamais rien. Il faut donc une reference independante.

⚠ Une liste recopiee a la main derive, et une reference qui derive produit de **faux**
avertissements — ce qui est pire que pas de verification du tout, parce qu'on cesse alors de
les lire. C'est `tests/test_config_valide.py` qui l'empeche : il compare cette liste a
l'arborescence reelle de `config.yaml` et echoue des qu'une cle est ajoutee sans etre
declaree ici. Le message d'echec dit quoi coller.

## Ce que la verification ne fait PAS

Elle **avertit**, elle ne refuse pas. Refuser transformerait une config aujourd'hui acceptee
en config rejetee — soit, a la regle du CHANGELOG de ce depot, un changement MAJEUR
(« l'utilisateur doit editer config.yaml »). Un avertissement suffit largement a faire gagner
les deux heures qu'une faute de frappe coute : le run se deroule entierement avec la valeur
par defaut, sans un mot, et rien ne le rattrape apres coup.
"""
from __future__ import annotations

#: Sous-arbres dont les cles sont NOMMEES PAR L'UTILISATEUR : on ne juge pas leurs enfants.
#: `llm.endpoints` porte des noms d'endpoints inventes, `langues.dossiers` des alias de
#: dossiers de sources. Les blocs d'agents (`modeles`, `temperatures`, `manga.modeles`) ne
#: sont deliberement PAS ici : leurs noms sont resolus par le code, donc une faute de frappe
#: y est un vrai defaut, et c'est exactement ce qu'on veut voir signale.
CLES_LIBRES: tuple[str, ...] = (
    "llm.endpoints",
    "langues.dossiers",
)


#: Toutes les cles connues, en chemin pointe. Verifiee par les tests.
CLES_CONNUES: frozenset[str] = frozenset({
    "chemins", "chemins.build", "chemins.glossaire_fichier", "chemins.prompts",
    "chemins.sources", "chemins.style_guide", "decoupage", "decoupage.chapter_patterns",
    "decoupage.detection", "decoupage.epub", "decoupage.epub.ruby",
    "decoupage.epub.titre_max_caracteres", "decoupage.marge_partie_bloc",
    "decoupage.max_block_chars", "decoupage.max_block_tokens", "decoupage.max_input_tokens",
    "decoupage.mise_en_forme", "decoupage.mise_en_forme.footer_bande_page",
    "decoupage.mise_en_forme.footer_frac_pages", "decoupage.mise_en_forme.ratio_taille_titre",
    "decoupage.mise_en_forme.titres_exclus",
    # Lot 37 — la verification de version, DESARMEE par defaut (`core/maj.py`).
    "maj", "maj.page", "maj.url", "maj.verifier",
    # Lot 39 — traduire, ou non. Defaut `true`, donc iso.
    "llm.actif",
    "garde_fous",
    "garde_fous.abandon_apres_timeouts_consecutifs", "garde_fous.cjk_residuel_seuil",
    "garde_fous.perte_mots_ratio", "garde_fous.perte_mots_ratio.correcteur",
    "garde_fous.perte_mots_ratio.mise_en_page", "garde_fous.perte_mots_ratio.traducteur",
    "garde_fous.redecoupage_profondeur_max", "garde_fous.redecoupage_sur_echec",
    "garde_fous.redecoupage_taille_min", "garde_fous.retry_temperature_facteur", "gui",
    "gui.apercu", "gui.apercu.fenetre", "gui.apercu.plafond_mo", "langues",
    "langues.appliquer_traductions_forcees", "langues.cible", "langues.dossiers",
    "langues.packs",
    "langues.optimiser_apres_terminologie", "langues.optimiser_glossaire_fin_volume",
    "langues.priorite_images", "langues.priorite_sens", "langues.sources_utilisees",
    "langues.traduire_titres", "llm", "llm.api_key", "llm.base_url",
    "llm.debit_plancher_tok_s", "llm.endpoints", "llm.extra_directive", "llm.max_retries",
    "llm.num_ctx", "llm.think", "llm.thinking_budget", "llm.timeout", "manga",
    "manga.chemins", "manga.contexte", "manga.contexte.budget_echantillon",
    "manga.contexte.max_tokens", "manga.contexte.planches_precedentes",
    "manga.contexte.repliques_max", "manga.detection", "manga.detection.conf_threshold",
    "manga.detection.iou_threshold", "manga.detection.model_path",
    "manga.detection.model_url", "manga.detection.providers", "manga.detection.scission",
    "manga.detection.scission.actif", "manga.detection.scission.aire_min",
    "manga.detection.scission.min_lobe_frac", "manga.detection.scission.remplissage_lobe_min",
    "manga.detection.scission.seuil_remplissage", "manga.detection.scission.seuil_suspect",
    "manga.detection.scission.aire_min_frac", "manga.detection.scission.germe_frac",
    "manga.detection.scission.k_max", "manga.detection.scission.max_lobes",
    "manga.detection.scission.stabilite", "manga.detection.scission.iou_stabilite",
    "manga.detection.scission.remplissage_lobe_relatif",
    "manga.detection.scission.remplissage_lobe_plancher",
    "manga.detection.scission.encre", "manga.detection.scission.encre.actif",
    "manga.detection.scission.encre.part_min",
    "manga.detection.scission.encre.facteur_seuil",
    "manga.detection.scission.encre.plancher_confirme",
    "manga.detection.fenetre_hauteur", "manga.detection.fenetre_ratio_min",
    "manga.detection.fenetre_recouvrement", "manga.detection.telechargement_auto",
    "manga.detection.fenetre_occupation_min", "manga.detection.fenetre_encre_min",
    "manga.detection.input_size", "manga.detection.aire_min_frac",
    "manga.detection.escalade", "manga.detection.escalade.actif",
    "manga.detection.escalade.conf_threshold", "manga.detection.escalade.input_size",
    "manga.detection.escalade.mediane_echantillon_min",
    "manga.detection.escalade.mediane_frac", "manga.detection.escalade.seuil_encre",
    "manga.formats", "manga.formats.webtoon",
    "manga.formats.webtoon.rendu", "manga.formats.webtoon.rendu.sens_lecture",
    "manga.formats.webtoon.rendu.psd_original",
    "manga.langue_source", "manga.lot", "manga.lot.plafond_sortie",
    "manga.lot.planches", "manga.lot.planches_vision", "manga.mode_traduction",
    "manga.modeles", "manga.modeles.glossariste", "manga.modeles.glossariste.model",
    "manga.modeles.manga_contexte", "manga.modeles.manga_contexte.endpoint",
    "manga.modeles.manga_contexte.model", "manga.modeles.manga_onomatopees",
    "manga.modeles.manga_onomatopees.model", "manga.modeles.manga_onomatopees.think",
    "manga.modeles.manga_traducteur", "manga.modeles.manga_traducteur.model",
    "manga.modeles.terminologue", "manga.modeles.terminologue.model", "manga.nettoyage",
    "manga.nettoyage.couleur_texte_clair", "manga.nettoyage.couleur_texte_sombre",
    "manga.nettoyage.dilatation_texte", "manga.nettoyage.marge_bord", "manga.nettoyage.mode",
    "manga.nettoyage.seuil_abandon", "manga.nettoyage.seuil_texte",
    "manga.nettoyage.seuil_uniformite", "manga.ocr", "manga.ocr.agrandissement_min",
    "manga.ocr.hors_ligne", "manga.ocr.marge_crop", "manga.ocr.masquer_hors_bulle",
    "manga.ocr.moteur",
    "manga.onomatopees", "manga.onomatopees.actif", "manga.onomatopees.aire_min",
    "manga.onomatopees.containment_bulle", "manga.onomatopees.groupement",
    "manga.onomatopees.mobilier_aire_max_frac", "manga.onomatopees.mobilier_frac_planches",
    "manga.onomatopees.mobilier_iou", "manga.onomatopees.mode",
    "manga.onomatopees.model_path", "manga.onomatopees.model_url",
    "manga.onomatopees.min_composante",
    "manga.onomatopees.fenetrage",
    "manga.onomatopees.fenetre_hauteur", "manga.onomatopees.fenetre_recouvrement",
    "manga.onomatopees.seuil_masque", "manga.onomatopees.telechargement_auto",
    "manga.rapport", "manga.rapport.max_lignes_section", "manga.rapport.seuil_confiance",
    "manga.rattrapage", "manga.rattrapage.actif", "manga.rattrapage.max_par_page",
    # Lot 15 — structure de planche, garde-fou de contenu, onomatopees avec image.
    "manga.garde_fous", "manga.garde_fous.ratio_court",
    "manga.garde_fous.ratio_court.cjk", "manga.garde_fous.ratio_court.latin",
    "manga.onomatopees.vision",
    # Lot 21 — lire l'onomatopee avant de pretendre l'ecrire. Les quatre premieres sont
    # DESARMEES par defaut ; seule `broderie_ratio` est armee, et c'est dit en tete du
    # CHANGELOG (cf. docs/mesures/sfx-2026-08-28.md).
    "manga.onomatopees.aire_max_frac", "manga.onomatopees.remplissage_max",
    "manga.onomatopees.concordance", "manga.onomatopees.crops_illisibles",
    "manga.onomatopees.broderie_ratio",
    # Lot 22 — l'effacement deterministe du texte hors bulle. Six cles, toutes desarmees :
    # `mode: "aucun"` suffit a rendre le bloc entier sans effet.
    "manga.onomatopees.effacement", "manga.onomatopees.effacement.mode",
    "manga.onomatopees.effacement.methode",
    "manga.onomatopees.effacement.seuil_uniformite",
    "manga.onomatopees.effacement.seuil_abandon",
    "manga.onomatopees.effacement.seuil_encre",
    "manga.onomatopees.effacement.dilatation",
    "manga.onomatopees.effacement.passes_diffusion",
    "manga.structure", "manga.structure.actif",
    "manga.structure.cri_harmonique_min", "manga.structure.cri_ondulation_min",
    "manga.structure.gouttiere_min_frac", "manga.structure.locuteur_min_bulles",
    "manga.structure.locuteur_rayon_frac", "manga.structure.pensee_pointes_min",
    "manga.structure.pensee_harmonique_min", "manga.structure.pensee_ondulation_max",
    "manga.structure.recitatif_rectangularite_min",
    "manga.structure.recitatif_remplissage_min",
    "manga.temperatures.manga_relecteur",
    "manga.rendu", "manga.rendu.formats", "manga.rendu.langue_iso", "manga.rendu.pdf_dpi",
    "manga.rendu.pdf_largeur_max", "manga.rendu.pdf_qualite", "manga.rendu.psd_original",
    "manga.rendu.psd_texte", "manga.rendu.sens_lecture", "manga.temperatures",
    "manga.temperatures.glossariste", "manga.temperatures.manga_contexte",
    "manga.temperatures.manga_onomatopees", "manga.temperatures.manga_traducteur",
    "manga.temperatures.terminologue", "manga.terminologie", "manga.terminologie.actif",
    "manga.terminologie.dominance", "manga.terminologie.min_occurrences", "manga.typeset",
    "manga.typeset.aire_min_bulle", "manga.typeset.cesure_traits_union",
    "manga.typeset.contour", "manga.typeset.contour_epaisseur", "manga.typeset.debordement",
    # Lot 22, L22.3 — le lettrage d'une zone HORS BULLE. Trois cles, toutes desarmees ou
    # sans effet tant que `manga.onomatopees.effacement.mode` vaut "aucun".
    "manga.typeset.contour_epaisseur_sfx", "manga.typeset.aire_min_sfx",
    "manga.typeset.sfx_rotation",
    "manga.typeset.font_path", "manga.typeset.font_path_gras",
    "manga.typeset.font_path_italique", "manga.typeset.glissement_vertical",
    "manga.typeset.glose_contour", "manga.typeset.glose_contour_mesure",
    "manga.typeset.glose_ecart", "manga.typeset.glose_marge",
    "manga.typeset.glose_taille_max", "manga.typeset.glose_taille_min",
    "manga.typeset.harmonisation", "manga.typeset.harmonisation_ratio_max",
    "manga.typeset.interligne", "manga.typeset.interligne_min", "manga.typeset.majuscules",
    "manga.typeset.marge_interne", "manga.typeset.marqueur_vide", "manga.typeset.taille_max",
    "manga.typeset.taille_min", "manga.typeset.taille_min_absolue", "modeles",
    "modeles.correcteur", "modeles.glossariste", "modeles.glossariste.endpoint",
    "modeles.glossariste.model", "modeles.mise_en_page", "modeles.terminologue",
    "modeles.terminologue.endpoint", "modeles.terminologue.model", "modeles.traducteur",
    "modeles.traducteur.endpoint", "modeles.traducteur.model", "naturalisation",
    "naturalisation.intensite", "options", "options.dry_run", "rendu",
    "rendu.dialogue_dash_in_text", "rendu.epub_css", "rendu.formats", "rendu.metadata",
    "rendu.metadata.auteur", "rendu.metadata.langue", "rendu.metadata.titre",
    "rendu.pdf_engine", "rendu.reference_docx", "rendu.styles", "rendu.styles.dialogue",
    "rendu.styles.pensee", "scan", "scan.caracteres_par_tranche", "scan.colonnes_min",
    "scan.illustration_encre_max", "scan.lot_ocr", "scan.ocr", "scan.ocr.hors_ligne",
    "scan.ruby", "scan.seuil_encre", "scan.titre_pas_min", "temperatures",
    "temperatures.correcteur", "temperatures.glossariste", "temperatures.mise_en_page",
    "temperatures.terminologue", "temperatures.traducteur",
    # Lot 24 — le socle generatif. TOUTES desarmees : `illustration.actif: false` suffit a
    # rendre le bloc entier sans effet, et `poids.fichier`/`comfyui.workflow` vides
    # empechent tout telechargement et toute generation reelle.
    "illustration", "illustration.actif", "illustration.moteur",
    "illustration.poids", "illustration.poids.dossier", "illustration.poids.fichier",
    "illustration.poids.url", "illustration.poids.sha256",
    "illustration.poids.telechargement_auto",
    "illustration.image", "illustration.image.largeur", "illustration.image.hauteur",
    "illustration.image.pas", "illustration.image.guidage", "illustration.image.graine",
    "illustration.image.par_requete",
    "illustration.comfyui", "illustration.comfyui.base_url",
    "illustration.comfyui.workflow", "illustration.comfyui.timeout",
    "illustration.comfyui.plancher_secondes",
    "illustration.vram", "illustration.vram.decharger_llm",
    "illustration.vram.decharger_image", "illustration.vram.recharger_llm",
    # Lot 27 — l'insertion dans les sorties. `inserer_dans_sorties: false` par défaut : un
    # tome relancé sans que l'utilisateur ait rien demandé sort iso-octet.
    "illustration.inserer_dans_sorties",
    "illustration.insertion", "illustration.insertion.position",
    "illustration.marquage", "illustration.marquage.identifiant_oeuvre",

    # Lot 25 — l'identite. Le juge, ses planchers, et le conditionnement par reference.
    # Toutes sans effet tant que `illustration.actif: false`, et `identite.actif: false`
    # laisse la phase image se comporter exactement comme au lot 24.
    "illustration.identite", "illustration.identite.actif",
    "illustration.identite.references_max", "illustration.identite.cote_reference",
    "illustration.identite.encodeur", "illustration.identite.encodeur.dossier",
    "illustration.identite.encodeur.fichier", "illustration.identite.encodeur.url",
    "illustration.identite.encodeur.sha256", "illustration.identite.encodeur.agregation",
    "illustration.identite.encodeur.cadrage", "illustration.identite.encodeur.cote",
    "illustration.identite.planchers", "illustration.identite.planchers.confusion",
    "illustration.identite.planchers.nouveaute",
    "illustration.identite.planchers.style_descripteurs",
    "illustration.identite.planchers.juge_utilisable",

    # Lot 26 — le prompt vient de l'oeuvre. Defauts ISO : `forme: prose`, `langue: fr`,
    # `llm.actif: false`, `style: mots`, `ancrages_max: 0`. Une phase 1 se comporte donc
    # comme au lot 25 — squelette deterministe, aucun appel reseau — tant que l'utilisateur
    # n'arme pas le modele de vision.
    "illustration.prompt", "illustration.prompt.forme", "illustration.prompt.langue",
    "illustration.prompt.cadrage", "illustration.prompt.gabarit",
    "illustration.prompt.style", "illustration.prompt.references_max",
    "illustration.prompt.ancrages_max",
    "illustration.prompt.llm", "illustration.prompt.llm.actif",
    "illustration.prompt.llm.modele", "illustration.prompt.llm.cote_vision",
    "illustration.prompt.llm.max_input_tokens",
    "illustration.budget", "illustration.budget.images_par_run",
})


# ═════════════════════════════════════════════════════════════════════════════
# CONTRAINTES DE VALEUR
#
# `CLES_CONNUES` attrape `font_paht`. Elle ne dit rien de `conf_threshold: "0.35"` (une
# chaine), de `taille_min: -5`, ni de `interligne: 12` la ou une fraction est attendue. Ces
# valeurs-la passent la verification sans un mot, puis cassent loin de leur cause — ou, pire,
# ne cassent pas et produisent silencieusement un mauvais rendu sur 150 planches.
#
# Le depot avait deja le bon patron a UN endroit : `LLM._effort` valide `think` contre
# `NIVEAUX_REFLEXION` et leve un `SystemExit` actionnable. On le generalise ici.
#
# ## Une table par NATURE, pas par cle
#
# 91 cles numeriques, mais quatre natures. Ecrire 91 bornes a la main serait une seconde
# reference a maintenir — exactement le defaut que `CLES_CONNUES` documente et que
# `tests/test_config_valide.py` empeche.
#
# ## Deliberement PARTIELLE
#
# ⚠ Une contrainte FAUSSE est pire que pas de contrainte : elle avertit sur une config saine,
# et on cesse alors de lire les avertissements. Ne sont donc declarees que les cles dont la
# borne ne fait aucun doute. Une cle absente d'ici n'est pas « non verifiee par oubli », elle
# est « verifiee nulle part parce qu'on ne sait pas ce qui est sain ».
#
# ## Avertit, ne refuse pas
#
# Meme regle que le reste du module : refuser transformerait une config acceptee en config
# rejetee, soit un changement MAJEUR au sens du CHANGELOG.
# ═════════════════════════════════════════════════════════════════════════════

#: Nature -> (predicat, description lisible). La description part telle quelle dans
#: l'avertissement : elle doit dire ce qui est ATTENDU, pas ce qui est faux.
NATURES: dict[str, tuple] = {
    "fraction": (lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
                 and 0.0 <= float(v) <= 1.0,
                 "un nombre entre 0 et 1"),
    "positif": (lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
                and float(v) > 0,
                "un nombre strictement positif"),
    "positif_ou_nul": (lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
                       and float(v) >= 0,
                       "un nombre positif ou nul"),
    "entier_positif": (lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0,
                       "un entier strictement positif"),
    # 2.0 et non 1.0 : l'API OpenAI accepte jusqu'a 2, et un modele local aussi.
    "temperature": (lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
                    and 0.0 <= float(v) <= 2.0,
                    "une temperature entre 0 et 2"),
}

#: Sous-arbres dont TOUTES les feuilles partagent une nature. Les noms d'agents y sont
#: resolus par le code, mais leurs valeurs sont toutes des temperatures.
PREFIXES_CONTRAINTS: tuple[tuple[str, str], ...] = (
    ("temperatures.", "temperature"),
    ("manga.temperatures.", "temperature"),
)

#: Cle pointee -> nature. Cf. le commentaire ci-dessus : partielle par principe.
CONTRAINTES: dict[str, str] = {
    # — LLM —
    "llm.timeout": "positif",
    "llm.debit_plancher_tok_s": "positif",
    "llm.max_retries": "positif_ou_nul",
    "llm.thinking_budget": "entier_positif",
    "llm.num_ctx": "entier_positif",

    # — Decoupage —
    "decoupage.max_block_chars": "entier_positif",
    "decoupage.max_block_tokens": "entier_positif",
    "decoupage.max_input_tokens": "entier_positif",
    "decoupage.marge_partie_bloc": "fraction",
    "decoupage.epub.titre_max_caracteres": "entier_positif",
    "decoupage.mise_en_forme.ratio_taille_titre": "positif",
    "decoupage.mise_en_forme.footer_frac_pages": "fraction",
    "decoupage.mise_en_forme.footer_bande_page": "fraction",

    # — Garde-fous —
    "garde_fous.perte_mots_ratio.traducteur": "fraction",
    "garde_fous.perte_mots_ratio.correcteur": "fraction",
    "garde_fous.perte_mots_ratio.mise_en_page": "fraction",
    "garde_fous.retry_temperature_facteur": "positif_ou_nul",
    "garde_fous.redecoupage_profondeur_max": "entier_positif",
    "garde_fous.redecoupage_taille_min": "entier_positif",
    "garde_fous.cjk_residuel_seuil": "entier_positif",
    "garde_fous.abandon_apres_timeouts_consecutifs": "entier_positif",

    "naturalisation.intensite": "fraction",

    # — Manga : detection —
    # Ces deux-la sont les plus exposees : elles arrivent aussi par `--conf` / `--iou`, et
    # une chaine venue du YAML remonterait jusqu'au filtrage.
    "manga.detection.conf_threshold": "fraction",
    "manga.detection.iou_threshold": "fraction",
    "manga.detection.fenetre_ratio_min": "positif",
    "manga.detection.fenetre_hauteur": "entier_positif",
    "manga.detection.fenetre_recouvrement": "entier_positif",
    # ⚠ En PIXELS DU CANEVAS, pas en fraction : c'est une constante de détectabilité du
    # réseau. Cf. `detection.OCCUPATION_MIN`. 0 = « dérive-la de `fenetre_ratio_min` ».
    "manga.detection.fenetre_occupation_min": "positif_ou_nul",
    # Part de pixels s'écartant du fond, comme `escalade.seuil_encre`. 0 = porte désarmée.
    "manga.detection.fenetre_encre_min": "fraction",
    "manga.detection.scission.seuil_remplissage": "fraction",
    "manga.detection.scission.remplissage_lobe_min": "fraction",
    "manga.detection.scission.min_lobe_frac": "fraction",
    "manga.detection.scission.aire_min": "entier_positif",
    "manga.detection.scission.seuil_suspect": "fraction",
    # — Lot 13 —
    # `aire_min_frac` remplace `aire_min` quand elle est non nulle : le seuil veut dire
    # « assez grande pour qu'un goulot soit interpretable », et ca se mesure relativement a
    # la planche, pas en pixels. 0.0 = on garde les pixels, et c'est le defaut.
    "manga.detection.scission.aire_min_frac": "fraction",
    "manga.detection.scission.germe_frac": "fraction",
    # 0 = automatique (petit cote de la boite // 3). D'ou `positif_ou_nul`.
    "manga.detection.scission.k_max": "positif_ou_nul",
    "manga.detection.scission.max_lobes": "entier_positif",
    "manga.detection.scission.stabilite": "entier_positif",
    "manga.detection.scission.iou_stabilite": "fraction",
    "manga.detection.scission.remplissage_lobe_relatif": "fraction",
    "manga.detection.scission.remplissage_lobe_plancher": "fraction",
    "manga.detection.scission.encre.part_min": "fraction",
    "manga.detection.scission.encre.facteur_seuil": "fraction",
    "manga.detection.scission.encre.plancher_confirme": "fraction",
    # Resolution d'entree du reseau : un entier positif, arrondi au multiple de 32 par
    # `detection.normaliser_input_size` (qui le DIT quand il arrondit). Le schema ne verifie
    # pas le multiple : ce n'est pas une faute de config, c'est une valeur approchee.
    "manga.detection.input_size": "entier_positif",
    # Une FRACTION de l'aire de la planche, 0.0 compris — c'est le defaut, et il vaut « aucun
    # filtre ». `fraction` accepte bien 0.
    "manga.detection.aire_min_frac": "fraction",
    "manga.detection.escalade.input_size": "entier_positif",
    "manga.detection.escalade.conf_threshold": "fraction",
    "manga.detection.escalade.mediane_frac": "fraction",
    "manga.detection.escalade.mediane_echantillon_min": "entier_positif",
    "manga.detection.escalade.seuil_encre": "fraction",

    # — Manga : onomatopees —
    "manga.onomatopees.seuil_masque": "fraction",
    # Aire minimale d'une COMPOSANTE, avant groupement. `positif_ou_nul` et non
    # `entier_positif` : la valeur est ramenee a 1 au plancher par `hors_des_bulles`, et
    # refuser 0 pour une cle dont 1 est le defaut serait une chicane.
    "manga.onomatopees.min_composante": "positif_ou_nul",
    "manga.onomatopees.containment_bulle": "fraction",
    "manga.onomatopees.aire_min": "entier_positif",
    # Le fenêtrage de la passe hors bulle (lot 14, L6.1). `fenetrage` est un booléen, donc
    # non typé ici — comme `escalade.actif` : le dictionnaire ne vérifie que les nombres, un
    # `true`/`false` mal orthographié est déjà refusé par le lecteur YAML.
    "manga.onomatopees.fenetre_hauteur": "entier_positif",
    "manga.onomatopees.fenetre_recouvrement": "entier_positif",
    "manga.onomatopees.groupement": "positif_ou_nul",
    "manga.onomatopees.mobilier_frac_planches": "fraction",
    "manga.onomatopees.mobilier_iou": "fraction",
    "manga.onomatopees.mobilier_aire_max_frac": "fraction",
    # Lot 21. `fraction` et non `positif` : 0 DESARME la borne, et c'est le defaut livre —
    # la mesure ne separe pas le dessin du texte (docs/mesures/sfx-2026-08-28.md, L21.1). Refuser 0
    # interdirait le seul reglage que la mesure soutient.
    "manga.onomatopees.aire_max_frac": "fraction",
    "manga.onomatopees.remplissage_max": "fraction",
    # Nombre de crops ecrits par tome (voie C). 0 = aucun.
    "manga.onomatopees.crops_illisibles": "positif_ou_nul",
    # Rapport tokens(rendu)/tokens(source) au-dela duquel une traduction d'onomatopee est
    # refusee. Calibre au-dela du 99e centile des 1 596 paires en cache ; 0 desarme.
    # `positif_ou_nul` et non `fraction` : la valeur livree est 3,0.
    "manga.onomatopees.broderie_ratio": "positif_ou_nul",
    # `concordance` est un booleen, donc non type ici — meme raison que `fenetrage`.

    # — Manga : effacement du texte hors bulle (lot 22) —
    # `mode` et `methode` sont des enumerations de chaines, donc non typees ici : le
    # dictionnaire ne verifie que les nombres, et une valeur inconnue retombe sur le defaut du
    # code (`fusion` ignore ce qu'elle ne connait pas).
    "manga.onomatopees.effacement.seuil_uniformite": "fraction",
    "manga.onomatopees.effacement.seuil_abandon": "fraction",
    # Ecart de LUMINANCE, donc 0-255 et non une fraction. Meme nature que `nettoyage.seuil_texte`.
    "manga.onomatopees.effacement.seuil_encre": "positif_ou_nul",
    # Multiple du rayon adaptatif. 0 desarme la dilatation (on peint l'encre franche seule),
    # ce qui est un reglage legitime : d'ou `positif_ou_nul`.
    "manga.onomatopees.effacement.dilatation": "positif_ou_nul",
    "manga.onomatopees.effacement.passes_diffusion": "entier_positif",

    # — Manga : contexte, lot, rattrapage, terminologie —
    "manga.contexte.planches_precedentes": "entier_positif",
    "manga.contexte.repliques_max": "entier_positif",
    "manga.contexte.budget_echantillon": "entier_positif",
    "manga.contexte.max_tokens": "entier_positif",
    "manga.lot.planches": "entier_positif",
    "manga.lot.planches_vision": "entier_positif",
    "manga.lot.plafond_sortie": "entier_positif",
    "manga.rattrapage.max_par_page": "entier_positif",
    "manga.terminologie.min_occurrences": "entier_positif",
    "manga.terminologie.dominance": "positif",

    "manga.nettoyage.marge_bord": "fraction",

    # — Manga : lettrage —
    # Les tailles sont en POINTS, donc des entiers positifs ; les ratios et marges sont des
    # fractions de la bulle. Melanger les deux — `interligne: 12` pour « 12 points » — donne
    # un lettrage grotesque sans le moindre message.
    "manga.typeset.taille_min": "entier_positif",
    "manga.typeset.taille_max": "entier_positif",
    "manga.typeset.taille_min_absolue": "entier_positif",
    "manga.typeset.aire_min_bulle": "entier_positif",
    "manga.typeset.glose_taille_min": "entier_positif",
    "manga.typeset.glose_taille_max": "entier_positif",
    "manga.typeset.glose_ecart": "positif_ou_nul",
    "manga.typeset.glose_marge": "fraction",
    "manga.typeset.marge_interne": "fraction",
    "manga.typeset.contour_epaisseur": "fraction",
    "manga.typeset.contour_epaisseur_sfx": "fraction",
    # Plancher d'aire en px². `positif_ou_nul` : 0 DESARME le plancher, et c'est le defaut
    # livre — `manga.onomatopees.aire_min` borne deja la detection plus haut.
    "manga.typeset.aire_min_sfx": "positif_ou_nul",
    # `sfx_rotation` est un booleen, donc non type ici.
    "manga.typeset.glissement_vertical": "fraction",
    "manga.typeset.interligne": "positif",
    "manga.typeset.interligne_min": "positif",
    "manga.typeset.harmonisation_ratio_max": "positif",

    # — Manga : rendu —
    "manga.rendu.pdf_dpi": "entier_positif",
    "manga.rendu.pdf_qualite": "entier_positif",

    # — Scan —
    "scan.caracteres_par_tranche": "entier_positif",
    "scan.lot_ocr": "entier_positif",
    "scan.colonnes_min": "entier_positif",
    "scan.illustration_encre_max": "fraction",
    "scan.titre_pas_min": "positif",
    "scan.seuil_encre": "fraction",

    # — Illustration (lot 24) —
    # `graine` n'est PAS declaree : `null` y est legitime (« celle de la requete »), 0 aussi,
    # et une borne fausse serait pire que pas de borne. Meme raison pour `guidage`, dont la
    # valeur saine depend du modele et n'est mesuree sur aucun corpus de ce depot.
    "illustration.image.largeur": "entier_positif",
    "illustration.image.hauteur": "entier_positif",
    "illustration.image.pas": "entier_positif",
    "illustration.image.par_requete": "entier_positif",
    "illustration.comfyui.timeout": "positif",
    # 0 est une valeur LÉGITIME : elle désarme le contrôle du cache d'exécution.
    "illustration.comfyui.plancher_secondes": "positif_ou_nul",
    "illustration.identite.references_max": "entier_positif",
    "illustration.identite.cote_reference": "entier_positif",
    "illustration.identite.encodeur.cote": "entier_positif",
    # ⚠ `references_max` est plafonne a 2 par la MESURE du lot 25, pas par le schema : un
    # utilisateur a le droit de monter a 3, le graphe le cable. Ce qui est verifie ici est
    # seulement qu'il ne descend pas a 0 — une requete sans reference retombe sur de la
    # generation pure, ce que le lot 25 refuse deja ailleurs avec un motif nomme.
    "illustration.prompt.references_max": "entier_positif",
    "illustration.prompt.ancrages_max": "positif_ou_nul",
    "illustration.prompt.llm.cote_vision": "entier_positif",
    "illustration.prompt.llm.max_input_tokens": "positif_ou_nul",
    "illustration.budget.images_par_run": "entier_positif",
}


def nature_de(chemin: str) -> str | None:
    """Nature attendue pour une cle pointee, ou `None` si on ne se prononce pas."""
    nature = CONTRAINTES.get(chemin)
    if nature is not None:
        return nature
    for prefixe, nature_prefixe in PREFIXES_CONTRAINTS:
        if chemin.startswith(prefixe):
            return nature_prefixe
    return None
