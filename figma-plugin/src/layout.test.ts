import { describe, expect, it } from "vitest";
import { bumpFrameName, digitalFrameSpecs, gridColumns, layoutGrid, pageName } from "./layout";
import type { Job } from "./layout";

const JOB: Job = {
  id: "2026-09-25_autumn-sale",
  name: "Autumn Sale",
  slug: "autumn-sale",
  created: "2026-09-25T15:02:11+03:00",
  version: 1,
  formats: [
    { id: "ig-post", kind: "social", size: { w: 1080, h: 1350, unit: "px" }, safe_px: 0 },
    { id: "flyer-a5", kind: "print", size: { w: 148, h: 210, unit: "mm" } },
    {
      id: "led-mall-entrance",
      kind: "screen",
      size: { w: 384, h: 1920, unit: "px" },
      safe_px: 20,
    },
  ],
  deliverables: [
    {
      format_id: "ig-post",
      type: "png",
      panel: null,
      expected_stem: "2026-09-25_autumn-sale_ig-post_1080x1350px_v01",
    },
    {
      format_id: "flyer-a5",
      type: "pdf",
      panel: null,
      expected_stem: "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01",
    },
    {
      format_id: "led-mall-entrance",
      type: "png",
      panel: null,
      expected_stem: "2026-09-25_autumn-sale_led-mall-entrance_384x1920px_v01",
    },
    {
      format_id: "led-mall-entrance",
      type: "mp4",
      panel: null,
      expected_stem: "2026-09-25_autumn-sale_led-mall-entrance_384x1920px_v01",
    },
  ],
};

describe("digitalFrameSpecs", () => {
  it("includes png/jpg digital deliverables only", () => {
    const specs = digitalFrameSpecs(JOB);
    expect(specs.map((s) => s.formatId)).toEqual(["ig-post", "led-mall-entrance"]);
  });

  it("excludes print formats even if a deliverable type would otherwise match", () => {
    const specs = digitalFrameSpecs(JOB);
    expect(specs.some((s) => s.formatId === "flyer-a5")).toBe(false);
  });

  it("excludes mp4 deliverables and doesn't double-count a shared stem", () => {
    const specs = digitalFrameSpecs(JOB);
    expect(specs.filter((s) => s.formatId === "led-mall-entrance")).toHaveLength(1);
  });

  it("carries safe_px through", () => {
    const specs = digitalFrameSpecs(JOB);
    const led = specs.find((s) => s.formatId === "led-mall-entrance");
    expect(led?.safePx).toBe(20);
  });

  it("uses the deliverable's expected_stem as the frame name", () => {
    const specs = digitalFrameSpecs(JOB);
    const ig = specs.find((s) => s.formatId === "ig-post");
    expect(ig?.stem).toBe("2026-09-25_autumn-sale_ig-post_1080x1350px_v01");
  });

  it("skips a deliverable whose format is missing from job.formats", () => {
    const job: Job = {
      ...JOB,
      deliverables: [
        { format_id: "does-not-exist", type: "png", panel: null, expected_stem: "x" },
      ],
    };
    expect(digitalFrameSpecs(job)).toEqual([]);
  });
});

describe("pageName", () => {
  it("combines the job id's date and the job name", () => {
    expect(pageName(JOB)).toBe("2026-09-25 Autumn Sale");
  });
});

describe("gridColumns", () => {
  it("is roughly square and never zero", () => {
    expect(gridColumns(0)).toBe(1);
    expect(gridColumns(1)).toBe(1);
    expect(gridColumns(4)).toBe(2);
    expect(gridColumns(5)).toBe(3);
    expect(gridColumns(9)).toBe(3);
  });
});

describe("layoutGrid", () => {
  it("places items left to right then wraps", () => {
    const items = [
      { widthPx: 100, heightPx: 100 },
      { widthPx: 100, heightPx: 100 },
      { widthPx: 100, heightPx: 100 },
    ];
    const positions = layoutGrid(items); // gridColumns(3) = 2
    expect(positions[0]).toMatchObject({ x: 0, y: 0 });
    expect(positions[1]).toMatchObject({ x: 200, y: 0 });
    expect(positions[2]).toMatchObject({ x: 0, y: 200 });
  });

  it("uses each row's tallest item for the next row's y", () => {
    const items = [
      { widthPx: 100, heightPx: 300 },
      { widthPx: 100, heightPx: 100 },
      { widthPx: 100, heightPx: 100 },
    ];
    const positions = layoutGrid(items);
    expect(positions[2].y).toBe(400); // 300 (tallest in row 1) + 100 gap
  });

  it("returns the original item, not a re-lookup by size", () => {
    const a = { widthPx: 100, heightPx: 100, label: "a" };
    const b = { widthPx: 100, heightPx: 100, label: "b" };
    const positions = layoutGrid([a, b]);
    expect(positions[0].item.label).toBe("a");
    expect(positions[1].item.label).toBe("b");
  });
});

describe("bumpFrameName", () => {
  it("increments a two-digit version suffix", () => {
    expect(bumpFrameName("2026-09-25_autumn-sale_ig-post_1080x1350px_v01")).toBe(
      "2026-09-25_autumn-sale_ig-post_1080x1350px_v02"
    );
  });

  it("pads back to the same width past 9", () => {
    expect(bumpFrameName("x_v09")).toBe("x_v10");
  });

  it("leaves a name with no version suffix unchanged", () => {
    expect(bumpFrameName("no-version-here")).toBe("no-version-here");
  });
});
