from numpy import ceil
from pkginfo.commandline import Base
from endstone import Player
from sys import api_version
from endstone.plugin import Plugin
from endstone.event import event_handler, ActorDamageEvent, PlayerJoinEvent, PlayerQuitEvent, PlayerDeathEvent
from endstone import ColorFormat as cf
import math
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from pathlib import Path
from typing import Any

class CombatlogConfig(BaseModel):
    timer_ceiling: int
    addend_per_attack: int

class CombatlogPlugin(Plugin):
    api_version = "0.11"
    _config: CombatlogConfig

    def on_enable(self):
        self.register_events(self)

        self._config = self._load_config()

        self.players_in_combat: list[Player] = []
        self.combat_timers: dict[Player, int] = {}
        self.offenders: list[str] = [] # XUIDs, simpler

        self.server.scheduler.run_task(self, self.on_twenty_tick_interval, period=20)

        self.logger.info("If you want to reset the config, delete it and reload the plugin.")

    def get_timer(self, player: Player) -> int:
        timer = self.combat_timers.get(player)
        if not timer:
            self.combat_timers[player] = self.config.timer_ceiling
            timer = self.combat_timers.get(player, self.config.timer_ceiling)
        return timer

    def on_twenty_tick_interval(self):
        for player in self.players_in_combat:
            timer = self.get_timer(player)
            timer -= 1
            if timer <= 0:
                self.players_in_combat.remove(player)
                self.combat_timers.pop(player)

    @event_handler
    def on_player_attack(self, event: ActorDamageEvent):
        if not isinstance(event.actor, Player) or not isinstance(event.damage_source.actor, Player):
            return

        player = event.actor
        attacker = event.damage_source.actor

        # Even if the player the attacker attacks dies instantly upon their hit, we still put
        # them in combat. They're participating in PvP, that's clear to us.
        self.players_in_combat.append(attacker)

        timer = self.get_timer(attacker)
        timer = min(timer+self.config.addend_per_attack, self.config.timer_ceiling)

    @property
    def config(self) -> CombatlogConfig:
        return self._config

    @event_handler
    def on_combatlog(self, event: PlayerQuitEvent):
        if not event.player in self.players_in_combat:
            return
        
        player = event.player

        self.drop_and_clear_inventory(player)

        self.offenders.append(player.xuid)
        self.players_in_combat.remove(player)
        self.combat_timers.pop(player)

    def drop_and_clear_inventory(self, player: Player) -> None:
        inventory = player.inventory
        location = player.location

        all_slots = list(inventory.contents or [])
        extras = [
            inventory.item_in_main_hand,
            inventory.item_in_off_hand,
            inventory.helmet,
            inventory.chestplate,
            inventory.leggings,
            inventory.boots,
        ]

        for item in all_slots + extras:
            if item is not None:
                player.dimension.drop_item(location, item)

        inventory.clear()

    @event_handler
    def on_offender_join(self, event: PlayerJoinEvent):
        if not event.player.xuid in self.offenders:
            return

        player = event.player

        player.send_message(f"{cf.RED}Because you combatlogged, your inventory was cleared and the items were dropped on the floor!!")

    def _load_config(self) -> CombatlogConfig:
        folder = Path(self.data_folder)
        folder.mkdir(parents=True, exist_ok=True)
        cfg_path = folder / "config.yml"
        
        yml = YAML()
        yml.version = (1, 2)
        yml.preserve_quotes = False
        
        defaults = [
            ("timer_ceiling", 15, "Maximum value the timer can be at, and the value the timer will be set to for the original attack"),
            ("addend_per_attack", 10, "Added value to the timer after initial attack (the timer will never go above timer_ceiling, still)"),
        ]
        
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                existing = yml.load(f)
            if not isinstance(existing, CommentedMap):
                existing = CommentedMap(existing or {})
        else:
            existing = CommentedMap()

        for key, default, comment in defaults:
            keys = key.split(".")
            current = existing
            for i, k in enumerate(keys[:-1]):
                if k not in current:
                    current[k] = CommentedMap()
                current = current[k]
            
            if keys[-1] not in current:
                current[keys[-1]] = default
                current.yaml_add_eol_comment(comment, keys[-1])

        with open(cfg_path, "w", encoding="utf-8") as f:
            yml.dump(existing, f)

        config_dict = self._commented_map_to_dict(existing)
        return CombatlogConfig(**config_dict)

    def _commented_map_to_dict(self, data: Any) -> Any:
        if isinstance(data, CommentedMap):
            return {k: self._commented_map_to_dict(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._commented_map_to_dict(v) for v in data]
        return data