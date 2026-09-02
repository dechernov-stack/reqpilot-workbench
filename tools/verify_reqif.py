#!/usr/bin/env python3
"""Verify structural and referential integrity of a native StrictDoc ReqIF file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lxml import etree  # type: ignore[import-untyped]


def local_name(element: etree._Element) -> str:
    """Return an XML element's namespace-independent local name."""

    return etree.QName(element).localname


def verify(path: Path) -> dict[str, Any]:
    """Return a concise verification result or raise on a broken reference."""

    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    root = etree.parse(str(path), parser).getroot()
    identified = [element for element in root.iter() if element.get("IDENTIFIER")]
    identifiers = [str(element.get("IDENTIFIER")) for element in identified]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("ReqIF contains duplicate IDENTIFIER values.")

    references = [
        (local_name(element), (element.text or "").strip())
        for element in root.iter()
        if local_name(element).endswith("-REF") and (element.text or "").strip()
    ]
    known = set(identifiers)
    unresolved = sorted({value for _kind, value in references if value not in known})
    if unresolved:
        raise ValueError(f"ReqIF has unresolved references: {unresolved[:10]}")

    specifications = [element for element in root.iter() if local_name(element) == "SPECIFICATION"]
    hierarchies = [element for element in root.iter() if local_name(element) == "SPEC-HIERARCHY"]
    objects = [element for element in root.iter() if local_name(element) == "SPEC-OBJECT"]
    hierarchy_object_refs = [
        (element.text or "").strip()
        for hierarchy in hierarchies
        for element in hierarchy.iter()
        if local_name(element) == "SPEC-OBJECT-REF"
    ]
    if not specifications:
        raise ValueError("ReqIF contains no SPECIFICATION.")
    if not hierarchies:
        raise ValueError("ReqIF contains no SPEC-HIERARCHY.")
    if not hierarchy_object_refs:
        raise ValueError("ReqIF hierarchy contains no SPEC-OBJECT references.")

    return {
        "path": path.as_posix(),
        "root": local_name(root),
        "specifications": len(specifications),
        "spec_hierarchies": len(hierarchies),
        "spec_objects": len(objects),
        "identified_elements": len(identifiers),
        "references": len(references),
        "unresolved_references": 0,
        "size": path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reqif", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.reqif.resolve(strict=True)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
