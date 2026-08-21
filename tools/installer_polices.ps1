# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

﻿<#
.SYNOPSIS
    Installe les polices de lettrage livrées dans `templates/fonts/`, pour que Photoshop
    trouve celles que les PSD réclament.

.DESCRIPTION
    Le lettrage est dessiné avec les fichiers de `templates/fonts/`. Les sorties images, CBZ
    et PDF n'ont donc besoin d'aucune installation : la police est lue depuis le fichier.

    Le PSD, lui, est différent. Un calque de texte ne peut pas embarquer sa police — il n'en
    déclare que le NOM PostScript, et Photoshop va chercher la police correspondante parmi
    celles installées sur la machine. Sans elle : « Polices manquantes » à chaque ouverture,
    et une SUBSTITUTION dès la première modification — la bulle réécrite change de dessin et
    jure avec ses voisines, restées sur les pixels d'origine.

    Par défaut l'installation se fait POUR L'UTILISATEUR COURANT : aucun droit administrateur,
    rien qui touche les autres comptes de la machine, et `-Desinstaller` remet tout en place.

.PARAMETER Dossier
    Où prendre les polices. Défaut : `templates/fonts` à la racine du dépôt.

.PARAMETER Machine
    Installer pour TOUS les utilisateurs (C:\Windows\Fonts). Demande une session
    administrateur ; le script le vérifie et le dit plutôt que d'échouer à mi-parcours.

.PARAMETER Desinstaller
    Retirer ce que ce script a posé.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/installer_polices.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/installer_polices.ps1 -Desinstaller
#>
[CmdletBinding()]
param(
    [string]$Dossier,
    [switch]$Machine,
    [switch]$Desinstaller
)

$ErrorActionPreference = 'Stop'

if (-not $Dossier) {
    $Dossier = Join-Path (Split-Path -Parent $PSScriptRoot) "templates\fonts"
}

# Rendre la police visible des applications DÉJÀ lancées, sans redémarrer la session.
# Photoshop, lui, ne relit sa liste qu'au démarrage : le script le rappelle à la fin.
if (-not ("Polices" -as [type])) {
    Add-Type -Name Polices -Namespace Win32 -MemberDefinition @'
[DllImport("gdi32.dll", CharSet = CharSet.Unicode)] public static extern int AddFontResourceW(string p);
[DllImport("gdi32.dll", CharSet = CharSet.Unicode)] public static extern bool RemoveFontResourceW(string p);
[DllImport("user32.dll")] public static extern int SendMessageTimeout(
    IntPtr hWnd, uint msg, IntPtr wp, IntPtr lp, uint flags, uint timeout, out IntPtr res);
'@
}

function Diffuser-Changement {
    # HWND_BROADCAST = 0xffff, WM_FONTCHANGE = 0x001D, SMTO_ABORTIFHUNG = 2
    $res = [IntPtr]::Zero
    [void][Win32.Polices]::SendMessageTimeout(
        [IntPtr]0xffff, 0x001D, [IntPtr]::Zero, [IntPtr]::Zero, 2, 1000, [ref]$res)
}

function Nom-Affichage($fichier) {
    <# Le nom que Windows donne à la police dans son registre : « Comic Neue Bold (TrueType) ».
       Lu via la colonne « Titre » du shell, qui vient de la table `name` du fichier — plutôt
       que déduit du nom de fichier, qui n'a aucune raison de coïncider. #>
    try {
        $sh = New-Object -ComObject Shell.Application
        $d = $sh.Namespace($fichier.DirectoryName)
        $titre = $d.GetDetailsOf($d.ParseName($fichier.Name), 21)
        if ($titre) { return "$titre (TrueType)" }
    } catch { }
    return "$($fichier.BaseName) (TrueType)"
}

