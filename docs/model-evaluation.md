# Pothole model — real-image evaluation

41 images from Wikimedia Commons (`fetch.py`), run through `weights/best.pt`
(`run_eval.py`). Scored by eye against the annotated output — Commons images
have no ground-truth boxes, so these are **image-level hit/miss rates, not mAP**.

Ground truth by inspection: 33 images contain a visible pothole, 8 do not.

| conf | recall (images w/ pothole detected) | false positives (on the 8 clean images) |
|------|-------------------------------------|------------------------------------------|
| 0.25 | 17/33 = 52%                         | 2/8                                      |
| 0.10 | 24/33 = 73%                         | 3/8                                      |

## Works well
- Indian/Bengaluru road surfaces, dry, daylight, medium range — the training domain.
  Best scores of the run: 0.61 and 0.42 on the Munnekollala shots, 0.50/0.36 Gaborone.
- Clean negatives: bird photo, Le Corbusier poster, Mumbai Sea Link, Chennai flood,
  highway repair crew — all correctly silent. It also ignored a manhole cover.

## Fails
- **Water-filled potholes** — the single biggest gap. Missed `Potholes_on_road`,
  `Driving_through_potholes`, `Potholed_road_outside_Kolkata_Airport` (in-domain India),
  `Philip_Lane` entirely, even at conf 0.10.
- **Low light / dusk** — `A_photo_of_a_pothole_2021-07-11`, a clear pothole, scored nothing.
- **Large or extreme close-up holes** — `A_pothole_in_Dilova_Street_in_Kyiv` (huge, obvious)
  and `Broken_Roads_in_India_s_Capital_New_Delhi` both missed. Training crops were
  probably all mid-range; very large objects are out of distribution.
- **Unusual color casts** — `Roads_in_Bihar` (heavy blue/green cast) missed at 0.25.
- **False positives on bare dirt/gravel texture** — `Sturdy_Mahindra_Jeeps` (0.38) and
  `Robert_Magazine_Street` (0.34) fired on empty road/rut texture with no pothole.
- Boxes are often loose — correct object, oversized extent (e.g. `Nasty_pothole_Virginia_Ave`).

## Takeaway
Reported val metrics (mAP50 0.858) hold only for the held-out split of the same
Roboflow dataset. On unseen real-world photos the usable recall is roughly half that
at the default threshold. **conf 0.15–0.20 is a better operating point than 0.25** —
most correct detections land in 0.34–0.66 but genuine ones also appear at 0.19–0.22.

Biggest training-data win available: water-filled potholes and low-light shots.

---

# PotholeNet-YOLO11m vs. your best.pt

`weights/potholenet_yolo11m.pt`, from `huggingface.co/Vansh180/PotholeNet-V1`
(the URL given, `.../PotholeNet-YOLO11m-v1`, returns 401 — same author, same
model card, different repo name). YOLO11m, 20.1M params, 3 classes
(pothole / road_damage / garbage), imgsz 768. Run via `eval_new.py`,
pothole class only, on the identical 41 images.

| conf | best.pt (11n, 640) | PotholeNet (11m, 768) |
|------|--------------------|------------------------|
| 0.25 | 17/33 = **52%** recall, 2/8 FP | 15/33 = **45%** recall, **0/8** FP |
| 0.10 | 24/33 = **73%** recall, 3/8 FP | 20/33 = **61%** recall, 1/8 FP |
| speed (CPU, 720p in) | **54 ms** | 553 ms (10x slower) |

**The card's claimed mAP50 of 0.86 is not supported by the checkpoint.** The
stored `train_metrics` in the file read mAP50 **0.5909**, mAP50-95 0.3354,
precision 0.6365, recall 0.5517 (3-class mean). Your own model's stored 0.8596
is the honest higher number.

## Where PotholeNet is better
- **Much tighter boxes.** Where both fire, its extents are near-exact; best.pt
  routinely oversizes.
- **Hard cases best.pt misses entirely:** the dusk pothole (0.77 vs nothing),
  the huge Kyiv hole (0.34 vs nothing), Kolkata Airport (3 boxes vs nothing),
  and two water-filled potholes — the exact weakness noted for best.pt above.
- **Zero pothole false positives** at conf 0.25, including the dirt-track and
  empty-street shots that fooled best.pt.

## Where it is worse
- **Lower overall recall** at both thresholds.
- **Regressions on in-domain Indian road shots:** missed Munnekollala Bengaluru
  (best.pt: 0.61) and Huntington Creek (best.pt: 0.47).
- **The `garbage` class is broken.** It labels *people* as garbage — 22 boxes on
  a photo of soldiers (0.84), a cyclist in the Chennai flood (0.57), and a
  *bird* (0.76). Unusable as shipped; filter to class 0 only.
- 10x slower on CPU.

## Takeaway
The two models fail on different images. Union of both at conf 0.25 detects
**23/33 = 70%** — better than either alone (52% / 45%). If accuracy matters more
than latency, ensemble them or use PotholeNet's strengths (low light, large
holes, standing water) to pick the next round of training data for best.pt.
Do not ship PotholeNet's garbage class.

---

# Update: ensemble detection (shipped)

The single-model numbers above are why the product now runs **both** models on
every upload and merges the boxes with NMS. Re-measured on the same 41 images:

| strategy | recall @0.25 | false pos | ms/img |
|---|---|---|---|
| best.pt @640 | 57.6% | 3/8 | 260 |
| best.pt @960 | 60.6% | 1/8 | 270 |
| potholenet @768 | 45.5% | 0/8 | 549 |
| best.pt + TTA @640 | 51.5% | 3/8 | 315 |
| both models merged | 75.8% | 3/8 | 1096 |
| **accurate profile: best@640+TTA, best@960, potholenet@768+TTA** | **93.9%** | 4/8 | 1961 |

Consensus voting was measured as a hard filter and rejected — requiring two
passes to agree drops recall to 51.5% (1/8 FP) and three passes to 18.2%.
It is used instead as the public/review tier signal, which keeps the recall
and still holds the public map to 2/8 false positives.
