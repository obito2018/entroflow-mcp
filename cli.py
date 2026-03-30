# -*- coding: utf-8 -*-
import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from core import config, downloader, loader, store
from tools.platform import resolve_platform
from tools.system import check_updates, update_server


ASSETS_DIR = Path.home() / ".entroflow" / "assets"
PLATFORM_DOCS_DIR = Path.home() / ".entroflow" / "docs" / "platforms"


def _print(message: str = ""):
    print(message)


def _refresh_catalog():
    try:
        downloader.refresh_catalog()
    except Exception:
        # Catalog refresh is helpful for aliases, but not required for local execution.
        pass


def _resolve_platform_or_exit(name: str) -> str:
    platform_id, err = resolve_platform(name)
    if err or not platform_id:
        raise RuntimeError(err or f"Failed to resolve platform '{name}'.")
    return platform_id


def _load_catalog() -> list[dict]:
    catalog_path = ASSETS_DIR / "catalog.json"
    if not catalog_path.exists():
        return []

    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    platforms = data.get("platforms", [])
    if not isinstance(platforms, list):
        return []
    return [entry for entry in platforms if isinstance(entry, dict)]


def _platform_doc_path(platform_id: str) -> Path:
    return PLATFORM_DOCS_DIR / f"{platform_id}.md"


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def _platforms_for_listing(explicit_platform: str | None) -> list[str]:
    if explicit_platform:
        return [_resolve_platform_or_exit(explicit_platform)]

    platforms = config.get_connected_platforms()
    if platforms:
        return platforms

    if not ASSETS_DIR.exists():
        return []

    discovered = []
    for item in ASSETS_DIR.iterdir():
        if item.is_dir() and (item / "connector").exists():
            discovered.append(item.name)
    return discovered


def _connector_list_devices(connector):
    return loader.list_connector_devices(connector)


def cmd_list_platforms(args: argparse.Namespace) -> int:
    _refresh_catalog()
    catalog = _load_catalog()
    if not catalog:
        _print("No platform catalog is available locally. Run `entroflow update` and try again.")
        return 1

    query = (args.query or "").strip().lower()
    matched = []
    for entry in catalog:
        candidates = [
            entry.get("id", ""),
            entry.get("display_name", ""),
            *entry.get("aliases", []),
        ]
        normalized = [str(item).strip().lower() for item in candidates if str(item).strip()]
        if not query or any(query in item for item in normalized):
            matched.append(entry)

    if not matched:
        _print(f"No supported platform matched '{args.query}'.")
        _print("Run `entroflow update` if you expect a newly added platform.")
        return 1

    connected = set(config.get_connected_platforms())
    missing_docs = False

    _print(f"Found {len(matched)} supported platform(s):")
    _print("")
    for entry in matched:
        platform_id = entry.get("id", "?")
        display_name = entry.get("display_name") or platform_id
        aliases = [str(item) for item in entry.get("aliases", []) if str(item).strip()]
        description = str(entry.get("description", "")).strip()
        doc_path = _platform_doc_path(platform_id)
        doc_ready = doc_path.exists()
        status = "connected" if platform_id in connected else "available"

        _print(f"- {platform_id} ({display_name})")
        _print(f"  status     : {status}")
        if description:
            _print(f"  summary    : {description}")
        if aliases:
            _print(f"  aliases    : {', '.join(aliases)}")
        _print(f"  connect    : entroflow connect {platform_id}")
        if doc_ready:
            _print(f"  doc        : {doc_path}")
        else:
            missing_docs = True
            _print(f"  doc        : missing locally ({doc_path})")
            _print("  next       : run `entroflow update` to sync the latest platform docs")
            _print("  note       : if the doc is still missing after update, the guide has not been published locally yet")
        _print("")

    if missing_docs:
        _print("Some platform docs are missing locally. Run `entroflow update` before connecting a newly added platform.")
        _print("If a doc is still missing after update, stop and tell the user that the platform guide is not published yet.")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    _refresh_catalog()
    platform = _resolve_platform_or_exit(args.platform)

    _print(f"Connecting platform: {platform}")

    connector_dir = ASSETS_DIR / platform / "connector"
    devices_file = connector_dir / f"{platform}_devices.json"
    if connector_dir.exists() and devices_file.exists():
        _print(f"Platform connector already installed: {platform}")
    else:
        version = downloader.download_platform(platform)
        config.set_platform_version(platform, version)
        _print(f"Installed platform connector {platform} (v{version})")

    connector = loader.load_connector(platform)
    result = connector.start_qr_login(region="cn")
    session_id = result.get("session_id")
    qr_url = result.get("qr_url")
    expires_in = result.get("expires_in")

    if not session_id or not qr_url:
        raise RuntimeError(f"Unsupported login response for platform '{platform}': {result}")

    _print("")
    opened = _open_browser(qr_url)
    if opened:
        _print("A browser window was opened for login. Complete confirmation in the platform app.")
    else:
        _print("Could not open the browser automatically. Open the following URL and complete login in the platform app:")
    _print(qr_url)
    if expires_in:
        _print(f"QR code expires in {expires_in} seconds.")
    _print("")
    input("Press Enter after you have scanned and confirmed the login...")

    while True:
        poll = connector.poll_qr_login(session_id)
        status = poll.get("status", "")
        if status == "ok":
            config.add_installed_platform(platform)
            _print(f"Platform '{platform}' connected successfully.")
            return 0
        if status == "waiting":
            _print("Still waiting for confirmation...")
            time.sleep(3)
            continue
        if status == "expired":
            _print("Login QR code expired. Run the command again to get a new code.")
            return 1
        raise RuntimeError(poll.get("message") or f"Login failed for platform '{platform}'.")


