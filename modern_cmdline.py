import requests
import sys

URL = "https://gist.githubusercontent.com/hugsy/b950d6c98596c02cc129ead22dfb648c/raw/9e8942f52bf6ac03f27e300ae1e283ff58175a57/info.json"

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
        return """<img title="Windows only" src="https://blog.thesysadmins.co.uk/wp-content/uploads/Windows-8-logo-100x100.jpg"height=23px> """

    with open("./rust_cmdline_tools_compat.md", "w") as f:
        f.write("| Unix tool | Rust version | Windows compatible? | Has prebuild? |\n")
        f.write("|:---:|:---:|:---:|:---:|\n")

        for tool in js:
            print(tool)
            is_windows_compatible = "✔" if tool["windows-compatible"] else "❌"
            prebuild_list = []
            for os in tool["prebuild"]:
                if os == "win": prebuild_list.append(win_logo())
                if os == "lin": prebuild_list.append(lin_logo())
                if os == "mac": prebuild_list.append(mac_logo())

            f.write(f'| `{tool["unix-tool"]}` | [`{tool["modern-tool"]}`]({tool["url"]}) | {is_windows_compatible} | {" ".join(prebuild_list)} |\n')


if sys.argv[1] == "--generate":
    create_table()
