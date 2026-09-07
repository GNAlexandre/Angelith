# Guide de style — conventions générales de traduction

Conventions **stables sur tous les projets et tous les volumes**. Lues par les agents
terminologue, traducteur, correcteur et mise en page. Ce fichier est **générique** :
il ne doit jamais contenir de nom de personnage, de lieu ou de réplique tirée d'une œuvre en
particulier — seulement des règles de forme, applicables à n'importe quel light novel. Les
éléments propres à une œuvre (noms, genres, surnoms) vont dans son `glossaire.yaml`, jamais ici.

## Registre et temps verbaux
- **Narration** : passé simple + imparfait par défaut. Corriger tout présent qui traîne en pleine narration.
- **Dialogues familiers** : présent + passé composé tolérés.
- **Verbes d'attribution** au passé simple (dit-il, demanda-t-il, répondit X, acquiesça X, déclara X,
  soupira X…). Pas de passé composé en narration hors dialogue.

## Ponctuation
- **Aucun guillemet** dans ce roman : ni « … » ni "…". Les retirer systématiquement.
- Apostrophes et guillemets typographiques français (’ et, si jamais nécessaire, «») — jamais de versions droites.

## Trois registres de paragraphe (→ trois styles)
1. **Narration** → style **« Corps de texte »**.
   Tout le récit, y compris les passages descriptifs avec attribution narrative.
2. **Dialogue** → style **« Paragraphe de liste »**.
   Réplique parlée par un personnage, avec ou sans verbe d'attribution, sur SA PROPRE ligne.
   Le tiret cadratin « — » ouvre la réplique (voir `dialogue_dash_in_text` dans config.yaml).
   Jamais de guillemets.
3. **Pensée intérieure** → style **« Pensée »** (italique automatique).
   Monologue intérieur, souvent en réaction immédiate, sans interlocuteur, sur sa propre ligne.

## Cas particuliers
- **Drop-cap** : le **premier mot ou la première expression** du chapitre, quel qu'il soit, en **gras**.
- **Encadrés game-menu** (statut, succès, recette de craft) → style **« Corps de texte »** + gras + italique.
- **Italique inline ponctuelle** (emphase dans un paragraphe d'un autre style) : `*mot*` en Markdown.

## Pièges de traduction récurrents
- Sujets implicites et pronoms ambigus — surtout l'anglais *it* → genre français correct.
- Négations et ellipses mal rendues.
- Onomatopées japonaises rendues en anglais dans les fantrads → onomatopée française adaptée.
- Doublons (une même phrase sortie deux fois) → garder la meilleure version.
- Répliques scindées en milieu de phrase → recoller.

## Découpage
- Respecter les sauts de paragraphe de la VO de référence sans jamais perdre de contenu.
