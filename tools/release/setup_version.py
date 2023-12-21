import sys
import json
import os
from dataclasses import dataclass, asdict
import re


@dataclass
class Version:
    major: str
    minor: str
    patch: str
    ext: str

    def bump_ext_version(self) -> None:
        if not self.ext:
            return
        reg = re.compile(r'[0-9]+$')
        num = reg.findall(self.ext)[0]

        self.ext = self.ext.replace(num, str(int(num) + 1))

    def validate_suffix(self, suffix="dev"):
        if suffix not in self.ext:
            raise Exception(f"Version does not contain suffix {suffix}")

    def __str__(self) -> str:
        """returns a string representation of a version"""
        version_str = f"{self.major}.{self.minor}.{self.patch}"
        if self.ext:
            version_str = f"{version_str}.{self.ext}"
        return version_str


def __load_version_from_path(base_path: str) -> Version:
    """Load version.json file from base path."""
    with open(os.path.join(base_path, "version.json")) as version_file:
        data = json.load(version_file)
        return Version(**data)


def __write_version_to_path(base_path: str, version: Version) -> None:
    with open(os.path.join(base_path, "version.json"), "w") as version_file:
        json.dump(asdict(version), version_file)


def extract_version(base_path: str) -> Version:
    """
    Load version.json file from base path and return the version string.
    """
    return __load_version_from_path(base_path)


def bump_dev_version(base_path: str) -> None:
    """
    Load version.json file, bump its extension and write it to the base_path.
    """
    version = __load_version_from_path(base_path)
    version.bump_ext_version()
    __write_version_to_path(base_path, version)


def __setup_dev_version(version: Version) -> None:
    version.validate_suffix()
    print(f"VERSION={version}")
    __write_version_to_path(_base_path, version)
    print(f"NEW_VERSION={version}")


def __setup_prod_version(version: Version, target_version: str, branch_name: str) -> None:
    if str(version) != target_version:
        raise ValueError(f"Current version={version} does not match target version={target_version}")

    if target_branch_name := f"release/{version.major}.{version.minor}" != branch_name:
        raise ValueError(f"Branch name mismatch branch={branch_name} does not match target branch name={target_branch_name}")


if __name__ == "__main__":
    _base_path = sys.argv[1]
    _environment = sys.argv[2]

    _version = extract_version(_base_path)
    if _environment == "dev":
        __setup_dev_version(_version)

    if _environment == "prod":
        __setup_prod_version(_version, sys.argv[3], sys.argv[4])


