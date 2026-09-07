# PLAN 30 — Les canaux qui manquent : la position, la forme, la pose

> **Lire `00-CONTEXTE-AGENT.md`, `README-ILLUSTRATION-23-27.md`, puis `README-COMFYUI-28-30.md`.**
>
> **Nature attendue** — **MINEUR**. Un ou deux graphes de plus, des canaux **désarmés** par défaut,
> aucun changement du chemin nominal.
>
> **Charge estimée** — 10 jours, dont une part de R&D au résultat incertain. Ce lot peut se conclure
> par « aucun canal ne mérite d'être livré », et ce serait un résultat conforme.
>
> **⚠ Se lance sur le PC PRINCIPAL** — il installe des nœuds, télécharge des poids et génère.
>
> **⚠ Prérequis : `PLAN-28`** (le validateur, sans quoi chaque nouveau graphe se casse après le
> déchargement du LLM) **et `PLAN-29`** (sans juge étalonné, l'apport d'un canal ne se constate pas).

---

## 1. L'état, relevé à la source le 2026-08-30

Le lot 26 étape 0.4 a inventorié les canaux **sur le serveur réel** — `GET /object_info`, 907 nœuds —
et pas dans une page web, « une page amont peut annoncer un canal que l'installation locale n'a pas » :

| Canal | Argument / nœud | Exposé ? | Poids | Licence | État |
|---|---|---|---|---|---|
| images de référence | `TextEncodeQwenImageEditPlus` | ✅ | aucun | Apache-2.0 vérifiée | **LIVRÉ** |
| entités + masques | `eligen_entity_prompts` / `eligen_entity_masks` | ❌ **aucun nœud** | `Qwen-Image-EliGen-V2`, 0,2 Md | Apache-2.0 vérifiée | candidat non livré |
| image de contrôle | `ModelPatchLoader` → `QwenImageDiffsynthControlnet` | ✅ nœud présent, **liste de poids VIDE** | `MODEL_PATCH` ~1 Md | Apache-2.0 vérifiée | candidat non livré |
| couches | `EmptyQwenImageLayeredLatentImage` | ✅ | `Qwen-Image-Layered` | non instruite | **hors périmètre** |

**Et la marge existe** : après une génération réelle, il reste **8,4 à 9,1 Go libres** sur les
20 464 Mio de la carte. Un `MODEL_PATCH` d'environ 1 Md y tient.

⚠ **Ce qui a bloqué le lot 26 n'était pas la place, c'était l'ordre.** Son raisonnement est juste et
il faut le garder en tête : mesurer le coût VRAM de ces poids aurait demandé de les télécharger,
c'est-à-dire de télécharger des poids **dont l'apport n'est pas mesuré non plus** — « un canal dont
l'apport n'est pas mesuré est un canal qu'on ne livre pas ». Ce lot lève le blocage dans le bon
sens : il **mesure l'apport d'abord**, sur un seul canal, et n'installe que ce qu'il faut pour cela.

---

## 2. Étape 0 — décider quel canal vaut une installation

### 0.1 — Quel écart chacun promet de corriger

Ne partez pas de ce que le canal sait faire, partez de ce qui **ne va pas** dans les images actuelles.
Les deux écarts qui restent après le lot 26 sont mesurés :

| Écart mesuré | Généré | Tome | Quel canal le viserait |
|---|---:|---:|---|
| part d'aplats | 0,6300 | **0,3669** | ⚠ d'abord le **prompt** (`PLAN-29` L29.4) ; puis les **masques**, qui permettent de décrire un fond au lieu de le laisser uni |
| densité de trait | 0,1188 | **0,2664** | les **références** au trait (`PLAN-29` L29.1) ; aucun canal de ce lot ne la vise directement |
| cadrage et place du personnage | non mesuré | — | les **masques** (EliGen) |
| pose | non mesuré | — | l'**image de contrôle** |

⚠ **Deux des quatre lignes se corrigent sans installer quoi que ce soit**, et elles appartiennent au
`PLAN-29`. **Si ce plan est exécuté avant que le 29 ait livré, il installera des poids pour un
problème que le 29 aurait réglé pour un mot.** C'est le motif du prérequis.