def cmd_list_devices(args: argparse.Namespace) -> int:
    _refresh_catalog()
    platforms = _platforms_for_listing(args.platform)
    if not platforms:
        _print("No connected platforms found. Run `entroflow connect <platform>` first.")
        return 1

    registered = {item.get("device_id"): item for item in store.load()}
    any_output = False

    for platform in platforms:
        try:
            connector = loader.load_connector(platform)
            user_devices = _connector_list_devices(connector)
            supported_models = loader.load_platform_devices(platform)
        except Exception as exc:
            _print(f"[{platform}] Failed to list devices: {exc}")
            _print("")
            continue

        _print(f"[{platform}] {len(user_devices)} connected device(s)")
        for item in user_devices:
            did = item.get("did", "?")
            model = item.get("model", "?")
            name = item.get("name", "?")
            device_id = f"{platform}:{did}"
            supported = model in supported_models
            registered_record = registered.get(device_id)
            readiness = "ready" if registered_record else "needs setup"
            support_text = "supported" if supported else "unsupported"

            _print(f"- {name}")
            _print(f"  device_id : {device_id}")
            _print(f"  did       : {did}")
            _print(f"  model     : {model}")
            _print(f"  support   : {support_text}")
            _print(f"  runtime   : {readiness}")
            if registered_record:
                _print(f"  location  : {registered_record.get('location', '-')}")
                _print(f"  remark    : {registered_record.get('remark', '-')}")
            _print("")
        any_output = True

    if not any_output:
        _print("No devices could be listed from the connected platforms.")
        return 1
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    _refresh_catalog()
    platform = _resolve_platform_or_exit(args.platform)
    model = (args.model or "").strip()
    version = args.version.strip() if isinstance(args.version, str) and args.version.strip() else None

    if not model:
        raise RuntimeError("Download requires --model.")

    downloaded_version = downloader.download_device(model, platform, version)
    config.set_device_version(platform, model, downloaded_version)
    _print(f"Downloaded device resource: {model} (v{downloaded_version})")
    return 0


def _normalize_setup_inputs(args: argparse.Namespace) -> tuple[str, str, str]:
    platform = args.platform
    did = args.did
    model = args.model

    if args.device:
        if ":" in args.device and not did:
            maybe_platform, maybe_did = args.device.split(":", 1)
            platform = platform or maybe_platform
            did = maybe_did
        elif not did:
            did = args.device

    if not platform or not did or not model:
        raise RuntimeError("Setup requires platform, did, and model.")

    return _resolve_platform_or_exit(platform), did, model


