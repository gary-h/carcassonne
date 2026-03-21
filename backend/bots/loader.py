from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

from backend.bots.heuristic_utils import BotMove
from backend.engine.models import GameState


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOT_DIRECTORY = PROJECT_ROOT / "bots"


class BotLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotDefinition:
    slug: str
    name: str
    description: str
    choose_move: Callable[[GameState, Callable], BotMove]
    path: Path


class BotRegistry:
    def list_bots(self) -> list[BotDefinition]:
        definitions: list[BotDefinition] = []
        seen_slugs: set[str] = set()
        if not BOT_DIRECTORY.exists():
            return definitions
        for path in sorted(BOT_DIRECTORY.glob("*.py")):
            definition = self._load_definition(path)
            if definition is None:
                continue
            if definition.slug in seen_slugs:
                raise BotLoadError(f"Duplicate bot slug '{definition.slug}' in {path.name}.")
            seen_slugs.add(definition.slug)
            definitions.append(definition)
        return definitions

    def get_bot(self, slug: str) -> BotDefinition:
        for definition in self.list_bots():
            if definition.slug == slug:
                return definition
        raise BotLoadError(f"Bot '{slug}' was not found in {BOT_DIRECTORY}.")

    def _load_definition(self, path: Path) -> BotDefinition | None:
        module = self._load_module(path)
        if bool(getattr(module, "IS_TEMPLATE", False)):
            return None
        choose_move = getattr(module, "choose_move", None)
        if not callable(choose_move):
            raise BotLoadError(f"{path.name} does not export choose_move(game, trace_component).")
        slug = str(getattr(module, "BOT_SLUG", path.stem)).strip() or path.stem
        name = str(getattr(module, "BOT_NAME", slug)).strip() or slug
        description = str(getattr(module, "BOT_DESCRIPTION", "")).strip()
        return BotDefinition(
            slug=slug,
            name=name,
            description=description,
            choose_move=choose_move,
            path=path,
        )

    def _load_module(self, path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(f"carcassonne_bot_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise BotLoadError(f"Could not import bot module from {path}.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
