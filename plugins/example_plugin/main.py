"""
Example LADA Plugin - Demonstrates the plugin interface.
"""

import random


class ExamplePlugin:
    """Example plugin with coin flip and dice roll capabilities."""

    def on_load(self):
        """Called when plugin is loaded."""
        pass

    def on_activate(self):
        """Called when plugin is activated."""
        pass

    def on_deactivate(self):
        """Called when plugin is deactivated."""
        pass

    def on_unload(self):
        """Called when plugin is unloaded."""
        pass

    def handle_coin_flip(self, query: str) -> str:
        """Flip a coin and return the result."""
        result = random.choice(["Heads", "Tails"])
        return f"I flipped a coin and got: **{result}**!"

    def handle_dice_roll(self, query: str) -> str:
        """Roll a dice and return the result."""
        result = random.randint(1, 6)
        return f"I rolled a dice and got: **{result}**!"
