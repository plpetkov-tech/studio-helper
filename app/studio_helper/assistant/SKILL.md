---
name: studio-helper
description: Use Studio Helper, the designer's local app that sets up, names, checks, exports and packages every size of a campaign (print in Illustrator, digital in Photoshop or Figma, video through Concat). Use it to see what's left on a job, add sizes for a new mall, start revisions, export, make the screen videos, and pack files for the manager.
---

# Studio Helper

Studio Helper runs on her PC. It doesn't design anything: it sets up her
Illustrator/Photoshop/Figma files at the right sizes, names every export
correctly, checks each exported file against its spec, makes the video
versions through Concat, and packs the finished files for her manager.

## Words it uses

- **Job**: one campaign or task, e.g. "Black November". Has an id like
  `2026-10-20_black-november`. Get ids from `jobs_list`.
- **Format / size**: one placement with its spec (A4 flyer, Instagram story,
  Paradise Center LED column...). Ids from `formats_list`. Some sizes are
  marked `estimated` until the operator confirms them.
- **Deliverable**: one expected file of a job, with a status: ok, warn,
  fail, missing.
- **Revision** (v01, v02...): a new round of changes. She keeps working in
  the same files; exports get the new version.
- **Add sizes**: a finished campaign extended to a new mall. The new sizes
  join the job (no new version). Then `print_setup` / `digital_setup` with
  the batch number adds them to her files, each starting from her closest
  existing artwork on a "Starting point - adjust me" layer.
- **Video**: every size that may be MP4 (LED screens, stories, posts).
  - A **master** is a video she made in Higgsfield. `video_get` says which
    master shapes to make (9:16, 3:4, 4:3...).
  - The **juice box** is what must stay visible; the fitter zooms in as
    far as it allows.
  - **Fill** is what shows where the video can't cover a screen:
    blur, black or a brand colour. Management may dislike blur: switch with
    `video_set_fill`.
  - **Motion** makes a moving version of her static: push-in, crossfade,
    pieces-reveal, loop.
  - **Brand pieces** (logo, the line under it, promo text) enter one after
    another near the end.
  - The Paradise column wraps around, so it repeats the video 3 times.
- **Package**: a ZIP of the files that passed, for her manager.

## How to help

1. Start with `jobs_list` or `job_get` to see where things stand. Report
   problems in plain words, with the file name.
2. When she names a new placement with a spec sheet, check `formats_list`
   first; if it's not there, `format_add` with the sizes from the sheet and
   its requirements in `notes`.
3. For "Mall X wants the campaign too": `job_add_sizes`, then
   `print_setup`/`digital_setup` with the batch, tell her the new artboards
   start from her closest artwork for her to adjust, then after she's done
   `print_export`/`digital_export`, then `package_make` with the batch.
4. For video: `video_get` to see the plan, set the juice box and fill if
   she asks, `video_render`, then `job_get` to confirm the files pass.
   She can fine-tune any video in Concat afterwards (its project is in the
   job's 03_working/video folder).
5. You can combine this with the Concat tools: read the screen's spec and
   the deliverable file name here, edit in Concat, export to that name.

## Rules

- Never claim a file is fine unless `job_get` shows it ok.
- Exporting saves her open document first: say so before you export.
- Don't overwrite an MP4 she made herself (`video_render` skips it unless
  she asks for `overwrite`).
- Nothing here deletes her files. Removing a size only stops expecting it.
- Dates are YYYY-MM-DD.
