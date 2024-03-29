"""
This script will automatically download and install modern versions of the popular
Unix tools (`ls`, `cat`, `wc`, etc.) and create aliases for them to be added directly
to your shell startup file (bashrc, zshrc, Microsoft.PowerShell_profile.ps1, etc.).

It also allows to create a markdown table with the tool names, along with their Windows
compatibility and prebuild status.

TODO:
 - progress bar
 - use rich
"""
import argparse
import functools
import json
import logging
import os
import pathlib
import platform
import pprint
import shutil
import sys
import tempfile
import zipfile

import magic
import requests


DEFAULT_SCRIPT_NAME = pathlib.Path(__file__)
DEFAULT_SCRIPT_DIR  = DEFAULT_SCRIPT_NAME.parent
DEFAULT_OUTPUT_FILE = "./README.md"
GIST_ROOT_URL       = "https://gist.githubusercontent.com/hugsy/b950d6c98596c02cc129ead22dfb648c"
GIST_URL            = f"{GIST_ROOT_URL}/raw/487c78174b38a595c7e39a22a9a9a58e9690be77/info.json"
GITHUB_API_URL      = "https://api.github.com"
DEBUG               = False
HOME                = pathlib.Path( os.path.expanduser("~") )

logger = logging.getLogger( __file__ )
logging_handler = logging.StreamHandler()
logging_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%d/%m/%Y-%H:%M:%S"))
logger.addHandler(logging_handler)

class MissingPrebuildException(Exception):
    pass


class UnsupportedOperatingSystemException(Exception):
    pass


class UnsupportedPlatformException(Exception):
    pass


def download_json_data(url: str) -> list[dict]:
    h : requests.Response = requests.get(url)
    if h.status_code != requests.codes.ok:
        print(f"Critical error while fetching '{url}': {h.status_code}")
        sys.exit(1)
    return h.json()


@functools.lru_cache(maxsize=None)
def collect_json_data() -> list[dict]:
    info_json = DEFAULT_SCRIPT_DIR / "info.json"
    # if local
    if info_json.exists() and info_json.is_file():
        return list(json.load(open(str(info_json.absolute()), "r")))
    # otherwise grab online
    return download_json_data(GIST_URL)

@functools.lru_cache(maxsize=None)
def lookup_tool_by_name(name: str, is_unix_tool : bool, is_modern_tool : bool) -> list[dict]:
    logger.debug(f"Searching for {'unix' if is_unix_tool else 'rust'} tool '{name}'")
    js = collect_json_data()
    matches = []
    for tool in js:
        if is_unix_tool and tool["unix-tool"] == name: matches.append(tool)
        if is_modern_tool and tool["modern-tool"] == name: matches.append(tool)
    if len(matches) == 0:
        raise Exception(f"Tool {name} not found")
    return matches


def lookup_unix_tool_by_name(name: str) -> list[dict]:
    return lookup_tool_by_name(name, is_unix_tool = True, is_modern_tool = False)


def lookup_rust_tool_by_name(name: str) -> list[dict]:
    return lookup_tool_by_name(name, is_unix_tool = False, is_modern_tool = True)


def create_table(output_file: str = DEFAULT_OUTPUT_FILE):
    def lin_logo():
        return """<img title="Linux only" src=https://www.ximea.com/support/attachments/download/1160/linux_logo_small.png height=23px>"""

    def mac_logo():
        return """<img title="OSX only" src=https://www.alessioatzeni.com/mac-osx-lion-css3/res/img/apple-logo-login.png height=23px>"""

    def win_logo():
        return """<img title="Windows only" src="https://blog.thesysadmins.co.uk/wp-content/uploads/Windows-8-logo-100x100.jpg" height=23px> """

    js = collect_json_data()
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"| Unix tool | Rust version | Windows compatible? | Has prebuild? |\n")
        f.write(f"|:---:|:---:|:---:|:---:|\n")

        for tool in js:
            is_windows_compatible = "✔" if tool["windows-compatible"] else "❌"
            is_preferred = "⭐" if tool["preferred"] else ""
            prebuild_list = []
            for o in tool["prebuild"]:
                if o == "win": prebuild_list.append(win_logo())
                if o == "lin": prebuild_list.append(lin_logo())
                if o == "mac": prebuild_list.append(mac_logo())

            f.write(f'| `{tool["unix-tool"]}` {is_preferred} | [`{tool["modern-tool"]}`]({tool["url"]}) | {is_windows_compatible} | {" ".join(prebuild_list)} |\n')
    return


