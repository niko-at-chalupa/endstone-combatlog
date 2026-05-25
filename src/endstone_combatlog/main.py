from endstone import Player
from sys import api_version
from endstone.plugin import Plugin
from endstone.event import event_handler, ActorDamageEvent

class CombatlogPlugin(Plugin):
    api_version = "0.11"

    def on_enable(self):
        self.register_events(self)

        self.players_in_combat: list[Player] = []

    @event_handler
    def on_player_attack(self, event: ActorDamageEvent):
        if not isinstance(event.actor, Player) or not isinstance(event.damage_source.actor, Player):
            return

        player = event.actor
        attacker = event.damage_source.actor

        # Even if the player the attacker attacks dies instantly upon their hit, we still put
        # them in combat. They're participating in PvP, that's clear to us.
        self.players_in_combat.append(attacker)

        def remove_from_combat():
            try:
                self.players_in_combat.remove(attacker)
            except Exception:
                # There might be exceptions? I don't know, just do this anyways. Not good to
                # have unhandled exceptions on a production server, is it?
                pass
        self.server.scheduler.run_task(self, remove_from_combat, 20*15)