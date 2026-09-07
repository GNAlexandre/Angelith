# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Règles typographiques de la langue CIBLE, compilées une fois par run.

## Pourquoi ici et pas dans `core/`

Ces règles servent au découpage des dialogues et au rendu `docx`/`epub` : des artefacts du
LIGHT NOVEL. `tests/test_core_cli.py` interdit qu'une clé de rendu de brique remonte dans le
socle, et `core.langues.Pack.fichier` documente la frontière. Le socle sert les DONNÉES du
pack ; la brique sait ce qu'elle en fait.

## Pourquoi une classe et pas des constantes de module

`pipeline/render.py` portait `_DIALOGUE_SPAN`, `_SPEECH_VERB_START` et `_SENTENCE_END` en
constantes compilées à l'import. Elles étaient donc les mêmes pour tout le processus, ce qui
allait très bien tant que la seule langue cible était le français.

## Le cas qui commande la conception : les verbes de parole

`_SPEECH_VERB_START` n'est pas un caractère à paramétrer, c'est un **lexique** de ~40 verbes
français conjugués, forme inversée comprise (`dit-il`, `hurla-t-elle`). Il décide si l'incise
qui suit une réplique lui reste collée.

Cette construction **n'a pas d'équivalent mécanique dans toutes les langues** : l'anglais
écrit `"...," he said`, sans inversion ni conjugaison à énumérer. Fournir une « autre liste »
ne suffirait donc pas — il faut pouvoir ne pas coller d'incise du tout.

D'où `verbes_de_parole = None` quand le pack ne déclare rien : le rendu n'essaie pas, plutôt
que d'essayer selon des règles françaises. C'est ce que l'inventaire appelait « une fonction
du pack, pas une donnée » (cf. `docs/mesures/inventaire-couplage-fr.md`, §4).

⚠ Les défauts de ce module sont les valeurs françaises EXACTES d'avant l'externalisation. Ils
ne sont pas un « français raisonnable » : ils sont le comportement de référence, et le mode
compatibilité en dépend au bit près.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Guillemets de dialogue français. Le rendu s'en sert pour REPÉRER une réplique.
GUILLEMETS_DEFAUT = ("«", "»")

#: Ponctuations de fin de phrase. Quasi universelles en écriture latine, mais déclarables :
#: l'espagnol ouvre ses interrogations par `¿`, et une langue peut vouloir d'autres signes.
FIN_DE_PHRASE_DEFAUT = ";.!?…"

#: Le lexique français, verbatim (cf. l'en-tête pour ce qu'il décide).
VERBES_DE_PAROLE_DEFAUT = (
    r"(?:s['’]\s*)?(?:"
    r"d(?:it|is|isait|isaient|irent)|répond(?:it|irent|ait)?|répliqua|rétorqua|"
    r"demand(?:a|ait|èrent)|interrogea|questionna|hurl(?:a|ait|èrent)|cri(?:a|ait|èrent)|"
    r"écria|exclama|murmur(?:a|ait)|chuchota|souffla|marmonna|bredouilla|balbutia|"
    r"pens(?:a|ait)|song(?:ea|eait)|réfléchit|ajouta|repr(?:it|enait)|poursuivit|continua|"
    r"soupira|gémit|grogna|gronda|grommela|lança|beugla|tonna|affirma|déclara|annonça|"
    r"objecta|insista|conclut|répéta"
    r")\b"
)

#: Titre du guide de style, pour le garde-fou qui détecte un guide régurgité par un modèle.
TITRE_GUIDE_DEFAUT = "Guide de style"

#: Styles Word et classes CSS d'origine.
STYLES_WORD_DEFAUT = {"dialogue": "List Paragraph", "pensee": "Pensée"}
CLASSES_CSS_DEFAUT = {"dialogue": "dialogue", "pensee": "pensee"}


@dataclass(frozen=True)
class Typographie:
    """Règles compilées. Construite une fois par rendu, passée en paramètre."""

    dialogue_span: re.Pattern
    fin_de_phrase: re.Pattern
    #: `None` = cette langue ne colle pas d'incise (cf. l'en-tête). **Pas** un défaut manquant.
    verbes_de_parole: re.Pattern | None
    guide_de_style: re.Pattern
    tiret_dialogue: str
    tiret_dans_le_texte: bool
    styles_word: dict
    classes_css: dict

    @classmethod
    def depuis_pack(cls, pack=None, rendu: dict | None = None) -> "Typographie":
        """Compile les règles du pack, en retombant sur le français d'origine.

        `rendu` est le bloc `rendu` de `config.yaml`. Il garde la main sur `styles_word` et
        `dialogue_dash_in_text` : ce sont des réglages que l'utilisateur ajuste pour SON
        `reference.docx`, et un pack ne doit pas les lui reprendre. Le pack ne fournit que le
        défaut, comme il le fait pour les gabarits."""
        typo = dict(getattr(pack, "typographie", None) or {})
        rendu = dict(rendu or {})

        ouvrant, fermant = (typo.get("guillemets") or GUILLEMETS_DEFAUT)[:2]
        verbes = typo.get("verbes_de_parole", VERBES_DE_PAROLE_DEFAUT)

        # ⚠ `styles_word` : la config PRIME sur le pack. L'inverse reprendrait à
        # l'utilisateur un réglage calé sur son propre `reference.docx`.
        styles = {**STYLES_WORD_DEFAUT,
                  **(getattr(pack, "styles_word", None) or {}),
                  **(rendu.get("styles") or {})}

        return cls(
            dialogue_span=re.compile(
                rf"{re.escape(ouvrant)}\s*(.+?)\s*{re.escape(fermant)}", re.DOTALL),
            fin_de_phrase=re.compile(
                f"[{re.escape(str(typo.get('fin_de_phrase') or FIN_DE_PHRASE_DEFAUT))}]"),
            # Une clé absente rend le défaut français ; une clé explicitement VIDE ou nulle
            # dit « cette langue ne colle pas d'incise », et c'est un choix, pas un oubli.
            verbes_de_parole=(re.compile(rf"^\s*{verbes}", re.IGNORECASE) if verbes else None),
            guide_de_style=re.compile(
                rf"(?im)^#{{1,6}}\s*"
                rf"{re.escape(str(typo.get('titre_guide_de_style') or TITRE_GUIDE_DEFAUT))}\b"),
            tiret_dialogue=str(typo.get("tiret_dialogue") or "—"),
            tiret_dans_le_texte=bool(rendu.get("dialogue_dash_in_text",
                                               typo.get("tiret_dans_le_texte", False))),
            styles_word=styles,
            classes_css={**CLASSES_CSS_DEFAUT,
                         **(getattr(pack, "classes_css", None) or {})},
        )


#: Règles françaises, pour les appelants qui n'ont pas de pack sous la main (garde-fous
#: appelés hors d'un rendu, tests). Identiques au comportement d'avant l'externalisation.
DEFAUT = Typographie.depuis_pack()
