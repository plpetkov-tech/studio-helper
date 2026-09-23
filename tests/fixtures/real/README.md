# Real samples

This folder is gitignored (SPEC.md §8: "the repo must not contain
client artwork"). Drop real exported files here to validate them for
real -- the first one should be a previously rejected print PDF
(SPEC.md §13 open items).

For each file, add an entry to `expected.yaml` in this folder:

```yaml
my_rejected_flyer.pdf:
  format:
    id: flyer-a5
    kind: print
    size: {w: 148, h: 210, unit: mm}
    bleed_mm: 3
    exports: [pdf]
    min_image_ppi: {warn: 300, fail: 200}
  deliverable:
    format_id: flyer-a5
    type: pdf
    panel: null
    expected_stem: my_rejected_flyer
  status: fail   # the overall status you expect: ok | warn | fail
```

`tests/validators/test_real_samples.py` picks this up automatically
and validates every listed file, asserting the overall status
matches. It's skipped (not failed) when this folder has no
`expected.yaml`, which is the normal state for everyone except
whoever has real samples locally.
