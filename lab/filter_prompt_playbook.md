# FILTER & PROMPT PLAYBOOK — sketch-to-model laboratory
MARPA · 2026-07-10 · companion to marpa_lab.py
Organized by GOAL, because the pipeline routes by goal: extract structure, isolate
classes, recover depth, clean for tracing, vectorize, or restyle for presentation.

═══════════════════════════════════════════════════════════════════
A · ISOLATE STRUCTURE (linework from a colored sketch)
═══════════════════════════════════════════════════════════════════
The proven winner on Brian's sketch is the ControlNet **lineart** preprocessor —
trained to keep drawn structure and discard shading, which is exactly why Canny
failed (it fires on every pencil-hatch gradient).

fal endpoints (lineart/teed/hed verified live on our key):
  fal-ai/image-preprocessors/lineart    clean outlines · our 4.6% ink result
  fal-ai/image-preprocessors/teed       soft edges, mid-weight (TEED two-stage)
  fal-ai/image-preprocessors/hed        soft thick strokes; best "quality" softedge
  fal-ai/image-preprocessors/scribble   chunky abstraction; compositional only
  fal-ai/image-preprocessors/pidi       (verify slug) PiDiNet — recommended default
                                        softedge in ControlNet docs
  fal-ai/image-preprocessors/mlsd       (verify slug) M-LSD straight-line detector —
                                        purpose-built for architecture: property
                                        lines, house walls, decks. Run it and UNION
                                        with lineart: MLSD owns the straight, lineart
                                        owns the organic.
Variants worth knowing from the ControlNet family: lineart_anime_denoise
(aggressive simplification — abstracts detail away, useful when a sketch is TOO
busy), scribble_xdog (XDoG stylized lines, threshold-tunable).

Local OpenCV complements:
  adaptive threshold (GAUSSIAN_C, block 31, C 9)   ink mask when lines are dark
  morphological thinning / skeletonize             centerlines for path networks
  component-size despeckle (area >= 10-24)          our standard cleanup pass
  Hough circles                                    tree canopy candidates — tune
                                                   param2 44, minDist 48 (our values)

═══════════════════════════════════════════════════════════════════
B · ISOLATE CLASSES & ELEMENTS (masks per material / per object)
═══════════════════════════════════════════════════════════════════
Three tiers, cheap to smart:

1. HSV color gating (local, deterministic) — our L-101 masks. Green/teal/magenta/
   tan windows + open/close morphology. Splits ZONES not objects; fuse with A.
2. SAM2 auto-segment — fal-ai/sam2/auto-segment. Returns combined_mask +
   individual_masks; knobs: points_per_side 32, pred_iou_thresh 0.88,
   min_mask_region_area (raise to ~400 on sketches to skip pencil noise).
   Everything-mode: great first pass to SEE what the model thinks the regions are.
3. EVF-SAM (text-prompted) — fal-ai/evf-sam. THE unlock for this pipeline:
   natural-language mask requests against the plan. Prompts that map to our classes:
     "all tree canopies"          -> AI-PLNT-TREE candidates
     "the house building"         -> AI-BLDG-MASS
     "the swimming pool and pond" -> AI-WATR
     "the lawn"                   -> AI-TURF
     "the driveway and paths"     -> AI-HARD-PAVE
   Supports negative prompts ("not the lawn"). ~$0.005/call — cheap enough to run
   the whole ontology per sheet. Masks -> cv2.findContours -> manifest polygons.
4. GenAI pseudo-segmentation (edit-model trick): prompt the restyle model to BE a
   segmenter — see prompt P7 below. Output is a flat class-color map you then
   HSV-gate trivially. Surprisingly robust because the model understands "tree vs
   lawn" semantically where hue gating cannot.

═══════════════════════════════════════════════════════════════════
C · DEPTH & 3D CUES
═══════════════════════════════════════════════════════════════════
  fal-ai/image-preprocessors/depth-anything/v2 — verified family; SOTA monocular
  depth. On a TOP-DOWN PLAN depth is meaningless; run it on the AXON RENDERS to
  get relief maps -> displacement terrain hints, or on site PHOTOS when they land.
  Normal maps (BAE / DSINE in the ControlNet family) same story: photo/axon inputs.
  Depth + plan together is the cheap road to a 2.5D relief model before VW exists.

═══════════════════════════════════════════════════════════════════
D · CLEAN / ENHANCE BEFORE TRACING
═══════════════════════════════════════════════════════════════════
  fal-ai/esrgan                 fidelity 4x — THE truth-preserving upscale (our
                                slider base). No restyle.
  fal-ai/clarity-upscaler       creative upscale, prompt-guided; resemblance 0.85 /
                                creativity 0.35 = our enhanced master. Shifts
                                palette — never use for the truth side.
  OpenCV: bilateral x2-3 (paint-flatten), median 7 (hatch-kill), detailEnhance /
  edgePreservingFilter / pencilSketch / stylization (cv2 NPR module — one-liners,
  all four worth exposing as lab filters), unsharp for ink pop.
  Research-grade: sketch-simplification CNNs (Simo-Serra) turn rough pencil into
  clean raster linework before vectorizing — heavier lift, note for the trained
  pipeline phase.

