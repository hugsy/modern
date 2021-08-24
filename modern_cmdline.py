"""
This script will automatically download and install modern versions of the popular
Unix tools (`ls`, `cat`, `wc`, etc.) and create aliases for them to be added directly
to your shell startup file (bashrc, zshrc, Microsoft.PowerShell_profile.ps1, etc.).

It also allows to create a markdown table with the tool names, along with their Windows
compatibility and prebuild status.
"""
import argparse
import glob
import json
import os
import pathlib
import platform
import pprint
import requests
import shutil
import sys
import tempfile
import zipfile


DEFAULT_SCRIPT_NAME = os.path.basename(__file__)
DEFAULT_OUTPUT_FILE = "./README.md"
GIST_ROOT_URL = "https://gist.githubusercontent.com/hugsy/b950d6c98596c02cc129ead22dfb648c"
GIST_URL = f"{GIST_ROOT_URL}/raw/487c78174b38a595c7e39a22a9a9a58e9690be77/info.json"
GITHUB_API = "https://api.github.com"
DEBUG = False


class MissingPrebuildException(Exception): pass
class UnsupportedOperatingSystemException(Exception): pass


def dbg(x: str):
    if DEBUG:
        print(f"[*] {x}")
    return


def download_json_data(url: str) -> list[dict]:
    h : requests.Response = requests.get(url)
    if h.status_code != requests.codes.ok:
        print(f"Critical error while fetching '{url}': {h.status_code}")
        sys.exit(1)
    return h.json()


def collect_json_data() -> list[dict]:
    # if local
    if os.access("./info.json", os.R_OK):
        return list(json.load(open("./info.json", "r")))
    # else grab online
    return download_json_data(GIST_URL)


def lookup_tool_by_name(name: str, is_unix_tool : bool, is_modern_tool : bool) -> list[dict]:
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
            prebuild_list = []
            for o in tool["prebuild"]:
                if o == "win": prebuild_list.append(win_logo())
                if o == "lin": prebuild_list.append(lin_logo())
                if o == "mac": prebuild_list.append(mac_logo())

            f.write(f'| `{tool["unix-tool"]}` | [`{tool["modern-tool"]}`]({tool["url"]}) | {is_windows_compatible} | {" ".join(prebuild_list)} |\n')
    return


def download_latest_release(tool: dict) -> pathlib.Path:
    __os = platform.system().lower()
    __arch = platform.architecture()[0]
    possible_oses = []
    if __os == "windows": possible_oses = ("windows", "msvc")
    possible_arches = []
    if __arch == "64bit": possible_arches = ("amd64", "x86_64")

    if (__os == "windows" and "win" not in tool["prebuild"]) \
        or (__os == "linux" and "lin" not in tool["prebuild"]) \
        or (__os == "macos" and "mac" not in tool["prebuild"]):
            raise MissingPrebuildException(f"Tool {tool['unix-tool']} is not available for {__os}")

    gh_tool_author, gh_tool_name = tool["url"].replace("https://github.com/", "").split("/")

    # download the data
    release_js = download_json_data(f"{GITHUB_API}/repos/{gh_tool_author}/{gh_tool_name}/releases")

    # find the right asset in the latest release
    latest_release = release_js[0]
    assets = latest_release["assets"]

    match = None
    for asset in assets:
        for o in possible_oses:
            for a in possible_arches:
                dbg(f"trying {a}/{o} for {asset['name']}")
                if o in asset["name"].lower() and a in asset["name"].lower():
                    match = asset
                    dbg(f"match found: '{match['name'].lower()}'")
                    break
            if match: break
        if match: break

    if not match:
        raise Exception(f"No asset found for {__os} {__arch}")

    # download the asset in tempdir
    h = requests.get(match["browser_download_url"])
    tmpdir = tempfile.mkdtemp()
    fname = pathlib.Path( tmpdir ) / asset['name']
    with open(str(fname.absolute()), "wb") as fd:
        fd.write(h.content)

    ## if archive, extract it
    if asset["content_type"] == "application/zip":
        with zipfile.ZipFile(str(fname.absolute()), 'r') as zfd:
            zfd.extractall(tmpdir)

    # check if binary has expected mime type for the current OS (PE, ELF, Mach-O)
    if __os == "windows": expected_binary_glob_path = os.sep.join([tmpdir, "*",  tool["modern-tool"] + ".exe"])
    else: expected_binary_glob_path = __os.sep.join([tmpdir, "*",  (tool["modern-tool"])])

    for fname in glob.iglob(expected_binary_glob_path):
        fpath = pathlib.Path(fname)
        if fpath.exists():
            return fpath

    raise Exception(f"The binary cannot be found at '{tmpdir}'")


