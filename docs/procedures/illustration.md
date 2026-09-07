# Procédure — l'atelier d'illustration (`run_illustration.py`)

Produire des images **neuves** pour une œuvre traduite : un personnage seul, reconnaissable
d'une image à l'autre, dans le registre graphique du tome.

> ⚠ **Cette brique est EXPÉRIMENTALE et DÉSARMÉE.** `illustration.actif` vaut `false` dans la
> configuration livrée. Un utilisateur qui ne touche à rien ne télécharge aucun poids, ne perd
> aucune seconde au démarrage, et ne voit aucune différence sur `run.py` ni `run_manga.py`.

> ⚠ **Elle ne modifie AUCUNE image de l'œuvre.** Elle lit `media/`, elle écrit des fichiers qui
> n'existaient pas, dans un dossier qui lui appartient. Le principe « l'IA ne dessine jamais »
> porte sur les pixels de l'œuvre et reste vrai mot pour mot — c'est vérifié à l'exécution par
> `illustration/frontiere.py`, pas seulement affirmé.

---

## 1. La commande

```powershell
python run_illustration.py "Mon LN"
```

C'est tout. L'atelier pose ses questions dans cet ordre :

1. **qui illustrer** — la liste des personnages de l'œuvre, les mieux documentés d'abord, ou
   « une description personnalisée » où tu écris toi-même ce que tu veux voir ;
2. **le cadrage** — visage, buste, pied. Il ne vient jamais du texte : c'est ton choix ;
3. **combien d'images** ;
4. **quelles images montrer au modèle** — une par une, avec ce qu'on en sait, et — si tu le
   demandes — ce que le modèle de vision en dit ;
5. **valide ?** — le prompt complet s'affiche, avec d'où vient chaque mot. Répondre demande
   **ton nom**, qui part dans le sidecar de chaque image.

⚠ **Une ŒUVRE, pas un tome.** Les références d'un personnage vivent où l'éditeur les a mises :
sur le corpus de mesure, **7 des 10 références validées sont dans un autre volume que le
premier**. L'atelier lit donc tous les tomes, et écrit dans `build/<Projet>/illustrations/`.
Nommer un tome (`python run_illustration.py "Mon LN" Vol.2`) **restreint la lecture** ; ça ne
change pas où l'on écrit.

---

## 2. Avant la première image

```powershell
python run_illustration.py --check
```

Il dit, sans rien télécharger : la brique est-elle armée, quel moteur, quel gabarit, quels
plafonds, et **ce que chaque réglage désarmé vous coûte**.

Trois choses doivent être vraies pour qu'une image sorte :

| il faut | pourquoi | où |
|---|---|---|
| `illustration.actif: true` | c'est le seul interrupteur général | `config.yaml` |
| un **serveur ComfyUI** qui tourne, et `illustration.moteur: "comfyui"` | le dépôt n'embarque aucun modèle d'image — comme pour Ollama, tu l'installes | `config.yaml` |
| une **bible visuelle** pour l'œuvre | sans elle, le prompt ne viendrait pas de l'œuvre mais d'un modèle | `python tools/bible.py "Mon LN" --proposer` puis `--revue` |

⚠ Sans bible, l'atelier fonctionne quand même — mais seulement en **description
personnalisée** : c'est toi qui écris, et le sidecar le dit (`origine: humain`).

⚠ Pour que le personnage RESSEMBLE à celui de l'œuvre, il faut en plus
`illustration.identite.actif: true`. Sans lui, les images de référence ne partent pas au
modèle, et il invente un visage. Le diagnostic le dit en toutes lettres.

---

## 3. Ce que l'atelier montre, et pourquoi

### Les personnages, en trois états

| état | ce qu'il a | ce que l'atelier en fait |
|---|---|---|
| **prêt** | des attributs cités **et** au moins une image validée par un humain | proposé en premier |
| **à relire** | des attributs cités **et** des images proposées, aucune validée | proposé aussi — tu regardes les images, tu tranches |
| non proposé | pas d'attribut cité, ou aucune image candidate | écarté, **avec le motif** |

