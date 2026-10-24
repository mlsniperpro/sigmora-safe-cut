# Safe Cut labelling guide

Status: **v1, written 2026-10-24 (PRE-B, before kickoff).** Source rules: [EVAL.md](../EVAL.md) §1 (entities and labels) and §6 (schedule), [DESIGN.md](../DESIGN.md) §2.5 (policy) and §2.7b (identifiability), [SHOTLIST.md](../SHOTLIST.md) (the clip categories). WP7 copies this file to `eval/LABELING-GUIDE.md` at kickoff; until then this is the master copy.

Related files in this folder: [CVAT-SETUP.md](CVAT-SETUP.md) (the tool), [LABEL-FORMAT.md](LABEL-FORMAT.md) (the files you produce), [SCHEDULE.md](SCHEDULE.md) (how long it takes and in what order).

## 1. What you are deciding

For every clip you answer one question per person or object:

> **Could this clip be published with this person or item visible, without anyone's further consent?**
> If yes, `should_hide: false`. If no, `should_hide: true`.

That is the ground truth Safe Cut is scored against. Recall, exposure and leak bursts are measured on the `should_hide: true` entities; over-blur is measured on the `should_hide: false` ones ([EVAL.md](../EVAL.md) §2). A wrong label moves a number in the submission, so label what is true, not what you expect the model to get right.

You are labelling **roles from behaviour and context**, never identity. Don't write anyone's name in a label unless it is said on camera by a consenting participant, and never try to find out who a stranger is.

## 2. Entities