**Publiez ce tableau rempli, avec l'état après le `PLAN-29`**, et choisissez **un** canal. Pas deux.

### 0.2 — Ce qu'une installation engage

Trois choses à écrire avant de télécharger, et la troisième est celle qu'on oublie :

1. **la licence des POIDS, vérifiée à la source primaire** le jour de l'installation. Apache-2.0 a
   été vérifiée le 2026-08-30 pour les deux candidats ; revérifiez, une page bouge ;
2. **le nœud tiers** qui expose le canal : son dépôt, sa licence, sa date de dernier commit. Un canal
   qui dépend d'un nœud abandonné est une dette ;
3. **le coût en surface de test.** Chaque canal ajoute un graphe à valider, des marqueurs à
   substituer, un motif de refus, et une ligne dans `requete.yaml`. Le dépôt a déjà refusé OpenCV
   pour 60 Mo ; un canal se juge aussi à ce prix-là.

### 0.3 — Le coût mesuré, sur la marge et non sur la fiche

Après installation, relevez ce que le journal du serveur dit — pas ce que la taille du fichier
annonce : `loaded completely` ou `loaded partially`, le `lowvram patches: N` s'il apparaît, le pic de
VRAM, et le temps par image comparé aux **233,7 s** de l'édition à une référence.

⚠ **Un `lowvram patches` qui apparaît après l'installation du canal est un signal d'arrêt** : cela
signifie que le transformeur a été rogné pour faire de la place, et le lot 24 a chiffré ce que cela
coûte — **facteur 9,6** sur le pas de débruitage. Un canal qui déclenche le rognage ne se livre pas,
même s'il améliore l'image.

---

## L30.1 — Le canal retenu, un graphe, un marqueur, un refus

Un graphe de plus dans `illustration/workflows/`, dérivé du graphe d'édition **qui marche**, avec les
marqueurs que le client connaît déjà (`%masque_1%`, `%entite_1%`, `%image_controle%`) — ils sont
**déjà** dans `MARQUEURS`, il n'y a rien à inventer côté client.

Trois exigences reprises du plan de série :

1. **le canal est désarmé par défaut.** Le graphe par défaut de `config.yaml` ne change pas ;
2. **le refus reste nommé.** Un graphe qui ne porte pas le marqueur refuse le canal avant le GPU —
   c'est déjà le comportement, ne l'affaiblissez pas pour faire passer un cas ;
3. **le validateur du `PLAN-28` connaît le nouveau graphe** et vérifie que le nœud et son poids
   existent. Un canal livré sans validateur est un canal qui échouera chez l'utilisateur.

⚠ **Les masques doivent venir de quelque part.** Un masque n'est pas une donnée que l'utilisateur
dessinera à la main dans un fichier YAML. Le plus honnête pour un premier lot : **des masques
géométriques dérivés du cadrage** — le rectangle du personnage pour `visage`, `buste`, `pied`, déjà
un choix du gabarit. Un éditeur de masque est un lot à lui seul, et le `PLAN-27` L27.1 bis a déjà
écrit qu'il ne le fait pas.

## L30.2 — La mesure, sur le même banc que les autres

`tools/banc_identite.py` et `tools/banc_prompt.py` existent. Le canal se mesure **avec eux**, sur les
mêmes descripteurs, le même juge étalonné, les mêmes dénominateurs — sinon son apport n'est pas
comparable à celui des références, et c'est la seule comparaison qui décide.

**Publiez les quatre grandeurs côte à côte** : ressemblance (opposable seulement après le `PLAN-29`),
nouveauté, style, et **temps par image**. Un canal qui gagne 0,01 de style pour +120 s par image est
un canal qu'on documente et qu'on ne livre pas.

## L30.3 — La copie non marquée, et c'est une dette de la frontière

`SaveImage` écrit une copie dans le dossier de sortie de ComfyUI. Angelith récupère l'image, la
marque, l'écrit sous `build/<Projet>/<Tome>/illustrations/` — mais **la copie de ComfyUI ne porte ni
bloc `tEXt` ni sidecar**.