⚠ « À relire » est le cas **normal** d'une œuvre neuve. C'est la raison d'être de cet atelier :
la revue humaine se faisait avant dans `tools/bible.py --revue`, **hors contexte** — on
validait des images sans savoir pour quelle illustration. Ici tu les valides au moment où tu
demandes le portrait. Si tu le veux, l'atelier inscrit ensuite ton choix dans `bible.yaml`
(`confiance: humaine`) — **une question explicite, jamais un effet de bord**.

### Les images candidates

Chacune s'affiche avec ce qu'on en sait :

- `déjà validée` — un humain l'a retenue par le passé ;
- `COUVERTURE — titre et logo dans les pixels` — **à éviter**. Le garde de marquage refuse le
  titre de l'œuvre dans les métadonnées, mais il ne voit pas un titre **peint dans une image**.
  Ces pixels partent dans le conditionnement, et le modèle peut les reproduire ;
- ce que le **modèle de vision** en dit, si tu l'as demandé (~5 s par image).

⚠ **Le plafond est de 2 images**, et c'est une mesure : à une seule référence le modèle rend un
collage ; à deux, un portrait cohérent ; la troisième est indiscernable de la deuxième pour un
temps de calcul supérieur.

---

## 4. Le chemin scripté, en deux phases

Pour rejouer, mesurer, ou automatiser :

```powershell
python run_illustration.py "Mon LN" --phase prompt     # → build/<Projet>/illustrations/requete.yaml
#   … tu relis le fichier, tu corriges, tu écris ton nom, tu passes `valide` à true …
python run_illustration.py "Mon LN" --phase image      # bascule VRAM + génération
python run_illustration.py --rejouer build/…/x.png.provenance.json
```

`requete.yaml` est fait pour être lu. Il porte, par personnage :

| champ | ce qu'il dit | peux-tu le vider ? |
|---|---|---|
| `references` | les images d'IDENTITÉ, chacune avec son `motif` et son `retenue` | ❌ **non** — sans référence, la phase 2 refuse |
| `ancrages_style` | les images de REGISTRE, à préférer **sans visage** | ✅ |
| `attributs_sources` | d'où vient chaque mot : le fichier, la citation, l'origine | ✅ |
| `graine` | `null` = aléatoire, un entier = reproductible | ✅ |
| `canaux` | les arguments TYPÉS du moteur — livrés **désarmés** | ✅ |

Trois surcharges pour un run, sans toucher à `config.yaml` :

```powershell
python run_illustration.py "Mon LN" --phase prompt --cadrage visage
python run_illustration.py "Mon LN" --phase prompt --forme categories
python run_illustration.py "Mon LN" --phase prompt --langue-prompt en
```

---

## 5. Les réglages qu'on touche vraiment

| clé | défaut | ce qu'elle change |
|---|---|---|
| `illustration.actif` | `false` | l'interrupteur général |
| `illustration.moteur` | `"factice"` | `"comfyui"` pour produire une vraie image. Le factice rend un carré uni : il vérifie la chaîne, pas l'image |
| `illustration.comfyui.workflow` | le graphe **texte-vers-image** | ⚠ **à changer pour `qwen-image-edit-2511.api.json` dès que tu armes l'identité** — c'est le seul graphe livré qui sache recevoir une image de référence |
| `illustration.identite.actif` | `false` | envoie les références au modèle. **Sans lui, le personnage ne ressemble à personne** |
| `illustration.prompt.style` | `"mots"` | comment le registre du tome entre dans le prompt. `"mots"` est le seul qui corrige le régime de couleur, mesuré |
| `illustration.prompt.llm.actif` | `false` | fait relire les images par le modèle de vision. Coûte ~5 s par image, et **peut réduire fortement le nombre de personnages illustrables** — ses refus sont justes, et ils mesurent la qualité de la bible |
| `illustration.budget.images_par_run` | `8` | le plafond d'un run, motif d'arrêt nommé |
| `illustration.comfyui.plancher_secondes` | `2.0` | refuse une « génération » trop rapide pour en être une — c'est le cache de ComfyUI |

