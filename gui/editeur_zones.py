# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Gestes d'edition de zone — dessiner, retailler, scinder, relire, retraduire.

## Pourquoi ce fichier existe

`gui/editeur.py` avait atteint 2 088 lignes et 96 methodes sur une seule classe. Les methodes
y sont courtes — le probleme n'etait pas la testabilite mais la NAVIGATION : trouver le
chemin d'un apercu au milieu des gestionnaires de zones demandait de parcourir tout le
fichier.

⚠ Ce module est un **deplacement**, pas une reecriture. Les corps de methodes sont repris au
caractere pres, a la meme indentation, pour que le diff reste lisible. C'est exactement
l'argument que `manga/orchestrator_manga.py` avance pour ne PAS reindenter `_process_volume` :
un refactor qu'on ne peut pas relire n'est pas un refactor, c'est un pari.

## Comment ca se branche

Un mixin, herite par `PanneauEditeur`. Il n'a donc ni `__init__` ni etat propre : tous les
attributs qu'il touche (`self.tome`, `self.planche`, `self.cache`, `self.scene`…) sont poses
par `PanneauEditeur.__init__` et restent sa responsabilite. C'est le prix assume d'un
decoupage par SUJET plutot que par dependance — le sujet est ce qu'on cherche quand on ouvre
le fichier.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from manga import checkpoints
from manga import document as doc_mod
from manga import edition, geometry

from . import apercu as apercu_mod
from .travailleur import (GENRE_EDITION, GENRE_OCR, GENRE_REPRISE, GENRE_TRADUCTION, Tache)


def _resume_edition(res: dict) -> str:
    """Ce qu'on affiche après une édition de zone — y compris ce que le nettoyage a refusé."""
    bouts = [f"{res['regions']} bulle(s)", f"{res['textes_conserves']} texte(s) conservé(s)"]
    if res.get("indices_a_relire"):
        bouts.append("à relire : " + ", ".join(str(i + 1) for i in res["indices_a_relire"]))
    net = res.get("nettoyage")
    if net:
        if net["videes"]:
            bouts.append(f"{net['videes']} zone(s) vidée(s)")
        if net["restaurees"]:
            bouts.append(f"{net['restaurees']} zone(s) rendue(s) au dessin")
        if net["abandons"]:
            bouts.append("⚠ nettoyage abandonné (intérieur trop peu uniforme) : le japonais "
                         "reste visible")
    return " · ".join(bouts)


def _bbox(boite) -> tuple[int, int, int, int]:
    """`QRectF` de scène → bbox entière en pixels de planche."""
    return (int(round(boite.left())), int(round(boite.top())),
            int(round(boite.right())), int(round(boite.bottom())))


