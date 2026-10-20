"""A stand-in for `concat --mcp headless` in CI, where Concat isn't
installed. Speaks the same MCP lines, offers Concat 0.2.8's real tool
list (concat_tools_v0.2.8.json), keeps a tiny project state, and on
export writes a header-valid MP4 at the project's size, rate and length,
so the real video validator can check the result.

Run: python fake_concat.py   (stdin/stdout JSON-RPC lines)
Env FAKE_CONCAT_LOG=<file> appends every tool call as a JSON line.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "app"))

from mp4_fixture import make_mp4  # noqa: E402

TOOLS = json.loads((HERE / "concat_tools_v0.2.8.json").read_text(encoding="utf-8"))["tools"]
projects: dict[str, dict] = {}
jobs: dict[str, str] = {}


def media_length(file: str) -> float:
    if file.lower().endswith((".mp4", ".mov", ".m4v")):
        from studio_helper.validators.mp4info import read_mp4
        return read_mp4(Path(file)).duration_s
    return 5.0  # a still, as in Concat


def tool(name: str, a: dict) -> dict:
    log = os.environ.get("FAKE_CONCAT_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tool": name, "args": a}) + "\n")
    if name == "concat_version":
        return {"concat": "0.2.8", "apiVersion": "0.2"}
    if name == "project_create":
        path = str(Path(a["location"]) / a["name"])
        if Path(path).exists():
            raise ValueError(f"{path} already exists")
        Path(path).mkdir(parents=True)
        (Path(path) / "concat.json").write_text("{}")
        projects[path] = {"video": a.get("video") or {"width": 1920, "height": 1080,
                                                      "rateNum": 30, "rateDen": 1},
                          "media": {}, "clips": {}, "tracks": ["T1", "T2", "T3", "T4"], "n": 0}
        return {"project": {"name": a["name"]}}
    if name == "project_open":
        if a["path"] not in projects:
            raise ValueError(f"could not read {a['path']}/concat.json")
        return {"project": {}}
    p = projects.get(a.get("path", ""))
    if name in ("project_save", "project_close"):
        return {}
    if name == "timeline_read":
        clips = [dict(c, id=cid) for cid, c in p["clips"].items()]
        return {"timeline": {"id": "TL1", "tracks": [{"id": t, "index": i}
                                                    for i, t in enumerate(p["tracks"])],
                             "clips": clips}}
    if name == "track_add":
        p["tracks"].append(f"T{len(p['tracks']) + 1}")
        return {"createdId": p["tracks"][-1]}
    if name == "media_import":
        for f in p["media"].values():
            if f == a["file"]:
                return {}  # already in the bin: no new id, like Concat
        p["n"] += 1
        mid = f"m{p['n']}"
        p["media"][mid] = a["file"]
        return {"createdId": mid}
    if name == "clip_add":
        p["n"] += 1
        cid = f"c{p['n']}"
        length = media_length(p["media"][a["mediaId"]])
        p["clips"][cid] = {"track": a["trackId"], "start": a["start"], "duration": length,
                           "end": a["start"] + length, "media": a["mediaId"]}
        return {"createdId": cid}
    if name == "clip_trim":
        c = p["clips"][a["clipId"]]
        c["duration"] += a["delta"]
        c["end"] = c["start"] + c["duration"]
        return {}
    if name in ("clip_transform", "clip_update", "keyframe_set", "timeline_background"):
        return {}
    if name == "export_start":
        v = p["video"]
        length = max((c["end"] for c in p["clips"].values()), default=0.0)
        make_mp4(Path(a["output"]), w=a.get("width") or v["width"],
                 h=a.get("height") or v["height"], seconds=length,
                 fps=round(a.get("rateNum") or v["rateNum"]))
        jobs["j1"] = a["output"]
        return {"job": "j1"}
    if name == "export_wait":
        return {"state": "done", "output": jobs.get(a["job"])}
    if name == "preview_frame":
        from PIL import Image
        Image.new("RGB", (a.get("width") or 64, a.get("height") or 64)).save(a["output"])
        return {"path": a["output"]}
    raise ValueError(f"fake concat doesn't know {name}")


def main() -> None:
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        method = msg["method"]
        if method == "initialize":
            result = {"serverInfo": {"name": "concat", "version": "0.2.8"}, "capabilities": {}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg["params"]
            try:
                data = tool(params["name"], params.get("arguments", {}))
                result = {"structuredContent": data,
                          "content": [{"type": "text", "text": json.dumps(data)}]}
            except Exception as exc:  # noqa: BLE001
                result = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        else:
            result = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
