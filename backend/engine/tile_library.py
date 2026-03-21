from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image


DIRECTIONS = ("N", "E", "S", "W")
HALF_PORTS = ("Nw", "Ne", "En", "Es", "Se", "Sw", "Ws", "Wn")
OPPOSITE_DIRECTION = {"N": "S", "E": "W", "S": "N", "W": "E"}
OPPOSITE_PORT = {
    "N": "S",
    "E": "W",
    "S": "N",
    "W": "E",
    "Nw": "Sw",
    "Ne": "Se",
    "En": "Wn",
    "Es": "Ws",
    "Se": "Ne",
    "Sw": "Nw",
    "Ws": "Es",
    "Wn": "En",
}
STEP_BY_DIRECTION = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
STEP_BY_PORT = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
    "Nw": (0, -1),
    "Ne": (0, -1),
    "En": (1, 0),
    "Es": (1, 0),
    "Se": (0, 1),
    "Sw": (0, 1),
    "Ws": (-1, 0),
    "Wn": (-1, 0),
}


@dataclass(frozen=True)
class FeatureDefinition:
    id: str
    kind: str
    edges: Tuple[str, ...] = ()
    center: bool = False
    score_bonus: int = 0
    adjacent_cities: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TileDefinition:
    id: str
    name: str
    image_name: str
    edges: Dict[str, str]
    features: Tuple[FeatureDefinition, ...]
    count: int = 3


def rotate_direction(direction: str, turns: int) -> str:
    if direction in DIRECTIONS:
        index = DIRECTIONS.index(direction)
        return DIRECTIONS[(index + turns) % 4]
    index = HALF_PORTS.index(direction)
    return HALF_PORTS[(index + 2 * turns) % len(HALF_PORTS)]


def rotate_edges(edges: Dict[str, str], turns: int) -> Dict[str, str]:
    return {rotate_direction(direction, turns): value for direction, value in edges.items()}


def rotate_feature(feature: FeatureDefinition, turns: int) -> FeatureDefinition:
    return FeatureDefinition(
        id=feature.id,
        kind=feature.kind,
        edges=tuple(rotate_direction(direction, turns) for direction in feature.edges),
        center=feature.center,
        score_bonus=feature.score_bonus,
        adjacent_cities=feature.adjacent_cities,
    )


def rotated_features(tile: TileDefinition, turns: int) -> List[FeatureDefinition]:
    return [rotate_feature(feature, turns) for feature in tile.features]


ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets" / "img"
FEATURE_MAP_ROOT = ASSET_ROOT / "feature_maps"

COLOR_BY_KIND = {
    "field": (0, 255, 0),
    "road": (200, 150, 100),
    "city": (120, 80, 50),
    "monastery": (255, 165, 0),
}
KIND_PRIORITY = {"city": 0, "road": 1, "field": 2, "monastery": 3}
MIN_COMPONENT_SIZE = 100
EDGE_MARGIN = 3


def _nearest_kind(rgb: Tuple[int, int, int]) -> str:
    return min(COLOR_BY_KIND.items(), key=lambda item: sum((channel - ref) ** 2 for channel, ref in zip(rgb, item[1])))[0]


