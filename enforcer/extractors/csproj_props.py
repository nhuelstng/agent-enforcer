"""CsprojProps: extracts MSBuild property names and PackageReference ids from a .csproj/.props file."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class CsprojProps:
    """Extracts MSBuild property names and PackageReference ids from a .csproj/.props file.

    Emits every ``<PropertyGroup>`` child element name (e.g. ``Nullable``,
    ``TargetFramework``, ``TreatWarningsAsErrors``) and every ``PackageReference``
    id from its ``Include``/``Update`` attribute. Namespaces (classic non-SDK
    projects) are stripped. Malformed XML yields an empty set. Pair with
    ``KeySetSyncMatcher`` to require a set of properties/packages or to keep a
    central ``Directory.Packages.props`` in sync with project files."""

    def extract(self, raw: str) -> set[str]:
        """Parse .csproj/.props XML and return property names and PackageReference ids."""
        keys: set[str] = set()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return keys
        for element in root.iter():
            keys.update(self._keys_for(element))
        return keys

    def _keys_for(self, element) -> set[str]:
        """Return the key(s) an element contributes: property names or a package id."""
        tag = self._local_name(element.tag)
        if tag == "PropertyGroup":
            return {self._local_name(child.tag) for child in element}
        if tag == "PackageReference":
            package = element.get("Include") or element.get("Update")
            return {package} if package else set()
        return set()

    @staticmethod
    def _local_name(tag: str) -> str:
        """Strip any ``{namespace}`` prefix from an XML tag."""
        return tag.rsplit("}", 1)[-1]