def download_latest_release(tool: dict) -> pathlib.Path:
    __os = platform.system().lower()
    __arch = platform.architecture()[0]
    possible_oses = []
    if __os == "windows":
        possible_oses = ("windows", "msvc", "win")
    elif __os == "linux":
        possible_oses = ("linux", "lin", "lnx")
    elif __os == "darwin":
        possible_oses = ("mac", "osx", "darwin")
    else:
        raise UnsupportedOperatingSystemException(f"Unsupported operating system: {__os}")

    possible_arches = []
    if __arch == "64bit":
        possible_arches = ("amd64", "x86_64")
    elif __arch == "32bit":
        possible_arches = ("x86", "i686")
    else:
        raise UnsupportedPlatformException(f"Unsupported architecture: {__arch}")

    if (__os == "windows" and "win" not in tool["prebuild"]) \
        or (__os == "linux" and "lin" not in tool["prebuild"]) \
        or (__os == "macos" and "mac" not in tool["prebuild"]):
            raise MissingPrebuildException(f"Tool '{tool['unix-tool']}' is not available for {__os}")

    gh_tool_author, gh_tool_name = tool["url"].replace("https://github.com/", "").split("/")

    # download the data
    release_js = download_json_data(f"{GITHUB_API_URL}/repos/{gh_tool_author}/{gh_tool_name}/releases")

    if len(release_js) < 1:
        raise MissingPrebuildException(f"Missing release for '{tool['unix-tool']}' on {__os} {__arch} ")

    # find the right asset in the latest release
    latest_release = release_js[0]
    assets = latest_release["assets"]

    match = None
    for asset in assets:
        for o in possible_oses:
            for a in possible_arches:
                logger.debug(f"trying {a}/{o} for {asset['name']}")
                if o in asset["name"].lower() and a in asset["name"].lower():
                    if o == "win":
                        if "darwin" not in asset["name"].lower(): # hack
                            match = asset
                            logger.debug(f"match found: '{match['name'].lower()}'")
                            break
                    else:
                        match = asset
                        logger.debug(f"match found: '{match['name'].lower()}'")
                        break

            if match: break
        if match: break

    if not match:
        raise MissingPrebuildException(f"No asset found for '{gh_tool_name}' on {__os} {__arch}")

    # download the asset in tempdir
    h = requests.get(match["browser_download_url"])
    tmpdir = pathlib.Path( tempfile.mkdtemp() )
    fname = pathlib.Path( tmpdir ) / asset['name']
    with open(str(fname.absolute()), "wb") as fd:
        fd.write(h.content)

    ## if archive, extract it
    logger.debug(f"Checking '{fname}' for archive formats...")
    mime_type = magic.from_file(str(fname.absolute()), mime=True)
    extract_dir = (tmpdir / "extracted").absolute()
    if mime_type == "application/zip":
        logger.debug(f"Extracting zip '{fname.absolute()}' to '{extract_dir}'")
        with zipfile.ZipFile(fname.absolute(), 'r') as zfd:
            zfd.extractall(str(extract_dir))
    elif mime_type == "application/gzip" and fname.name.endswith(".tar.gz"):
        logger.debug(f"Extracting tar.gz '{fname.absolute()}' to '{extract_dir}'")
        os.makedirs(str(extract_dir), exist_ok=True)
        os.system(f"tar -vxzf {fname.absolute()} -C {extract_dir}")
    else:
        logger.info(f"No archive format found for '{fname.absolute()}' ({mime_type=})")

    # check if binary has expected mime type for the current OS (PE, ELF, Mach-O)
    file_pattern = tool.get('modern-tool-bin', None) or tool.get('modern-tool')
    file_pattern += "*"
    if __os == "windows":
        file_pattern += ".exe"

    logger.debug(f"Looking for '{file_pattern}' in '{tmpdir.absolute()}'...")

    for curdir, _, files in os.walk(tmpdir.absolute()):
        for fname in files:
            fpath = pathlib.Path(curdir) / fname
            if fpath.exists() and fpath.is_file() and fpath.match(file_pattern):
                logger.info(f"Found {fpath}")
                return fpath

    raise Exception(f"The binary cannot be found at '{tmpdir}'")


