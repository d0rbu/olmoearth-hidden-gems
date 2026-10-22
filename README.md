# Earth, off the shortlist

An open experiment in using **real Ai2 OlmoEarth v1.3 satellite embeddings** to find candidate hidden landscapes. A 128-dimensional difference-of-means direction learns a subjective scenic-versus-ordinary contrast, then ranks unlabelled satellite footprints.

**Live website:** https://slots-adaptive-tracked-contributing.trycloudflare.com

This is a Cloudflare Quick Tunnel from the project host. It works while the host and tunnel are running; the hostname is temporary and can change after a restart. The repository contains the complete static website and published experiment outputs.

## Results

- **90 author-curated examples:** 30 scenic landmarks/natural beauty sites, 30 ordinary developed places, and 30 ordinary open-land/rural landscapes.
- Six geographic groups: Utah, Arizona, California, Nevada, Pacific Northwest, and Rockies; each has five scenic, five developed, and five open-land examples.
- **0.910 out-of-fold AUROC**, **87.5% balanced accuracy**, holding out one geographic group at a time.
- Separate out-of-fold contrasts: **0.983 scenic vs developed**, **0.837 scenic vs ordinary open land**. These use predictions from the same mixed-control model; no separate model or favorable threshold was fit for the contrasts.
- **9,216 footprints** scored over **235.93 km²** in four deliberately chosen western-US search regions: San Rafael, Escalante, Vermilion, and Basin and Range.
- **24 spatially separated candidate landscapes**, at least 5 km from every seed and 1.5 km from one another. Some search regions may have no global top-24 picks; the site still shows their scanned blocks.

These metrics measure the curated labels, **not beauty or low visitor numbers at the new candidates**. Labels, search extents, all 9,216 cell scores, 90 seed vectors, the learned direction, and source-block hashes are included. No GPU, paid inference, Studio account, or API key was used.

## Method

