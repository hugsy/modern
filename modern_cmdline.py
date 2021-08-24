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

GIST_ROOT_URL = "https://gist.githubusercontent.com/hugsy/b950d6c98596c02cc129ead22dfb648c"
GIST_URL = f"{GIST_ROOT_URL}/raw/487c78174b38a595c7e39a22a9a9a58e9690be77/info.json"
GITHUB_API = "https://api.github.com"


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


def create_table():
    def lin_logo():
        return """<img title="Linux only" src=https://www.ximea.com/support/attachments/download/1160/linux_logo_small.png height=23px>"""

    def mac_logo():
        return """<img title="OSX only" src=https://www.alessioatzeni.com/mac-osx-lion-css3/res/img/apple-logo-login.png height=23px>"""

    def win_logo():
        return """<img title="Windows only" src="https://blog.thesysadmins.co.uk/wp-content/uploads/Windows-8-logo-100x100.jpg" height=23px> """

    js = collect_json_data()
    with open("./rust_cmdline_tools_compat.md", "w", encoding="utf-8") as f:
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


def download_latest_release(tool: dict) -> pathlib.Path:
    gh_tool_author, gh_tool_name = tool["url"].replace("https://github.com/", "").split("/")

    # download the data
    release_js = download_json_data(f"{GITHUB_API}/repos/{gh_tool_author}/{gh_tool_name}/releases")

    # find the right asset in the latest release
    latest_release = release_js[0]
    assets = latest_release["assets"]
    __os = platform.system().lower()
    possible_oses = []
    if __os == "windows": possible_oses = ("windows", "msvc")

    arch = platform.architecture()[0]
    possible_arches = []
    if arch == "64bit": possible_arches = ("amd64", "x86_64")

    match = None
    for asset in assets:
        for o in possible_oses:
            for a in possible_arches:
                if o in asset["name"].lower() and a in asset["name"].lower():
                    match = asset
                    break
            if match: break
        if match: break

    if not match:
        raise Exception(f"No asset found for {__os} {arch}")

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
    tmpbin = download_latest_release(tool)

    # 2. copy the file to output directory
    shutil.copy(tmpbin, output_directory)

    # 3. print the aliasing command for the tool for the current OS
    print("------8<------")
    if is_windows:
        install_path = output_directory.absolute() / tool['modern-tool']+".exe"
        print(f"New-Alias -Name {tool['unix-tool']} -Value '{install_path}' -Option ReadOnly")
    else:
        install_path = output_directory.absolute() / tool['modern-tool']
        print(f"alias {tool['unix-tool']}='{install_path}'")
    print("------>8------")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("-v", "--verbose", action="count", dest="verbose", help="Increase verbosity")

    generate_group = parser.add_argument_group("generate table")
    generate_group.add_argument("--generate-table", help="Update the Markdown summary table of tools available", action="store_true")

    install_group = parser.add_argument_group("install table")
    install_group.add_argument("-u", "--search-unix", help="Search for a unix tool", type=str, metavar="NAME")
    install_group.add_argument("-r", "--search-rust", help="Search for a rust tool", type=str, metavar="NAME")
    install_group.add_argument("-s", "--switch", help="Download and install a legacy unix tool with a rust tool", type=str, metavar="RUST_TOOL_NAME")
    install_group.add_argument("-S", "--switch-all", help="Download and install all legacy unix tool with rust tools", action="store_true")

    args = parser.parse_args()

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
        for entry in js:
            res = lookup_rust_tool_by_name(entry["modern-tool"])
            if len(res) != 1:
                print("/!\\ Found multiple matches, cannot proceed /!\\")
                break

            tool = res[0]
            if install(tool) != 0:
                print(f"/!\\ Error installing tool '{tool}' /!\\")
                break