---

## 6. Quand ça ne marche pas

**« la brique d'illustration est DÉSARMÉE »** — c'est le défaut livré. `illustration.actif:
true` dans `config.yaml`, puis relis le bloc : chaque clé y porte le chiffre qui la justifie.

**« le moteur n'est pas disponible »** — ComfyUI ne répond pas. Lance-le, puis
`python run_illustration.py --check`.

**« canal références refusé par le moteur »** — **le piège le plus courant**, et il n'a qu'une
cause : `illustration.identite.actif` est armé, mais `illustration.comfyui.workflow` pointe
encore sur le graphe **texte-vers-image**, qui n'a aucun nœud pour recevoir une image.

```yaml
illustration:
  comfyui:
    workflow: "illustration/workflows/qwen-image-edit-2511.api.json"
```

⚠ **Ces deux clés vont par paire.** `--check` les croise et le dit, et l'atelier le dit dans
son bandeau **avant la première question** — parce que ce refus tombait auparavant à la toute
fin, après avoir choisi son personnage, relu ses images une par une et tapé son nom.

**« aucune référence validée par un humain »** — le personnage n'a aucune image que quelqu'un
ait regardée. Ce n'est pas un bug : générer un portrait depuis une image que personne n'a vue
ferait passer une invention pour une illustration de l'œuvre. Utilise l'atelier : il te montre
les candidates et enregistre ton choix.

**« c'est son CACHE D'EXÉCUTION, pas une génération »** — ComfyUI a resservi le résultat d'un
graphe déjà exécuté, et ce cache **survit à une interruption** : après un `/interrupt`, une
image partiellement débruitée peut revenir. Redémarre ComfyUI.

⚠ **N'interromps pas une génération.** Mesuré : un `POST /interrupt` a coûté **22 minutes** de
réinitialisation de modèle au run suivant. Laisse la file se vider.

**« référence AMBIGUË »** — une référence écrite `media/image1.png` existe dans plusieurs
tomes. Préfixe-la par son tome : `Vol.2/media/image1.png`. Une bible construite depuis le
2026-08-31 le fait toute seule.

**La carte reste prise après un run** — le modèle d'image reste chargé. Ferme ComfyUI, ou vois
`docs/COMMANDES.fr.md` pour l'appel qui rend la VRAM. `illustration.vram.decharger_image` le
fait tout seul, mais il est **désarmé** : sur sept appels mesurés, un a fait planter ComfyUI.

---

## 7. L'atelier graphique, et la galerie (lot 27)

```powershell
python gui.py          # destination « Illustrations », dans la nav latérale (2.25.0)
```

**L'écran central n'est pas la galerie, c'est la relecture du prompt.** La destination a deux pages,
et on ne va de la première à la seconde qu'en passant par la phase 1 :

1. **le catalogue** — les personnages avec leur pastille d'état, le cadrage, le nombre
   d'images, la graine, et la galerie de ce qui a déjà été produit. Un personnage sans
   attribut cité ni image candidate est **grisé**, avec l'infobulle qui dit quoi faire :
   aucune génération ne part, et aucun message d'erreur n'arrive après le clic ;
2. **la relecture** — le prompt éditable avec son original restaurable, le prompt négatif avec
   le motif de chaque terme, les vignettes en **deux groupes** (identité / registre du tome)
   chacune avec son motif, la source de chaque attribut, et les canaux structurés qu'on peut
   **désarmer** mais pas éditer. « Valider et générer » demande **ton nom**.

⚠ **Il n'y a pas de « générer directement »** — ni bouton, ni raccourci, ni clé de
configuration, pas même pour rejouer une requête déjà validée. Le rejeu passe par `--rejouer`
sur un sidecar, donc sur un prompt qu'un humain a validé une fois.