class MixinZones:
    """Tout ce qui MODIFIE une bulle. Cf. l'en-tete du module."""

    def _contexte(self) -> edition.ContextePlanche | None:
        """Le contexte qui autorise la repeinte de `pages_clean/`.

        `None` quand l'image source est introuvable : l'opération se fera alors en
        métadonnées seules, et l'appelant le dit — mieux vaut une zone non vidée annoncée
        qu'un échec opaque.

        ⚠ Coûteux au PREMIER appel d'un tome : `chemin_source` déclenche
        `sources_manga.scan_volume`, qui extrait une archive CBZ entière. Ne pas l'appeler
        depuis un gestionnaire d'événement — passer par `_fabrique_contexte`."""
        if self.tome is None or self.planche is None:
            return None
        return self._fabrique_contexte()()

    def _fabrique_contexte(self):
        """Rend une fonction sans argument qui construira le contexte **là où on l'appellera**.

        Tout ce qui est bon marché (le tome, l'index, les chemins, la config) est capturé
        maintenant, sur le fil d'affichage ; la seule opération chère — la résolution de
        l'image source, qui peut extraire un CBZ entier — est repoussée dans la file de
        travail. C'est ce qui enlève le gel au relâchement de la souris."""
        if self.tome is None or self.planche is None:
            return lambda: None
        tome, index = self.tome, self.planche.index
        clean, cfg = (self.planche.chemin_clean,
                      (self.tome.config.get("manga") or {}).get("nettoyage"))

        def _construire():
            source = tome.chemin_source(index)
            if source is None:
                return None
            return edition.ContextePlanche(
                image_source=source, chemin_clean=clean, cfg_nettoyage=cfg)

        return _construire

    def _soumettre(self, genre: str, libelle: str, fonction, *,
                   fusionnable: bool = False, discret: bool = False) -> None:
        if self.fil is None or self.planche is None:
            return
        planche = self.planche.index
        cle = (planche, genre) if fusionnable else None
        accepte = self.fil.soumettre(Tache(genre=genre, fonction=fonction, planche=planche,
                                           libelle=libelle, cle_fusion=cle))
        # `discret` : la composition d'aperçu tourne à chaque changement de planche.
        # La journaliser noierait les messages qui comptent sous un défilé de routine.
        if not discret:
            self.journal.emit("info", f"{libelle}…" if accepte
                              else f"{libelle} : déjà en attente, demande fusionnée")

    def _executer_edition(self, operation, description: str, *, suivre=None) -> None:
        """Une édition de zone : vérification de fraîcheur ICI (sur le fil d'affichage, où la
        boîte de dialogue est légale), exécution LÀ-BAS (dans la file).

        `suivre` est la boîte de la zone manipulée. Après l'édition la planche est rechargée et
        la sélection perdue ; on la retrouve par cette géométrie (cf. `_resuivre_zone`), parce
        que `reading_order` a pu réordonner les index entre-temps."""
        if not self._verifier_fraicheur():
            return
        if suivre is not None and self.planche is not None:
            self._zone_a_resuivre = (self.planche.index, tuple(suivre))
        # Instantané des brouillons AVANT l'édition : une insertion décale les index, et une
        # réplique tapée mais non retenue doit suivre SA bulle. On la repère par sa géométrie,
        # au même seuil que `_resuivre_zone` — c'est la même question, elle ne peut pas avoir
        # deux réponses.
        if self.planche is not None and self._brouillons:
            self._brouillons_a_resuivre = (
                self.planche.index,
                [(tuple(b.bbox), self._brouillons[b.index])
                 for b in self.planche.bulles if b.index in self._brouillons])
        # ⚠ Le document est VIDÉ SUR DISQUE avant de lâcher l'édition. `poser_regions` remappe
        # les corrections manuelles qu'il trouve dans le cache — pas celles restées en mémoire.
        # Sans ce vidage, une correction posée mais pas encore écrite serait perdue par
        # l'invalidation qui suit. Les brouillons, eux, ne sont PAS écrits : ils suivent leur
        # bulle par géométrie (cf. `_resuivre_brouillons`).
        self._vider_document_avant_edition()
        self._soumettre(GENRE_EDITION, description, lambda: _resume_edition(operation()))

    def _vider_document_avant_edition(self) -> None:
        """Écrit les corrections déjà posées, pour qu'elles survivent au réordonnancement."""
        if self.planche is None or self.tome is None:
            return
        document = self.documents.get(self.planche.index)
        if document is None or not document.modifie:
            return
        try:
            document.enregistrer(revision_actuelle=self.tome.revision())
        except doc_mod.ErreurDocument as err:
            self.journal.emit(
                "warn", f"Planche {self.planche.index} : corrections non écrites avant "
                        f"l'édition ({err}) — elles risquent d'être perdues.")

    def _sur_zone_dessinee(self, boite, forme: str) -> None:
        if self.planche is None:
            return
        bbox, ckpt, fab = _bbox(boite), self.planche.ckpt_dir, self._fabrique_contexte()
        self._executer_edition(
            lambda: edition.ajouter_zone(ckpt, bbox, forme=forme, ctx=fab()),
            f"Planche {self.planche.index} : zone ajoutée")

    def _sur_zone_modifiee(self, index: int, boite, forme: str) -> None:
        if self.planche is None or index < 0:
            return
        bbox, ckpt, fab = _bbox(boite), self.planche.ckpt_dir, self._fabrique_contexte()
        self._executer_edition(
            lambda: edition.modifier_zone(ckpt, index, bbox, forme=forme, ctx=fab()),
            f"Planche {self.planche.index} : bulle {index + 1} redessinée")

    def _sur_coupe(self, index: int, ligne) -> None:
        if self.planche is None or index < 0:
            return
        coupe = ((ligne.x1(), ligne.y1()), (ligne.x2(), ligne.y2()))
        ckpt, fab = self.planche.ckpt_dir, self._fabrique_contexte()
        self._executer_edition(
            lambda: edition.scinder_zone(ckpt, index, coupe, ctx=fab()),
            f"Planche {self.planche.index} : bulle {index + 1} scindée")

    def _sur_texte_deplace(self, index: int, rect) -> None:
        """Un bloc de texte vient d'être déposé ailleurs.

        Son rectangle part dans `mise_en_page.json` — que le pipeline ne réécrit jamais, comme
        `traduction_manuelle.json` — puis l'aperçu est recomposé pour rejouer l'habillage sur
        la nouvelle zone. Le déplacement lui-même était instantané ; seul le ré-habillage
        coûte, et il n'arrive qu'au dépôt."""
        if self.planche is None or self.tome is None:
            return
        if not self._verifier_fraicheur():
            self.rafraichir()
            return
        if self.document is None:
            return
        # ⚠ La taille vient de l'ITEM, qui la porte depuis sa construction. L'ancien code la
        # cherchait dans un `_calques_prets` qui n'a jamais été assigné nulle part : la branche
        # était morte, `taille` ne partait donc pas dans `mise_en_page.json`, `fit_impose`
        # prenait `taille_max` par défaut, échouait, et le corps se retrouvait RECALCULÉ après
        # un simple déplacement — l'exact contraire de ce que la docstring promettait.
        item = self.scene.calque(index)
        entree = apercu_mod.entree_mise_en_page(item, rect=_bbox(rect))
        self.document.poser_mise_en_page(index, entree)
        self.planche.mises_en_page = dict(self.document.etat.mises_en_page)
        self._maj_etat_document()
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"position retenue — Ctrl+S pour l'écrire")
        # ⚠ Un dernier passage FORCÉ : sans lui, l'étranglement aurait pu avaler le tout
        # dernier mouvement et laisser à l'écran un texte décalé de la position déposée.
        self._rafraichir_bulle_rapide(index, rect=_bbox(rect), force=True)
        self._recomposer_courante()

    def _sur_texte_glisse(self, index: int, rect) -> None:
        """Le bloc de texte suit la souris : on le ré-habille dans son rectangle visé."""
        self._rafraichir_bulle_rapide(index, rect=_bbox(rect))

    def _sur_zone_en_cours(self, index: int, boite) -> None:
        """Une poignée (ou le cadre) bouge : le texte se ré-habille dans le masque étiré.

        ⚠ Le masque est calculé ici, avant toute écriture. C'est ce qui permet de voir le
        résultat exact pendant qu'on tire, et non un rectangle vide qu'on remplirait après
        coup."""
        masque = self._masque_etire(index, boite)
        if masque is not None:
            self._rafraichir_bulle_rapide(index, masque=masque)

    def _masque_etire(self, index: int, boite):
        """Le masque qu'aurait la zone `index` si elle était retaillée à `boite`. `None` si le
        calcul échoue — une boîte dégénérée pendant un geste n'est pas une erreur."""
        bulle = self._bulle(index)
        if bulle is None or self.planche is None:
            return None
        # ⚠ Le document D'ABORD. L'ordre inverse appelait `load_regions` — décodage de
        # `masks.png` PLEINE PAGE et reconstruction des masques numpy de toutes les bulles —
        # pour jeter le résultat la ligne suivante, puisqu'un document existe toujours dès que
        # la planche est chargée. Et cette fonction est appelée à CHAQUE événement de mouvement
        # de souris pendant qu'on tire une poignée : c'était un décodage PNG complet par pixel
        # parcouru. Le repli disque ne sert plus qu'au cas, théorique, du document absent.
        if self.document is not None:
            regions = self.document.etat.regions
        else:
            regions = checkpoints.load_regions(self.planche.ckpt_dir)
        if not regions or not (0 <= index < len(regions)):
            return None
        region = regions[index]
        hauteur, largeur = region.mask.shape[:2]
        try:
            return edition.etirer_masque(region.mask, region.bbox, _bbox(boite),
                                         (largeur, hauteur))
        except edition.ErreurEdition:
            return None

    def _sur_zone_retaillee(self, index: int, boite) -> None:
        """La zone détectée a été déposée à une nouvelle taille (ou à une nouvelle place).

        ⚠ `retailler_zone`, pas `modifier_zone` : la bulle reste la même bulle, elle garde donc
        son OCR et sa traduction. « Redessiner » reste le geste qui repart de zéro, et c'est à
        lui qu'il revient de les jeter.

        L'écriture part dans la file : elle réécrit `regions.json`, `masks.png`, et **repeint
        la planche nettoyée** — ouverture du scan d'origine comprise. C'est de l'ordre de la
        seconde, donc hors de question pendant le geste ; le direct s'est arrêté à l'aperçu."""
        if self.planche is None or index < 0:
            return
        bbox, ckpt, fab = _bbox(boite), self.planche.ckpt_dir, self._fabrique_contexte()
        self._executer_edition(
            lambda: edition.retailler_zone(ckpt, index, bbox, ctx=fab()),
            f"Planche {self.planche.index} : bulle {index + 1} retaillée", suivre=bbox)

    def _resuivre_brouillons(self) -> None:
        """Ré-attache les brouillons à leur bulle après une édition qui a bougé les index.

        Un brouillon dont la zone a disparu (bulle supprimée, ou trop déformée pour être
        reconnue sous `edition.SEUIL_REPORT`) est abandonné — et **on le dit**. Le reposer au
        jugé écrirait une réplique dans la mauvaise bulle, ce qui est pire que de la perdre :
        une perte se voit, un déplacement silencieux se découvre au rendu final."""
        vise, self._brouillons_a_resuivre = self._brouillons_a_resuivre, None
        if vise is None or self.planche is None or self.planche.index != vise[0]:
            return
        anciennes = [bbox for bbox, _texte in vise[1]]
        nouvelles = [tuple(b.bbox) for b in self.planche.bulles]
        suivi = geometry.suivre_boites(anciennes, nouvelles, edition.SEUIL_REPORT)
        garde = {suivi[i]: texte for i, (_bbox, texte) in enumerate(vise[1]) if i in suivi}
        perdus = len(vise[1]) - len(garde)
        self._brouillons_par_planche[self.planche.index] = garde
        if perdus:
            self.journal.emit(
                "warn", f"Planche {self.planche.index} : {perdus} saisie(s) en cours "
                        f"abandonnée(s) — leur bulle n'existe plus après cette édition.")

    def _resuivre_zone(self) -> None:
        """Resélectionne, après une édition, la zone qu'on venait de manipuler.

        ⚠ **L'index n'est pas une identité stable.** `poser_regions` recalcule l'ordre de
        lecture : agrandir une bulle vers le haut peut la faire passer devant sa voisine, et
        tout se décale. On la retrouve donc par sa géométrie, au même seuil que
        `edition.SEUIL_REPORT` — c'est la même question (« est-ce la même bulle ? »), et deux
        seuils pour une seule question finiraient par se contredire.

        Sous le seuil, on ne sélectionne rien : mieux vaut aucune sélection qu'une sélection
        fausse, qui ferait porter le geste suivant sur une autre bulle."""
        vise, self._zone_a_resuivre = self._zone_a_resuivre, None
        if vise is None or self.planche is None or self.planche.index != vise[0]:
            return
        candidates = [(geometry.iou_bbox(b.bbox, vise[1]), b.index)
                      for b in self.planche.bulles]
        if not candidates:
            return
        score, index = max(candidates)
        if score >= edition.SEUIL_REPORT:
            self.liste_bulles.setCurrentRow(index)

    def _sur_corps(self, valeur: int) -> None:
        """Le réglage de corps a bougé : l'aperçu suit tout de suite, le document plus tard.

        Les deux minuteurs ont des durées très différentes, et c'est le point : voir doit être
        immédiat, s'engager ne doit pas l'être (cf. `_minuteur_corps`)."""
        if self._index_affiche < 0:
            return
        self._corps_en_attente = (self._index_affiche, int(valeur))
        self._rafraichir_bulle_rapide(self._index_affiche, taille=int(valeur) or None,
                                      force=True)
        self._minuteur_corps.start()

    def _deposer_corps(self) -> None:
        """Écrit le corps choisi dans le document (en mémoire, annulable).

        ⚠ L'entrée n'a **pas** de `rect`. Fabriquer un rectangle depuis la bbox pour la seule
        raison qu'on change la taille remplacerait l'intérieur du ballon par ses quatre coins
        (`typeset.style_impose`), et le texte s'écrirait par-dessus le contour dessiné. Un
        corps seul laisse le masque mesuré intact."""
        attente, self._corps_en_attente = self._corps_en_attente, None
        if attente is None or self.planche is None or self.document is None:
            return
        index, valeur = attente
        if not self._verifier_fraicheur():
            self.rafraichir()
            return
        ancienne = dict(self.planche.mises_en_page.get(index) or {})
        if valeur:
            ancienne["taille"] = int(valeur)
            ancienne.setdefault("ancre", "libre")
        else:
            ancienne.pop("taille", None)        # « auto » : on rend la taille au moteur
        entree = ancienne if (ancienne.get("rect") or ancienne.get("taille")) else None

        self.document.poser_mise_en_page(index, entree)
        self.planche.mises_en_page = dict(self.document.etat.mises_en_page)
        self._maj_etat_document()
        self.bouton_corps_auto.setEnabled(index in self.planche.mises_en_page)
        corps = f"corps {valeur} px" if valeur else "corps rendu au moteur"
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"{corps} — Ctrl+S pour l'écrire")
        self._recomposer_courante()


    def _supprimer_zone(self) -> None:
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0:
            return
        ckpt, fab = self.planche.ckpt_dir, self._fabrique_contexte()
        self._executer_edition(
            lambda: edition.supprimer_zone(ckpt, index, ctx=fab()),
            f"Planche {self.planche.index} : bulle {index + 1} supprimée")

    def _retirer_correction(self) -> None:
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0 or not self._verifier_fraicheur():
            return
        if self.document is None:
            return
        self.document.poser_correction(index, None)
        self._brouillons.pop(index, None)
        self._appliquer_document()
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"correction manuelle retirée — Ctrl+S pour l'écrire")

    def _prerequis_bulle(self) -> tuple | None:
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0 or self.tome is None or self.services is None:
            return None
        return index, self.planche.ckpt_dir, (self.tome.config.get("manga") or {})

    def _relire_bulle(self) -> None:
        prets = self._prerequis_bulle()
        if prets is None:
            return
        index, ckpt, mcfg = prets
        services, tome, numero = self.services, self.tome, self.planche.index

        def _travail():
            source = tome.chemin_source(numero)          # peut extraire un CBZ : dans la file
            if source is None:
                raise edition.ErreurEdition(
                    "l'image d'origine de cette planche est introuvable sous sources/ — "
                    "l'OCR ne peut pas relire la bulle.")
            texte = edition.relire_zone(ckpt, source, index, cfg_manga=mcfg,
                                        lecteur=services.lecteur())
            return f"Bulle {index + 1} relue : « {texte[:60]} »"

        self._soumettre(GENRE_OCR, f"Relecture OCR de la bulle {index + 1}", _travail,
                        fusionnable=True)

    def _retraduire_bulle(self) -> None:
        prets = self._prerequis_bulle()
        if prets is None:
            return
        index, ckpt, _mcfg = prets
        services = self.services

        def _travail():
            texte, motif = edition.retraduire_zone(
                ckpt, index, services.traducteur(), gloss_text=services.gloss_text(),
                langue=services.langue, pack=services.pack())
            if motif is not None:
                from manga.quality_manga import LIBELLES_RATTRAPAGE
                raise RuntimeError(
                    f"réponse refusée — {LIBELLES_RATTRAPAGE.get(motif, motif)} ; "
                    f"la réplique précédente est conservée")
            return f"Bulle {index + 1} : « {texte[:60]} »"

        self._soumettre(GENRE_TRADUCTION, f"Retraduction de la bulle {index + 1}", _travail,
                        fusionnable=True)

    def _reprendre_bulle(self) -> None:
        """Le bouton unique : vide la zone, la lit, la traduit."""
        prets = self._prerequis_bulle()
        if prets is None:
            return
        index, ckpt, mcfg = prets
        ctx = self._contexte()
        if ctx is None:
            QMessageBox.warning(self, "Image source introuvable",
                                "L'image d'origine est nécessaire pour vider la zone et la "
                                "relire. Elle n'a pas été retrouvée sous sources/.")
            return
        services = self.services

        def _travail():
            compte = edition.reprendre_zone(
                ckpt, index, ctx=ctx, lecteur=services.lecteur(), langue=services.langue,
                agent=services.traducteur(), gloss_text=services.gloss_text(),
                cfg_manga=mcfg)
            if compte["refus"] == "nettoyage_abandonne":
                return (f"Bulle {index + 1} : intérieur trop peu uniforme pour être vidé "
                        f"sans abîmer le dessin — le japonais reste visible.")
            if compte["refus"]:
                raise RuntimeError(f"traduction refusée ({compte['refus']}) ; la zone est "
                                   f"vidée et lue, la réplique reste à faire")
            return f"Bulle {index + 1} vidée, lue et traduite : « {compte['traduction']} »"

        self._soumettre(GENRE_REPRISE, f"Reprise complète de la bulle {index + 1}", _travail)

    def _rendre_au_moteur(self) -> None:
        """Retire la mise en page imposée : la bulle retrouve le lettrage calculé.

        ⚠ Cette méthode existait déjà, complète et documentée — mais n'était **branchée à
        aucun bouton**. Le seul candidat plausible (`bouton_rendre`) pointe `_retirer_correction`,
        qui est un tout autre geste : l'un rend le TEXTE au modèle, l'autre rend sa POSITION au
        moteur. Il n'y avait donc aucun moyen d'annuler un déplacement hors Ctrl+Z."""
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0 or not self._verifier_fraicheur():
            return
        if self.document is None:
            return
        self._minuteur_corps.stop()             # le dépôt en attente n'a plus d'objet
        self._corps_en_attente = None
        self.document.poser_mise_en_page(index, None)
        self.planche.mises_en_page = dict(self.document.etat.mises_en_page)
        self._maj_etat_document()
        self._afficher_bulle(index)             # le réglage de corps repasse à « auto »
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"mise en page rendue au moteur — Ctrl+S pour l'écrire")
        self._rafraichir_bulle_rapide(index, force=True)
        self._recomposer_courante()
