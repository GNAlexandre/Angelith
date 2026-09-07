# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Apercus et vignettes de l'editeur — le cache d'images de la planche affichee.

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

from PySide6.QtCore import Qt

from . import apercu as apercu_mod
from . import pellicule as pel
from .cache_apercu import fenetre_retenue, fenetre_tenable, signature
from .travailleur import GENRE_APERCU, GENRE_VIGNETTE


class MixinApercus:
    """Composition, mise en cache et invalidation des apercus. Cf. l'en-tete du module."""

    def _figer_plan_apercu(self, numero: int) -> None:
        """Fige, **sur le fil d'affichage**, tout ce qu'il faut pour composer une planche.

        La voie de lecture ne doit jamais parcourir un état que l'utilisateur est en train de
        modifier : une liste de répliques lue pendant qu'on tape produirait un aperçu qui ne
        correspond à rien. On lui remet donc un instantané immuable, et la clé du cache est
        calculée dessus — ce qui fait qu'une correction non enregistrée invalide l'entrée
        toute seule, sans invalidation explicite à écrire donc à oublier."""
        if self.tome is None:
            return
        courante = self.planche if (self.planche and self.planche.index == numero) else None
        planche = courante or self.tome.planche(numero)
        if not planche.detectee or not planche.chemin_clean.exists():
            self._plans_apercu.pop(numero, None)
            return
        document = self.documents.get(numero)
        if document is not None:
            etat = document.etat
            textes = [etat.manuelles.get(k, texte)
                      for k, texte in enumerate(etat.traduction)]
            layouts = dict(etat.mises_en_page)
        else:
            textes = [b.affichee for b in planche.bulles]
            layouts = dict(planche.mises_en_page)
        for k, texte in (self._brouillons_par_planche.get(numero) or {}).items():
            if 0 <= k < len(textes):
                textes[k] = texte
        mcfg = (self.tome.config.get("manga") or {})
        self._plans_apercu[numero] = (
            planche.ckpt_dir, planche.chemin_clean, tuple(textes), layouts,
            (mcfg.get("typeset") or {}).get("font_path") or None,
            mcfg.get("typeset"), mcfg.get("nettoyage"))

    def _cle_apercu(self, numero: int):
        plan = self._plans_apercu.get(numero)
        if plan is None:
            return None
        return signature(numero, plan[1], plan[2], plan[3], plan[4])

    def travail_restant(self, numero: int) -> str | None:
        """Ce qu'il reste à faire pour cette planche. ⚠ Appelé depuis la VOIE DE LECTURE.

        Deux travaux de nature différente, et c'est le fil de lecture qui en tire l'ordre : sa
        **vignette** (toutes les planches en ont une, elle est sur disque et coûte quelques
        dizaines de millisecondes) et son **aperçu** (seulement la fenêtre autour de la planche
        courante, il coûte 1,4 s et pèse 1 Mo en mémoire). Une planche sans plan compte comme
        réglée : il n'y a rien à en faire, et la redemander sans fin affamerait les autres.

        La vignette d'abord dans la réponse comme dans le temps : tant qu'elle manque, c'est
        elle qui manque à l'écran."""
        if self.tome is not None and not pel.vignette_a_jour(self.tome.build_dir, numero):
            return GENRE_VIGNETTE
        if numero not in self._fenetre_apercu:
            return None
        cle = self._cle_apercu(numero)
        return None if (cle is None or cle in self.cache) else GENRE_APERCU

    def apercu_en_cache(self, numero: int) -> bool:
        """La planche est-elle entièrement réglée ? Mince délégué de `travail_restant`,
        conservé parce qu'il est nommé dans la docstring de la voie de lecture et lu comme la
        question qu'on se pose depuis le fil d'affichage."""
        return self.travail_restant(numero) is None

    def fabriquer_vignette(self, numero: int) -> bool:
        """Écrit la vignette d'une planche si elle manque ou a vieilli. ⚠ VOIE DE LECTURE.

        Séparée de `composer_planche`, et ce n'est pas un rangement : les deux partageaient un
        seul code de retour, si bien qu'une vignette fraîchement écrite était perdue dès que la
        suite ne se passait pas bien — aperçu déjà en cache (`return False`), scan source
        introuvable ou composition en échec (exception). Dans les deux derniers cas la planche
        entrait dans la mémoire d'échec du fil et son icône ne revenait plus de la session.
        Deux unités de travail distinctes, deux annonces distinctes."""
        if self.tome is None or pel.vignette_a_jour(self.tome.build_dir, numero):
            return False
        return pel.fabriquer_vignette(self.tome.build_dir, numero) is not None

    def composer_planche(self, numero: int) -> bool:
        """Compose l'aperçu d'une planche et le range au cache.

        ⚠ Appelé depuis la VOIE DE LECTURE : ne touche aucun widget, ne construit aucun
        `QPixmap`, n'écrit aucun checkpoint. Composer exige le SCAN D'ORIGINE — les styles de
        bulle (polarité, couleur de fond) ne se mesurent que là — et l'obtenir peut extraire
        une archive CBZ entière. C'est exactement le genre d'appel que la 1.1.0 faisait sur le
        fil d'affichage."""
        if self.tome is None:
            return False
        plan = self._plans_apercu.get(numero)
        if plan is None or numero not in self._fenetre_apercu:
            return False
        ckpt, chemin_clean, textes, layouts, police, cfg_typeset, cfg_nettoyage = plan
        cle = signature(numero, chemin_clean, textes, layouts, police)
        if cle in self.cache:
            return False
        from . import apercu as apercu_mod
        source = self.tome.chemin_source(numero)
        if source is None:
            raise RuntimeError(
                "image d'origine introuvable sous sources/ : les styles de bulle "
                "(polarité, couleur de fond) ne se lisent que sur le scan.")
        vue = apercu_mod.composer(
            ckpt, chemin_clean, source, textes=list(textes), font_path=police,
            cfg_typeset=cfg_typeset, cfg_nettoyage=cfg_nettoyage, layouts=layouts)
        self.cache.poser(cle, vue)
        return True

    def _precharger(self) -> None:
        """Demande à la voie de lecture la fenêtre de planches autour de la courante.

        C'est tout le lot de fluidité : composer coûte 1,37 s en médiane, et l'utilisateur ne
        doit jamais l'attendre pour une planche qu'il allait forcément atteindre."""
        if self.fil_lecture is None or self.planche is None or self.tome is None:
            return
        numeros = [int(self.liste_planches.item(ligne).data(Qt.UserRole))
                   for ligne in range(self.liste_planches.count())]
        if not numeros:
            return
        courante = self.planche.index
        rang = numeros.index(courante) if courante in numeros else 0
        marge = self.fenetre_prechargement
        # Deux portées, et c'est délibéré : les APERÇUS ne couvrent que la fenêtre (bornée en
        # mémoire), les VIGNETTES couvrent tout le tome (sur disque, une fois).
        voulues = numeros[max(0, rang - marge): rang + marge + 1]
        # ⚠ …et une TROISIÈME borne, mesurée : le plafond du cache. Une fenêtre de 21 planches
        # à 9,35 Mo pièce demande ~196 Mo là où le plafond en tient 120 ; le cache évinçait
        # alors ce que la voie de lecture venait de composer, qui le recomposait aussitôt —
        # 136 compositions pour 12 aperçus gardés en 120 s, mesuré au rang 60 d'un tome de 118
        # planches (`docs/mesures/retouche-2026-09-05.md`). La décision est dans
        # `gui/cache_apercu.py`, sans Qt, avec ses tests.
        self._fenetre_tenable = fenetre_tenable(
            self.cache.plafond, self.cache.poids_moyen(), len(voulues))
        self._fenetre_demandee = len(voulues)
        self._fenetre_apercu = set(
            fenetre_retenue(voulues, courante, self._fenetre_tenable))
        for numero in self._fenetre_apercu:
            if numero not in self._plans_apercu:
                self._figer_plan_apercu(numero)
        self.fil_lecture.vouloir(numeros, courante)

    def _poser_apercu_si_pret(self, numero: int) -> bool:
        """Pose les calques déjà en cache. Sur le FIL D'AFFICHAGE — une scène Qt ne se touche
        jamais depuis un autre fil, et un `QPixmap` ne se construit pas ailleurs."""
        if self.planche is None or self.planche.index != numero:
            return False
        if self.bouton_finale.isChecked():
            return False
        cle = self._cle_apercu(numero)
        if cle is None:
            return False
        vue = self.cache.lire(cle)
        if vue is None:
            return False
        # ⚠ On garde la référence : c'est cet aperçu qui porte les `StyleCompact`, donc la
        # possibilité de ré-habiller une bulle en quelques millisecondes au lieu de 1,37 s.
        self._apercu_courant = vue
        self.scene.poser_calques(vue.calques)
        return True

    def _recomposer_courante(self) -> None:
        """Ce qui est affiché vient de changer : on refige le plan et on redemande.

        La nouvelle signature ne correspond à aucune entrée du cache, donc la voie de lecture
        recompose ; l'ancienne reste au cache et servira si l'on annule."""
        if self.planche is None:
            return
        numero = self.planche.index
        self._figer_plan_apercu(numero)
        if not self._poser_apercu_si_pret(numero):
            self._precharger()

    def apercu_pret(self, numero: int) -> None:
        """La voie de lecture vient de composer une planche (aperçu et/ou vignette).

        ⚠ **La fenêtre se resserre ICI, et c'est le seul endroit où elle le peut.** À
        l'ouverture le cache est vide : `fenetre_tenable` ne sait rien du poids d'un aperçu de
        ce tome et ne bride donc rien — c'est délibéré, deviner un poids serait remplacer une
        valeur fausse par une autre. Le premier aperçu composé donne la vraie mesure, et c'est
        ce passage qui la fait redescendre dans la fenêtre. Sans lui, la borne n'arriverait
        qu'au prochain changement de planche, c'est-à-dire trop tard : l'emballement a lieu
        pendant qu'on regarde la première."""
        item = self._item_de(numero)
        if item is not None:
            self._parer_item(item, numero)
        self._poser_apercu_si_pret(numero)
        self._resserrer_fenetre()

    def _resserrer_fenetre(self) -> None:
        """Redemande un préchargement si la fenêtre promet plus que le plafond ne garde.

        ⚠ Le test d'abord, l'appel ensuite : `_precharger` parcourt la pellicule entière
        (226 items sur le plus gros tome du corpus) et il est appelé à chaque aperçu prêt.
        Le comparateur, lui, coûte une division."""
        if self.fil_lecture is None or self.planche is None:
            return
        poids = self.cache.poids_moyen()
        if poids <= 0:
            return
        tenable = fenetre_tenable(self.cache.plafond, poids,
                                  getattr(self, "_fenetre_demandee", 0)
                                  or len(self._fenetre_apercu))
        if tenable < len(self._fenetre_apercu):
            self._precharger()

    def oublier_apercu(self, numero: int) -> None:
        """Un run a réécrit cette planche : son aperçu ne vaut plus rien."""
        self.cache.oublier_planche(numero)
        self.cache_etats.oublier(numero)
        self._plans_apercu.pop(numero, None)
        if self.fil_lecture is not None:
            self.fil_lecture.reessayer(numero)

    def invalider_document(self, numero: int) -> None:
        """Jette le document EN MÉMOIRE d'une planche : le disque fait désormais foi.

        ⚠ À appeler après **toute** édition de zone. `manga/edition.py` écrit directement sur
        disque depuis le fil de travail, en passant par `document.poser_regions` qui réordonne
        et remappe correctement — mais le document que l'éditeur garde en mémoire, lui, reste
        à l'état d'avant. `_appliquer_document` réaligne PAR POSITION : sans cette invalidation,
        il recolle les anciens textes sur les nouvelles bulles, chaque réplique après le point
        d'insertion glisse d'un cran, et `poser_correction` finit par lever sur un index que le
        document périmé ne connaît pas.

        Les brouillons ne sont PAS jetés : ils sont re-cléfés par géométrie au rechargement
        (cf. `_resuivre_brouillons`)."""
        self.documents.pop(numero, None)

    def _rafraichir_bulle_rapide(self, index: int, *, rect=None, masque=None,
                                 taille: int | None = None, force: bool = False) -> bool:
        """Ré-habille la bulle `index` et remplace son calque **sans détruire l'item**.

        `False` si le chemin rapide n'était pas disponible (aperçu pas encore composé, texte
        vide, corps intenable) : l'appelant laisse alors le geste continuer sans texte plutôt
        que d'échouer bruyamment. Un geste qui s'interrompt pour annoncer une erreur est pire
        qu'un geste dont le texte arrive un peu plus tard.

        ## L'étranglement, et pourquoi il est adaptatif

        `force=True` (un relâchement, une fin de frappe) passe toujours. Sinon on espace les
        appels d'au moins deux fois le coût du précédent, avec un plancher de 40 ms. Un
        intervalle fixe à 25 Hz saturerait le fil d'affichage sur une planche lourde, et c'est
        alors le RECTANGLE lui-même qui se met à saccader — on aurait échangé un texte en
        retard contre un geste qui accroche. En mesurant, une planche lourde s'auto-régule.

        ⚠ Le relâchement doit **toujours** repasser ici avec `force`. Le mode de panne
        classique d'un étranglement est de perdre le dernier événement, donc de laisser à
        l'écran un texte qui ne correspond pas à la position réellement déposée."""
        vue = self._apercu_courant
        if vue is None or self.planche is None or self.bouton_finale.isChecked():
            return False
        if not force:
            attente = max(40.0, 2.0 * self._cout_rapide_ms)
            if self._dernier_rapide.elapsed() < attente:
                return False
        bulle = self._bulle(index)
        if bulle is None:
            return False
        texte = self._brouillons.get(index, bulle.affichee)
        if taille is None:
            taille = self._corps_affiche(index) or None

        self._chrono_rapide.start()
        try:
            calque = apercu_mod.recomposer_bulle(vue, index, texte, rect=rect, taille=taille,
                                                 masque=masque)
        except Exception as err:                # noqa: BLE001
            # Un ré-habillage est du CONFORT : il ne doit jamais faire tomber un geste en
            # cours. Le journal garde la trace, la composition complète tranchera.
            self.journal.emit("warn", f"Aperçu rapide indisponible : {err}")
            return False
        finally:
            self._cout_rapide_ms = float(self._chrono_rapide.elapsed())
            self._dernier_rapide.restart()
        if calque is None:
            return False
        return self.scene.remplacer_calque(calque)

    def _corps_affiche(self, index: int) -> int:
        """La valeur à montrer dans le réglage de corps. `0` (« auto ») si rien n'est imposé."""
        mises = self.planche.mises_en_page if self.planche else {}
        impose = (mises.get(index) or {}).get("taille")
        return int(impose or 0)
