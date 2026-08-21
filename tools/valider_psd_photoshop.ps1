# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

﻿<#
.SYNOPSIS
    Valide un PSD par le MOTEUR DE PHOTOSHOP lui-même, via son automation COM.

.DESCRIPTION
    `psd-tools` (dépendance de test) valide la conformité à la SPÉCIFICATION du format.
    Photoshop valide ce qu'Adobe accepte vraiment — et c'est le second qui décide. Trois
    tentatives d'écriture de calques de type ont échoué faute de cette boucle :

      · v0.18/0.19.0 — alerte « Problèmes à la lecture des calques », dégradation en pixels ;
      · v0.19.1      — plantage à l'ouverture, sans même un message ;
      · v0.21.0      — retour à `rasterise` par défaut, faute de pouvoir valider.

    Le script ouvre le fichier, parcourt ses calques et affirme pour chacun son type SELON
    PHOTOSHOP (`LayerKind.TEXTLAYER` = 2), plus le contenu réel de `TextItem.Contents`. Il
    tente ensuite une RÉÉCRITURE du texte sur le premier calque de type, puis referme SANS
    enregistrer : c'est la seule preuve qui compte — « le calque est-il éditable ? » — et la
    seule que ni psd-tools ni l'œil ne peuvent donner.

    Outil MANUEL : il ouvre l'application. Il n'a donc pas sa place dans pytest, où il
    bloquerait la suite sur une boîte de dialogue.

.PARAMETER Chemin
    Le .psd à valider. Défaut : psd_test.psd à la racine du dépôt.

.PARAMETER Fermer
    Quitter Photoshop à la fin (utile en enchaînement ; par défaut l'application reste
    ouverte pour un contrôle visuel).

