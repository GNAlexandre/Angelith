# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel
#
# ============================================================================
#  Le gel — PLAN-37 L37.3. UN DOSSIER, jamais un fichier.
# ============================================================================
#
#     pyinstaller angelith.spec --noconfirm --workpath .pyinstaller --distpath dist
#
# ⚠ **`--workpath .pyinstaller` n'est pas décoratif.** Le défaut de PyInstaller est `build/`,
# et `build/` est le dossier des SORTIES du pipeline dans ce dépôt : des tomes traduits, des
# checkpoints qui coûtent des heures de GPU. Laisser l'empaqueteur écrire dedans mêlerait ses
# intermédiaires aux œuvres de l'utilisateur. Le chemin est donc passé à la commande, et la CI
# le passe aussi.
#
# ## ⚠ `--onefile` est REFUSÉ, et le motif est écrit ici plutôt qu'ailleurs
#
# 1. **Antivirus.** Le mode un-fichier extrait l'application dans un dossier temporaire au
#    démarrage, puis l'exécute. Ce motif extraction-puis-exécution est exactement celui de
#    beaucoup de logiciel malveillant, et c'est lui qui déclenche les heuristiques. Le mode
#    un-dossier ne l'a pas.
# 2. **Coût de lancement.** Le paquet pèse des centaines de mégaoctets ; un-fichier paierait
#    une décompression à CHAQUE lancement, pas une fois.
# 3. **Réparabilité.** Un dossier se regarde. Quand un utilisateur dit « ça ne démarre pas »,
#    `dir` répond ; une archive auto-extractible ne répond rien.
#
# ⚠ Et l'inverse est vrai aussi, il faut le dire : un dossier de plus de dix mille fichiers est
# plus lent à installer et à désinstaller qu'un fichier unique, et c'est ce que l'installeur
# paie. Le compte exact est publié dans `docs/mesures/empaquetage-2026-09-06.md`.
#
# ## Ce qui N'EST PAS dedans, et c'est la liste de l'étape 0.3
#
# Aucun poids de détection (GPL-3.0 + Manga109-s : non redistribuable), aucun modèle de langue,
# aucun modèle d'OCR, ni Pandoc, ni WeasyPrint, ni `unrar`, ni ComfyUI, aucune œuvre. Cette
# liste est aussi le texte de l'écran 1 de l'installeur — pas de l'écran 6.

import sys
from pathlib import Path

RACINE = Path(SPECPATH).resolve()                                       # noqa: F821
sys.path.insert(0, str(RACINE))
from core.version import __version__                                    # noqa: E402

# --------------------------------------------------------------------------- #
#  Les données livrées
# --------------------------------------------------------------------------- #
#
# ⚠ Tout ce qui est listé ici est résolu à l'exécution par `core/installation.py:ressource()`,
# et par elle seule. Un chemin construit avec `Path(__file__)` désignerait l'intérieur du gel ;
# `tests/test_installation_chemins.py` échoue si l'un d'eux réapparaît.

DONNEES = [
    # Le document de configuration. ⚠ Livré en LECTURE SEULE : au premier lancement,
    # `installation.installer_config_utilisateur()` en pose une copie dans
    # `%LOCALAPPDATA%/Angelith/`, qu'aucune mise à jour ne remplace (`PLAN-37` L37.4).
    ("config.yaml", "."),

    # ⚠ **Les prompts sont du CODE SOURCE** (interdit 6 du contexte agent). Ils partent
    # entiers, lisibles, avec leur en-tête de licence à la FIN du fichier — un modèle lit le
    # haut d'un fichier comme une instruction. Le dossier porte aussi les gabarits `docx`/`css`
    # et les guides de style de chaque pack.
    ("langues", "langues"),

    # Les polices livrées (`manga/typeset.py:POLICES_LIVREES`) et le modèle de glossaire.
    # ⚠ Sans elles, la chaîne de lettrage tombe sur Arial — « un tome en Arial, sans un mot ».
    ("templates/fonts", "templates/fonts"),
    ("templates/glossaire_modele.yaml", "templates"),

    # Les gabarits de prompt d'illustration : des YAML dans un paquet, que PyInstaller ne
    # ramasse pas tout seul (il ne suit que les imports).
    ("illustration/gabarits", "illustration/gabarits"),

    # ⚠ Ce script-ci fait exception à l'exclusion de `tools/`, et c'est mesuré, pas supposé :
    # `manga/reparations.py:_installer_polices` l'APPELLE à l'exécution, depuis un bouton de la
    # page Diagnostic. Sans lui, la réparation échouerait chez l'utilisateur sur un « script
    # introuvable » — le mode de panne exact que ce lot existe pour fermer.
    ("tools/installer_polices.ps1", "tools"),

    # L'AGPL exige que le texte de la licence accompagne le binaire. Le NOTICE porte les
    # licences des dépendances et des polices (SIL OFL 1.1).
    ("LICENSE", "."),
    ("NOTICE", "."),
    ("README.md", "."),
    ("CHANGELOG.md", "."),
]

# ⚠ Les deux `reference.*.bak.docx` de `templates/` ne partent PAS : ce sont des sauvegardes
# d'un gabarit que le pipeline ne lit jamais (il lit `langues/<code>/templates/reference.docx`,
# qui part, lui). Les embarquer coûterait deux fichiers pour zéro chemin de code.

# --------------------------------------------------------------------------- #
#  Les exclusions
# --------------------------------------------------------------------------- #
#
# ⚠ **Chaque nom ci-dessous a été vérifié par un lancement**, pas seulement par un tableau de
# poids : un module Qt retiré casse parfois un widget qu'on n'a pas ouvert au test. La
# vérification est `angelith-gui.exe --verifier-demarrage`, que la CI rejoue sur le gel.