La lecture actuelle est défendable et elle est écrite : « la frontière d'écriture d'Angelith couvre
**ses** écritures, pas celles d'un programme tiers que l'utilisateur a lancé lui-même ». Elle reste
une **surface d'erreur** : une image de synthèse non marquée, sur le disque, hors de toute trace, au
moment même où le dépôt fait du marquage un défaut sans interrupteur (AI Act art. 50(2)).

**Deux corrections possibles, à trancher sur mesure :**

| Option | Ce qu'elle coûte | Ce qu'elle règle |
|---|---|---|
| remplacer `SaveImage` par **`SaveImageWebsocket`** dans les graphes du dépôt | l'image transite par le websocket ; le client doit le gérer, et `/view` ne sert plus | ✅ plus aucune copie non marquée |
| documenter et laisser | rien | ⚠ rien, mais c'est honnête et déjà écrit |

⚠ **Mesurez avant de choisir** : `SaveImageWebsocket` change le chemin de récupération de l'image,
donc le cœur du client, pour un gain de conformité sur une copie locale. Si le transport websocket
s'avère fragile sur cette pile, **livrez la documentation et dites pourquoi** — c'est la même
discipline que le `/free` désarmé.

## L30.4 — `/free`, une fois sur sept, et peut-être plus jamais

`illustration.vram.decharger_image` est désarmé pour une raison mesurée : sur **7 appels à `/free`,
1 a fait segfauter ComfyUI** (violation d'accès `0xC0000005` dans son propre
`comfy/model_management.py:model_unload`). Le plantage est chez ComfyUI.

Ce lot fait deux choses, et pas une de plus :

1. **revérifier sur la version installée du jour.** Un correctif amont peut avoir eu lieu ; 7 appels
   ne sont pas un dénominateur solide. Relevez-en **20**, et publiez le taux avec sa version de
   ComfyUI ;
2. **armer, ou ne pas armer, d'après ce chiffre** — et si le taux reste non nul, garder désarmé en
   documentant le geste manuel (`POST /free`, mesuré : 12 083 Mio → ~470 Mio).

⚠ **Ne contournez pas le segfault par une relance automatique de ComfyUI.** Angelith ne pilote pas le
cycle de vie d'un programme que l'utilisateur a installé ; le faire créerait une dépendance qu'aucune
mesure ne justifie.

---

## 3. Les critères de ce lot

1. Le tableau « quel écart chaque canal viserait » est publié **après** le `PLAN-29`, et **un** canal
   est choisi sur cette base.
2. Licence des poids et du nœud tiers **vérifiées à la source primaire le jour de l'installation**,
   avec l'URL, la date et l'empreinte SHA-256 du fichier récupéré.
3. Le coût est relevé dans le **journal du serveur** : chargement complet ou partiel, `lowvram
   patches`, pic de VRAM, temps par image contre les 233,7 s de référence. **Un rognage constaté
   annule la livraison du canal**, et c'est écrit.
4. Le canal est livré **désarmé**, avec son graphe dédié, son marqueur, son refus nommé, et le
   validateur du `PLAN-28` le connaît.
5. Les quatre grandeurs (ressemblance, nouveauté, style, temps) sont publiées côte à côte, sur le
   corpus du `PLAN-29`.
6. La question de la copie non marquée est tranchée : `SaveImageWebsocket` mesuré et adopté, ou refusé
   avec son motif.
7. Le taux d'échec de `/free` est repris sur **20 appels** avec la version de ComfyUI, et
   `decharger_image` est armé ou reste désarmé **d'après ce chiffre**.
8. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe sans serveur, sans poids et
   sans GPU.
9. `docs/mesures/canaux-<date>.md` reprend ces critères un par un, y compris les non tenus, et dit ce
   que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il n'installe **pas deux** canaux. Un seul, celui dont l'apport est mesuré.
- Il ne livre aucun éditeur de masque : les masques du premier lot sont géométriques et dérivés du
  cadrage.
- Il ne touche ni au juge, ni au corpus, ni au prompt.
- Il ne pilote pas le cycle de vie de ComfyUI.
- Il ne sort pas du périmètre « un personnage seul » : ni planche, ni grille de variantes, ni couches.
