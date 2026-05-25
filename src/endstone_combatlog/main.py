from pkginfo.commandline import Base
from endstone import Player
from sys import api_version
from endstone.plugin import Plugin
from endstone.event import event_handler, ActorDamageEvent, PlayerJoinEvent, PlayerQuitEvent, PlayerDeathEvent
from endstone import ColorFormat as cf
import math
from pydantic import BaseModel

class CombatlogConfig(BaseModel):
    timer_ceiling: int
    addend_per_attack: int

class CombatlogPlugin(Plugin):
    api_version = "0.11"
    _config: CombatlogConfig

    def on_enable(self):
        self.register_events(self)

        temporary_config = {"timer_ceiling": 15, "addend_per_attack": 15}
        self._config = CombatlogConfig(**temporary_config)

        self.players_in_combat: list[Player] = []
        self.combat_timers: dict[Player, int] = {}
        self.offenders: list[str] = [] # XUIDs, simpler

        self.server.scheduler.run_task(self, self.on_twenty_tick_interval, period=20)

    def get_timer(self, player: Player) -> int:
        timer = self.combat_timers.get(player)
        if not timer:
            self.combat_timers[player] = self._config.timer_ceiling
            timer = self.combat_timers.get(player, self._config.timer_ceiling)
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
        # Initialize the timer this way--it's simpler (I think?).
        self.get_timer(attacker)

    @event_handler
    def on_combatlog(self, event: PlayerQuitEvent):
        if not event.player in self.players_in_combat:
            return
        
        player = event.player

        self.offenders.append(player.xuid)
        self.players_in_combat.remove(player)
        self.combat_timers.pop(player)

    @event_handler
    def on_offender_join(self, event: PlayerJoinEvent):
        if not event.player.xuid in self.offenders:
            return

        player = event.player

        player.health = 0
    
    @event_handler
    def on_offender_death(self, event: PlayerDeathEvent):
        if not event.player in self.offenders:
            return
        
        # Strangely, mutating death messages (or messages in PlayerChatEvent) doesn't work.
        # I'll look into it soon.
        event.death_message = f"{event.player.name} died to combatlogging"