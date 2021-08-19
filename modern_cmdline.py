import requests
import sys, os

URL = "https://gist.githubusercontent.com/hugsy/b950d6c98596c02cc129ead22dfb648c/raw/487c78174b38a595c7e39a22a9a9a58e9690be77/info.json"

def create_table():
    h = requests.get(URL)
    if h.status_code != requests.codes.ok:
        print("Error:", h.status_code)
        sys.exit(1)

    js = h.json()

    def lin_logo():
        return """<img title="Linux only" src=https://www.ximea.com/support/attachments/download/1160/linux_logo_small.png height=23px>"""

    def mac_logo():
        return """<img title="OSX only" src=https://www.alessioatzeni.com/mac-osx-lion-css3/res/img/apple-logo-login.png height=23px>"""

    def win_logo():
        return """<img title="Windows only" src="https://blog.thesysadmins.co.uk/wp-content/uploads/Windows-8-logo-100x100.jpg" height=23px> """

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


if sys.argv[1] == "--generate":
    create_table()