EXCLUSIONS = [
    # L'outillage de test et de mesure. Il n'a aucun chemin d'exécution dans l'application, et
    # `pytest` tire `pluggy`, `iniconfig` et son propre système de plugins.
    "pytest", "_pytest", "pluggy", "psd_tools", "coverage", "ruff",
    "tests", "tools.banc", "tools.banc_candidats", "tools.banc_effacement",
    "tools.banc_identite", "tools.banc_prompt", "tools.banc_sfx", "tools.corpus_synthetique",
    "tools.juge_humain", "tools.compte_de_tests", "tools.compte_sans_pyside",

    # Les modules Qt qu'aucun fichier du dépôt n'importe. Le relevé est mécanique :
    # `grep -rho "PySide6\\.[A-Za-z]*"` sur tout le dépôt rend QtCore, QtGui, QtSvg et
    # QtWidgets, et rien d'autre.
    #
    # ⚠ `QtNetwork` n'est PAS exclu bien qu'aucun fichier ne l'importe : les greffons de
    # plateforme Qt en dépendent, et l'exclure fait échouer la création de la QApplication —
    # constaté au lancement, pas déduit.
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtWebSockets",
    "PySide6.QtWebChannel", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",

    # ⚠ `tkinter` et `matplotlib` : aucun des deux n'est une dépendance déclarée du projet,
    # mais l'un arrive avec CPython et l'autre s'invite parfois par une dépendance transitive.
    # Les nommer coûte une ligne et évite d'embarquer une seconde boîte à outils graphique.
    "tkinter", "matplotlib", "IPython", "notebook", "jupyter",
]

# ⚠ **Les dépendances ne se déclarent PAS ici.** Elles vivent dans `pyproject.toml`, et un
# `hiddenimports` qui doublerait un extra finirait par en diverger — le jour venu, le gel
# manquerait un module et le symptôme serait un `ImportError` chez l'utilisateur, pas ici.
# Ce qui suit n'est donc pas une liste de dépendances : ce sont les modules qu'aucun `import`
# statique ne désigne, et que l'analyse ne peut donc pas trouver seule.
IMPORTS_CACHES = [
    # Chargés par nom, depuis la configuration ou une chaîne.
    "yaml", "encodings.idna",
    # Les briques que l'interface importe tardivement, dans une fonction.
    "pipeline.doctor", "manga.doctor", "core.diagnostic", "core.reparations", "core.maj",
]


def _fichier_de_version() -> str:
    """Écrit la ressource de version Windows, depuis `core/version.py`, et rend son chemin.

    ⚠ Hors Windows, PyInstaller ignore l'argument ; le fichier est écrit quand même, ce qui
    coûte deux cents octets et évite une branche."""
    majeur, mineur, correctif = (int(n) for n in __version__.split("."))
    quadruplet = (majeur, mineur, correctif, 0)
    texte = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={quadruplet}, prodvers={quadruplet},
                    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
        StringStruct('CompanyName', 'Alexandre Tournel'),
        StringStruct('FileDescription',
                     "Angelith - traduction assistee de light novels, mangas et webtoons"),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', 'angelith-gui'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 Alexandre Tournel - AGPL-3.0-or-later'),
        StringStruct('OriginalFilename', 'angelith-gui.exe'),
        StringStruct('ProductName', 'Angelith'),
        StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])
  ]
)
"""
    cible = Path(workpath) / "version_windows.txt"                      # noqa: F821
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8")
    return str(cible)


a_gui = Analysis(                                                       # noqa: F821
    ["gui.py"],
    pathex=[str(RACINE)],
    binaries=[],
    datas=DONNEES,
    hiddenimports=IMPORTS_CACHES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUSIONS,
    noarchive=False,
)

pyz_gui = PYZ(a_gui.pure)                                               # noqa: F821

exe_gui = EXE(                                                          # noqa: F821
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="angelith-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # ⚠ UPX compresse, et une section compressée est un signal
                        # d'heuristique antivirus de plus. On ne l'active pas.
    # ⚠ `console=False` : sans ça, Windows ouvre une console noire derrière la fenêtre. C'est la
    # même distinction que `[project.gui-scripts]` contre `[project.scripts]`.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # ⚠ La version de la ressource Windows est GÉNÉRÉE depuis `core/version.py` (ci-dessus),
    # jamais saisie : c'est elle que l'explorateur de fichiers affiche dans les propriétés du
    # `.exe`, et un numéro tapé à la main y aurait vieilli en silence.
    version=_fichier_de_version(),
)

# ⚠ **Un SECOND exécutable, console, et il n'est pas un confort.** Sous Windows, un binaire
# lié en sous-système « fenêtre » n'a pas de sortie standard : `print()` n'écrit nulle part, et
# la CI ne peut donc pas lire `--version`, `--diagnostic-json` ni `--verifier-demarrage` sur
# `angelith-gui.exe`. Mesuré le 2026-09-06 : le premier essai de `--verifier-demarrage` sur le
# binaire fenêtré n'a rien écrit et n'est jamais sorti.
#
# `angelith-console.exe` est le MÊME programme — même analyse, même code, même `_internal` —
# lié en sous-système console. C'est lui que la CI pilote, et c'est lui que sert le « raccourci
# console optionnel » du `PLAN-37` L37.5 point 2.
exe_console = EXE(                                                      # noqa: F821
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="angelith-console",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_fichier_de_version(),
)

COLLECT(                                                                # noqa: F821
    exe_gui,
    exe_console,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Angelith",
)