═══════════════════════════════════════════════════════════════════
E · VECTORIZE (raster -> SVG/DXF)
═══════════════════════════════════════════════════════════════════
  vtracer  — built FOR hand-drawn architectural plan scans (its origin story),
             O(n), handles COLOR input directly, gigapixel-safe.
             Recipe for our sheets: --preset bw --filter_speckle 5 --mode spline
             on the lineart output; or color mode straight on the class-color map
             from P7 -> per-class SVG paths in one shot.
  potrace  — binary-only, global-optimal curves; prettier on low-res single shapes,
             chokes on huge sheets. Use for individual masks (one EVF-SAM mask ->
             potrace -> one clean polygon).
  centerline/medial-axis — for PATH NETWORKS (our ribbons need centerlines, not
             outlines): vectorized outline -> Voronoi medial axis -> prune. The
             skeletonize+approxPolyDP route in OpenCV is the pragmatic version.
  Routing rule: regions -> vtracer color / potrace-per-mask; strokes & paths ->
             centerline; never trace hatching (kill it in A/D first).

═══════════════════════════════════════════════════════════════════
F · PROMPT LIBRARY (edit models: Nano Banana, Kontext, Seedream, Qwen)
═══════════════════════════════════════════════════════════════════
The pattern that testing (ours + the Kontext guides) converges on — three layers:
  [ACTION]  specific verb + named style ("change/replace" beats "transform";
            "watercolor and ink site plan" beats "make it artistic")
  [CONTEXT] what the image is + orientation facts (our compass anchors)
  [PRESERVE] explicit list of what must not move — the golden rule: anything the
            model altered last run gets ADDED to the preserve clause next run.
Plus our two hard-won rules: "absolutely no text, labels, or numbers" on every
plan prompt (kills gibberish annotation), and bake the content aspect (0.414)
into the request rather than fixing it in post.

P1 LINE PLAN (proven)      monochrome construction-document redraw; CAD line
                           conventions; double-line walls; dashed bed outlines.
P2 WATERCOLOR HERO (proven) firm-caliber presentation; named firms anchor quality;
                           shadow direction stated; medium named exactly.
P3 SPECIES-TRUE (proven)   palette physics from the schedules: Bakeri spruce
                           blue-green, redbud rose-pink not fuchsia, Hakone
                           chartreuse blades, serviceberry copper, catmint drifts.
P4 RECONCILIATION (proven) multi-image with authority hierarchy: layout > line >
                           finish; explicit do-not list.
P5 COMPASS AXON (proven)   north=top contract + per-camera foreground/background
                           assignments; "do not mirror, move, add, or remove."
P6 FIGURE-GROUND           "Redraw as a figure-ground diagram: buildings solid
                           black, hardscape mid-gray, all planting and lawn white,
                           property line thin black. Flat, no texture, no shadows,
                           no text. Preserve exact layout."
P7 CLASS-COLOR MAP         "Repaint as a flat segmentation map, one solid color
                           per material, hard edges, no gradients or texture:
                           trees pure green #00A000, lawn light green #90EE90,
                           water blue #0060FF, hardscape orange #FF8000, buildings
                           gray #808080, beds purple #8000FF, background white.
                           Preserve every element's exact position and shape. No
                           text." -> HSV-gate the result into manifest masks.
P8 ELEMENT ISOLATION       "Remove everything except the tree canopies; pure white
                           background; keep every canopy in its exact position,
                           size, and color. No text." (swap subject per class —
                           genAI as a mask factory when EVF-SAM struggles.)
P9 BLUEPRINT               "Redraw as a classic blueprint: white linework on
                           Prussian-blue ground, fine consistent line weight,
                           subtle paper grain. Preserve exact layout. No text."
P10 POCHÉ / CD HATCH       "Construction-document graphic language: 45-degree
                           hatch on hardscape, sand stipple on gravel, wall poché
                           solid, canopies as thin double-ring outlines with
                           center dot. Black on white. Preserve layout. No text."
P11 SEASONAL SET           "Same plan in [autumn: serviceberry copper-red, Hakone
                           bronze / winter: structure only, evergreens dark, 
                           deciduous as bare outline canopies]. Preserve layout,
                           linework, and composition exactly."
P12 NIGHT / LIGHTING       "Dusk lighting plan mood: deep blue-gray wash, warm
                           glow pools at path lights and house openings, canopy
                           silhouettes. Preserve layout exactly. No text."

═══════════════════════════════════════════════════════════════════
ROUTING TABLE — which tool for which pipeline stage
═══════════════════════════════════════════════════════════════════
  extraction substrate      A: lineart (+ MLSD union when verified)
  manifest region masks     B: EVF-SAM per class -> potrace/contours; P7 fallback
  tree census               A Hough + B EVF-SAM "all tree canopies" cross-check
  truth-side display        D: esrgan only
  presentation family       F: P1/P2/P3 off the reconciled candidate
  client variants           F: P9-P12 (cheap wow, zero geometry risk)
  terrain preview           C: depth-anything on axons
  DXF/SVG emit              E: vtracer(color map) + centerline(paths)