def cmd_setup(args: argparse.Namespace) -> int:
    _refresh_catalog()
    platform, did, model = _normalize_setup_inputs(args)
    version = args.version.strip() if isinstance(args.version, str) and args.version.strip() else None

    if not all([args.name, args.location, args.remark]):
        raise RuntimeError("Setup requires --name, --location, and --remark.")

    connector = loader.load_connector(platform)
    user_devices = _connector_list_devices(connector)
    discovered = next((item for item in user_devices if str(item.get("did")) == str(did)), None)
    if not discovered:
        raise RuntimeError(
            f"Device did='{did}' was not found on platform '{platform}'. Run `entroflow list-devices --platform {platform}` first."
        )

    discovered_model = discovered.get("model")
    if discovered_model and discovered_model != model:
        raise RuntimeError(
            f"Model mismatch for did '{did}': discovered '{discovered_model}', got '{model}'."
        )

    supported_models = loader.load_platform_devices(platform)
    if model not in supported_models:
        raise RuntimeError(
            f"Device model '{model}' is not currently supported on platform '{platform}'."
        )

    driver_path = ASSETS_DIR / platform / "devices" / model / f"{model}.py"
    if driver_path.exists():
        installed_version = config.get_device_version(platform, model)
        if version and installed_version == version:
            _print(f"Device driver already installed: {model} (v{installed_version})")
        elif version:
            installed_version_text = f"v{installed_version}" if installed_version else "unknown version"
            _print(f"Replacing device driver {model} ({installed_version_text}) with v{version}")
            downloaded_version = downloader.download_device(model, platform, version)
            config.set_device_version(platform, model, downloaded_version)
            _print(f"Installed device driver {model} (v{downloaded_version})")
        else:
            _print(f"Device driver already installed: {model}")
    else:
        downloaded_version = downloader.download_device(model, platform, version)
        config.set_device_version(platform, model, downloaded_version)
        _print(f"Installed device driver {model} (v{downloaded_version})")

    result = store.register(did, model, platform, args.name, args.location, args.remark)
    if result["ok"]:
        record = result["record"]
        _print(f"Registered device: {record['name']} ({record['device_id']})")
        return 0

    _print(result["message"])
    return 1


def cmd_update(_: argparse.Namespace) -> int:
    _print(check_updates())
    _print("")
    _print(update_server())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="entroflow", description="EntroFlow setup and runtime control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    platforms_parser = subparsers.add_parser("list-platforms", help="List currently supported platforms")
    platforms_parser.add_argument("query", nargs="?", help="Optional keyword to filter by id, name, or alias")
    platforms_parser.set_defaults(func=cmd_list_platforms)

    connect_parser = subparsers.add_parser("connect", help="Connect a platform and complete authentication")
    connect_parser.add_argument("platform", help="Platform id or alias, e.g. mihome")
    connect_parser.set_defaults(func=cmd_connect)

    list_parser = subparsers.add_parser("list-devices", help="List devices from connected platforms")
    list_parser.add_argument("--platform", help="Only list devices for one platform")
    list_parser.set_defaults(func=cmd_list_devices)

    download_parser = subparsers.add_parser("download", help="Download a device resource into local assets")
    download_parser.add_argument("--platform", required=True, help="Platform id, e.g. mihome")
    download_parser.add_argument("--model", required=True, help="Device model id")
    download_parser.add_argument("--version", help="Optional device driver version, e.g. 1.0.2")
    download_parser.set_defaults(func=cmd_download)

    setup_parser = subparsers.add_parser("setup", help="Install a device driver and register the device locally")
    setup_parser.add_argument("device", nargs="?", help="Optional did or platform:did")
    setup_parser.add_argument("--platform", help="Platform id, e.g. mihome")
    setup_parser.add_argument("--did", help="Platform device id")
    setup_parser.add_argument("--model", help="Device model id")
    setup_parser.add_argument("--version", help="Optional device driver version, e.g. 1.0.2")
    setup_parser.add_argument("--name", help="Human-friendly device name")
    setup_parser.add_argument("--location", help="Device location")
    setup_parser.add_argument("--remark", help="Device remark")
    setup_parser.set_defaults(func=cmd_setup)

    update_parser = subparsers.add_parser("update", help="Update local assets and server code")
    update_parser.set_defaults(func=cmd_update)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        _print("\nCancelled.")
        return 130
    except Exception as exc:
        _print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