def install(tool: dict) -> int:
    is_windows = platform.system() == "Windows"
    # 0. check if we have a writable directory
    home = os.path.expanduser("~")
    writable_directory_candidates = [pathlib.Path(home) / "bin",]
    if is_windows:
        writable_directory_candidates += [pathlib.Path(home) / "AppData" / "Local" / "bin",]
    else:
        writable_directory_candidates += [pathlib.Path(home) / ".local" / "bin",]

    output_directory = None
    for candidate in writable_directory_candidates:
        if candidate.is_dir(): # todo: check if writable too
            output_directory = candidate.absolute()
            break

    if not output_directory:
        raise Exception("No writable directory found")


    # 1. check & download the latest release for the current OS
    try:
        tmpbin = download_latest_release(tool)
    except MissingPrebuildException as e:
        print(f"Exception raised: {str(e)}")
        print(f"Trying running with `-c` instead...")
        raise e

    # 2. copy the file to output directory
    shutil.copy(tmpbin, output_directory)

    # 3. print the aliasing command for the tool for the current OS
    if is_windows:
        alias_file = pathlib.Path(home) / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
        install_path = output_directory.absolute() / (tool['modern-tool']+".exe")
        line_to_add = f"New-Alias -Name {tool['unix-tool']} -Value '{install_path}' -Option ReadOnly # added by {DEFAULT_SCRIPT_NAME}"
    else:
        alias_file = pathlib.Path(home) / ".aliases"
        install_path = output_directory.absolute() / tool['modern-tool']
        line_to_add = f"alias {tool['unix-tool']}='{install_path}' # added by {DEFAULT_SCRIPT_NAME}"

    if alias_file.is_file():
        if line_to_add not in open(str(alias_file.absolute()), "r").readlines():
            with open(str(alias_file.absolute()), "a") as f:
                f.write(f"{line_to_add} {os.linesep}")
            print(f"Alias added to `{alias_file}`")
        else:
            print(f"Alias to `{tool['modern-tool']}` already in `{alias_file}`")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("-v", "--verbose", action="count", dest="verbose", help="Increase verbosity")

    generate_group = parser.add_argument_group("generate table")
    generate_group.add_argument("--generate-table", help="Update the Markdown summary table of tools available", action="store_true")

    install_group = parser.add_argument_group("install table")
    install_group.add_argument("-u", "--search-unix", help="Search for a unix tool", type=str, metavar="NAME")
    install_group.add_argument("-r", "--search-rust", help="Search for a rust tool", type=str, metavar="NAME")
    install_group.add_argument("-s", "--switch", help="Download prebuild and install a legacy unix tool with a rust tool", type=str, metavar="RUST_TOOL_NAME")
    install_group.add_argument("-S", "--switch-all", help="Download prebuild and install all legacy unix tool with rust tools", action="store_true")
    install_group.add_argument("-c", "--compile", help="Download, compile and install a legacy unix tool with a rust tool", type=str, metavar="RUST_TOOL_NAME")
    install_group.add_argument("-C", "--compile-all", help="Download, compile and install all legacy unix tool with rust tools", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        DEBUG = True

    if args.generate_table:
        create_table()
        exit(0)

    if args.search_unix:
        pprint.pprint(lookup_unix_tool_by_name(args.search_unix))
        exit(0)

    if args.search_rust:
        res = lookup_rust_tool_by_name(args.search_rust)
        if len(res) != 1:
            print("/!\\ Found multiple matches /!\\")
        pprint.pprint(res)
        exit(0)

    if args.switch:
        res = lookup_rust_tool_by_name(args.switch)
        if len(res) != 1:
            print("/!\\ Found multiple matches, cannot proceed /!\\")
            exit(1)
        exit(install(res[0]))

    if args.switch_all:
        js = collect_json_data()
        retcode = 0
        for entry in js:
            res = lookup_rust_tool_by_name(entry["modern-tool"])
            if len(res) != 1:
                print("/!\\ Found multiple matches, cannot proceed /!\\")
                continue

            tool = res[0]
            if install(tool) != 0:
                print(f"/!\\ Error installing tool '{tool}' /!\\")
                retcode += 1
        exit(retcode)

    if args.compile:
        raise NotImplementedError("Compiling is not yet implemented")

    if args.compile_all:
        raise NotImplementedError("Compiling is not yet implemented")
