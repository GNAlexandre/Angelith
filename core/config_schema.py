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
    "decoupage.mise_en_forme.titres_exclus", "garde_fous",
    "garde_fous.abandon_apres_timeouts_consecutifs", "garde_fous.cjk_residuel_seuil",
    "garde_fous.perte_mots_ratio", "garde_fous.perte_mots_ratio.correcteur",
    "garde_fous.perte_mots_ratio.mise_en_page", "garde_fous.perte_mots_ratio.traducteur",
    "garde_fous.redecoupage_profondeur_max", "garde_fous.redecoupage_sur_echec",
    "garde_fous.redecoupage_taille_min", "garde_fous.retry_temperature_facteur", "gui",
    "gui.apercu", "gui.apercu.fenetre", "gui.apercu.plafond_mo", "langues",
    "langues.appliquer_traductions_forcees", "langues.dossiers",
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
    "manga.detection.telechargement_auto", "manga.lot", "manga.lot.plafond_sortie",
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
    "manga.onomatopees", "manga.onomatopees.actif", "manga.onomatopees.aire_min",
    "manga.onomatopees.containment_bulle", "manga.onomatopees.groupement",
    "manga.onomatopees.mobilier_aire_max_frac", "manga.onomatopees.mobilier_frac_planches",
    "manga.onomatopees.mobilier_iou", "manga.onomatopees.mode",
    "manga.onomatopees.model_path", "manga.onomatopees.model_url",
    "manga.onomatopees.seuil_masque", "manga.onomatopees.telechargement_auto",
    "manga.rapport", "manga.rapport.max_lignes_section", "manga.rapport.seuil_confiance",
    "manga.rattrapage", "manga.rattrapage.actif", "manga.rattrapage.max_par_page",
    "manga.rendu", "manga.rendu.formats", "manga.rendu.langue_iso", "manga.rendu.pdf_dpi",
    "manga.rendu.pdf_largeur_max", "manga.rendu.pdf_qualite", "manga.rendu.psd_original",
    "manga.rendu.psd_texte", "manga.rendu.sens_lecture", "manga.temperatures",
    "manga.temperatures.glossariste", "manga.temperatures.manga_contexte",
    "manga.temperatures.manga_onomatopees", "manga.temperatures.manga_traducteur",
    "manga.temperatures.terminologue", "manga.terminologie", "manga.terminologie.actif",
    "manga.terminologie.dominance", "manga.terminologie.min_occurrences", "manga.typeset",
    "manga.typeset.aire_min_bulle", "manga.typeset.cesure_traits_union",
    "manga.typeset.contour", "manga.typeset.contour_epaisseur", "manga.typeset.debordement",
    "manga.typeset.font_path", "manga.typeset.font_path_gras",
    "manga.typeset.font_path_italique", "manga.typeset.glissement_vertical",
    "manga.typeset.glose_contour", "manga.typeset.glose_ecart", "manga.typeset.glose_marge",
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
})
