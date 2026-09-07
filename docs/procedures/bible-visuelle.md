# Procédure — la bible visuelle (`tools/bible.py`)

Rassembler ce que le dépôt sait déjà de l'**apparence** d'un personnage et du **registre
graphique** d'un tome : les illustrations de `media/`, les phrases des chapitres traduits, et
le glossaire de l'œuvre.

> **Cette brique ne génère aucune image**, n'importe aucun modèle génératif, ne touche à aucun
> pixel d'une planche et n'entre dans aucun cache. Elle lit et elle écrit deux fichiers, tous
> deux sous `sources/<Projet>/`.

---

## 1. Ce que ça produit, et où

| Fichier | Écrit par | Ce que c'est |
|---|---|---|
| `sources/<Projet>/bible.propositions.yaml` | `--proposer` | ce qu'un modèle **propose**. Rien n'y est vrai tant qu'un humain ne l'a pas lu |
| `sources/<Projet>/bible.yaml` | `--revue` | ce qu'un humain a **validé**. C'est le seul fichier qui fait autorité |

⚠ **La bible n'entre JAMAIS dans le prompt du traducteur.** C'est un fichier **séparé** du
glossaire, et pour une raison de fond : y ajouter un champ ferait entrer l'apparence dans le
prompt, donc changerait le caractère de la traduction de tous les tomes — un MAJEUR.

⚠ Les deux fichiers restent sous `sources/`, que `.gitignore` exclut **en bloc** : l'arbre git
exposerait sinon le nom de chaque œuvre comme nom de dossier. Ne pas les déplacer ailleurs.

## 2. Regarder ce qu'on a, sans rien écrire

```powershell
python tools/bible.py --tous --inventaire        # classes d'illustrations, par tome
python tools/bible.py "Mon LN" --inventaire
python tools/bible.py --tous --signature         # la signature de style de chaque tome
```

`--inventaire` classe chaque fichier de `media/` en **couverture / pleine page / double page /
vignette / indéterminée**, et dit s'il est posé dans un chapitre, en tête de volume, ou cité
par personne. Les seuils sont **tous relatifs au tome** — sa propre surface médiane, sa propre
dynamique de luminance.

`--signature` mesure le registre graphique : palette dominante, saturation, contraste, densité
de trait, part d'aplats. **Chaque signature porte son `echantillon`** — une signature calculée
sur 3 images et une sur 30 ne valent pas la même chose.

## 3. Proposer

```powershell
python tools/bible.py "Mon LN" --proposer                  # texte + illustrations
python tools/bible.py "Mon LN" --proposer --sans-images    # texte seul, aucun appel vision
python tools/bible.py "Mon LN" --proposer --lot 25         # passages par appel LLM
```

Deux passes, dans cet ordre :

1. **lexicale, déterministe** — croise un lexique d'apparence avec le nom du personnage et ses
   variantes, dans une fenêtre de deux phrases. Aucun modèle. C'est elle qui donne le
   dénominateur : *combien de personnages ont au moins un passage candidat* ;
2. **modèle** — sur les seuls passages candidats, puis une fois par illustration exploitable.

**Ce que le code refuse au modèle, et c'est le point de l'outil :**

- un **nom hors glossaire** est rejeté, pas ajouté — le glossaire reste la source unique des
  noms ;
- une ligne **sans numéro de passage valable** est rejetée sans être lue ;
- une **valeur qui est une phrase** est rejetée plutôt que tronquée — une phrase tronquée reste
  fausse.

Le compte des refus est affiché, avec quelques lignes en exemple. Le lire : sur roman D,
`passage_invalide: 25` ne se comprend qu'en voyant les lignes — le modèle y répétait le même
attribut en incrémentant le numéro de passage **de 26 à 50**, hors du lot fourni.

## 4. Relire, et c'est la seule chose qui fait entrer quoi que ce soit

```powershell
python tools/bible.py "Mon LN" --revue
python tools/bible.py "Mon LN" --revue --role identite    # ne relit que l'identité (lot 29)
python tools/bible.py "Mon LN" --revue --ecrire-genre     # ⚠ voir plus bas
python tools/bible.py "Mon LN" --revue --tout             # repasse aussi les entrées validées
```

