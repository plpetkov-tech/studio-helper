// code.ts -- Figma plugin main thread (SPEC.md §6.6). Runs in Figma's
// sandboxed plugin environment; talks to ui.html only via postMessage
// (no disk access, no network -- see manifest.json's networkAccess).

import { bumpFrameName, digitalFrameSpecs, layoutGrid, pageName } from "./layout";
import type { Job } from "./layout";

figma.showUI(__html__, { width: 360, height: 460 });

type UiMessage =
  | { type: "create-frames"; jobJson: string }
  | { type: "bump-version" };

figma.ui.onmessage = async (msg: UiMessage) => {
  try {
    if (msg.type === "create-frames") {
      const job: Job = JSON.parse(msg.jobJson);
      const message = await createFrames(job);
      figma.ui.postMessage({ type: "result", ok: true, message });
    } else if (msg.type === "bump-version") {
      const message = bumpVersion();
      figma.ui.postMessage({ type: "result", ok: true, message });
    }
  } catch (e) {
    figma.ui.postMessage({ type: "result", ok: false, message: String(e) });
  }
};

function findPage(name: string): PageNode | null {
  return (figma.root.children.find((p) => p.name === name) as PageNode) ?? null;
}

async function createFrames(job: Job): Promise<string> {
  const name = pageName(job);
  let page = findPage(name);
  let isNewPage = false;
  if (!page) {
    page = figma.createPage();
    page.name = name;
    isNewPage = true;
  }

  const specs = digitalFrameSpecs(job);
  if (specs.length === 0) {
    return "This job has no digital (png/jpg) deliverables to create frames for.";
  }

  // Idempotent (SPEC.md §6.6): only add frames that aren't already on
  // the page, by name -- never touch existing content.
  const existingNames = new Set(page.children.map((n) => n.name));
  const toCreate = specs.filter((s) => !existingNames.has(s.stem));
  const positions = layoutGrid(toCreate);

  for (const pos of positions) {
    const frame = figma.createFrame();
    frame.name = pos.item.stem;
    frame.resize(pos.item.widthPx, pos.item.heightPx);
    frame.x = pos.x;
    frame.y = pos.y;
    frame.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];

    if (pos.item.safePx > 0) {
      frame.layoutGrids = [
        {
          pattern: "GRID",
          sectionSize: pos.item.safePx,
          visible: true,
          color: { r: 1, g: 0, b: 0, a: 0.1 },
        },
      ];
    }

    page.appendChild(frame);
  }

  figma.currentPage = page;
  figma.viewport.scrollAndZoomIntoView(page.children);

  const skipped = specs.length - toCreate.length;
  const parts: string[] = [];
  if (toCreate.length > 0) {
    parts.push(`Created ${toCreate.length} frame(s)`);
  }
  if (skipped > 0) {
    parts.push(`${skipped} already existed and were left as-is`);
  }
  const prefix = isNewPage ? `on new page "${page.name}"` : `on page "${page.name}"`;
  return parts.length > 0
    ? `${parts.join(", ")} ${prefix}.`
    : `All frames already exist ${prefix} -- nothing to add.`;
}

function bumpVersion(): string {
  const page = figma.currentPage;
  let renamed = 0;
  for (const node of page.children) {
    const next = bumpFrameName(node.name);
    if (next !== node.name) {
      node.name = next;
      renamed += 1;
    }
  }
  return renamed === 0
    ? "No versioned frames found on this page."
    : `Renamed ${renamed} frame(s). Click "Start revision" in Studio Helper too.`;
}
