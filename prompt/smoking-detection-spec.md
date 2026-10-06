# Smoking Detection Model — Technical Specification for AntiGravity

**Project type:** Personal project, offline/batch video analysis via a basic UI.
**Author of spec:** Claude (technical design), for implementation by AntiGravity.
**Status:** Ready for implementation. All open design questions below are resolved — do not re-litigate architecture choices without new evidence (see "Decision Log").

---

## 1. Context & Goal

Train a single-class ("smoke") object detector on the Kyunghee University smoking-detection dataset (YOLO format, 18,230 images, CC BY 4.0). The trained model will run **offline inference on user-uploaded video files** through a basic UI — the user throws a video in, the model analyzes it and returns results. This is **not** a real-time surveillance stream: inference latency is not the primary constraint, detection accuracy (especially recall on small objects) is.

## 2. Hardware / Environment

- **Primary:** Local machine — Lenovo Legion 5 15IRX10, Intel Core i7-14700HX, NVIDIA GeForce RTX 5060 Laptop GPU, **8 GB VRAM (GDDR7)**, 24 GB system RAM.
- **Fallback / parallel experiments:** Cloud GPU acceptable. Kaggle Notebooks (~30 GPU-hours/week free tier, P100/T4, 12h session cap) preferred over Colab free tier for quota predictability.
- **Implication for config:** Use `batch=-1` (Ultralytics auto-batch, targets ~60% VRAM utilization) instead of a hardcoded batch size — do not assume a fixed batch value; 8GB VRAM is workable for YOLOv8s/YOLOv8s-P2 at imgsz=640 but auto-batch avoids OOM crashes across local vs. Kaggle GPU swaps.
- Enable `amp=True` (mixed precision) — mandatory to make full use of RTX 5060 Tensor Cores and to reduce VRAM pressure.

## 3. Dataset

