# -*- coding: utf-8 -*-
import argparse
import getpass
import json
import sys
import time
import webbrowser
from pathlib import Path

from core import config, downloader, loader, store
from tools.platform import resolve_platform
from tools.system import check_updates, managed_iot_platforms, update_server


ASSETS_DIR = Path.home() / ".entroflow" / "assets"
PLATFORM_DOCS_DIR = Path.home() / ".entroflow" / "docs" / "platforms"
BUNDLED_CATALOG_PATH = Path(__file__).resolve().parent / "assets" / "catalog.json"


def _print(message: str = ""):
    print(message)


def _refresh_catalog() -> dict:
    try:
        return downloader.refresh_catalog()
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }


def _ensure_bundled_catalog_seeded():
    catalog_path = ASSETS_DIR / "catalog.json"
    if catalog_path.exists() or not BUNDLED_CATALOG_PATH.exists():
        return
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(BUNDLED_CATALOG_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _resolve_platform_or_exit(name: str) -> str:
    platform_id, err = resolve_platform(name)
    if err or not platform_id:
        raise RuntimeError(err or f"Failed to resolve platform '{name}'.")
    return platform_id


def _load_catalog() -> list[dict]:
    catalog_path = ASSETS_DIR / "catalog.json"
    if not catalog_path.exists():
        _ensure_bundled_catalog_seeded()
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


def _platform_doc_manifest_path(platform_id: str) -> Path:
    return PLATFORM_DOCS_DIR / f"{platform_id}.manifest.json"


def _load_cached_platform_doc_manifest(platform_id: str) -> dict | None:
    path = _platform_doc_manifest_path(platform_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def _is_interactive_stdin() -> bool:
    stdin = getattr(sys, "stdin", None)
    return bool(stdin and hasattr(stdin, "isatty") and stdin.isatty())


def _should_wait_for_login_prompt(args: argparse.Namespace) -> bool:
    if getattr(args, "no_prompt", False):
        return False
    return _is_interactive_stdin()


def _collect_connect_inputs(args: argparse.Namespace) -> dict:
    inputs: dict[str, str] = {}
    for key in ("url", "token"):
        value = getattr(args, key, None)
        if value:
            inputs[key] = str(value)
    for item in getattr(args, "input", None) or []:
        if "=" not in item:
            raise RuntimeError("--input must use key=value format.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeError("--input key cannot be empty.")
        inputs[key] = value
    return inputs


def _connect_presentation(args: argparse.Namespace) -> str:
    value = str(getattr(args, "presentation", "auto") or "auto").strip().lower()
    if value not in {"auto", "url", "file", "none"}:
        raise RuntimeError(f"Unsupported connection presentation: {value}")
    return value


def _build_connect_context(platform: str, args: argparse.Namespace, inputs: dict | None = None) -> dict:
    return {
        "protocol_version": "2.0",
        "platform_id": platform,
        "runtime_dir": str(Path.home() / ".entroflow" / "runtime"),
        "interactive": _is_interactive_stdin(),
        "presentation": _connect_presentation(args),
        "timeout_seconds": int(getattr(args, "timeout", 600) or 600),
        "inputs": dict(inputs or {}),
    }


def _connector_connect(connector, context: dict) -> dict:
    if not hasattr(connector, "connect"):
        raise RuntimeError(
            "This platform connector does not implement EntroFlow connector protocol v2. "
            "Run `entroflow update`; if the issue remains, the platform package must be republished."
        )
    result = connector.connect(context)
    if not isinstance(result, dict):
        raise RuntimeError(f"Connector returned an invalid connect result: {result!r}")
    return result


def _connector_poll_connect(connector, session_id: str, context: dict) -> dict:
    if not hasattr(connector, "poll_connect"):
        raise RuntimeError("Connector returned a pending connection but does not implement poll_connect().")
    result = connector.poll_connect(session_id, context)
    if not isinstance(result, dict):
        raise RuntimeError(f"Connector returned an invalid poll result: {result!r}")
    return result


def _connect_status(result: dict) -> str:
    return str(result.get("status") or "").strip().lower()


def _print_connect_actions(actions: list, presentation: str) -> None:
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or "instruction").strip().lower()
        message = str(action.get("message") or action.get("label") or "").strip()
        url = str(action.get("url") or action.get("connect_url") or "").strip()
        file_path = str(action.get("file_path") or action.get("path") or "").strip()

        if message:
            _print(message)

        if file_path:
            _print(file_path)

        if url:
            opened = False
            if presentation == "auto" and action_type in {"open_url", "complete_form", "scan_qr"}:
                opened = _open_browser(url)
            if opened:
                _print("Opened the connection URL in the default browser.")
            elif presentation != "none":
                _print(url)


def _print_required_inputs(required_inputs: list) -> None:
    if not required_inputs:
        return
    _print("Required connection inputs:")
    for item in required_inputs:
        if isinstance(item, str):
            _print(f"  - {item}")
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or item.get("prompt") or "").strip()
        secret = " secret" if item.get("secret") else ""
        if description:
            _print(f"  - {name}{secret}: {description}")
        else:
            _print(f"  - {name}{secret}")


def _prompt_required_inputs(required_inputs: list, inputs: dict, args: argparse.Namespace) -> bool:
    if not required_inputs or not _should_wait_for_login_prompt(args):
        return False
    changed = False
    for item in required_inputs:
        if isinstance(item, str):
            name = item.strip()
            prompt = f"{name}: "
            secret = False
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            prompt = str(item.get("prompt") or item.get("description") or name or "value").strip()
            if not prompt.endswith(":"):
                prompt += ":"
            prompt += " "
            secret = bool(item.get("secret"))
        else:
            continue
        if not name or inputs.get(name):
            continue
        inputs[name] = getpass.getpass(prompt) if secret else input(prompt)
        changed = True
    return changed


def _print_connect_result(result: dict, presentation: str) -> None:
    message = str(result.get("message") or "").strip()
    if message:
        _print(message)
    actions = result.get("actions") or []
    if isinstance(actions, list):
        _print_connect_actions(actions, presentation)
    diagnostics = result.get("diagnostics")
    if isinstance(diagnostics, dict) and diagnostics:
        _print("Diagnostics:")
        for key, value in diagnostics.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            _print(f"  {key}: {value}")


def _refresh_platform_devices_table(platform: str) -> dict | None:
    try:
        return downloader.refresh_platform_devices_file(platform)
    except Exception as exc:
        _print(f"Platform device table refresh failed for {platform}: {exc}")
        return None


def _catalog_platform_ids() -> set[str]:
    return {
        str(entry.get("id")).strip()
        for entry in _load_catalog()
        if isinstance(entry, dict) and str(entry.get("id", "")).strip()
    }


def _migrate_state():
    config.ensure_state_migrated(_catalog_platform_ids() or None)


def _ensure_platform_connector_ready(platform: str) -> dict:
    connector_dir = ASSETS_DIR / platform / "connector"
    client_path = connector_dir / "client.py"
    devices_file = connector_dir / f"{platform}_devices.json"
    local_ver = config.read_local_connector_version(platform)
    remote_ver = downloader.get_platform_latest_version(platform)

    should_install = (
        not client_path.exists()
        or not devices_file.exists()
        or not local_ver
        or local_ver != remote_ver
    )

    if should_install:
        previous = local_ver or "missing"
        new_ver = downloader.download_platform(platform)
        config.set_platform_version(platform, new_ver)
        config.add_connected_iot_platform(platform)
        return {
            "status": "installed" if previous == "missing" else "updated",
            "previous_version": previous,
            "version": new_ver,
            "path": str(client_path),
        }

    config.add_connected_iot_platform(platform)
    return {
        "status": "ready",
        "previous_version": local_ver,
        "version": local_ver,
        "path": str(client_path),
    }


def _platforms_for_listing(explicit_platform: str | None) -> list[str]:
    if explicit_platform:
        return [_resolve_platform_or_exit(explicit_platform)]

    _migrate_state()
    platforms = config.get_connected_iot_platforms()
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
    refresh_result = _refresh_catalog()
    _migrate_state()
    catalog = _load_catalog()
    if not catalog:
        _print("No platform catalog is available locally. Run `entroflow update` and try again.")
        return 1

    if refresh_result.get("status") == "error":
        _print(f"Platform catalog refresh failed: {refresh_result['error']}")
        _print("Using the local cached catalog instead.")
        _print("")

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
        cached_manifest = _load_cached_platform_doc_manifest(platform_id)
        doc_ready = doc_path.exists()
        status = "connected" if platform_id in connected else "available"
        remote_manifest = None
        remote_error = None

        try:
            remote_manifest = downloader.get_platform_guide_latest(platform_id)
        except Exception as exc:
            remote_error = str(exc)

        _print(f"- {platform_id} ({display_name})")
        _print(f"  status     : {status}")
        if description:
            _print(f"  summary    : {description}")
        if aliases:
            _print(f"  aliases    : {', '.join(aliases)}")
        _print(f"  connect    : entroflow connect {platform_id}")
        if doc_ready and cached_manifest and remote_manifest and cached_manifest.get("version") == remote_manifest.get("version"):
            locale_name = cached_manifest.get("selected_locale") or "unknown"
            _print(f"  doc        : cached locally ({doc_path}, v{cached_manifest.get('version')}, {locale_name})")
        elif doc_ready and cached_manifest:
            latest_version = remote_manifest.get("version") if isinstance(remote_manifest, dict) else None
            if latest_version and cached_manifest.get("version") != latest_version:
                _print(f"  doc        : cached locally ({doc_path}, v{cached_manifest.get('version')}; latest on server: v{latest_version})")
            else:
                _print(f"  doc        : cached locally ({doc_path})")
        elif doc_ready:
            _print(f"  doc        : cached locally ({doc_path})")
        elif remote_manifest:
            missing_docs = True
            locales = ", ".join(remote_manifest.get("locales", [])) or "unknown locales"
            _print(f"  doc        : available on server (v{remote_manifest.get('version')}, {locales})")
            _print("  next       : guide will be synced automatically during `entroflow connect`")
        elif remote_error:
            missing_docs = True
            _print(f"  doc        : guide check failed ({remote_error})")
        else:
            missing_docs = True
            _print("  doc        : not published on server yet")
            _print("  note       : platform connection can continue, but no local guide will be synced")
        _print("")

    if missing_docs:
        _print("Platform guides are now synced on demand from the server.")
        _print("If a guide is not published yet, `entroflow connect <platform>` will continue without a local guide.")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    _refresh_catalog()
    _migrate_state()
    platform = _resolve_platform_or_exit(args.platform)

    _print(f"Connecting platform: {platform}")

    try:
        guide_sync = downloader.download_platform_guide(platform)
        if guide_sync:
            guide_status = guide_sync.get("status")
            guide_version = guide_sync.get("version")
            guide_locale = guide_sync.get("locale")
            guide_path = guide_sync.get("path")
            if guide_status == "cached":
                _print(f"Platform guide already up to date: {guide_path} (v{guide_version}, {guide_locale})")
            else:
                _print(f"Synced platform guide: {guide_path} (v{guide_version}, {guide_locale})")
        else:
            _print("No published platform guide is available on the server yet. Continuing without a local guide.")
    except Exception as exc:
        _print(f"Platform guide sync skipped: {exc}")

    connector_result = _ensure_platform_connector_ready(platform)
    status = connector_result["status"]
    version = connector_result["version"]
    if status == "installed":
        _print(f"Installed platform connector {platform} (v{version})")
    elif status == "updated":
        _print(
            f"Updated platform connector {platform} "
            f"({connector_result['previous_version']} -> v{version})"
        )
    else:
        _print(f"Platform connector already installed and up to date: {platform} (v{version})")

    refreshed = _refresh_platform_devices_table(platform)
    if refreshed:
        _print(f"Refreshed device support table: {refreshed['count']} models -> {refreshed['path']}")

    connector = loader.load_connector(platform)
    inputs = _collect_connect_inputs(args)
    presentation = _connect_presentation(args)

    while True:
        context = _build_connect_context(platform, args, inputs)
        result = _connector_connect(connector, context)
        status = _connect_status(result)

        if status in {"connected", "ok"}:
            config.add_connected_iot_platform(platform)
            _print_connect_result(result, presentation)
            if not result.get("message"):
                _print(f"Platform '{platform}' connected successfully.")
            return 0

        if status == "requires_input":
            _print_connect_result(result, presentation)
            required_inputs = result.get("required_inputs") or []
            if isinstance(required_inputs, list):
                _print_required_inputs(required_inputs)
                if _prompt_required_inputs(required_inputs, inputs, args):
                    continue
            _print("Provide the required values with `--input key=value` or a platform-specific documented shortcut such as `--url` / `--token`.")
            return 1

        if status in {"requires_environment", "failed", "error", "expired"}:
            _print_connect_result(result, presentation)
            if not result.get("message"):
                _print(f"Platform '{platform}' connection failed ({status}).")
            return 1

        if status in {"pending", "requires_user_action", "waiting"}:
            _print("")
            _print_connect_result(result, presentation)
            expires_in = result.get("expires_in")
            if expires_in:
                _print(f"Connection session expires in {expires_in} seconds.")
            _print("")

            if _should_wait_for_login_prompt(args):
                input("Press Enter after completing the requested connection action...")
            else:
                _print("Non-interactive mode detected; waiting for the connector to report connection status...")

            session_id = str(result.get("session_id") or "").strip()
            if not session_id:
                raise RuntimeError(f"Connector returned '{status}' without session_id: {result}")

            while True:
                poll = _connector_poll_connect(connector, session_id, _build_connect_context(platform, args, inputs))
                poll_status = _connect_status(poll)
                if poll_status in {"connected", "ok"}:
                    config.add_connected_iot_platform(platform)
                    _print_connect_result(poll, presentation)
                    if not poll.get("message"):
                        _print(f"Platform '{platform}' connected successfully.")
                    return 0
                if poll_status in {"pending", "waiting", "requires_user_action"}:
                    wait_message = str(poll.get("message") or "").strip()
                    _print(wait_message or "Still waiting for the connector to report connection status...")
                    time.sleep(3)
                    continue
                if poll_status == "requires_input":
                    _print_connect_result(poll, presentation)
                    required_inputs = poll.get("required_inputs") or []
                    if isinstance(required_inputs, list):
                        _print_required_inputs(required_inputs)
                    return 1
                if poll_status in {"requires_environment", "failed", "error", "expired"}:
                    _print_connect_result(poll, presentation)
                    return 1
                raise RuntimeError(f"Unsupported connector poll status '{poll_status}' for platform '{platform}': {poll}")

        raise RuntimeError(f"Unsupported connector status '{status}' for platform '{platform}': {result}")


def cmd_list_devices(args: argparse.Namespace) -> int:
    _refresh_catalog()
    _migrate_state()
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
    refresh_result = _refresh_catalog()
    _migrate_state()
    _print(check_updates())
    _print("")
    _print(update_server())
    _print("")
    if refresh_result.get("status") == "synced":
        _print(f"Platform catalog refreshed ({refresh_result.get('count', 0)} platforms).")
    else:
        _print(f"Platform catalog refresh failed: {refresh_result.get('error', 'unknown error')}")
        if _load_catalog():
            _print("Continuing with the local cached catalog.")

    local_platforms = managed_iot_platforms()
    if local_platforms:
        _print("")
        _print("Platform device tables:")
        for platform in local_platforms:
            refreshed = _refresh_platform_devices_table(platform)
            if refreshed:
                _print(f"  {platform}: refreshed {refreshed['count']} models -> {refreshed['path']}")

    connected_platforms = config.get_connected_iot_platforms()
    if connected_platforms:
        _print("")
        _print("Platform guides:")
        for result in downloader.refresh_platform_guides(connected_platforms):
            status = result.get("status")
            platform = result.get("platform_id", "?")
            if status in {"cached", "synced"}:
                _print(
                    f"  {platform}: {status} v{result.get('version')} ({result.get('locale')}) -> {result.get('path')}"
                )
            elif status == "missing":
                _print(f"  {platform}: guide not published on server")
            else:
                _print(f"  {platform}: guide refresh failed ({result.get('error')})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="entroflow", description="EntroFlow setup and runtime control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    platforms_parser = subparsers.add_parser("list-platforms", help="List currently supported platforms")
    platforms_parser.add_argument("query", nargs="?", help="Optional keyword to filter by id, name, or alias")
    platforms_parser.set_defaults(func=cmd_list_platforms)

    connect_parser = subparsers.add_parser("connect", help="Connect a platform and complete authentication")
    connect_parser.add_argument("platform", help="Platform id or alias, e.g. mihome")
    connect_parser.add_argument("--no-prompt", action="store_true", help="Do not wait for a manual Enter prompt before polling login status")
    connect_parser.add_argument("--url", help="Connection input shortcut for platforms that require a URL")
    connect_parser.add_argument("--token", help="Connection input shortcut for platforms that require an access token")
    connect_parser.add_argument("--input", action="append", default=[], help="Additional connector input in key=value format")
    connect_parser.add_argument(
        "--presentation",
        choices=("auto", "url", "file", "none"),
        default="auto",
        help="How the CLI should present connector-provided connection actions.",
    )
    connect_parser.add_argument("--timeout", type=int, default=600, help="Connection session timeout in seconds")
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
