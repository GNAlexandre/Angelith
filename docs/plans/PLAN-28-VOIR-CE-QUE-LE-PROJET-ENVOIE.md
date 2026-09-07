# PLAN 28 — Voir ce que le projet envoie à ComfyUI

> **Lire `00-CONTEXTE-AGENT.md`, `README-ILLUSTRATION-23-27.md`, puis `README-COMFYUI-28-30.md`.**
>
> **Nature attendue** — **MINEUR**. Un outil neuf, un `--check` enrichi, un fichier de trace en
> plus. **Aucune image ne change**, aucun prompt, aucun seuil, aucun format de sortie.
>
> **Charge estimée** — 8 jours.
>
> **⚠ Ce plan se lance sur le PC PRINCIPAL.** Il n'a aucun sens sur le secondaire : tout ce qu'il
> produit est une lecture du serveur ComfyUI et de la carte.
>
> **Le problème qu'il traite, dit par l'utilisateur** : « la construction et le déploiement du
> système d'image se fait au travers du projet sans que je puisse avoir une réelle vision sur ce
> dernier. » Ce n'est pas un problème de confort. Un pipeline qu'on ne peut pas inspecter ne peut
> pas être débogué, et une mesure qu'on ne peut pas rejouer à la main n'est pas une mesure.

---

## 1. Ce qui existe déjà, et qu'il ne faut pas réécrire

| Brique | Où | Ce qu'elle sait déjà faire |
|---|---|---|
| le client | `illustration/comfyui.py` | substitution de marqueurs, `/prompt`, sondage de `/history`, `/view`, `/upload/image`, `/free`, `/system_stats` |
| la lecture des canaux | `illustration/comfyui.py:MARQUEURS` | `CANAUX_SUPPORTES` est **lu dans le graphe** ; un canal absent est refusé avec un motif nommé |
| le sondage du serveur | `tools/banc_prompt.py` l. 267 et 623 | `GET /object_info` (907 nœuds relevés) et `GET /system_stats` |
| les graphes | `illustration/workflows/` | trois `.api.json`, dont **un seul** porte `%reference_1%` |

⚠ **`tools/banc_prompt.py` sait déjà interroger `/object_info`.** Ce lot **extrait** ce code, il ne
le duplique pas. Un second sondeur qui divergerait du premier est précisément le défaut que
`core/config_schema.py` documente en tête : « une liste recopiée à la main dérive, et une référence
qui dérive produit de **faux** avertissements — ce qui est pire que pas de vérification du tout ».

---

## 2. Étape 0 — relever la pile, une fois, proprement

### 0.1 — Quelle installation, et où sont ses modèles

Le document de mesure du 2026-08-29 dit ComfyUI **0.34.2 standalone `win-amd`** ; l'utilisateur
décrit une installation **Desktop**. Les deux existent et **ne rangent pas les modèles au même
endroit**. Relevez, et écrivez-le dans `docs/procedures/comfyui.md` §0 :

