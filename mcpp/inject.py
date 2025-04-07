import ast
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

global _verbose
_verbose = False

NETWORK_PACKAGES = {
    # fmt:off
    'requests', 'http', 'httpx', 'aiohttp', 'urllib3', 'http.client', 'urllib.request', 'socket',
    'socketserver', 'websockets', 'tornado', 'flask', 'django', 'fastapi', 'grpc', 'pika', 'kafka',
    'boto3', 'azure', 'google.cloud', 'firebase', 'pymongo', 'mysql', 'psycopg2', 'fastmcp', 'mcp',
    # fmt:on
}


def log(msg):
    """Log a message to stderr if verbose mode is enabled"""
    if _verbose:
        sys.stderr.write(f"{msg}\n")


@dataclass
class PackageInfo:
    """Information about an installed package"""

    name: str
    version: str
    location: Optional[str] = None
    is_network: bool = False


@dataclass
class InjectionPoint:
    """Represents a potential code injection point"""

    path: Path
    rel_path: str
    priority: int
    func_count: int
    import_count: int


@dataclass
class PackageManager:
    """Represents a package manager configuration"""

    name: str
    directory: Optional[str] = None


class ImportFinder(ast.NodeVisitor):
    """AST visitor to find imports in Python code"""

    def __init__(self):
        self.imports = set()
        self.from_imports = {}

    def visit_Import(self, node):
        for name in node.names:
            self.imports.add(name.name.split('.')[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            pkg = node.module.split('.')[0]
            if pkg not in self.from_imports:
                self.from_imports[pkg] = []
            for name in node.names:
                self.from_imports[pkg].append(name.name)
            self.imports.add(pkg)
        self.generic_visit(node)


def get_python_path(pm: PackageManager) -> str:
    """Get the full path of the Python interpreter"""
    try:
        # TODO: use default shell instead of bash? $SHELL?
        if pm.name == 'uv':
            if pm.directory:
                cmd = ['bash', '-c', f'source "{pm.directory}/.venv/bin/activate" && python -c "import sys; print(sys.executable)" && deactivate']
        elif pm.directory:
            cmd = ['bash', '-c', f'source "{pm.directory}/.venv/bin/activate" && {pm.name} -c "import sys; print(sys.executable)" && deactivate']
        else:
            cmd = [pm.name, "-c", "import sys; print(sys.executable)"]

        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        log(f"Error getting Python path: {e}")
        return "python"


def get_package_manager(command: str, args: List[str]) -> PackageManager:
    """Determine the package manager from command and args"""
    known_pkg_managers = ["pip", "poetry", "conda", "pipenv"]

    if command == "uv":
        for i, arg in enumerate(args):
            if arg == "--directory" and i + 1 < len(args):
                return PackageManager(name="uv", directory=args[i + 1])
        return PackageManager(name="uv")
    elif command in known_pkg_managers:
        # TODO: Handle other package managers
        return PackageManager(name=command)
    elif command == "python" or command.startswith("python3"):
        # If command is python, look for pip in args
        for i, arg in enumerate(args):
            if arg == "-m" and i + 1 < len(args) and args[i + 1] in known_pkg_managers:
                return PackageManager(name=args[i + 1])
        return PackageManager(name="pip")  # Default to pip for python command
    else:
        return PackageManager(name="pip")  # Fallback to pip


def get_installed_packages(python_path: str, pm: PackageManager) -> Dict[str, PackageInfo]:
    """Get information about all installed packages"""

    cmd = []

    if pm.name == 'uv':
        cmd = ['uv', 'pip', 'list', '--format=json']
        if pm.directory:
            cmd = ['sh', '-c', f'source "{pm.directory}/.venv/bin/activate" && uv pip list --format=json && deactivate']
    else:
        cmd = [python_path, "-m", "pip", "list", "--format=json"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        packages = json.loads(result.stdout)
        return {
            pkg["name"].lower(): PackageInfo(
                name=pkg["name"], version=pkg["version"], is_network=pkg["name"].lower() in NETWORK_PACKAGES or any(pkg["name"].lower().startswith(f"{p}.") for p in NETWORK_PACKAGES)
            )
            for pkg in packages
        }
    except subprocess.CalledProcessError as e:
        log(f"Failed to retrieve package information: {e}")
        return {}


@lru_cache(maxsize=128)
def get_package_path(python_path: str, package_name: str) -> Optional[str]:
    """Get the filesystem location of a package"""
    try:
        cmd = f"import sys,{package_name}; print({package_name}.__file__ if hasattr({package_name}, '__file__') else None, file=sys.stderr)"
        result = subprocess.run([python_path, "-c", cmd], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stderr.strip() != "None":
            path = Path(result.stderr.strip())
            return str(path.parent if path.is_file() else path)
        return None
    except Exception as e:
        log(f"Error locating {package_name}: {e}")
        return None


def analyze_script(script_path: str) -> Tuple[Set[str], Dict]:
    """Extract imported packages from a Python script"""
    try:
        path = Path(script_path)
        if path.stat().st_size > 10 * 1024 * 1024:
            log(f"File too large to analyze: {script_path}")
            return set(), {}

        code = path.read_text()
        tree = ast.parse(code)
        finder = ImportFinder()
        finder.visit(tree)
        return finder.imports, finder.from_imports
    except Exception as e:
        log(f"Error analyzing {script_path}: {e}")
        return set(), {}


def find_injection_points(pkg_path: str) -> List[InjectionPoint]:
    """Find suitable injection points in a package"""
    points = []
    pkg_dir = Path(pkg_path)

    if not pkg_dir.exists() or not pkg_dir.is_dir():
        return points

    for py_file in pkg_dir.glob("**/*.py"):
        rel_path = py_file.relative_to(pkg_dir)
        priority = 0

        if py_file.name == "__init__.py":
            priority += 50

        try:
            code = py_file.read_text()

            if re.search(r"(http|socket|connect|request|response|url)", code, re.IGNORECASE):
                priority += 30

            if 'subprocess' in code:
                priority += 40

            tree = ast.parse(code)
            funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            func_count = len(funcs)

            signatures = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("__")]
            sig_count = len(signatures)

            if func_count > 0:
                priority += 10 * (1 + math.log(func_count, 2))
                density = func_count / max(sig_count, 1)

                if density > 0.1:
                    priority += 15
                elif density < 0.01:
                    priority -= 10

            module_name = py_file.stem
            import_count = 0

            for f in pkg_dir.glob("**/*.py"):
                if f != py_file:
                    try:
                        other_code = f.read_text()
                        if f"import {module_name}" in other_code or f"from {module_name}" in other_code:
                            import_count += 1
                    except:
                        pass

            priority += min(import_count * 5, 20)

            points.append(InjectionPoint(path=py_file, rel_path=str(rel_path), priority=priority, func_count=func_count, import_count=import_count))

        except Exception as e:
            log(f"Error analyzing {py_file}: {e}")

    return sorted(points, key=lambda p: p.priority, reverse=True)


def inject_code(file_path: str, payload: str) -> bool:
    """Inject monitoring code into a Python file"""
    try:
        content = Path(file_path).read_text()

        if "# Injected monitoring code - Do not modify" in content:
            return False

        if payload in content:
            return False
        tree = ast.parse(content)
        last_import_line = 0
        lines = content.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and hasattr(node, 'lineno'):
                line_idx = node.lineno - 1
                if line_idx < len(lines) and not lines[line_idx].startswith((' ', '\t')):
                    last_import_line = max(last_import_line, node.lineno)

        if last_import_line > 0:
            # After the last import
            new_content = '\n'.join(lines[:last_import_line]) + '\n\n' + payload + '\n\n' + '\n'.join(lines[last_import_line:])
        elif tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
            # After the docstring if present
            docstring_end = 0
            for i, line in enumerate(lines):
                if i >= tree.body[0].lineno - 1 and ('"""' in line or "'''" in line):
                    docstring_end = i + 1
                    break

            if docstring_end > 0:
                new_content = '\n'.join(lines[:docstring_end]) + '\n\n' + payload + '\n\n' + '\n'.join(lines[docstring_end:])
            else:
                new_content = payload + '\n\n' + content
        else:
            new_content = payload + '\n\n' + content
        log(f"{file_path = }")

        Path(f"{file_path}.bak").write_text(content)
        Path(file_path).write_text(new_content)
        return True

    except Exception as e:
        log(f"Injection failed for {file_path}: {e}")
        return False


def inject_modules(command: str, args: List[str], script_path: str, payload: str, dry_run: bool = False) -> bool:
    """Inject monitoring code into network packages used by a script"""
    pm = get_package_manager(command, args)

    python_path = get_python_path(pm)
    packages = get_installed_packages(python_path, pm)
    if pm and pm.directory:
        script_path = os.path.join(pm.directory, script_path)

    imports, _ = analyze_script(script_path)
    network_pkgs = []
    for pkg_name in imports:
        pkg_lower = pkg_name.lower()
        if pkg_lower in packages and packages[pkg_lower].is_network:
            pkg_info = packages[pkg_lower]
            if not pkg_info.location:
                pkg_info.location = get_package_path(python_path, pkg_name)
            if pkg_info.location:
                network_pkgs.append(pkg_info)

    if not network_pkgs:
        log("No network packages to inject")
        return False

    success = False

    for pkg in network_pkgs:
        log(f"Package: {pkg.name} v{pkg.version}")
        inject_points = find_injection_points(pkg.location)

        if not inject_points:
            log(f"No suitable injection points in {pkg.name}")
            continue

        target = inject_points[0]
        log(f"Target: {target.rel_path} (score: {target.priority})")

        if not dry_run:
            pkg_success = inject_code(str(target.path), payload)
            if pkg_success:
                log(f"Successfully injected into {pkg.name}")
                success = True
            else:
                log(f"Failed to inject into {pkg.name}")

    return success
