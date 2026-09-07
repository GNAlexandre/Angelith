; SPDX-License-Identifier: AGPL-3.0-or-later
; Copyright (C) 2026 Alexandre Tournel
;
; ============================================================================
;  Installeur Windows — PLAN-37 L37.5. Par UTILISATEUR, sans UAC.
; ============================================================================
;
;   python installeur/generer.py            (écrit installeur/version.iss)
;   iscc installeur\angelith.iss            (Inno Setup 6)
;
; ⚠ **La version n'est PAS saisie ici.** Elle vient de `core/version.py` par
; `installeur/version.iss`, que `installeur/generer.py` écrit et que la CI régénère à chaque
; construction. Un numéro tapé à la main dans un installeur est un numéro qui vieillit en
; silence — et l'installeur est précisément l'endroit où personne ne le relit.
;
; ## Les quatre décisions, et leurs motifs
;
; 1. **`PrivilegesRequired=lowest`** — installation par utilisateur, dans
;    `%LOCALAPPDATA%\Programs\Angelith`, jamais dans `Program Files`. Pas d'invite UAC, pas de
;    dossier en lecture seule à contourner ensuite. C'est aussi ce qui rend cohérente la
;    résolution de `core/installation.py` : les œuvres vont dans `Documents\Angelith`, les
;    réglages dans `%LOCALAPPDATA%\Angelith`, et le dossier d'installation ne reçoit rien.
;
; 2. **La désinstallation ne touche à aucune donnée.** Ni `sources/`, ni `build/`, ni les poids
;    téléchargés, ni le `config.yaml` de l'utilisateur, ni `.angelith/`. Une case à cocher,
;    **décochée**, propose de supprimer les réglages — et elle ne propose PAS de supprimer les
;    œuvres, qui ne sont pas à ce logiciel. Un tome traduit, c'est des heures de GPU.
;
; 3. **Aucun poids, aucun modèle, aucun outil externe.** La page d'information ci-dessous le
;    dit à l'écran 1, pas à l'écran 6 : « un installeur en un clic qui laisse cinq installations
;    manuelles à faire doit le dire avant ».
;
; 4. **Aucune signature de code au 2026-09-06**, et ce n'est pas un oubli : la décision est
;    écrite, mesurée et publiée dans `docs/mesures/empaquetage-2026-09-06.md`. Conséquence
;    annoncée plutôt que découverte : SmartScreen avertira sur chaque nouvelle version tant
;    qu'aucun certificat ne signe le binaire.

#include "version.iss"

#define MonNom "Angelith"
#define MonExe "angelith-gui.exe"
#define MonExeConsole "angelith-console.exe"
#define MonEditeur "Alexandre Tournel"
#define MonSite "https://github.com/GNAlexandre/Angelith"

[Setup]
; ⚠ **Cet identifiant ne change JAMAIS.** C'est lui, et pas le nom, qui fait qu'une nouvelle
; version REMPLACE l'installation précédente au lieu d'en poser une seconde à côté. Il est
; dérivé une fois pour toutes de l'URL du dépôt (UUID v5, espace de noms URL), donc
; reproductible et non tiré au sort.
AppId={{ABB50651-2E51-5191-BFC3-5B72BE031AF6}
AppName={#MonNom}
AppVersion={#MaVersion}
AppVerName={#MonNom} {#MaVersion}
AppPublisher={#MonEditeur}
AppPublisherURL={#MonSite}
AppSupportURL={#MonSite}/issues
AppUpdatesURL={#MonSite}/releases
VersionInfoVersion={#MaVersionQuadruplet}

; ⚠ `{autopf}` deviendrait `Program Files` si l'installeur tournait élevé. `{localappdata}`
; est explicite : on veut CE dossier, quel que soit le contexte de lancement.
DefaultDirName={localappdata}\Programs\{#MonNom}
DefaultGroupName={#MonNom}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=

; Une licence qu'on peut lire avant d'installer. L'AGPL l'exige pour un binaire redistribué,
; et le NOTICE porte les licences des dépendances et des polices (SIL OFL 1.1).
LicenseFile=..\LICENSE
InfoBeforeFile=avant-installation.txt

OutputDir=..\dist
OutputBaseFilename=Angelith-{#MaVersion}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName={#MonNom} {#MaVersion}
UninstallDisplayIcon={app}\{#MonExe}

; ⚠ **Trois icônes, une seule source.** `SetupIconFile` habille le `.exe` de l'installeur —
; celui qu'on télécharge et qu'on double-clique, donc la toute première image du logiciel.
; `UninstallDisplayIcon` ci-dessus et les raccourcis de `[Icons]` pointent, eux, sur
; `angelith-gui.exe`, qui porte déjà la même icône par `icon=` dans `angelith.spec`. Le
; fichier est donc nommé une fois ici et une fois là, jamais copié.
;
; ⚠ Le chemin est relatif à CE fichier, pas à la racine : `iscc` résout les chemins depuis le
; dossier du script.
SetupIconFile=..\templates\icone\angelith.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "raccourcibureau"; Description: "Créer un raccourci sur le Bureau"; \
    GroupDescription: "Raccourcis :"
; ⚠ Le raccourci console est OPTIONNEL et décoché : il ouvre le même programme dans une
; fenêtre de terminal. Il sert au diagnostic (`--diagnostic-json`) et à qui veut voir ce que
; l'application écrit ; ce n'est pas le chemin normal.
Name: "raccourciconsole"; Description: "Ajouter un raccourci « Angelith (console) »"; \
    GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
; Le dossier gelé, entier. ⚠ `recursesubdirs` et `createallsubdirs` : `_internal` a plusieurs
; niveaux, et un sous-dossier vide non créé est une donnée introuvable à l'exécution.
Source: "..\dist\Angelith\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{autodesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: raccourcibureau
Name: "{autoprograms}\{#MonNom} (console)"; Filename: "{app}\{#MonExeConsole}"; \
    Tasks: raccourciconsole

[Run]
Filename: "{app}\{#MonExe}"; Description: "Lancer {#MonNom}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; ⚠ **Rien ici, et c'est délibéré.** La seule chose que la désinstallation supprime est ce
; qu'elle a installé — le dossier `{app}`. Les œuvres (`Documents\Angelith`), les poids
; téléchargés et le `config.yaml` de l'utilisateur (`%LOCALAPPDATA%\Angelith`) restent, et
; c'est `CurUninstallStepChanged` ci-dessous qui propose — une fois, en demandant — de retirer
; les seuls réglages.

[Code]
// ⚠ Ne supprime QUE `%LOCALAPPDATA%\Angelith` : les réglages, le `config.yaml` utilisateur et
// les poids téléchargés. Jamais `Documents\Angelith`, qui porte les œuvres et les tomes
// traduits — des heures de GPU qu'un installeur n'a pas à décider d'effacer.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Donnees: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Donnees := ExpandConstant('{localappdata}\Angelith');
    if DirExists(Donnees) then
    begin
      if MsgBox('Supprimer aussi vos réglages Angelith ?' + #13#10 + #13#10
                + Donnees + #13#10 + #13#10
                + 'Cela efface votre config.yaml, la disposition de la fenêtre et les poids '
                + 'que vous aviez téléchargés.' + #13#10
                + 'Vos œuvres et vos tomes traduits (Documents\Angelith) ne sont PAS '
                + 'touchés.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Donnees, True, True, True);
    end;
  end;
end;
