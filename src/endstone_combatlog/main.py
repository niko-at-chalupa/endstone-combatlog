import time
from numpy import ceil
from pkginfo.commandline import Base
from endstone import Player
from sys import api_version
from endstone.plugin import Plugin
from endstone.event import event_handler, ActorDamageEvent, PlayerJoinEvent, PlayerQuitEvent, PlayerDeathEvent, PlayerSkinChangeEvent
from endstone import ColorFormat as cf
import math
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from pathlib import Path
from typing import Any
from .etc import generate_timer_bar

class CombatlogConfig(BaseModel):
    timer_ceiling: int
    addend_per_attack: int
    messages: dict[str, str]

class CombatlogPlugin(Plugin):
    api_version = "0.11"
    _config: CombatlogConfig

    def on_enable(self):
        self.register_events(self)

        self._config = self._load_config()

        self.players_in_combat: set[str] = set()
        self.combat_timers: dict[str, int] = {}
        self.offenders: list[str] = [] # XUIDs, simpler

        self.server.scheduler.run_task(self, self.on_twenty_tick_interval, period=20)
        self.server.scheduler.run_task(self, self.every_tick, period=1)


        self.logger.info("If you want to reset the config, delete it and reload the plugin.")

    def get_timer(self, player: str) -> int:
        timer = self.combat_timers.get(player)
        if not timer:
            self.combat_timers[player] = self.config.timer_ceiling
            timer = self.combat_timers.get(player, self.config.timer_ceiling)
        return timer

    def every_tick(self):
        for xuid in self.players_in_combat.copy():
            player = None
            for p in self.server.online_players:
                if p.xuid == xuid:
                    player = p
                    break
            if player:
                timer = self.combat_timers.get(xuid)
                if timer:
                    timer_bar = generate_timer_bar((timer / self.config.timer_ceiling) * 100)
                    player.send_tip(self.config.messages.get("you_are_in_combat", "you are in combat").replace("[sword]", "").replace("[timer]", timer_bar))

    def on_twenty_tick_interval(self):
        for xuid in self.players_in_combat.copy():
            timer = self.get_timer(xuid)
            timer -= 1
            
            if timer <= 0:
                self.players_in_combat.remove(xuid)
                self.combat_timers.pop(xuid, None)
                player = None
                for p in self.server.online_players:
                    if p.xuid == xuid:
                        player = p
                        break
                if player:
                    player.send_toast(
                        self.config.messages.get("exit_combat_title", "exit combat message"), 
                        self.config.messages.get("exit_combat_description", "exit combat description")
                    )
            else:
                self.combat_timers[xuid] = timer

    @event_handler
    def on_player_attack(self, event: ActorDamageEvent):
        if not isinstance(event.actor, Player) or not isinstance(event.damage_source.actor, Player):
            return

        player = event.actor
        attacker = event.damage_source.actor

        if not attacker in self.players_in_combat:
            attacker.send_toast(self.config.messages.get("enter_combat_title", "enter combat message"), self.config.messages.get("enter_combat_description", "enter combat description"))

        # Even if the player the attacker attacks dies instantly upon their hit, we still put
        # them in combat. They're participating in PvP, that's clear to us.
        self.players_in_combat.add(attacker.xuid)

        timer = self.get_timer(attacker.xuid)
        timer = min(timer+self.config.addend_per_attack, self.config.timer_ceiling)
        self.combat_timers[attacker.xuid] = timer

        # Do the same thing again, but for the player who got hit.
        if not player in self.players_in_combat:
            player.send_toast(self.config.messages.get("enter_combat_title", "enter combat message"), self.config.messages.get("enter_combat_description", "enter combat description"))

        self.players_in_combat.add(player.xuid)

        timer = self.get_timer(player.xuid)
        timer = min(timer+self.config.addend_per_attack, self.config.timer_ceiling)
        self.combat_timers[attacker.xuid] = timer

    @property
    def config(self) -> CombatlogConfig:
        return self._config

    @event_handler
    def on_combatlog(self, event: PlayerQuitEvent):
        if not event.player.xuid in self.players_in_combat:
            return
        
        player = event.player

        self.drop_and_clear_inventory(player)

        self.offenders.append(player.xuid)
        self.players_in_combat.remove(player.xuid)
        self.combat_timers.pop(player.xuid)

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

        player.send_message(self.config.messages.get("combatlog_rejoin_message", "combatlog rejoin message"))

    def _load_config(self) -> CombatlogConfig:
        folder = Path(self.data_folder)
        folder.mkdir(parents=True, exist_ok=True)
        cfg_path = folder / "config.yml"
        
        yml = YAML()
        yml.version = (1, 2)
        yml.preserve_quotes = False
        yml.width = 4096
        
        defaults = [
            ("timer_ceiling", 15, "Maximum value the timer can be at, and the value the timer will be set to for the original attack"),
            ("addend_per_attack", 10, "Added value to the timer after initial attack (the timer will never go above timer_ceiling, still)"),

            ("messages.combatlog_rejoin_message", "§cBecause you combatlogged, your inventory was cleared and the items were dropped on the floor!!", "Message shown in chat upon player rejoin after combatlogging"),
            ("messages.enter_combat_title", "You are now in combat!", "Toast title that appears when players engage in PvP"),
            ("messages.enter_combat_description", "Do not quit the game! Otherwise, you will drop all of your items!", "Toast content (i.e., description) that appears when players engage in PvP"),
            ("messages.exit_combat_title", "You are no longer in combat.", "Toast title that appears when players are no longer in PvP"),
            ("messages.exit_combat_description", "You're free to quit the game.", "Toast content (i.e., description) that appears when players are no longer in PvP"),
            ("messages.you_are_in_combat", "[sword] You are in combat! [timer] [sword]", "Tip message while in combat. [timer] will be replaced with the timer (optional), and [sword] will be replaced with a glyph of a sword (optional)"),
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