An **entity** is one person or one object a reviewer would discuss. Label each one **once per clip**, even if it leaves and comes back (that's what the `reentry` difficulty tag is for).

Label a **person** when their head is visible and at least **24 px tall at the source resolution** (1080p) on at least one frame. Smaller heads are not entities; write "N far faces below threshold" in the clip `notes`. Label an **object** (plate, screen, document, address, photo) when **any text, digit or face on it is legible at source resolution on at least one frame** (pause and zoom to check). An object nobody could read is not an exposure; mention it in `notes`.

### 2.1 Categories

| `category` | Use for | Default `should_hide` |
|---|---|---|
| `participant` | The host or creator, and anyone who **knowingly takes part**: introduced, interviewed, spoken to and answering, or clearly performing for the creator with the creator's agreement | `false` |
| `bystander` | Every other adult or teen: passers-by, shop workers, people watching, people in vehicles, people in reflections | `true` |
| `child` | Anyone who looks under about 16, **whatever their role** | `true`, always |
| `plate` | Vehicle number plates (cars, matatus, boda-bodas, trucks) | `true` |
| `screen` | Phones, laptops, TVs, monitors, displays. Judged **by content** | `true` if the content is personal; `false` if harmless (menu, map with no home pinned, slide, public broadcast) |
| `document` | Paper or cards with personal data: ID-style cards, bank statements, letters, name badges, receipts with names | `true` |
| `address` | Things that place a person or child: house numbers, gate numbers, addressed envelopes and parcel labels, a school name shown in a child's clip | `true` |
| `photo` | Printed or framed images of people (family photos, posters, billboards) | `true` for private photos; `false` for public advertising |
| `other` | Anything personal that doesn't fit above. Explain it in `reason` | case by case |

### 2.2 Who counts as a participant

A person is a participant when **at least one** of these is visible or audible in the clip:
1. They are introduced ("this is Amina") or introduce themselves to the camera.
2. They hold a conversation with the host that the host is clearly recording on purpose (they answer questions, they face the host and the lens together).
3. They are the creator: holding the camera, talking to it, or in a mirror while filming.
4. They are listed as a participant on a signed release for this clip (staged clips only: check the release sheet).

These are **not** enough on their own: looking at the camera, waving, smiling, walking close to the lens, standing near the guest, being famous, being in uniform, or a short transactional exchange (selling something, giving directions).

Rule 4 matters for staged clips: an actor playing a passer-by has signed a release, but in the story they are a **bystander**, and Safe Cut has no way to know about the release. Label the **role in the story**, not the paperwork. (The release is what lets us show them unblurred in raw footage; it isn't what the model is judged on.)

### 2.3 Boxes

The box conventions are what the coverage metric measures against ([EVAL.md](../EVAL.md) §2: coverage is the share of the ground-truth box area under a redaction). Keep them consistent:

| Entity | Box covers | Don't include |
|---|---|---|
| Person (any category) | The **whole head**: top of the hair (or hat or helmet) to the chin, ear to ear | Neck, shoulders, the rest of the body |
| Plate | The whole plate including its frame | The bumper |
| Screen | The lit display area | The bezel, the hand holding it |
| Document, address, photo | The whole sheet, card, label, number plaque or frame | The surface it sits on |

- **Tight boxes, no padding.** Padding is Safe Cut's job, not yours. A box edge should sit within about 5% of the object's size from the true edge.
- **Visible part only.** If a head is half behind a pillar, box the visible half. If it is fully hidden, mark the track `outside` for those frames (see CVAT-SETUP.md): those frames are not "visible frames" and are not counted.
- **Clip at the frame edge.** A head half out of frame is boxed to the frame edge.
- **Keyframes every 15 frames (2 fps at 30 fps)**, plus a key wherever the motion changes direction or speed, then scrub the interpolated frames at fast motion and fix any frame where the box drifts off the head.
- A person appears **once**: label their head as the entity. Safe Cut may hide the whole body ([DESIGN.md](../DESIGN.md) §2.7b); that's fine, coverage only asks whether the head box is covered.

### 2.4 Tools that may draw boxes for you

- **Not allowed for ground truth: any SAM-family tracker**, including CVAT's "Segment Anything 2 Tracker". Safe Cut is built on SAM 3.1, and ground truth drawn by a SAM model inherits SAM's misses: the zeroed masks and late starts the leak guard exists to cover ([DESIGN.md](../DESIGN.md) §2.6). Those are exactly the frames the exposure metric has to catch, so this would inflate our numbers. (CVAT's own docs also restrict that tracker to CVAT Online and Enterprise or a separate agent, and it tracks polygons and masks, not boxes.)
- **Allowed as a draft aid:** linear interpolation between your keyframes (CVAT's track mode) and CVAT's built-in OpenCV **TrackerMIL**, which isn't a Meta model ([CVAT-SETUP.md](CVAT-SETUP.md) §6). Keyframes every 15 frames and a frame-by-frame check of fast motion are still required. Record in `clips.md` which clips used TrackerMIL.

## 3. Worked edge cases

Each case gives the category, `should_hide`, and the `reason` you would write. Reasons are short, plain and about behaviour.

| # | Situation | `category` | `should_hide` | `reason` (example) |
|---|---|---|---|---|
| 1 | A passer-by **looks straight at the camera** for two seconds but never speaks and isn't addressed | `bystander` | `true` | "looks at camera, never speaks or is addressed" |
| 2 | A **shop worker in the background** serving other customers | `bystander` | `true` | "shop worker in background, not part of the interview" |
| 3 | The host **buys a drink**; the vendor hands it over and says "thank you" | `bystander` | `true` | "brief sale, not introduced or interviewed" |
| 4 | A bystander's face **reflected in a shop window** (the person is also directly visible elsewhere) | `bystander` (a separate entity) | `true` | "reflection of e3 in window" |
| 5 | The **host's own reflection** in a window | `participant` (separate entity) | `false` | "reflection of host e1" |
| 6 | A **poster or billboard** with a model's face, advertising a product | `photo` | `false` | "public advertising" |
| 7 | A **framed family photo** on a wall in a home tour | `photo` | `true` | "private family photo" |
| 8 | A **TV showing a newsreader** on a broadcast channel | `screen` | `false` | "public broadcast" |
| 9 | A **TV or laptop showing a video call** or home video of a private person | `screen` | `true` | "video call shows a private person". Our staged home tour (SHOTLIST F) uses this case: the TV shows a fabricated video call with a consenting actor, not broadcast TV, which also keeps third-party broadcast content out of public footage |
| 10 | A **partly visible plate**: half behind another car, 3 characters legible | `plate` | `true` | "plate partly occluded, 3 characters legible". Box the visible part only |
| 11 | A **plate too far away** to read on any frame | not an entity | — | Note it: "1 distant plate, illegible" |
| 12 | The **guest leaves frame at 0:08 and walks back in at 0:12** | `participant` (one entity, tag `reentry`) | `false` | "interview guest, leaves and returns". The track is `outside` for the gap |
| 13 | A **bystander ducks behind a van** and reappears (hero clip 1, take B) | `bystander` (one entity, tag `reentry`, `occluded`) | `true` | "passer-by, hidden behind van then reappears" |
| 14 | A **participant's own child, with a signed guardian consent**, standing next to the parent who is being interviewed | `child` | `true` | "child; children are always hidden" |
| 15 | A **child walking past** with an adult | `child` | `true` | "child passing in background" |
| 16 | A person **stops to watch the interview** for ten seconds (category H "watcher") | `bystander` | `true` | "stops to watch, never addressed" |
| 17 | Someone **waves into the lens** or photobombs | `bystander` | `true` | "waves at camera, not invited to take part" |
| 18 | A bystander seen **only from behind** with a visible head | `bystander` | `true` | "passer-by, back to camera". Head box as usual |
| 19 | A **driver** visible through the windscreen of a passing car | `bystander` (the plate is a separate entity) | `true` | "driver of passing car" |
| 20 | A **police officer or guard** on duty | `bystander` | `true` | "officer on duty, not part of the interview" |
| 21 | A **well-known public figure** passes by | `bystander` | `true` | "passes by, not part of the clip" |
| 22 | A bystander with a **helmet or face mask** | `bystander` | `true` | "masked passer-by; identifiable by clothing" |
| 23 | A **phone showing a (fake) chat** with a phone number | `screen` | `true` | "chat with a phone number" |
| 24 | A **laptop showing a café menu** (the context test) | `screen` | `false` | "menu, no personal data" |
| 25 | A **map** on a screen with no home or person marked | `screen` | `false` | "city map, nothing personal" |
| 26 | A **map with a pin labelled "home"** or an address | `screen` | `true` | "map pins a home address" |
| 27 | A **name badge** on a shop worker | `document` (the worker is a separate `bystander`) | `true` | "name badge" |
| 28 | A **house number on a gate** in a home tour | `address` | `true` | "house number" |
| 29 | A **street-name sign** or shop sign | not an entity (public signage) | — | — |
| 30 | A **school name** on a gate or uniform in a clip that shows a child | `address` | `true` | "school name places a child" |
| 31 | The **labellers can't agree** whether someone is a participant (e.g. a friend of the guest who stands beside them and nods but never speaks) | per the adjudication in §5; default `bystander` | `true` | "stands with guest, never speaks or is introduced" |

Case 14 is deliberate. Safe Cut locks children hidden and the creator can't un-hide them ([ARCHITECTURE.md](../ARCHITECTURE.md) §3.6, [DESIGN.md](../DESIGN.md) §2.5), because the system can't verify a guardian's consent. The ground truth follows the same rule, so a hidden child is never counted as over-blur.

Case 12 has an honest consequence: Safe Cut gives a re-acquired person a new hidden ID until the creator merges it. Eval runs score the policy's decisions without creator edits (WP5's `--auto-approve-policy`; WP7 confirms this when it builds the runner), so the returning guest's second segment counts towards **over-blur**. Don't relabel to hide that; it's a real cost of deny-by-default, and the review-load metric shows the one tap it takes to fix.

## 4. Difficulty tags

Add every tag that applies (`difficulty` in the label JSON):

| Tag | When |
|---|---|
| `small` | the head or object is under 48 px tall at 1080p on most of its frames |
| `occluded` | more than a third of it is hidden for at least 1 s |
| `reentry` | it leaves the frame or is fully hidden, then comes back |
| `motion_blur` | it is smeared on at least 5 frames |
| `crowd` | 16 or more labelled **people** share a frame. SAM 3.1 returns at most 16 objects per frame for each request, and Safe Cut makes one request per concept ([DESIGN.md](../DESIGN.md) §2.2), so it's 16 faces or people that hit the cap, not 16 entities of mixed kinds. Tag every person on those frames |

## 5. Two labellers, agreement, and disagreements

- **Labeller A** builds the entity list, draws all the boxes (CVAT) and writes the label JSON.
- **Labeller B** works independently from the clip and A's entity list (entity ID, first frame, where it is in frame, **without** A's category or `should_hide`). B records their own `category` and `should_hide` for each entity and may add entities A missed. B doesn't draw boxes; B spot-checks 10% of A's boxes by scrubbing.
- **Agreement is computed before anything is resolved**, from the labeller-A and labeller-B files only, per split, over **the entities on A's list** (B labels every one of them, so each has two independent labels). WP7 reports three things together ([EVAL.md](../EVAL.md) §1; human agreement on bystander calls is 80–93% in Hasan et al. 2020):
  1. **Raw percent agreement** on `should_hide`.
  2. **Cohen's κ** on `should_hide` (the standard two-rater statistic; e.g. scikit-learn's `cohen_kappa_score`, which cites Artstein & Poesio 2008). Most entities are `should_hide: true`, and with skewed classes κ can come out low even when raw agreement is high (Feinstein & Cicchetti 1990, "High agreement but low kappa"), so κ is never shown without the raw percentage and the 2×2 counts.
  3. **Detection agreement:** the number of entities B added that A missed, reported separately as A's miss count. These are not folded into κ, because A never labelled them independently.
  Never "fix" B's file to raise agreement. What this measures is agreement on the *decision* given a shared entity list, and WP7's report says so.
- **Resolving:** for each disagreement, both labellers reread this guide and the case table.
  1. If a worked case covers it, the case wins.
  2. If not, discuss for at most 5 minutes. If you agree, add the situation as a new worked case here (with the date).
  3. If you still disagree, the label is `should_hide: true` (deny by default), the reason starts with "disputed:", and it's logged. Nobody casts a deciding vote, so no one person's view settles a dispute.
- Every disagreement goes in the adjudication log ([LABEL-FORMAT.md](LABEL-FORMAT.md) §4), including the ones resolved in step 1.
- **Entities B added** that A missed: A adds them, with boxes, to the resolved file, using B's `should_hide` unless a worked case says otherwise. They count towards the detection-agreement number above, never towards κ.

If there is only one labeller (see [SCHEDULE.md](SCHEDULE.md)), say so: report κ as "not measured (single labeller)" and never estimate it.

## 6. Privacy while labelling

- Real-public clips (the `test` split) are labelled **only** on the build box running CVAT locally ([CVAT-SETUP.md](CVAT-SETUP.md)), never on a hosted labelling service, never in this repo, never in the cloud sandbox ([AGENTS.md](../../AGENTS.md) rule 5).
- Don't take screenshots of real-public clips. Labeller B's entity list uses frame numbers and positions ("left third, red jacket"), not crops.
- The `dev` and `hero` splits must be **consented clips only** (staged actors, or the owner's own talking-head footage), because they go to the private bucket the cloud agents read. **Every real-public clip goes to `test`.** The `test` split may also include staged clips (e.g. the re-entry and negative categories), so it covers every category; staged test clips are handled like any test clip and never go to the bucket. If a real passer-by is caught on a staged clip, that clip moves to `test` (or is deleted).
- If anyone asks to be removed, delete the clip and its labels everywhere, and note "withdrawn" in the clip list.
