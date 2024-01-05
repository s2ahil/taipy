import os
import sys
from typing import Dict

BASE_PATH = "./tools/packages"


def update_setup_requirements(package: str, versions: Dict) -> None:
    _path = os.path.join(BASE_PATH, package, "setup.requirements.txt")
    lines = []
    with open(_path, mode="r") as req:
        for line in req:
            if v := versions.get(line.strip()):
                line = f"{line.strip()} @ https://github.com/Avaiga/taipy/releases/download/{v}/{v}.tar.gz\n"
            lines.append(line)

    with open(_path, 'w') as file:
        file.writelines(lines)


if __name__ == "__main__":
    package = sys.argv[1]
    versions = {
        "taipy-config": sys.argv[2],
        "taipy-core": sys.argv[3],
        "taipy-gui": sys.argv[4],
        "taipy-rest": sys.argv[5],
        "taipy-templates": sys.argv[6],
    }
    packages = [
        "taipy",
        "taipy-config",
        "taipy-core",
        "taipy-rest",
        "taipy-gui",
        "taipy-templates",
    ]

    update_setup_requirements(package, versions)