def _extract_topology(feature_map_name: str, coa_bonus: bool) -> tuple[Dict[str, str], Tuple[FeatureDefinition, ...]]:
    image = Image.open(FEATURE_MAP_ROOT / feature_map_name).convert("RGB")
    width, height = image.size
    pixels = image.load()
    kinds = [[_nearest_kind(pixels[x, y]) for x in range(width)] for y in range(height)]
    visited = [[False] * width for _ in range(height)]
    raw_components: List[dict] = []

    for y in range(height):
        for x in range(width):
            if visited[y][x]:
                continue
            kind = kinds[y][x]
            queue = deque([(x, y)])
            visited[y][x] = True
            points: List[Tuple[int, int]] = []
            min_x = max_x = x
            min_y = max_y = y
            while queue:
                px, py = queue.popleft()
                points.append((px, py))
                min_x = min(min_x, px)
                max_x = max(max_x, px)
                min_y = min(min_y, py)
                max_y = max(max_y, py)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = px + dx, py + dy
                    if 0 <= nx < width and 0 <= ny < height and not visited[ny][nx] and kinds[ny][nx] == kind:
                        visited[ny][nx] = True
                        queue.append((nx, ny))
            raw_components.append(
                {
                    "kind": kind,
                    "points": points,
                    "size": len(points),
                    "bbox": (min_x, min_y, max_x, max_y),
                }
            )

    significant = [component for component in raw_components if component["size"] >= MIN_COMPONENT_SIZE]
    road_components = [component for component in significant if component["kind"] == "road"]
    if len(road_components) > 1:
        merged_points: List[Tuple[int, int]] = []
        remaining = [component for component in significant if component["kind"] != "road"]
        for component in road_components:
            merged_points.extend(component["points"])
        merged_component = {
            "kind": "road",
            "points": merged_points,
            "size": len(merged_points),
            "bbox": (
                min(point[0] for point in merged_points),
                min(point[1] for point in merged_points),
                max(point[0] for point in merged_points),
                max(point[1] for point in merged_points),
            ),
        }
        significant = remaining + [merged_component]
    significant.sort(key=lambda component: (KIND_PRIORITY[component["kind"]], component["bbox"][1], component["bbox"][0]))

    feature_id_by_component: Dict[int, str] = {}
    counters = defaultdict(int)
    for index, component in enumerate(significant):
        counters[component["kind"]] += 1
        feature_id_by_component[index] = f"{component['kind']}_{counters[component['kind']]}"

    component_index_by_point = [[-1] * width for _ in range(height)]
    for index, component in enumerate(significant):
        for x, y in component["points"]:
            component_index_by_point[y][x] = index

    adjacent_cities_by_feature: Dict[str, set[str]] = defaultdict(set)
    for index, component in enumerate(significant):
        if component["kind"] != "field":
            continue
        feature_id = feature_id_by_component[index]
        for x, y in component["points"]:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                neighbor_index = component_index_by_point[ny][nx]
                if neighbor_index == -1:
                    continue
                neighbor = significant[neighbor_index]
                if neighbor["kind"] == "city":
                    adjacent_cities_by_feature[feature_id].add(feature_id_by_component[neighbor_index])

    port_regions = {
        "Nw": lambda x, y: y < EDGE_MARGIN and x < width // 2,
        "Ne": lambda x, y: y < EDGE_MARGIN and x >= width // 2,
        "En": lambda x, y: x >= width - EDGE_MARGIN and y < height // 2,
        "Es": lambda x, y: x >= width - EDGE_MARGIN and y >= height // 2,
        "Se": lambda x, y: y >= height - EDGE_MARGIN and x >= width // 2,
        "Sw": lambda x, y: y >= height - EDGE_MARGIN and x < width // 2,
        "Ws": lambda x, y: x < EDGE_MARGIN and y >= height // 2,
        "Wn": lambda x, y: x < EDGE_MARGIN and y < height // 2,
    }
    side_band_x = range(width // 3, width - width // 3)
    side_band_y = range(height // 3, height - height // 3)
    side_regions = {
        "N": lambda x, y: y < EDGE_MARGIN and x in side_band_x,
        "E": lambda x, y: x >= width - EDGE_MARGIN and y in side_band_y,
        "S": lambda x, y: y >= height - EDGE_MARGIN and x in side_band_x,
        "W": lambda x, y: x < EDGE_MARGIN and y in side_band_y,
    }

    features: List[FeatureDefinition] = []
    city_feature_ids: List[str] = []
    for index, component in enumerate(significant):
        feature_id = feature_id_by_component[index]
        ports: List[str] = []
        if component["kind"] == "field":
            for port, matcher in port_regions.items():
                if any(matcher(x, y) for x, y in component["points"]):
                    ports.append(port)
            if not ports and not adjacent_cities_by_feature.get(feature_id):
                continue
        elif component["kind"] in {"road", "city"}:
            for direction, matcher in side_regions.items():
                if any(matcher(x, y) for x, y in component["points"]):
                    ports.append(direction)
            if not ports:
                continue
        feature = FeatureDefinition(
            id=feature_id,
            kind=component["kind"],
            edges=tuple(ports),
            center=component["kind"] == "monastery",
            adjacent_cities=tuple(sorted(adjacent_cities_by_feature.get(feature_id, set()))),
        )
        features.append(feature)
        if component["kind"] == "city":
            city_feature_ids.append(feature_id)

    if coa_bonus and len(city_feature_ids) == 1:
        boosted_city = city_feature_ids[0]
        features = [
            FeatureDefinition(
                id=feature.id,
                kind=feature.kind,
                edges=feature.edges,
                center=feature.center,
                score_bonus=1 if feature.id == boosted_city else feature.score_bonus,
                adjacent_cities=feature.adjacent_cities,
            )
            for feature in features
        ]

    edges: Dict[str, str] = {}
    for direction, matcher in side_regions.items():
        if any(
            component["kind"] == "city" and any(matcher(x, y) for x, y in component["points"])
            for component in significant
        ):
            edges[direction] = "city"
        elif any(
            component["kind"] == "road" and any(matcher(x, y) for x, y in component["points"])
            for component in significant
        ):
            edges[direction] = "road"
        else:
            edges[direction] = "field"

    features.sort(key=lambda feature: (KIND_PRIORITY[feature.kind], feature.id))
    return edges, tuple(features)


TILE_SPECS = [
    {"id": "monastery", "name": "Monastery", "image": "monastery.png", "feature_map": "_feature_map_monastery.png", "count": 4},
    {"id": "monastery_road", "name": "Monastery With Road", "image": "monastery_with_road.png", "feature_map": "_feature_map_monastery_with_road.png", "count": 2},
    {"id": "straight", "name": "Straight", "image": "straight.png", "feature_map": "_feature_map_straight.png", "count": 8},
    {"id": "curve", "name": "Curve", "image": "curve.png", "feature_map": "_feature_map_curve.png", "count": 9},
    {"id": "triple_road", "name": "Triple Road", "image": "triple_road.png", "feature_map": "_feature_map_triple_road.png", "count": 4},
    {"id": "quadruple_road", "name": "Quadruple Road", "image": "quadruple_road.png", "feature_map": "_feature_map_quadruple_road.png", "count": 1},
    {"id": "triangle", "name": "Triangle", "image": "triangle.png", "feature_map": "_feature_map_triangle.png", "count": 3},
    {"id": "triangle_coa", "name": "Triangle With COA", "image": "triangle_with_coa.png", "feature_map": "_feature_map_triangle_with_coa.png", "count": 2, "coa_bonus": True},
    {"id": "triangle_road", "name": "Triangle With Road", "image": "triangle_with_road.png", "feature_map": "_feature_map_triangle_with_road.png", "count": 3},
    {"id": "triangle_road_coa", "name": "Triangle With Road With COA", "image": "triangle_with_road_with_coa.png", "feature_map": "_feature_map_triangle_with_road_with_coa.png", "count": 2, "coa_bonus": True},
    {"id": "city_cap", "name": "City Cap", "image": "city_cap.png", "feature_map": "_feature_map_city_cap.png", "count": 5},
    {"id": "left", "name": "Left", "image": "left.png", "feature_map": "_feature_map_left.png", "count": 3},
    {"id": "right", "name": "Right", "image": "right.png", "feature_map": "_feature_map_right.png", "count": 3},
    {"id": "city_cap_straight", "name": "City Cap With Straight", "image": "city_cap_with_straight.png", "feature_map": "_feature_map_city_cap_with_straight.png", "count": 4},
    {"id": "city_cap_crossroads", "name": "City Cap With Crossroads", "image": "city_cap_with_crossroads.png", "feature_map": "_feature_map_city_cap_with_crossroads.png", "count": 3},
    {"id": "separator", "name": "Separator", "image": "separator.png", "feature_map": "_feature_map_separator.png", "count": 3},
    {"id": "vertical_separator", "name": "Vertical Separator", "image": "vertical_separator.png", "feature_map": "_feature_map_vertical_separator.png", "count": 2},
    {"id": "connector", "name": "Connector", "image": "connector.png", "feature_map": "_feature_map_connector.png", "count": 1},
    {"id": "connector_coa", "name": "Connector With COA", "image": "connector_with_coa.png", "feature_map": "_feature_map_connector_with_coa.png", "count": 2, "coa_bonus": True},
    {"id": "triple_city", "name": "Triple City", "image": "triple_city.png", "feature_map": "_feature_map_triple_city.png", "count": 1},
    {"id": "triple_city_coa", "name": "Triple City With COA", "image": "triple_city_with_coa.png", "feature_map": "_feature_map_triple_city_with_coa.png", "count": 2, "coa_bonus": True},
    {"id": "triple_city_road", "name": "Triple City With Road", "image": "triple_city_with_road.png", "feature_map": "_feature_map_triple_city_with_road.png", "count": 3},
    {"id": "triple_city_road_coa", "name": "Triple City With Road With COA", "image": "triple_city_with_road_with_coa.png", "feature_map": "_feature_map_triple_city_with_road_with_coa.png", "count": 1, "coa_bonus": True},
    {"id": "quadruple_city_coa", "name": "Quadruple City With COA", "image": "quadruple_city_with_coa.png", "feature_map": "_feature_map_quadruple_city_with_coa.png", "count": 1, "coa_bonus": True},
]


TILE_LIBRARY: Dict[str, TileDefinition] = {}
for spec in TILE_SPECS:
    edges, features = _extract_topology(spec["feature_map"], spec.get("coa_bonus", False))
    TILE_LIBRARY[spec["id"]] = TileDefinition(
        id=spec["id"],
        name=spec["name"],
        image_name=spec["image"],
        edges=edges,
        features=features,
        count=spec["count"],
    )


FEATURE_OVERRIDES: Dict[str, Tuple[FeatureDefinition, ...]] = {
    "triple_road": (
        FeatureDefinition(id="road_1", kind="road", edges=("E", "S", "W")),
        FeatureDefinition(id="field_1", kind="field", edges=("Nw", "Ne", "En", "Wn")),
        FeatureDefinition(id="field_2", kind="field", edges=("Es", "Se")),
        FeatureDefinition(id="field_3", kind="field", edges=("Sw", "Ws")),
    ),
    "quadruple_road": (
        FeatureDefinition(id="road_1", kind="road", edges=("N", "E", "S", "W")),
        FeatureDefinition(id="field_1", kind="field", edges=("Nw", "Wn")),
        FeatureDefinition(id="field_2", kind="field", edges=("Ne", "En")),
        FeatureDefinition(id="field_3", kind="field", edges=("Es", "Se")),
        FeatureDefinition(id="field_4", kind="field", edges=("Sw", "Ws")),
    ),
    "city_cap_crossroads": (
        FeatureDefinition(id="city_1", kind="city", edges=("N",)),
        FeatureDefinition(id="road_1", kind="road", edges=("E", "S", "W")),
        FeatureDefinition(id="field_1", kind="field", edges=("En",), adjacent_cities=("city_1",)),
        FeatureDefinition(id="field_2", kind="field", edges=("Es", "Se")),
        FeatureDefinition(id="field_3", kind="field", edges=("Wn", "Ws", "Sw"), adjacent_cities=("city_1",)),
    ),
}

for tile_id, features in FEATURE_OVERRIDES.items():
    tile = TILE_LIBRARY[tile_id]
    TILE_LIBRARY[tile_id] = TileDefinition(
        id=tile.id,
        name=tile.name,
        image_name=tile.image_name,
        edges=tile.edges,
        features=features,
        count=tile.count,
    )


START_TILE_ID = "city_cap_straight"