La revue présente, personnage par personnage : chaque attribut proposé **avec sa citation**,
puis les illustrations candidates, puis les ancrages de style. Réponses : `o` retenir, `n`
rejeter, `?` ou `Entrée` passer, **`O` tout accepter pour ce personnage**.

### Depuis le lot 29 : le compte, le rôle, et le rectangle

**Le compte s'affiche avant ET après chaque revue**, en deux lignes : les références
d'identité validées par personnage (0 / 1 / 2 / ≥3), puis les mêmes **sans les couvertures**.
La cible est **8 personnages, dont 4 à 3 références ou plus, aucune couverture parmi elles**.
Pour le voir sans rien relire :

```powershell
python tools/bible.py "Mon LN" --corpus
python tools/bible.py --tous --corpus --markdown
```

⚠ **L'écart entre les deux comptes est le sujet.** Une couverture porte le titre de l'œuvre en
grandes lettres : excellente ancre de **style**, mauvaise référence d'**identité**, et ces
pixels partent dans le conditionnement. Au lot 25, les trois références validées du corpus
étaient trois couvertures — dont deux le même dessin — et le seul compte de gauche disait
« corpus prêt ». `--role identite` les **repousse en dernier sans les cacher** : un personnage
dont la couverture est la seule référence n'a pas d'autre choix.

**Sur une référence d'identité retenue, la revue propose un rectangle.** Elle demande le
cadrage (`visage` / `buste` / `pied`, ou `n` pour la page entière), affiche le cadre proposé
**avec le motif sur lequel il repose**, et attend : `Entrée` le garde, quatre fractions le
corrigent, `n` l'abandonne.

⚠ **C'est une assistance, pas une automatisation, et le chiffre le dit.** Le rectangle vient
de la boîte d'encre — aucune détection de visage, aucun OpenCV — et sur les 402 illustrations
du corpus elle couvre une **médiane de 77,5 %** de la page : elle retire les marges, pas la
page. Le motif affiché nomme son hypothèse en toutes lettres (« le haut de l'encre est la
tête »), parce qu'on ne corrige bien que ce dont on connaît la construction. Mesuré le
2026-09-03 (`docs/mesures/identite-2026-09-03.md` §3.2).

⚠ **Le champ s'appelle `cadre`.** Jusqu'au lot 29, la passe de propositions écrivait
`recadrage: []` pendant que le moteur lisait `cadre` : le champ **ne pouvait pas être rempli**.
L'ancien nom reste relu comme alias, et un cadre invalide est désormais **signalé** au lieu de
faire retomber la référence sur la page entière en silence.

**La règle non négociable :** *un attribut sans `citations[]` n'entre pas dans la bible.*
`bible.save` **retire** un attribut non cité au lieu de le signaler, et dit ce qu'il a retiré.
Un attribut sans sa source n'est pas une observation, c'est une invention — et il se
propagerait dans toutes les images générées du personnage sans que personne sache d'où il vient.

## 5. Mesurer

```powershell
python tools/bible.py --tous --rapport
python tools/bible.py --tous --rapport --markdown > docs/mesures/bible-visuelle-<date>.md
```

Colonnes : couverture de référence (personnages avec ≥ 1 référence **validée par un humain**),
couverture d'attributs, genre avant/après, illustrations exploitées, et **abstentions du LLM**.

⚠ **Une abstention basse est suspecte, pas rassurante.** Sur roman D, 26 des 35 appels vision
n'ont produit aucun attribut de certitude déclarée — sur des planches d'action, de décor ou de
personnage secondaire, c'est la réponse correcte.

---

## `--ecrire-genre` : le seul geste qui change une sortie de traduction

```powershell
python tools/bible.py "Mon LN" --revue --ecrire-genre
```

Quand une citation ou une illustration lève le genre d'un personnage, la revue propose de
l'écrire **dans `glossaire.yaml`** — c'est-à-dire dans le seul champ que le traducteur lit
déjà, et qui commande les accords français.

⚠ **Ce n'est pas un changement de schéma** — le champ existe et il est vide. **C'est un
changement de sortie** : les accords d'un tome relancé changeront. D'où l'option explicite,
jamais un défaut, et une confirmation à l'écran avant la première écriture.

