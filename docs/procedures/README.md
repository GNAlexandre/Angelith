# Procédures

Une fiche par brique : **quoi lancer, dans quel ordre, et quelles clés de `config.yaml` en
changent le résultat**. Chaque fiche tient en une lecture et se termine par « quand ça ne
marche pas ».

| Fiche | Brique | Commande d'entrée |
|---|---|---|
| [light-novel.md](light-novel.md) | Light novel — traduire un tome depuis un `.docx`, `.epub`, `.pdf`, `.txt` ou `.md` | `python run.py` |
| [manga.md](manga.md) | Manga et webtoon — détecter, nettoyer, lire, traduire, lettrer | `python run_manga.py` |
| [scan-ocr.md](scan-ocr.md) | Scans japonais — transformer des images de pages en texte lisible par la brique light novel | `python run_ocr.py` |
| [interfaces.md](interfaces.md) | Les deux façades — console `rich` et interface graphique PySide6 | `python app.py`, `python gui.py` |
| [illustration.md](illustration.md) | L'atelier d'illustration — produire des images NEUVES pour une œuvre, jamais retoucher les siennes. Console **et** destination « Illustrations » de `gui.py` (« Atelier » jusqu'à la 2.24.1) ; garder / jeter ; insertion étiquetée dans un tome ; **et le protocole en aveugle qui doit étalonner le juge de ressemblance** | `python run_illustration.py`, `python tools/juge_humain.py` |
| [bible-visuelle.md](bible-visuelle.md) | La bible visuelle — ce que le dépôt sait de l'apparence d'un personnage, **et le compte du corpus d'identité** (0 / 1 / 2 / ≥3, avec et sans les couvertures) | `python tools/bible.py` |
| [comfyui.md](comfyui.md) | ComfyUI — construire un graphe Qwen-Image, ranger les modèles, y brancher la brique d'illustration, et **voir ce que le projet envoie** : sonder le serveur, valider un graphe avant le GPU, écrire le graphe substitué | `python tools/comfy.py`, `python run_illustration.py` |
| [banc-de-mesure.md](banc-de-mesure.md) | Le banc — comment le projet mesure sa brique manga, sur quel corpus, sous quelles licences | `python tools/banc.py` |

---

## Ce que ces fiches ne sont pas

- **Ce ne sont pas le mémo des commandes.** [`../COMMANDES.fr.md`](../COMMANDES.fr.md) est
  exhaustif — tous les drapeaux, tous les cas particuliers. Ces fiches sont l'inverse : le
  chemin normal, et les seules clés qu'on touche vraiment.
- **Ce ne sont pas la documentation de référence.** [`../README.fr.md`](../README.fr.md) explique
  *pourquoi* chaque brique est faite ainsi, et porte les mesures qui justifient chaque valeur.
- **Ce ne sont pas des comptes rendus.** Les mesures datées vivent dans
  [`../mesures/`](../mesures/README.md), les plans de lot dans [`../plans/`](../plans/README.md).

## Trois choses vraies pour les trois briques

1. **Un projet est un dossier sous `sources/`, un tome est un dossier dedans.**
   `sources/<Projet>/<Tome>/` ; la sortie va dans `build/<Projet>/<Tome>/`. Le nom du projet
   est le nom du dossier — jamais un chemin.
2. **Tout est reprenable.** Un run interrompu — `Ctrl+C`, `--stop`, une coupure — se relance
   par la même commande et repart où il s'est arrêté. Le cache vit dans
   `build/<Projet>/<Tome>/.checkpoints/`, et c'est lui qui rend une relance gratuite.
3. **`--check` avant tout le reste.** Chaque brique porte son diagnostic d'environnement, et
   il dit ce qui manque avant que le temps de calcul soit dépensé.

```powershell
python run.py --check          # light novel
python run_manga.py --check    # manga / webtoon
python run_ocr.py --check      # scans
```

## `config.yaml` est un document, pas un fichier de réglages

95 Ko dont l'essentiel est de la prose commentée qui **justifie chaque valeur par un chiffre**.
Deux conséquences pratiques :

- **aucun outil du dépôt ne le réécrit** — un aller-retour `yaml.safe_dump` effacerait tous
  ses commentaires. On l'édite à la main ;
- **une clé s'ajoute avec le chiffre qui la justifie**, dans le style du fichier.

Les fiches ci-dessous ne listent que les clés **qu'on touche réellement**. Pour le reste, le
commentaire au-dessus de la clé dans `config.yaml` en dit plus que n'importe quel tableau.

⚠ **Une seule règle d'héritage à connaître.** `manga:` et `scan:` **héritent** des sections
racines par fusion profonde : n'y écrire que ce qui doit **différer**. Écrire un bloc `llm:`
complet sous `manga:` ne le remplace pas partiellement, il fait perdre tout ce qui n'y est pas
répété.