The public archive linked from the [OlmoEarth embeddings explorer](https://olmoearth.allenai.org/embeddings) stores quantized 128-dimensional embeddings at 10 m spacing. This run uses **2025**, the latest available annual slice when queried, from `utm10` through `utm13` as needed.

1. Read 126 aligned 256×256-pixel blocks using Zarr/obstore byte-range reads, including 90 seed blocks and 36 discovery blocks. Sharded arrays store 64 bands per inner chunk; both halves are read.
2. Dequantize `v = sign(q / 127.5) * abs(q / 127.5)^2`. Exclude nodata (`-128`). Apply the explorer's local 2×2 parity-offset correction within each aligned block.
3. Average a snapped 16×16-pixel footprint (160×160 m) and L2-normalize. Use the same footprint and preprocessing for seed and discovery vectors. Require at least 90% valid pixels.
4. Compute `w = unit(mean(scenic unit vectors) - mean(ordinary unit vectors))`. The ordinary mean pools the 30 developed and 30 open-land controls equally by sample count.
5. Score `s(x) = unit(x) · w + b`, where `b` puts the midpoint of the two training class means at zero. Scores and scan percentiles are **not probabilities**. A percentile describes rank within these 9,216 scanned cells only.
6. For evaluation, refit both `w` and `b` using five groups and predict the sixth. Publish every held-out seed score. A fixed-seed 2,000-resample seed bootstrap gives an AUROC range of approximately 0.846–0.965; this is not a population confidence interval or a geographic-group bootstrap.
7. Rank all discovery cells, exclude those within 5 km of any seed, and greedily suppress picks within 1.5 km of a higher-scoring pick until 24 remain. Nearest scenic analogues are cosine neighbors in the full training set and are explanatory, not independent validation.

Place names and coordinates select data windows but never enter the 128-D scorer. The search regions were chosen manually; this is not a global search. Geographic holdouts are coarse convenience groups, not a guarantee of independent biomes or perfect geographic separation.

## Run the published website

Requires Python 3.11+; the static UI has no build step. Map tiles and satellite previews load directly from Esri, and fonts load from Google; those services require internet access. Leaflet is vendored.

```bash
uv sync --locked
uv run python scripts/serve.py --port 8768
# Open http://127.0.0.1:8768
```

In another terminal, with `cloudflared` installed:

```bash
./scripts/tunnel.sh
```

Only `web/` is served. Raw caches, source files, local runtime logs, and the Python environment are outside the HTTP root.

## Reproduce the analysis

```bash
uv sync --locked
uv run python scripts/build_results.py
# Copy published downloads after rebuilding:
cp data/interestingness-vector.json data/seeds.json data/OLMOEARTH-LICENSE.txt web/data/
uv run python scripts/validate_results.py
```

The initial run requires internet access to the public Source Cooperative archive and caches about **1 GiB** of uncompressed embedding blocks under `.cache/blocks/`. Subsequent runs reuse these blocks. Expect a few minutes on a CPU workstation; transfer rate and hardware affect runtime. The archive is mutable; `data/source-manifest.json` records SHA-256 hashes of the exact retained `.npy` arrays. An upstream change can change the results, and the supplied manifest should be compared after a fresh run. Included vectors support offline reconstruction of the trained direction and geographic-holdout metrics; raw discovery vectors can be reconstructed from the public archive and the recorded block extents.

To inspect satellite-preview snapshots locally (optional, cached imagery is not committed):

```bash
uv run python scripts/fetch_previews.py
```

To check browser behavior, start the server and install a compatible Playwright Chromium if one is not present:

```bash
uv sync --locked --group dev
uv run playwright install chromium
uv run python scripts/browser_check.py
# The same checks can run against the tunnel URL:
uv run python scripts/browser_check.py https://YOUR-HOST.trycloudflare.com
```

The independent numerical check reconstructs the weight and all six held-out folds, verifies the published metrics and every candidate's score, exclusion distance, spatial separation, and source hashes when raw cache files are present. Browser checks exercise map markers, candidate selection, sorting, all region filters (including empty results), training-example overlays, downloads, decoded satellite imagery, and a 390px mobile viewport.

## Artifacts

| File | Purpose |
| --- | --- |
| `data/seeds.json` | All 90 coordinates, task labels, groups, label rationale, and source links |
| `data/seed-embeddings.npz` | Actual preprocessed 128-D seed embeddings, labels, and stable IDs |
| `data/interestingness-vector.json` | Learned weight, intercept, source, year, pooling, and formula |
| `data/scanned-cells.json` | Scores and coordinates for all 9,216 discovery footprints |
| `data/source-manifest.json` | Exact source-block identities and SHA-256 hashes |
| `data/preview-provenance.json` | Exact Esri preview requests, geographic extents, and attribution |
| `web/results.json` | Complete browser-ready results, holdout metrics, seed predictions, and candidate analogues |

## Interpretation and limits

“Interestingness” is a deliberately narrow, subjective research label. The ordinary open-land controls make the problem harder than simply detecting natural versus built surfaces, but the model may still prefer particular land-cover types, rock colors, water, or regional signatures. The relatively weak Nevada fold (AUROC 0.72) illustrates uneven transfer. No human candidate-ranking study was conducted, and search-region choice is another source of bias.

“Hidden” means absent from our examples and at least 5 km away from them. **It does not mean undiscovered or little visited.** Candidate names are region/sequence labels, not claims about named attractions. Similarity to Grand Canyon or another training site does not establish the same geology or visitor experience. Satellite previews can be from a different date than the 2025 embedding data. A 160 m footprint does not locate a precise viewpoint.

Public access, land ownership, trail availability, safety, and ecological sensitivity have not been assessed. Use the imagery and map links to investigate these candidate landscapes before treating any as a destination.

## Credits and licensing

[Ai2 OlmoEarth](https://olmoearth.allenai.org/embeddings) is the source of the model and embedding artifacts. Model: [OlmoEarth-v1_3-Base](https://huggingface.co/allenai/OlmoEarth-v1_3-Base). Dataset: [Source Cooperative](https://source.coop/olmoearth/olmoearth-v1-3-embeddings). The read path and parity correction follow the public explorer's exported analysis approach.

Original software is MIT-licensed. **OlmoEarth artifacts and derivatives remain subject to the [OlmoEarth Artifact License](data/OLMOEARTH-LICENSE.txt), including Section 2's restrictions on military/defense and extractive uses. These restrictions must accompany downstream distribution of derivatives.** See [LICENSE](LICENSE) for the scope of the software license.

Leaflet is BSD 2-Clause-licensed; its license is retained in `web/assets/LEAFLET-LICENSE.txt`. Esri World Imagery and contributors provide map tiles and satellite previews, loaded from the original provider rather than redistributed in Git. Those images remain under their providers' terms. Landscape reference links point to Wikipedia and OpenStreetMap; coordinates and task labels are manually curated and not extracted from a travel-ranking dataset. This project is not affiliated with or endorsed by Ai2, Esri, Wikipedia, or OpenStreetMap.
