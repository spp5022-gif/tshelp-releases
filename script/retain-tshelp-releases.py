"""Strict latest-three binary retention; ignores legacy protection markers.

Version order, not edited/published time. Never delete releases or tags.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request

REPO = "spp5022-gif/tshelp-releases"


def plan(rows):
    groups = {"exe": [], "apk": []}
    for release in rows:
        if release.get("draft"):
            continue
        binaries = [a for a in release["assets"]
                    if a["name"].lower().endswith((".exe", ".apk"))]
        if not binaries:
            continue
        match = re.fullmatch(r"(?:production-|development-|v)?(\d+)\.(\d+)\.(\d+)",
                             release["tag_name"])
        if not match:
            raise ValueError("Unrecognized binary version: " + release["tag_name"])
        version = tuple(map(int, match.groups()))
        for asset in binaries:
            if asset.get("state") != "uploaded" or asset["size"] <= 0:
                raise ValueError("Incomplete binary upload; refusing cleanup")
            groups[asset["name"].lower().rsplit(".", 1)[1]].append((version, release, asset))
    deletes, kept = [], []
    for extension, items in groups.items():
        items.sort(key=lambda x: (x[0], x[2].get("created_at", ""), x[2]["id"]), reverse=True)
        kept.extend((r["tag_name"], a["name"]) for _, r, a in items[:3])
        for _, release, asset in items[3:]:
            names = {asset["name"], asset["name"] + ".sha256"}
            # Remove platform metadata only if no binary of that platform remains.
            if not any(r["id"] == release["id"] for _, r, _ in items[:3]):
                names.add("android.json" if extension == "apk" else "windows.json")
            deletes.extend((release["tag_name"], a) for a in release["assets"] if a["name"] in names)
    unique = list({a["id"]: (tag, a) for tag, a in deletes}.values())
    # Sidecars first: once the binary disappears it no longer participates in rank.
    unique.sort(key=lambda item: item[1]["name"].lower().endswith((".exe", ".apk")))
    return kept, unique


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ["TSHELP_RELEASES_TOKEN"]

    def api(path, method="GET"):
        request = urllib.request.Request("https://api.github.com/repos/" + REPO + path,
            method=method, headers={"Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json", "User-Agent": "TSHELP-retention"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if method == "DELETE" and error.code == 404:
                return None
            raise

    def inventory():
        rows = []
        for page in range(1, 51):
            batch = api(f"/releases?per_page=100&page={page}")
            for release in batch:
                assets = []
                for asset_page in range(1, 51):
                    part = api(f"/releases/{release['id']}/assets?per_page=100&page={asset_page}")
                    assets.extend(part)
                    if len(part) < 100:
                        break
                else:
                    raise RuntimeError("Incomplete asset inventory")
                release["assets"] = assets
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise RuntimeError("Incomplete release inventory")

    kept, deletes = plan(inventory())
    print("Keep:", json.dumps(kept))
    for tag, asset in deletes:
        if args.apply:
            # Re-evaluate rank immediately before deletion, never trust stale plans.
            _, fresh = plan(inventory())
            if asset["id"] not in {a["id"] for _, a in fresh}:
                continue
            api(f"/releases/assets/{asset['id']}", "DELETE")
        print("Deleted" if args.apply else "Would delete", tag, asset["name"])
    if args.apply:
        kept, remaining = plan(inventory())
        if remaining:
            raise RuntimeError("Retention incomplete; rerun after concurrent publication")
        print("Verified retained binaries:", json.dumps(kept))


if __name__ == "__main__":
    main()