.EXAMPLE
    python run_manga.py --psd-test
    powershell -ExecutionPolicy Bypass -File tools/valider_psd_photoshop.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/valider_psd_photoshop.ps1 `
        -Chemin "build/Mon Manga/Vol.1/manga/pages_psd/page_0001.psd"
#>
[CmdletBinding()]
param(
    [string]$Chemin = "psd_test.psd",
    [switch]$Fermer
)

$ErrorActionPreference = 'Stop'

# Constantes de l'API Photoshop. `LayerKind` vaut 2 pour un calque de TEXTE ; les calques
# pixel rendent 1 (normal). C'est LA valeur que tout ce lot cherche à obtenir.
$LAYER_TEXT = 2
$LAYER_NORMAL = 1
$PS_NO_SAVE = 2          # PsSaveOptions.psDoNotSaveChanges

function Ecrire-Ligne($symbole, $texte) { Write-Host "  $symbole $texte" }

$chemin = (Resolve-Path -LiteralPath $Chemin -ErrorAction SilentlyContinue)
if (-not $chemin) {
    Write-Host "X Fichier introuvable : $Chemin"
    Write-Host "  Produis-en un avec :  python run_manga.py --psd-test"
    exit 2
}

Write-Host ""
Write-Host "=== Validation par le moteur de Photoshop ==="
Write-Host "Fichier : $chemin"

try {
    $app = New-Object -ComObject Photoshop.Application
} catch {
    Write-Host "X Photoshop n'a pas repondu en COM : $_"
    Write-Host "  Lance-le une fois a la main (l'enregistrement COM se fait au 1er demarrage)."
    exit 2
}

Write-Host "Photoshop : $($app.Version)"
# Aucune boite de dialogue : sans ceci, un profil colorimetrique manquant suspend le script
# indefiniment, et l'outil ne serait pas utilisable en enchainement.
$app.DisplayDialogs = 3          # PsDialogModes.psDisplayNoDialogs

$doc = $null
$codeSortie = 0
try {
    try {
        $doc = $app.Open($chemin)
    } catch {
        Write-Host ""
        Write-Host "X ECHEC A L'OUVERTURE — Photoshop refuse le fichier."
        Write-Host "  $_"
        exit 1
    }

    Write-Host "Ouvert : $($doc.Width) x $($doc.Height) px, $($doc.ArtLayers.Count) calque(s)"
    Write-Host ""

    $nType = 0
    $nPixel = 0
    $premierType = $null
    $policesDoc = @{}
    for ($i = 1; $i -le $doc.ArtLayers.Count; $i++) {
        $c = $doc.ArtLayers.Item($i)
        $kind = $c.Kind
        if ($kind -eq $LAYER_TEXT) {
            $nType++
            if ($null -eq $premierType) { $premierType = $c }
            $contenu = $c.TextItem.Contents -replace "`r", " / "
            $police = $c.TextItem.Font
            $policesDoc[$police] = $true
            $corps = [math]::Round([double]$c.TextItem.Size, 1)
            Ecrire-Ligne "T" "$($c.Name)  ->  '$contenu'  [$police, $corps pt]"
        } elseif ($kind -eq $LAYER_NORMAL) {
            $nPixel++
            Ecrire-Ligne "#" "$($c.Name)  (pixels)"
        } else {
            Ecrire-Ligne "?" "$($c.Name)  (Kind = $kind)"
        }
    }

    # Les polices du document sont-elles CONNUES DE PHOTOSHOP ? C'est exactement la liste qu'il
    # consulte pour decider d'afficher « Polices manquantes » — donc la verification
    # autoritaire, et elle ne coute rien puisqu'on lui parle deja. Une police absente est
    # SUBSTITUEE des la premiere modification : la bulle reecrite change de dessin et jure
    # avec ses voisines, restees sur les pixels d'origine.
    if ($policesDoc.Count -gt 0) {
        $installees = @{}
        for ($i = 1; $i -le $app.Fonts.Count; $i++) {
            $installees[$app.Fonts.Item($i).PostScriptName] = $true
        }
        $absentes = @($policesDoc.Keys | Where-Object { -not $installees.ContainsKey($_) })
        Write-Host ""
        if ($absentes.Count -eq 0) {
            Write-Host "Polices : les $($policesDoc.Count) police(s) du document sont connues de Photoshop."
        } else {
            Write-Host "X POLICE(S) MANQUANTE(S) : $($absentes -join ', ')"
            Write-Host "  Photoshop affichera « Polices manquantes » a l'ouverture et substituera"
            Write-Host "  des la premiere modification. Installe-les (aucun droit admin requis) :"
            Write-Host "    powershell -ExecutionPolicy Bypass -File tools/installer_polices.ps1"
            Write-Host "  puis REDEMARRE Photoshop."
            $codeSortie = 1
        }
    }

    Write-Host ""
    Write-Host "Verdict de Photoshop : $nType calque(s) de TYPE, $nPixel de pixels."

    if ($nType -eq 0) {
        Write-Host ""
        Write-Host "X AUCUN calque de type. Deux causes possibles :"
        Write-Host "  - le PSD a ete produit en mode 'rasterise' (c'est le defaut) ;"
        Write-Host "  - le bloc TySh est mal forme et Photoshop l'a ignore en silence,"
        Write-Host "    en se rabattant sur les donnees de pixels."
        $codeSortie = 1
    } else {
        # LA preuve : reecrire le texte. Un calque peut etre declare de type, s'afficher
        # correctement, et refuser malgre tout l'outil Texte — c'est exactement ce que
        # Photopea montrait en v0.19.1.
        $avant = $premierType.TextItem.Contents
        try {
            $premierType.TextItem.Contents = "REECRITURE OK"
            $relu = $premierType.TextItem.Contents
            if ($relu -eq "REECRITURE OK") {
                Write-Host "OK Reecriture du texte acceptee : '$avant' -> '$relu'."
            } else {
                Write-Host "X Reecriture refusee en silence : le contenu est reste '$relu'."
                $codeSortie = 1
            }
        } catch {
            Write-Host "X Reecriture impossible : $_"
            $codeSortie = 1
        }
    }
} finally {
    # Refermer SANS enregistrer : l'outil valide, il ne modifie jamais le fichier de l'utilisateur.
    if ($null -ne $doc) { try { $doc.Close($PS_NO_SAVE) } catch { } }
    if ($Fermer -and $null -ne $app) { try { $app.Quit() } catch { } }
}

Write-Host ""
if ($codeSortie -eq 0) {
    Write-Host "=== VALIDE : Photoshop lit et reecrit les calques de texte. ==="
} else {
    Write-Host "=== NON VALIDE (voir ci-dessus). ==="
}
exit $codeSortie
