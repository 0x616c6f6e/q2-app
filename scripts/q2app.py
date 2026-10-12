"""Create, validate and reproducibly pack independent Q2-App Lua projects (API 2)."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import uuid
import zipfile
import shutil

VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
CAP = re.compile(r"^[a-z0-9_.]{1,47}$")
ALLOWED = {
    "format",
    "id",
    "name",
    "description",
    "version",
    "entry",
    "type",
    "api",
    "capabilities",
    "resources",
    "icon",
    "supported_resolutions",
    "dynamic_resources",
    "ota",
}


def unique(pairs):
    """Reject ambiguous objects instead of silently accepting the last duplicate."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def manifest(path):
    """Read the API 2 manifest; return its parsed object and original UTF-8 bytes."""
    raw = path.read_bytes()
    if len(raw) > 4096 or b"\x00" in raw or b"\\u0000" in raw:
        raise ValueError("manifest size/NUL constraint")
    m = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(m, dict) or set(m) - ALLOWED:
        raise ValueError("unknown manifest field")
    if type(m.get("format")) is not int or m["format"] != 2 or type(m.get("api")) is not int or m["api"] != 2:
        raise ValueError("requires format 2 and API 2")
    identity = uuid.UUID(m["id"])
    if identity.version != 4 or str(identity) != m["id"]:
        raise ValueError("id must be lowercase UUID v4; keep it stable across builds")
    if not isinstance(m.get("name"), str) or not 0 < len(m["name"].encode()) < 64:
        raise ValueError("name must be 1..63 UTF-8 bytes")
    if (
        not isinstance(m.get("version"), str)
        or len(m["version"]) >= 64
        or not VERSION.fullmatch(m["version"])
    ):
        raise ValueError("strict SemVer version required")
    if m.get("entry") != "main.lua" or m.get("type") != "app":
        raise ValueError("this profile supports app / main.lua only")
    capabilities = m.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != {"required", "optional"}:
        raise ValueError("declare required and optional capabilities; scopes are not implemented")
    all_caps = []
    for kind in ["required", "optional"]:
        values = capabilities[kind]
        if (
            not isinstance(values, list)
            or len(values) > 16
            or any(not isinstance(x, str) or not CAP.fullmatch(x) for x in values)
        ):
            raise ValueError("invalid capability list")
        all_caps += values
    if len(all_caps) != len(set(all_caps)):
        raise ValueError("duplicate capability declaration")
    resources = m.get("resources")
    if (
        not isinstance(resources, dict)
        or set(resources) != {"lua_heap_kib"}
        or type(resources["lua_heap_kib"]) is not int
        or not 32 <= resources["lua_heap_kib"] <= 384
    ):
        raise ValueError("lua_heap_kib must be an integer from 32 to 384")
    for key in ["dynamic_resources", "ota"]:
        if key in m and (
            not isinstance(m[key], str) or not m[key].startswith("https://") or len(m[key].encode()) > 256
        ):
            raise ValueError(f"{key} must be an HTTPS metadata URL")
    if "description" in m and (not isinstance(m["description"], str) or len(m["description"].encode()) > 512):
        raise ValueError("description must be a string of at most 512 UTF-8 bytes")
    if "icon" in m and (
        not isinstance(m["icon"], str)
        or len(m["icon"].encode()) > 96
        or not re.fullmatch(r"assets/[A-Za-z0-9_./-]+", m["icon"])
        or ".." in m["icon"]
    ):
        raise ValueError("icon must be a relative asset path")
    if "supported_resolutions" in m:
        values = m["supported_resolutions"]
        if not isinstance(values, list) or not 1 <= len(values) <= 16:
            raise ValueError("supported_resolutions must contain 1..16 resolution strings")
        for value in values:
            if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{1,3}x[1-9][0-9]{1,3}", value):
                raise ValueError("resolution must use canonical WIDTHxHEIGHT, e.g. 502x410")
            if any(not 64 <= int(axis) <= 1024 for axis in value.split("x")):
                raise ValueError("resolution dimensions must be 64..1024 pixels")
        if len(set(values)) != len(values):
            raise ValueError("duplicate supported resolution")
    return m, raw


def bundle(root):
    """Bind local modules as lexical functions without enabling load or filesystem access."""
    source = (root / "main.lua").read_text(encoding="utf8")
    modules = sorted((root / "src").rglob("*.lua")) if (root / "src").exists() else []
    if not modules:
        result = source.encode()
    else:
        parts = [
            "local system_require = require\nlocal modules, cache, loading = {}, {}, {}\nlocal require\n",
            """require = function(name)
    if name == "q2" then return system_require(name) end
    if cache[name] ~= nil then return cache[name] end
    assert(modules[name], "module unavailable")
    assert(not loading[name], "module dependency cycle")
    loading[name] = true
    local value = modules[name]()
    if value == nil then value = true end
    cache[name], loading[name] = value, nil
    return value
end
""",
        ]
        names = set()
        for path in modules:
            name = ".".join(path.relative_to(root / "src").with_suffix("").parts)
            if (
                name == "q2"
                or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", name)
                or name in names
            ):
                raise ValueError("invalid/duplicate module name")
            names.add(name)
            parts += [
                f"modules[{json.dumps(name)}] = function()\n",
                path.read_text(encoding="utf8"),
                "\nend\n",
            ]
        parts += ["return (function()\n", source, "\nend)()\n"]
        result = "".join(parts).encode()
    if not result or len(result) > 32768 or result.startswith(b"\x1bLua"):
        raise ValueError("bundled text main.lua must be 1..32768 bytes")
    return result