⚠ **C'est un run par lot, et l'interface le dit.** Le coût mesuré est de 103,7 s par image en
médiane (n = 4, RX 7900 XT) et jusqu'à 1 524 s au pire cas : l'atelier annonce la fourchette
**avant** d'engager le GPU, et sa barre reste indéterminée jusqu'à la première image terminée.
Un pourcentage sur un coût qui varie d'un facteur 14,7 serait faux un jour sur deux.

### Garder, jeter, purger

```powershell
python run_illustration.py "Mon LN" --inventaire   # combien, dans quel état, quel poids
python run_illustration.py "Mon LN" --garder build/Mon_LN/illustrations/aya.png
python run_illustration.py "Mon LN" --jeter  build/Mon_LN/illustrations/rate.png
python run_illustration.py "Mon LN" --purger       # supprime les REJETÉES, sur confirmation
```

| Où | Quoi | Ce que ça devient |
|---|---|---|
| `build/<Projet>/illustrations/` | les candidates | effacées par un `rm -r build/` |
| `build/<Projet>/illustrations/rejetees/` | ce que tu as jeté | **conservé** — un rejet est une donnée de mesure |
| `sources/<Projet>/illustrations/` | ce que tu as **gardé** | survit à `rm -r build/` |

⚠ **Garder DÉPLACE**, image *et* sidecar, et l'image reçoit un suffixe plutôt que d'écraser
une homonyme. Une image produite en 103,7 s de GPU n'est **pas régénérable** : la même graine
sur une autre révision de modèle ne rend pas la même image.

⚠ **Garder l'inscrit dans `bible.yaml` sous `images_generees[]`**, une clé distincte de
`references[]` — et une image produite ne peut donc **jamais** devenir la référence d'une
génération suivante. Reboucler la sortie dans l'entrée ferait dériver le personnage à chaque
tour, et la dérive est invisible image par image.

⚠ **Le poids compte.** À 2,1 Mo par PNG (médiane mesurée) et 8 images par personnage, une
œuvre à 119 personnages atteint **~2,0 Go**, et ces images-là ne se libèrent que par un geste
explicite puisqu'elles vivent sous `sources/`.

---

## 8. Insérer les illustrations dans le tome (lot 27, light novel seulement)

```yaml
# config.yaml
illustration:
  inserer_dans_sorties: true      # false par défaut : un tome relancé sort ISO-OCTET
  insertion:
    position: "debut_chapitre"    # | "fin_chapitre" | "tete_de_volume"
```

Armée, `python run.py "Mon LN" Vol.1` place les images **retenues** dans le Markdown assemblé,
au début du premier chapitre qui **nomme le personnage** — le nom vient du sidecar, pas d'une
devinette. Une image dont le personnage n'apparaît nulle part va en tête de volume plutôt que
d'être perdue, et `RAPPORT.md` le dit, avec le personnage et la graine de chaque image.

⚠ **La légende n'a pas d'interrupteur.** « Illustration générée par IA — ne fait pas partie de
l'œuvre originale », sous chaque image, dans les trois formats. Aucune clé ne la vide ;
`core/insertion.py` lève sur une légende vide. Son texte vient du **pack de langue cible**.

⚠ **Rien n'est composité, aucun caractère de récit n'est réécrit** : on ajoute des paragraphes
neufs entre les siens, et rien d'autre.

---

## 9. Ce que la brique ne fait pas

- **Pas de scène, pas de décor, pas de plusieurs personnages** dans la même image. Le
  périmètre arrêté est « un personnage seul ».
- **Pas d'insertion sans que tu la demandes.** `illustration.inserer_dans_sorties` vaut
  `false` : un tome relancé sort iso-octet. Et rien n'entre jamais dans une **planche** de
  manga — cette clé ne concerne que le light novel.
- **Pas de partage, pas d'export public, pas de mise en ligne.** L'usage arrêté est privé, et
  l'outil ne rend pas facile ce que la décision a exclu.
