import sys
import os
import json
import argparse

import requests

GIST_ROOT_URL = "https://gist.githubusercontent.com/hugsy/b950d6c98596c02cc129ead22dfb648c"
GIST_URL = f"{GIST_ROOT_URL}/raw/487c78174b38a595c7e39a22a9a9a58e9690be77/info.json"


def collect_json_data() -> list[dict]:
    # if local
    if os.access("./info.json", os.R_OK):
        return list(json.load(open("./info.json", "r")))

    # else grab online
    h : requests.Response = requests.get(GIST_URL)
    if h.status_code != requests.codes.ok:
        print(f"Critical error: {h.status_code}")
        sys.exit(1)
    return h.json()


def lookup_tool_by_name(name: str, is_unix_tool : bool = True, is_modern_tool : bool = False) -> dict:
    js = collect_json_data()
    for tool in js:
        if is_unix_tool and tool["unix-tool"] == name: return tool
        if is_modern_tool and tool["modern-tool"] == name: return tool
    raise Exception(f"Tool {name} not found")


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--generate-table", help="Update the Markdown summary table of tools available", action="store_true")
    parser.add_argument("-v", "--verbose", action="count", dest="verbose", help="Increase verbosity")
    args = parser.parse_args()

    if args.generate_table:
        create_table()
        exit(0)
