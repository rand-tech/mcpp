from base64 import urlsafe_b64encode as b64, urlsafe_b64decode as b64d
import json

# TODO: MODIFY THIS!
configs = {
    "name": "ClaudeDesktop",
    "operation": 'add_entry',
    "payload": {
        'key': 'Search',
        'command': 'python',
        'args': ['path_to_script.py', 'arg1', 'arg2'],
    },
}


def crc32(data: bytes):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


def generate(configs):
    # name:operation:b64(payload)
    # e.g. `ClaudeDesktop:add_entry:b64(json payload)`
    ENV_KEY = 'MCPP'
    encoded = b64(json.dumps(configs['payload']).encode()).decode()
    crc = crc32(encoded.encode())
    line = f"{configs['name']}:{configs['operation']}:{encoded}:{crc:8X}"
    print(
        f'''
export I_KNOW_WHAT_I_AM_DOING_AND_THIS_IS_FOR_EDUCATIONAL_PURPOSES_ONLY=1
export {ENV_KEY}={line!r}
    '''.strip()
    )
    return line


def decode(cfg: str):
    try:
        name, operation, payload, crc = cfg.split(':')
        if int(crc, 16) != crc32(payload.encode()):
            raise ValueError(f"CRC check failed: {crc} != {crc32(payload.encode())}")
        payload = json.loads(b64d(payload))
        print()
        print(f'{name=}, {operation=} \n{payload}')
        return payload
    except Exception as e:
        print(f"Error decoding: {e}")
        return None


if __name__ == "__main__":
    l = generate(configs)
    decode(l)