- version et variante (`GET /system_stats`, et ⚙ → About) ;
- les dossiers de modèles réellement lus (`extra_model_paths.yaml` s'il existe) ;
- les nœuds tiers installés, avec leur licence.

**C'est la seule information de la série qui ne se déduit de rien.** Tant qu'elle n'est pas écrite,
tout diagnostic de « fichier introuvable » est une devinette.

### 0.2 — Ce que le serveur expose vraiment, en un tableau

`GET /object_info` rend les nœuds **et le contenu des listes déroulantes**. Publiez, pour les nœuds
que les trois graphes du dépôt utilisent : le nœud existe-t-il, et **le fichier de modèle nommé dans
le graphe est-il dans sa liste** ?

C'est la vérification qui manque aujourd'hui, et elle est bon marché. Un graphe versionné dans le
dépôt stocke le **nom** du fichier, pas un identifiant : renommer un modèle, ou changer de machine,
casse le graphe **au premier appel**, après le déchargement du LLM — donc au pire moment.

### 0.3 — Combien de temps une session perd-elle sur des causes déjà connues ?

Relevez, dans les journaux et l'historique du 2026-08-29 et 30, **les erreurs qui ont réellement
coûté du temps**. Le §9 de `docs/procedures/comfyui.md` en liste onze, toutes mesurées. Combien
seraient attrapées **avant** le GPU par une validation statique du graphe ? C'est ce chiffre qui
dimensionne L28.2, et non une intuition d'ergonomie.

---

## L28.1 — `tools/comfy.py` : la sonde et le validateur

Un outil, cinq sous-commandes, aucune qui envoie une génération.

```powershell
python tools/comfy.py --sonde                       # version, VRAM, nœuds, listes de modèles
python tools/comfy.py --valider <workflow.api.json> # avant le GPU : marqueurs, nœuds, modèles
python tools/comfy.py --graphe <requete.yaml>       # le graphe SUBSTITUÉ, écrit sur disque, non envoyé
python tools/comfy.py --diff <a.json> <b.json>      # ce qui change entre deux graphes
python tools/comfy.py --journal                     # le dernier run : temps, pic VRAM, lignes clés
```

**`--valider` est le cœur du lot.** Il vérifie, sans dépenser une seconde de GPU :

1. le fichier est bien au **format API** et non au format écran — le client sait déjà le dire, mais
   il le dit trop tard ;
2. chaque `class_type` du graphe **existe** dans `/object_info` ;
3. chaque valeur qui désigne un fichier de modèle (`unet_name`, `clip_name`, `vae_name`,
   `lora_name`, `image`) est **présente dans la liste** que le nœud expose ;
4. les marqueurs présents, et donc **les canaux que ce graphe déclare** — la même lecture que
   `MARQUEURS`, réutilisée et non recopiée ;
5. la **cohérence pas/guidage** : si le graphe porte une LoRA Lightning et que `config.yaml` demande
   `guidage: 4.0`, dites-le. C'est le premier défaut de la liste du §9 de la procédure, et il produit
   des images brûlées sans aucun message.

⚠ **`--graphe` est ce qui rend la vision.** Il écrit le JSON exactement tel qu'il partirait, marqueurs
substitués, références téléversées **non comprises** (les chemins sont laissés lisibles et le fichier
dit lesquels seraient téléversés). Ce fichier s'ouvre **dans ComfyUI** — glisser-déposer d'un
`.api.json` recharge le graphe — et c'est ainsi qu'on rejoue à la main ce que le projet a fait tourner.

⚠ **Aucune sous-commande n'envoie de génération.** L'outil est en lecture ; générer reste le travail
de `run_illustration.py`, qui porte la porte humaine et le marquage. Un outil qui pourrait générer
sans passer par la porte serait une seconde porte, non gardée.

## L28.2 — `--check` refuse avant le GPU, et dit quoi corriger

`run_illustration.py --check` existe. Il doit désormais faire tourner **la validation de L28.1** et
refuser, avec un motif nommé, quand :

- le serveur ne répond pas à `base_url` ;
- le workflow n'est pas au format API, ou nomme un nœud absent, ou un modèle absent ;
- `pas`/`guidage` contredisent le graphe ;
- un canal exigé par la requête n'est pas déclaré par le graphe — c'est déjà le cas, gardez-le ;
- la VRAM libre est inférieure au pic mesuré pour ce graphe (**14 417 Mio** relevé le 2026-08-29 sur
  le graphe Lightning) : dites-le **avant** de décharger le LLM, pas après.

Le message porte la **correction**, pas seulement le constat. Le dépôt a déjà ce standard : le
message d'échec de `tests/test_config_valide.py` « dit quoi coller ».

## L28.3 — Le graphe part avec l'image, dans la trace

Le sidecar de provenance archive déjà le payload de la requête. Ajoutez-y — ou à côté, sous le même
nom — **le graphe réellement envoyé**, et les trois lignes de journal qui décident : `loaded
completely` ou `loaded partially`, le `lowvram patches: N` s'il y en a, et le `Prompt executed in …`.

⚠ **C'est la différence entre une trace et un souvenir.** Aujourd'hui, un run qui a produit une image
étrange ne laisse aucun moyen de savoir si le transformeur avait été rogné — donc si l'image a été
produite dans le régime mesuré ou dans l'autre, celui à 64,3 s/pas.

⚠ **Ne mettez pas le graphe dans le PNG.** Le bloc `tEXt` porte l'identité de l'image, pas un JSON de
plusieurs kilo-octets. Un fichier à côté, ou une clé du sidecar — qui est déjà un `.json`.

## L28.4 — Une affirmation d'état porte sa date

`illustration/comfyui.py` l. 34 dit encore « Ce client **n'a jamais tourné contre un vrai serveur
ComfyUI** ». C'était vrai en 2.15.0 ; la 2.16.0 l'a mesuré sur **25 générations, 0 échec
d'exécution**, et la 2.18.0 a fait un run complet.

1. **Corrigez la phrase**, et renvoyez vers le document de mesure qui porte l'état à jour.
2. **Relevez les autres.** Cherchez dans `illustration/` et `core/` les affirmations d'état — « n'a
   jamais », « pas encore », « non mesuré », « à vérifier » — et donnez à chacune **sa date** et le
   document qui l'établit. Publiez le relevé : combien d'affirmations, combien périmées.
3. **La règle générale, à écrire dans le `00-CONTEXTE-AGENT.md`** : le dépôt exige déjà qu'un chiffre
   porte son dénominateur ; une affirmation d'état doit porter sa date, pour la même raison. Un
   commentaire qui vieillit sans le dire est un faux avertissement, et un faux avertissement se
   cesse d'être lu.

⚠ **Un document daté de `docs/mesures/` n'est PAS concerné** : il décrit l'état de son jour, c'est sa
fonction, et le réécrire serait effacer l'histoire de la mesure. Seul le code est visé.

## L28.5 — La procédure est un livrable, pas une annexe

`docs/procedures/comfyui.md` a été écrite le 2026-08-31 depuis les documents de mesure. Ce lot la
**corrige avec ce que la sonde révèle** : la variante d'installation, les dossiers réels, les nœuds
tiers, et tout écart entre ce qu'elle affirme et ce que le serveur dit.

Ajoutez la ligne correspondante au tableau de `docs/procedures/README.md`, et vérifiez que la fiche
finit bien par « quand ça ne marche pas » — c'est le contrat de ce dossier.

---

## 3. Les critères de ce lot

1. La variante d'installation, les dossiers de modèles et les nœuds tiers sont **relevés et écrits**,
   avec la sortie de `/system_stats` citée.
2. `tools/comfy.py --sonde` et `--valider` existent, réutilisent le code de sondage de
   `tools/banc_prompt.py` (extrait, pas dupliqué) et **ne peuvent pas générer**.
3. `--valider` attrape, sur les trois graphes du dépôt, au moins : format écran, nœud absent, modèle
   absent, incohérence pas/guidage, canaux déclarés. Le tableau des cinq vérifications est publié
   avec, pour chacune, **un cas réel où elle aurait servi**.
4. `--graphe` produit un `.api.json` qui **se recharge dans ComfyUI** et reproduit l'image à la main.
   Vérifié une fois, avec la graine, et l'image comparée.
5. `--check` refuse avant tout déchargement de LLM, et chaque refus porte sa correction.
6. Le graphe envoyé et les trois lignes de journal sont archivés à côté de chaque image.
7. Le relevé des affirmations d'état est publié ; celle de `comfyui.py` l. 34 est corrigée ; la règle
   « une affirmation d'état porte sa date » est écrite dans `00-CONTEXTE-AGENT.md`.
8. `ruff check .` passe ; `pytest -q -m "not modeles and not lent"` passe **sans serveur ComfyUI** —
   la sonde et le validateur se testent contre un `/object_info` factice, comme le client se teste
   déjà contre un transport factice.
9. `docs/mesures/comfy-visible-<date>.md` reprend ces critères un par un, y compris les non tenus,
   et dit ce que la mesure ne dit pas.

## 4. Ce que ce lot ne fait pas

- Il ne change **aucune** image, aucun prompt, aucun seuil, aucun descripteur.
- Il n'installe aucun nœud tiers et ne télécharge aucun poids : c'est le `PLAN-30`.
- Il ne touche pas au juge ni au corpus : c'est le `PLAN-29`.
- Il n'ajoute **aucun** chemin capable de générer hors de la porte humaine.