L'outil affiche un **indice déterministe** à côté de la question, avec ses phrases. Cet indice
est mesuré contre les genres déjà déclarés du corpus : **26 concordances sur 26, zéro
contradiction**, pour un rappel de **24,8 %**. Autrement dit il est **silencieux quatre fois
sur cinq**, et c'est voulu : un motif large aurait un meilleur rappel et une précision
inconnue, et produirait « il est arrivée » sur un tome entier.

---

## Les clés de `config.yaml` qui changent le résultat

**Aucune.** Cette brique n'ajoute aucune clé, armée ou non. Elle lit les sections existantes :

| Clé lue | Effet |
|---|---|
| `chemins.sources` / `chemins.build` | où sont les projets et les tomes |
| `chemins.glossaire_fichier` | le glossaire de l'œuvre, source unique des noms |
| `langues.cible` | quel pack fournit `prompts/bible_apparence.md` |
| `llm.*` et `modeles.*` | le serveur et les modèles disponibles |

Les seuils de classement et les descripteurs de style sont des **constantes documentées** de
`core/illustrations.py`, pas des clés : rien du chemin nominal ne lit la bible, et une clé que
rien ne lit encombrerait un fichier qui est un document.

### Le drapeau qui compte à la place

```powershell
python tools/bible.py "Mon LN" --proposer --agent mise_en_page      # le défaut
```

⚠ **`mise_en_page` et non `terminologue`** : c'est le seul agent du roster livré avec le
**raisonnement coupé**. Mesuré — avec `terminologue`, 8 des 10 lots de la passe texte sortent
« génération coupée net au plafond max_tokens », le budget entier étant parti dans le
`<think>`. Relever un attribut n'est pas un problème de raisonnement, c'est une lecture.

### Le prompt

`langues/<code>/prompts/bible_apparence.md`. Il est livré dans les deux packs et **absent de
`core/langues.py:PROMPTS_REQUIS`**, comme `manga_relecteur.md` : l'y ajouter rendrait invalide,
au démarrage d'un run de traduction, tout pack tiers écrit avant. Son absence vaut **refus
explicite** de la brique — jamais un repli silencieux vers le français.

---

## Quand ça ne marche pas

| Symptôme | Où regarder |
|---|---|
| `0 personnage a un passage candidat` | le projet n'a pas de `build/<Projet>/<Tome>/chapters/` — c'est le cas de tous les projets **manga**, qui n'ont ni texte traduit ni `media/` |
| `--inventaire` ne montre aucun tome | le tome n'a pas de dossier `media/` : les illustrations n'ont pas été extraites |
| Beaucoup de `passage_invalide` | lire les exemples affichés. C'est en général une boucle du modèle, et le refus est le bon comportement |
| Un attribut a disparu de `bible.yaml` | il n'avait pas de citation. La liste des attributs retirés est affichée à l'écriture |
| Une signature à `echantillon: 3` | le tome n'a que 3 illustrations exploitables. Le champ est là pour que ce soit visible, pas pour être ignoré |
| Le prompt manque | le pack de langue cible ne fournit pas `bible_apparence.md`. C'est un refus explicite, pas une panne |
| `--corpus` dit « aucune bible » | `bible.yaml` n'existe pas encore pour ce projet — lance `--proposer` puis `--revue` |
| La cible du `PLAN-29` reste hors d'atteinte | regarde d'abord combien d'illustrations **hors couverture** le tome porte : `python tools/bible.py "Mon LN" --inventaire`. Sur le corpus de référence il y en a 31 pour un besoin de 24 — la ressource n'est pas le blocage, l'œil humain l'est |
| Le cadre proposé prend toute la page | c'est le cas le plus fréquent, et c'est mesuré : médiane 77,5 % sur 402 illustrations. La boîte d'encre retire les marges, pas la page. Corrige le rectangle à la main |

La mesure complète du lot, avec ses trois résultats négatifs, est dans
[`../mesures/bible-visuelle-2026-08-29.md`](../mesures/bible-visuelle-2026-08-29.md). Ce que
le lot 29 y ajoute — le compte du corpus, le rôle à la revue, le rectangle proposé et les deux
noms du champ de recadrage — est dans
[`../mesures/identite-2026-09-03.md`](../mesures/identite-2026-09-03.md).
