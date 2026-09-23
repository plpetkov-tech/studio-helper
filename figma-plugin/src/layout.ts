// Pure job.json parsing, grid layout, and naming logic (SPEC.md §6.6,
// §9: "vitest on pure layout/naming modules"). No Figma API calls
// here -- see code.ts for the plugin-main-thread glue that actually
// creates pages/frames. Kept dependency-free so it's fully testable.

export interface JobFormat {
  id: string;
  kind: string;
  size?: { w: number; h: number; unit: string };
  safe_px?: number;
  allow_alpha?: boolean;
}

export interface JobDeliverable {
  format_id: string;
  type: string;
  panel: number | null;
  expected_stem: string;
}

export interface Job {
  id: string;
  name: string;
  slug: string;
  created: string;
  version: number;
  formats: JobFormat[];
  deliverables: JobDeliverable[];
}

export interface FrameSpec {
  stem: string;
  formatId: string;
  widthPx: number;
  heightPx: number;
  safePx: number;
}

const GRID_GAP_PX = 100;
const FRAME_EXPORT_TYPES = new Set(["png", "jpg"]);

/** One frame spec per digital deliverable Figma can actually produce
 * (png/jpg -- never print or mp4), deduplicated by stem so a format
 * with both a png and a jpg deliverable at the same size only gets
 * one frame. The frame's name is the full export stem (SPEC.md §6.6),
 * so Figma's native Export needs zero extra configuration. */
export function digitalFrameSpecs(job: Job): FrameSpec[] {
  const specs: FrameSpec[] = [];
  const seenStems = new Set<string>();

  for (const deliverable of job.deliverables) {
    if (!FRAME_EXPORT_TYPES.has(deliverable.type)) continue;
    if (seenStems.has(deliverable.expected_stem)) continue;

    const format = job.formats.find((f) => f.id === deliverable.format_id);
    if (!format || format.kind === "print" || !format.size) continue;

    seenStems.add(deliverable.expected_stem);
    specs.push({
      stem: deliverable.expected_stem,
      formatId: format.id,
      widthPx: format.size.w,
      heightPx: format.size.h,
      safePx: format.safe_px || 0,
    });
  }

  return specs;
}

/** "{date} {job name}" (SPEC.md §6.6), using the date embedded in the
 * job id rather than re-parsing `created`, since job.json's id is
 * already `{date}_{slug}` (SPEC.md §6.1). */
export function pageName(job: Job): string {
  const date = job.id.split("_")[0];
  return `${date} ${job.name}`;
}

export function gridColumns(count: number): number {
  return Math.max(1, Math.ceil(Math.sqrt(count)));
}

export interface Sized {
  widthPx: number;
  heightPx: number;
}

export interface Positioned<T> {
  item: T;
  x: number;
  y: number;
}

/** Left to right, wrapping into a roughly-square grid, matching
 * width/height with each row's tallest item (SPEC.md §6.6: "Arranges
 * them in a grid"). Generic so the caller gets its original items
 * back, not a re-lookup by dimensions (which could collide). */
export function layoutGrid<T extends Sized>(items: T[]): Positioned<T>[] {
  const columns = gridColumns(items.length);
  const positions: Positioned<T>[] = [];
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  let col = 0;

  for (const item of items) {
    positions.push({ item, x, y });
    rowHeight = Math.max(rowHeight, item.heightPx);
    x += item.widthPx + GRID_GAP_PX;
    col += 1;
    if (col >= columns) {
      col = 0;
      x = 0;
      y += rowHeight + GRID_GAP_PX;
      rowHeight = 0;
    }
  }

  return positions;
}

const VERSION_SUFFIX = /_v(\d+)$/;

/** "_vNN" -> "_vNN+1", padded back to the same width (SPEC.md §6.6
 * "Bump version"). Names with no version suffix are left unchanged. */
export function bumpFrameName(name: string): string {
  const match = VERSION_SUFFIX.exec(name);
  if (!match) return name;
  const digits = match[1];
  const next = String(parseInt(digits, 10) + 1).padStart(digits.length, "0");
  return name.slice(0, match.index) + "_v" + next;
}