- Format: YOLO (`class_id x_center y_center width height`, normalized), single class `smoke` (id 0).
- Splits: train 16,758 / valid 740 / test 732 images, already split by the dataset provider (Roboflow) **before** applying 3x flip/rotation augmentation — augmentation was applied to the train split only, so standard leakage from that pipeline step is not expected.
- **Known data quirk — composite images:** A subset of images are 2×2 grids or 3-4 panel strips (collages of multiple photos), each panel independently annotated. These originate from the original web-scraped source (not from Roboflow's augmentation step) and may appear in any split, including valid/test.

### Bbox size audit (already run — do not re-run unless dataset changes)

```
< 16x16   (area < 256)     :  426  ( 1.67%)
16-32px   (256-1024)       : 2409  ( 9.43%)   → small-object total: 11.10%
32-48px   (1024-2304)      : 3434  (13.45%)
48-64px   (2304-4096)      : 3446  (13.50%)
64-96px   (4096-9216)      : 5160  (20.21%)
96-128px  (9216-16384)     : 3461  (13.56%)
>=128px   (>=16384)        : 7197  (28.19%)
```

**Interpretation:** Distribution is skewed toward large objects (close-up stock photos). Real-world deployment video (subject at natural distance from camera) is expected to skew smaller than this training distribution — treat the 11.10% figure as a **lower bound**, not a representative estimate, of the small-object proportion the model will face in production.

## 4. Decision Log (resolved — implement as-is)

| Decision | Choice | Rationale |
|---|---|---|
| Class scheme | Single class `smoke` (as-is) | User requirement — no re-labeling. |
| Primary architecture | **YOLOv8s-P2** (`yolov8s-p2.yaml` + `yolov8s-p2.pt` pretrained) | Official Ultralytics pretrained P2 checkpoint exists for YOLOv8 (transfer learning available); YOLO11-P2 has no official pretrained weights as of this spec, only a community YAML — would require training the P2 head from random init, slower convergence. Small-object % (11.10%, likely underestimating deployment reality) + no FPS constraint + sufficient VRAM (8GB) justifies the extra compute cost of the P2 head. |
| Baseline comparison | **YOLOv8s** (standard P3-P5) trained in parallel | Free GPU quota available (local + Kaggle) — run as an ablation to quantify P2's actual gain on small-object recall. Not optional busywork: without this comparison you cannot prove P2 was worth the extra training/inference cost. |
| Batch size | `batch=-1` (auto) | Hardware will vary (local 8GB vs. Kaggle T4/P100) — do not hardcode. |
| Precision | `amp=True` | Required for RTX 5060 Tensor Core utilization. |
| Resume strategy | Ultralytics native `resume=True` from `last.pt` | Built-in, reliable since Ultralytics v8.4.30 (checkpoint config loaded earlier/more consistently). Do not build a custom checkpoint system. |

## 5. Pipeline — Implement as 5 sequential phases

### Phase 0 — Data Audit (mostly done; one remaining task)
Bbox histogram is complete (see Section 3). **Remaining task:** write a script to flag composite/collage images — heuristic: images with ≥3 bounding boxes in a single label file are very likely multi-panel composites (per dataset README, composites typically show 3-4 bbox lines). Use this to carve out a **"clean" evaluation subset** (single-subject images only) from `valid` and `test`. This subset is the true proxy for real-world video-frame performance; the full test set (with composites) is the "official" number for reporting but should not be the number used to judge production-readiness.

Deliverable: `scripts/audit_composites.py`, outputs `clean_test_ids.txt` / `clean_valid_ids.txt`.

### Phase 1 — Dry-Run Sanity Check (MANDATORY, blocking gate before Phase 2)
Before any full training run, train on a tiny hand-picked subset (8-16 images) for a short run and confirm the pipeline is correct.

```python
from ultralytics import YOLO

model = YOLO("yolov8s-p2.yaml").load("yolov8s-p2.pt")
model.train(
    data="sanity.yaml",   # points to the 8-16 image subset only
    epochs=50,
    imgsz=640,
    batch=4,
    name="sanity_check",
)
```

**Pass criteria (all must hold):**
- Loss curve decreases smoothly toward near-zero on this tiny subset (expected to overfit).
- No NaN/Inf loss at any epoch.
- No shape-mismatch or label-parsing errors.
- Manual visual check: run `model.predict()` on the same 8-16 images and confirm predicted boxes land on the actual cigarette/hand region.

**If any criterion fails: stop. Do not proceed to Phase 2.** Debug the data pipeline first — a bug caught here costs minutes; the same bug caught after a full multi-hour training run costs the entire run.

### Phase 2 — Baseline + P2 Training (run both)

```python
from ultralytics import YOLO

# Primary: P2 variant
model_p2 = YOLO("yolov8s-p2.yaml").load("yolov8s-p2.pt")
model_p2.train(
    data="data.yaml",
    epochs=100,
    imgsz=640,
    batch=-1,
    amp=True,
    save_period=5,      # checkpoint every 5 epochs, not just last+best
    patience=20,        # early stopping
    name="smoke_p2",
    exist_ok=True,       # keep path stable for resume
)

# Comparison baseline: standard P3-P5
model_base = YOLO("yolov8s.pt")
model_base.train(
    data="data.yaml",
    epochs=100,
    imgsz=640,
    batch=-1,
    amp=True,
    save_period=5,
    patience=20,
    name="smoke_baseline",
    exist_ok=True,
)
```

**Resume pattern (use whenever a run is interrupted, e.g. switching to Kaggle mid-training):**
```python
model = YOLO("runs/detect/smoke_p2/weights/last.pt")
model.train(resume=True)
```
Do not rename the `runs/` output directories between sessions — resume depends on the fixed path. If custom hyperparameters were passed originally, they must be re-passed on every `resume=True` call (Ultralytics does not persist custom augmentation args across resumes automatically).

### Phase 3 — Evaluation (dual metric, mandatory)
Evaluate both models on:
1. The **official** test set (732 images, as-is) — for reporting.
2. The **clean subset** from Phase 0 (single-subject images only) — the number that actually predicts real-world UI performance.

Report per-model: overall mAP50-95, **plus recall broken out by the bbox-size buckets from Section 3** (at minimum: <32×32 vs. ≥32×32). This is the number that determines whether P2 was worth it — do not just compare aggregate mAP, which can mask a small-object recall win.

### Phase 4 — Video Inference Integration (for the UI)
Since this is offline/batch video analysis (not real-time), use streaming inference to avoid loading the full video into memory:

```python
results = model.predict(source="uploaded_video.mp4", stream=True)
for r in results:
    # process per-frame detections here (append to results list / write to output)
    pass
```
Do **not** use `stream=False` on full videos — it buffers all frames' results in memory and is a memory-leak risk on longer videos.

## 6. Deliverables Checklist for AntiGravity

- [ ] `scripts/audit_composites.py` — composite detection + clean subset generation
- [ ] `sanity.yaml` + sanity-check run artifacts (loss curve, sample predictions)
- [ ] `smoke_p2` training run (resumable, checkpointed every 5 epochs)
- [ ] `smoke_baseline` training run (same config, standard architecture)
- [ ] Evaluation report: dual test-set metrics + per-bbox-size recall breakdown for both models
- [ ] Video inference script using `stream=True`
- [ ] Final model selection writeup: which of (P2, baseline) is shipped, with justification tied to the Phase 3 numbers — not a guess
