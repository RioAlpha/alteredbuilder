import os
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from decks.deck_utils import create_new_deck


STARTER_DECKS_DIR = Path(__file__).resolve().parent.parent / "starter-decks"


class Command(BaseCommand):
    help = "Seed the database with starter decks from the starter-decks directory"

    def handle(self, *args, **options):
        # Get or create a dummy user for the starter decks
        user, created = User.objects.get_or_create(
            username="altered",
            defaults={"is_active": True},
        )
        if created:
            user.set_password("altered")
            user.save()
            self.stdout.write(f"Created user: {user.username}")

        for filepath in sorted(STARTER_DECKS_DIR.iterdir()):
            if filepath.is_file():
                deck_name = filepath.name
                decklist = filepath.read_text().strip()

                try:
                    deck = create_new_deck(
                        user,
                        {
                            "name": deck_name,
                            "decklist": decklist,
                            "is_public": True,
                            "description": "",
                        },
                    )
                    self.stdout.write(f"Created deck: {deck.name} (id={deck.pk})")
                except Exception as e:
                    self.stderr.write(f"Failed to create '{deck_name}': {e}")