def pack(root, output):
    """Write deterministic ZIP_STORED package and checksums; this is not a signature."""
    root = root.resolve()
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("symlinks are not accepted")
    m, raw = manifest(root / "manifest.json")
    entries = {"manifest.json": raw, "main.lua": bundle(root)}
    for path in sorted((root / "assets").rglob("*")) if (root / "assets").exists() else []:
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if (
                len(name.encode()) > 96
                or not re.fullmatch(r"assets/[A-Za-z0-9_./-]+", name)
                or ".." in name.split("/")
            ):
                raise ValueError("invalid asset path")
            data = path.read_bytes()
            if len(data) > 256 * 1024:
                raise ValueError("asset exceeds 256 KiB")
            entries[name] = data
    if "icon" in m and m["icon"] not in entries:
        raise ValueError("icon must reference a packaged asset")
    if len(entries) > 32 or sum(map(len, entries.values())) > 1024 * 1024:
        raise ValueError("package quota exceeded")
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    entries["checksums.json"] = (json.dumps(hashes, sort_keys=True, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    staged = output.parent / (output.stem + ".run")
    if staged.is_symlink():
        raise ValueError("staging directory must not be a symlink")
    staged.mkdir(exist_ok=True)
    staged_assets = staged / "assets"
    # This is generated package content. Remove only the verified asset subtree, including stale images.
    if staged_assets.is_symlink() or staged_assets.resolve().parent != staged.resolve():
        raise ValueError("unsafe staging assets directory")
    if staged_assets.exists():
        shutil.rmtree(staged_assets)
    for name, data in entries.items():
        if name.startswith("assets/"):
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    (staged / "manifest.json").write_bytes(raw)
    (staged / "main.lua").write_bytes(entries["main.lua"])
    record = {
        "id": m["id"],
        "version": m["version"],
        "api": 2,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "package": output.name,
        "trust": "development package; no publisher signature",
        "entries": hashes,
    }
    output.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    return record


def pack_factory(root, output):
    """Build the trusted product catalog; APP manifests cannot assign factory/default status."""
    config = json.loads((root / "factory.json").read_text(encoding="utf8"), object_pairs_hook=unique)
    if (
        set(config) != {"format", "default_app", "apps"}
        or type(config["format"]) is not int
        or config["format"] != 1
    ):
        raise ValueError("invalid factory catalog")
    if not isinstance(config["apps"], list) or not 2 <= len(config["apps"]) <= 8:
        raise ValueError("factory catalog requires 2..8 apps")
    seen, ids, records = set(), set(), []
    for entry in config["apps"]:
        if not isinstance(entry, dict) or set(entry) != {"directory", "factory"}:
            raise ValueError("invalid catalog entry")
        name = entry["directory"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in seen:
            raise ValueError("invalid or duplicate APP directory")
        if type(entry["factory"]) is not bool:
            raise ValueError("factory status must be boolean")
        m, _ = manifest(root / "apps" / name / "manifest.json")
        if m["id"] in ids:
            raise ValueError("duplicate catalog UUID")
        seen.add(name)
        ids.add(m["id"])
        records.append({**entry, "id": m["id"]})
    flags = {entry["directory"]: entry["factory"] for entry in records}
    if config["default_app"] != "homepage" or not flags.get("homepage") or not flags.get("settings"):
        raise ValueError("homepage and settings must be factory apps; homepage is the default")
    for entry in records:
        pack(root / "apps" / entry["directory"], output / (entry["directory"] + ".q2app"))
    result = {**config, "apps": records}
    (output / "factory.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    return result


def create(root, name):
    """Generate the UUID only on project creation; never overwrite an existing project."""
    root.mkdir(parents=True, exist_ok=False)
    m = {
        "format": 2,
        "id": str(uuid.uuid4()),
        "name": name,
        "supported_resolutions": ["368x448", "448x368", "410x502", "502x410"],
        "version": "0.1.0",
        "type": "app",
        "entry": "main.lua",
        "api": 2,
        "capabilities": {"required": ["system.info"], "optional": ["display.text"]},
        "resources": {"lua_heap_kib": 64},
    }
    (root / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    (root / "main.lua").write_text(
        "local q = require('q2')\nreturn { on_start = function() assert(q.os.info()) end }\n", encoding="utf8"
    )
    (root / "src").mkdir()
    (root / "assets").mkdir()
    for resolution in m["supported_resolutions"]:
        (root / "assets" / resolution).mkdir()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("create")
    c.add_argument("directory", type=Path)
    c.add_argument("--name", required=True)
    v = commands.add_parser("validate")
    v.add_argument("directory", type=Path)
    b = commands.add_parser("pack")
    b.add_argument("directory", type=Path)
    b.add_argument("-o", "--output", type=Path, required=True)
    f = commands.add_parser("factory")
    f.add_argument("directory", type=Path)
    f.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            create(args.directory, args.name)
            print(args.directory)
        elif args.command == "factory":
            print(json.dumps(pack_factory(args.directory, args.output), indent=2))
        elif args.command == "validate":
            m, _ = manifest(args.directory / "manifest.json")
            bundle(args.directory)
            print("VALID", m["id"], m["version"])
        else:
            print(json.dumps(pack(args.directory, args.output), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")
