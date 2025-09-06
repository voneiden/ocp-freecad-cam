import argparse

import requests

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A tool to retrieve FreeCAD AppImage from release"
    )
    parser.add_argument("--release", help="Specify FreeCAD version or 'latest'")
    parser.add_argument("--pyver", required=True, help="Asset pyver (ex. py311)")
    parser.add_argument("--arch", required=True, help="Asset architecture")
    parser.add_argument("--suffix", required=True, help="File suffix of the asset")

    args = parser.parse_args()

    if args.release == "latest":
        release = requests.get(
            "https://api.github.com/repos/FreeCAD/FreeCAD/releases/latest"
        ).json()
    else:
        response = requests.get(
            f"https://api.github.com/repos/FreeCAD/FreeCAD/releases/tags/{args.release}"
        )
        if response.status_code != 200:
            raise RuntimeError(f"Tag {args.version} not found")
        release = response.json()

    assets = requests.get(release["assets_url"]).json()
    for asset in assets:
        name = asset["name"]
        if name.endswith(args.suffix) and args.pyver in name and args.arch in name:
            print(asset["browser_download_url"])
            break
    else:
        raise RuntimeError(
            f"Did not find asset matching arch {args.arch} and pyver {args.pyver}"
        )
