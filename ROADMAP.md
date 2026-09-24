# Roadmap

The project is ordered around a defensible prospective comparison, not a broad
health-app feature list.

## Now: synthetic foundation

Implemented:

- canonical SQLite observations with provenance, units, missingness, timezone,
  DST, transactional replay, and conflict detection;
- deterministic Efficiency, Recovery, and predicted Energy heuristics;
- event-relative configuration and validated label, context, exposure, and Coach
  insight records;
- format-neutral import-adapter interfaces;
- a deterministic 60-day CSV and synthetic Coach fixtures;
- historical-median, rolling-average, and Google-only comparison arms;
- personal-only and hybrid training interfaces;
- rolling-origin splits, leakage rejection, and evaluation metrics; and
- a static responsive phone-form prototype.

These components use synthetic data. No current result establishes personal or
medical usefulness.

## Next: one real capture vertical slice

1. Inspect an actual private Google account export.
2. Document its fields, timing, units, provenance, and missingness.
3. Implement one narrow adapter with a fictional public fixture.
4. Connect event-relative labels and exposure records to private persistence.
5. Test one phone-friendly submission path without making the public repository a
   data destination.
6. Capture Premium output manually when no verified machine-readable path exists.

Account exports, structured entry, screenshots, emulator-assisted capture, and a
future verified API remain replaceable acquisition paths.

## Data gates

- **Days 1-20:** debug timing, adherence, and missingness; descriptions only.
- **After 21 complete labels:** allow explicitly exploratory associations.
- **After 60 complete labels:** freeze the first feature and training protocol.
- **After 14 later predictions:** permit a preliminary held-out comparison.
- **90-180 days:** preferred range for more stable schedule and seasonal coverage.

Partial days remain available for targets whose required fields are complete.

## Then: personal-model comparison

- Fit an elastic-net model separately for each target.
- Compare historical, Google-only, personal-only, and hybrid arms on common days.
- Report MAE first, with within-one-point accuracy, rank correlation, calibration,
  coverage, uncertainty, and exposure sensitivity.
- Treat a 10% MAE improvement over the rolling median as a preliminary working
  threshold, not proof of general superiority.
- Suppress or qualify results when coverage, drift, leakage, or uncertainty makes
  comparison unreliable.

## Later

After the capture and evaluation loop works:

- present forecasts and evidence in a durable phone interface;
- add optional coaching downstream of stored predictions;
- document private backup, export, and deletion behavior; and
- decide whether scheduling, private hosting, or a packaged application adds
  enough value to justify its operational cost.

Public deployment, clinical claims, and population-level conclusions are out of
scope.