def install(tool: dict, is_dry_run: bool = False) -> int:
    is_windows = platform.system() == "Windows"
    # 0. check if we have a writable directory
    writable_directory_candidates = [HOME / "bin",]
    if is_windows:
        writable_directory_candidates += [HOME / "AppData" / "Local" / "bin",]
    else:
        writable_directory_candidates += [HOME / ".local" / "bin",]

    output_directory = None
    for candidate in writable_directory_candidates:
        if candidate.is_dir(): # todo: check if writable too
            output_directory = candidate.absolute()
            break

    if not output_directory:
        raise Exception("No writable directory found")

    logger.debug(f"Installing '{tool}' to '{output_directory}'")

    # 1. check & download the latest release for the current OS
    try:
        tmpbin = download_latest_release(tool)
    except MissingPrebuildException as e:
        logger.error(f"Exception raised: '{str(e)}'\n Trying running with `-c` instead...")
        raise e

    # 2. copy the file to output directory
    if not is_dry_run:
        shutil.copy(tmpbin, output_directory)

    tool_name = tool.get('modern-tool-bin', None) or tool.get('modern-tool')

    # 3. print the aliasing command for the tool for the current OS
    if is_windows:
        alias_file = HOME / "PowershellAliases.ps1"
        install_path = output_directory.absolute() / (tool_name+".exe")
        line_to_add = f"New-Alias -Force -Name {tool['unix-tool']} -Value '{install_path}' -Option ReadOnly,AllScope # added by {DEFAULT_SCRIPT_NAME.name}"
    else:
        alias_file = HOME / ".aliases"
        install_path = output_directory.absolute() / tool_name
        line_to_add = f"alias {tool['unix-tool']}='{install_path}' # added by {DEFAULT_SCRIPT_NAME.name}"

    alias_already_exists = False
    if alias_file.exists():
        if line_to_add in [line.strip() for line in open(str(alias_file.absolute()), "r").readlines()]:
            alias_already_exists = True
            logger.info(f"Alias for '{tool['unix-tool']}' already in `{alias_file}`")

    logger.debug(f"Adding `{line_to_add}` in '{alias_file.absolute()}'")
    if not is_dry_run and not alias_already_exists:
        with open(str(alias_file.absolute()), "a") as f:
            f.write(f"{line_to_add} {os.linesep}")

        logger.info(f"Alias '{tool['unix-tool']}' -> '{tool_name}' added to `{alias_file}`")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Modernize your command line with portable tools")
    parser.add_argument("-v", "--verbose", action="count", dest="verbose", help="Increase verbosity")

    generate_group = parser.add_argument_group("generate table")
    generate_group.add_argument("--generate-table", help="Update the Markdown summary table of tools available", action="store_true")

    install_group = parser.add_argument_group("install table")
    install_group.add_argument("-u", "--search-unix", help="Search for a unix tool", type=str, metavar="NAME")
    install_group.add_argument("-r", "--search-rust", help="Search for a rust tool", type=str, metavar="NAME")
    install_group.add_argument("-i", "--install", help="Download prebuild and install a legacy unix tool with a rust tool", type=str, metavar="RUST_TOOL_NAME")
    install_group.add_argument("-I", "--install-all", help="Download prebuild and install all legacy unix tool with rust tools", action="store_true")
    install_group.add_argument("-c", "--compile", help="Download, compile and install a legacy unix tool with a rust tool", type=str, metavar="RUST_TOOL_NAME")
    install_group.add_argument("-C", "--compile-all", help="Download, compile and install all legacy unix tool with rust tools", action="store_true")
    install_group.add_argument("--dry-run", help="If true, do not install the downloaded/compiled file(s)", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        DEBUG = True
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    else:
        logger.setLevel(logging.INFO)

    if args.generate_table:
        logger.debug("Re-generating tool table")
        create_table()
        exit(0)

    if args.search_unix:
        res = lookup_unix_tool_by_name(args.search_unix)
        logger.info(f"Found {len(res)} result{'s' if len(res) > 1 else ''}")
        if logger.isEnabledFor(logging.DEBUG):
            pprint.pprint(res)
        for tool in res:
            if any([ platform.system().lower().startswith(x) for x in tool['prebuild']]):
                logger.info(f"Prebuild of '{tool['modern-tool']}' available for {platform.system()}")
        exit(0)

    if args.search_rust:
        res = lookup_rust_tool_by_name(args.search_rust)
        if len(res) != 1:
            logger.warn("/!\\ Found multiple matches /!\\")
        pprint.pprint(res)
        exit(0)

    if args.install:
        res = lookup_rust_tool_by_name(args.install)
        if len(res) != 1:
            logger.warning("Found multiple matches, cannot proceed")
            exit(1)

        tool = res[0]

        try:
            retcode = install(tool, args.dry_run)
        except MissingPrebuildException as e:
            logger.warning(f"Missing prebuild for '{tool}', skipping")
            retcode = 0
        except Exception as e:
            logger.error(str(e))
            retcode = -1

        exit(retcode)

    if args.install_all:
        logger.debug(f"Collecting tool data...")
        js = collect_json_data()
        logger.info(f"Collected {len(js)} tools...")
        retcode = 0
        for entry in js:
            # is there multiple unix tools for this rust tool?
            res = lookup_unix_tool_by_name(entry["unix-tool"])
            if len(res) != 1 and not entry["preferred"]:
                logger.warning("Found multiple matches, skipping for preferred...")
                continue

            # if here, either 1 match for unix tool or it is the preferred
            res = lookup_rust_tool_by_name(entry["modern-tool"])
            tool = res[0]

            try:
                if install(tool, args.dry_run) != 0:
                    logger.error(f"Error installing tool '{tool}'")
                    retcode += 1
            except MissingPrebuildException as e:
                logger.warning(f"Missing prebuild for '{tool}', skipping")

        logger.debug(f"Done, exiting with code {retcode}")
        exit(retcode)

    if args.compile:
        raise NotImplementedError("Compiling is not yet implemented")

    if args.compile_all:
        raise NotImplementedError("Compiling is not yet implemented")
