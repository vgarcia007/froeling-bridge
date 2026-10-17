"""Start the native service from one protected configuration file."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

from .configure import validate_settings
from .standalone import serve_standalone


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    validate_settings(config)
    state = Path(config.get("state_dir", "/var/lib/froeling-bridge"))
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    history_path = state / "history-connection.json"
    profile_path = state / "reply-profile.json"
    from .host_test import atomic_json

    if config.get("history"):
        atomic_json(history_path, config["history"])
    atomic_json(profile_path, config.get("reply_profile", {}))
    return serve_standalone(
        SimpleNamespace(
            mode="standalone",
            state_dir=str(state),
            device=config["device"],
            host=config.get("host", "0.0.0.0"),
            port=config.get("port", 8000),
            interval=config.get("interval", 60),
            history_config=str(history_path) if config.get("history") else None,
            reply_profile=str(profile_path),
            write_validation=config.get("write_validation"),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