if (-not (Test-Path -LiteralPath $Dossier)) {
    Write-Host "X Dossier introuvable : $Dossier"
    exit 2
}
# ⚠ Filtrer sur l'extension, PAS avec `-Include` : combiné à `-Recurse`, celui-ci a laissé
# passer `OFL.txt` et `README.md`, qui se sont retrouvés inscrits au registre des polices.
$polices = @(Get-ChildItem -LiteralPath $Dossier -Recurse -File |
    Where-Object { $_.Extension -in '.ttf', '.otf', '.ttc' } | Sort-Object Name)
if (-not $polices) {
    Write-Host "X Aucune police (.ttf/.otf) dans $Dossier"
    exit 2
}

if ($Machine) {
    $estAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $estAdmin) {
        Write-Host "X -Machine installe dans C:\Windows\Fonts : relance ce script depuis une"
        Write-Host "  console PowerShell ADMINISTRATEUR, ou retire -Machine pour installer"
        Write-Host "  seulement pour ton compte (aucun droit particulier requis)."
        exit 2
    }
    $cible = Join-Path $env:WINDIR "Fonts"
    $cle = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts'
    $portee = "TOUTE LA MACHINE"
} else {
    $cible = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"
    $cle = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
    $portee = "l'utilisateur $env:USERNAME"
}

Write-Host ""
Write-Host "=== Polices de lettrage — $(if ($Desinstaller) { 'DESINSTALLATION' } else { 'installation' }) pour $portee ==="
Write-Host "Source : $Dossier"
Write-Host "Cible  : $cible"
Write-Host ""

if (-not (Test-Path -LiteralPath $cible)) { New-Item -ItemType Directory -Path $cible -Force | Out-Null }
if (-not (Test-Path -LiteralPath $cle)) { New-Item -Path $cle -Force | Out-Null }

$n = 0
foreach ($p in $polices) {
    $nom = Nom-Affichage $p
    $destination = Join-Path $cible $p.Name
    # Le registre par machine attend un nom de fichier nu (il est résolu dans %WINDIR%\Fonts) ;
    # celui par utilisateur attend un chemin complet.
    $valeur = if ($Machine) { $p.Name } else { $destination }
    $existe = (Get-ItemProperty -Path $cle -Name $nom -ErrorAction SilentlyContinue) -ne $null

    if ($Desinstaller) {
        if (-not $existe -and -not (Test-Path -LiteralPath $destination)) {
            Write-Host "  - $($p.Name)  (n'etait pas installee)"
            continue
        }
        [void][Win32.Polices]::RemoveFontResourceW($destination)
        if ($existe) { Remove-ItemProperty -Path $cle -Name $nom -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $destination) {
            try { Remove-Item -LiteralPath $destination -Force } catch {
                Write-Host "  ! $($p.Name) : fichier verrouille (une application l'utilise encore)"
            }
        }
        Write-Host "  X $nom  retiree"
        $n++
        continue
    }

    if ($existe -and (Test-Path -LiteralPath $destination)) {
        Write-Host "  = $nom  (deja installee)"
        continue
    }
    Copy-Item -LiteralPath $p.FullName -Destination $destination -Force
    New-ItemProperty -Path $cle -Name $nom -Value $valeur -PropertyType String -Force | Out-Null
    [void][Win32.Polices]::AddFontResourceW($destination)
    Write-Host "  + $nom"
    $n++
}

Diffuser-Changement

Write-Host ""
if ($Desinstaller) {
    Write-Host "$n police(s) retiree(s). Les PSD deja produits redemanderont cette police."
} elseif ($n -eq 0) {
    Write-Host "Rien a faire : tout etait deja installe."
} else {
    Write-Host "$n police(s) installee(s)."
    Write-Host ""
    Write-Host "-> REDEMARRE PHOTOSHOP : il ne relit la liste des polices qu'au demarrage."
    Write-Host "   Puis verifie :"
    Write-Host "     powershell -ExecutionPolicy Bypass -File tools/valider_psd_photoshop.ps1"
}
exit 0