- **Pas de retouche d'image dans l'interface** (recadrage, correction) : ce serait un lot
  séparé.
- **Aucune image sans marquage.** Chaque PNG porte son bloc `tEXt` (`AIGenerated=true`) et un
  manifeste `.provenance.json` à côté. Il n'y a **aucune clé** pour l'éteindre — AI Act,
  article 50(2), applicable depuis le 2026-08-02.
- **Aucune image sans validation humaine.** Ni drapeau, ni clé de configuration, ni mode
  « tout automatique ». C'est ce qui distingue « assisté » de « généré ».
- **Elle ne dit pas si l'image ressemble au personnage** — **au 2026-09-03**. Le juge
  automatique ne sépare « même personnage » de « personnages différents de la même œuvre » que
  **68 fois sur 100**, et **toute colonne « ressemblance » est donc marquée non opposable**.
  Le protocole humain en aveugle, qui doit servir d'étalon à ce juge, est **outillé depuis le
  lot 29 et n'a jamais été exécuté**.

## 10. Juger la ressemblance, quand tu voudras le faire (lot 29)

Rien de ce qui suit n'est fait par défaut, et rien ne se lance sans toi. C'est une demi-journée
d'œil, et elle n'est pas délégable.

```powershell
python tools/bible.py "Mon LN" --corpus                            # où en est le corpus
python tools/bible.py "Mon LN" --revue --role identite             # le corriger
python tools/banc_identite.py "Mon LN" --etalonnage --markdown     # réétalonner le juge
python tools/banc_identite.py "Mon LN" --devis                     # ce que la suite coûtera
python tools/juge_humain.py "Mon LN" --paires 20 --seuil 14        # le protocole en aveugle
python tools/juge_humain.py "Mon LN" --rapport --markdown          # l'ACCORD des deux juges
```

⚠ **L'ordre n'est pas négociable** : le corpus d'abord, le juge ensuite, la génération en
dernier. Changer de métrique avant d'avoir corrigé le corpus, c'est optimiser un instrument
contre un étalon faux — et le corpus du lot 25 était fait de trois couvertures, dont deux le
même dessin.

⚠ **Le seuil se fixe à la création du protocole, jamais au rapport.** Il n'existe pas d'option
`--seuil` à la lecture ; un seuil qu'on peut passer après avoir vu les résultats ne mesure
rien. Et **n'ouvre pas `protocole.json` avant d'avoir répondu** : il porte la correspondance
entre A/B et les configurations.

⚠ **Le produit n'est pas un verdict, c'est un étalon.** Personne ne sait si 68/100 est un
mauvais score tant que l'accord humain / automatique n'est pas mesuré sur les mêmes paires.

---

## 11. Quand ça ne marche pas, côté jugement

| Symptôme | Où regarder |
|---|---|
| `encodeur du juge introuvable` | dépose le poids ONNX sous `illustration_models/` et renseigne `illustration.identite.encodeur.fichier`. Aucune URL n'est codée dans le dépôt : la licence des poids se vérifie à la source primaire |
| `--rapport` dit « accord non mesuré » | soit le protocole n'a pas de référence, soit l'encodeur manque. C'est une **absence de mesure**, pas un désaccord : un accord de 0 % voudrait dire autre chose |
| `--paires` dit « rien à comparer » | le dossier `illustrations/balayage/` ne porte pas deux images. Lance d'abord `tools/banc_identite.py … --balayage` |
| `verdict: null`, « n'en résume pas N » | les paires opposent plus de deux configurations. « 14 sur 20 » compare **deux** configurations ; les voix sont publiées duel par duel, sans verdict global |
| Le juge est déclaré **inutilisable** | c'est un résultat, pas une panne. Les colonnes de ressemblance sont alors étiquetées d'après le juge humain, pas d'après lui |

Les mesures qui justifient chaque valeur de cette fiche vivent dans
[`../mesures/`](../mesures/README.md) — lots 24 à 29.
