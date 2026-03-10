from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import shutil


PLY_SCALAR_TYPES = {
    "char": ("b", 1),
    "uchar": ("B", 1),
    "int8": ("b", 1),
    "uint8": ("B", 1),
    "short": ("h", 2),
    "ushort": ("H", 2),
    "int16": ("h", 2),
    "uint16": ("H", 2),
    "int": ("i", 4),
    "uint": ("I", 4),
    "int32": ("i", 4),
    "uint32": ("I", 4),
    "float": ("f", 4),
    "float32": ("f", 4),
    "double": ("d", 8),
    "float64": ("d", 8),
}


@dataclass(frozen=True)
class PlyElement:
    name: str
    count: int
    properties: tuple[str, ...]


@dataclass(frozen=True)
class ParsedPlyHeader:
    lines: tuple[str, ...]
    line_ending: str
    data_offset: int
    format_name: str
    elements: tuple[PlyElement, ...]

    @property
    def vertex_element(self) -> PlyElement:
        for element in self.elements:
            if element.name == "vertex":
                return element
        raise ValueError("PLY file does not define a vertex element.")


@dataclass(frozen=True)
class DecimatedPly:
    source_path: Path
    output_path: Path
    original_vertices: int
    decimated_vertices: int
    ratio: float


def decimate_ply(source_path: Path, output_path: Path, ratio: float) -> DecimatedPly:
    if ratio <= 0 or ratio >= 1:
        raise ValueError("Decimation ratio must be between 0 and 1.")

    with source_path.open("rb") as handle:
        header = _read_header(handle)
        vertex_element = header.vertex_element
        original_vertices = vertex_element.count
        decimated_vertices = max(1, math.floor(original_vertices * ratio))

        if original_vertices <= 1:
            shutil.copy2(source_path, output_path)
            return DecimatedPly(
                source_path=source_path,
                output_path=output_path,
                original_vertices=original_vertices,
                decimated_vertices=original_vertices,
                ratio=ratio,
            )

        if decimated_vertices >= original_vertices:
            decimated_vertices = original_vertices - 1

        kept_indices = _build_kept_indices(original_vertices, decimated_vertices)

        if header.format_name == "ascii":
            vertex_lines = [handle.readline() for _ in range(original_vertices)]
            tail = handle.read()
            kept_vertices = [vertex_lines[index] for index in kept_indices]
        else:
            vertex_size = _vertex_record_size(header.vertex_element, header.format_name)
            vertex_blob = handle.read(original_vertices * vertex_size)
            if len(vertex_blob) != original_vertices * vertex_size:
                raise ValueError("PLY vertex data is truncated.")
            tail = handle.read()
            kept_vertices = [
                vertex_blob[index * vertex_size:(index + 1) * vertex_size]
                for index in kept_indices
            ]

    rebuilt_header = _rewrite_vertex_count(header, len(kept_vertices))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        handle.write(rebuilt_header)
        for vertex in kept_vertices:
            handle.write(vertex)
        handle.write(tail)

    return DecimatedPly(
        source_path=source_path,
        output_path=output_path,
        original_vertices=original_vertices,
        decimated_vertices=len(kept_vertices),
        ratio=ratio,
    )


def _read_header(handle) -> ParsedPlyHeader:
    lines: list[str] = []
    line_ending = "\n"
    while True:
        line = handle.readline()
        if not line:
            raise ValueError("PLY header is truncated.")
        decoded = line.decode("ascii")
        if line.endswith(b"\r\n"):
            line_ending = "\r\n"
        stripped = decoded.rstrip("\r\n")
        lines.append(stripped)
        if stripped == "end_header":
            break

    if not lines or lines[0] != "ply":
        raise ValueError("File is not a valid PLY document.")

    format_name = ""
    elements: list[PlyElement] = []
    current_name: str | None = None
    current_count = 0
    current_properties: list[str] = []

    for line in lines[1:]:
        if not line:
            continue
        parts = line.split()
        keyword = parts[0]
        if keyword == "format":
            if len(parts) < 2:
                raise ValueError("PLY format declaration is invalid.")
            format_name = parts[1]
            if format_name not in {"ascii", "binary_little_endian", "binary_big_endian"}:
                raise ValueError(f"Unsupported PLY format: {format_name}")
        elif keyword == "element":
            if current_name is not None:
                elements.append(PlyElement(current_name, current_count, tuple(current_properties)))
            if len(parts) != 3:
                raise ValueError("PLY element declaration is invalid.")
            current_name = parts[1]
            current_count = int(parts[2])
            current_properties = []
        elif keyword == "property":
            if current_name is None:
                raise ValueError("PLY property is declared before any element.")
            if len(parts) >= 2 and parts[1] == "list":
                raise ValueError("PLY list properties are not supported for decimation.")
            if len(parts) != 3:
                raise ValueError("PLY property declaration is invalid.")
            current_properties.append(parts[1])
        elif keyword == "end_header":
            break

    if current_name is not None:
        elements.append(PlyElement(current_name, current_count, tuple(current_properties)))

    if not format_name:
        raise ValueError("PLY header is missing a format declaration.")

    face_elements = [element for element in elements if element.name == "face" and element.count > 0]
    if face_elements:
        raise ValueError("PLY decimation does not support face elements.")

    return ParsedPlyHeader(
        lines=tuple(lines),
        line_ending=line_ending,
        data_offset=handle.tell(),
        format_name=format_name,
        elements=tuple(elements),
    )


def _rewrite_vertex_count(header: ParsedPlyHeader, vertex_count: int) -> bytes:
    rewritten_lines = []
    for line in header.lines:
        if line.startswith("element vertex "):
            rewritten_lines.append(f"element vertex {vertex_count}")
        else:
            rewritten_lines.append(line)
    return header.line_ending.join(rewritten_lines).encode("ascii") + header.line_ending.encode("ascii")


def _vertex_record_size(element: PlyElement, format_name: str) -> int:
    if format_name == "ascii":
        raise ValueError("ASCII PLY records do not use a fixed record size.")

    size = 0
    for property_type in element.properties:
        try:
            _, type_size = PLY_SCALAR_TYPES[property_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported PLY property type: {property_type}") from exc
        size += type_size
    return size


def _build_kept_indices(vertex_count: int, target_count: int) -> list[int]:
    if target_count >= vertex_count:
        return list(range(vertex_count))

    kept: list[int] = []
    previous = -1
    for index in range(target_count):
        candidate = int(index * vertex_count / target_count)
        if candidate <= previous:
            candidate = previous + 1
        if candidate >= vertex_count:
            candidate = vertex_count - 1
        kept.append(candidate)
        previous = candidate
    return kept
