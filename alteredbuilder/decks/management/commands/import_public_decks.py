import re
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

import requests

from decks.deck_utils import create_new_deck
from decks.models import Card


BASE_URL = "https://altered.ajordat.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

FACTION_CHOICES = [f.value for f in Card.Faction]


class DeckListParser(HTMLParser):
    """Parse the deck list page to extract deck URLs."""

    def __init__(self):
        super().__init__()
        self.deck_urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            attrs_dict = dict(attrs)
            onclick = attrs_dict.get("onclick", "")
            if "location.href=" in onclick:
                match = re.search(r"location\.href='([^']+)'", onclick)
                if match and "/decks/" in match.group(1):
                    self.deck_urls.append(match.group(1))


class DeckDetailParser(HTMLParser):
    """Parse a deck detail page to extract name and decklist."""

    def __init__(self):
        super().__init__()
        self.deck_name = None
        self.decklist = None
        self._in_deck_name = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "h1" and attrs_dict.get("id") == "deckName":
            self._in_deck_name = True
        if tag == "article" and attrs_dict.get("id") == "decklist-text":
            self.decklist = attrs_dict.get("data-decklist", "")

    def handle_data(self, data):
        if self._in_deck_name:
            self.deck_name = data.strip()
            self._in_deck_name = False


class Command(BaseCommand):
    help = "Import public decks from altered.ajordat.com into the local database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of decks to import (default: 10)",
        )
        parser.add_argument(
            "--faction",
            type=str,
            help="Comma-separated faction codes to filter (e.g. AX,BR,YZ)",
        )
        parser.add_argument(
            "--order",
            type=str,
            default="love",
            choices=["love", "views"],
            help="Sort order: love (most loved) or views (most viewed). Default: love",
        )

    def handle(self, *args, **options):
        count = options["count"]
        order = options["order"]
        factions = options.get("faction")

        if factions:
            faction_list = [f.strip().upper() for f in factions.split(",")]
            for f in faction_list:
                if f not in FACTION_CHOICES:
                    raise CommandError(
                        f"Invalid faction '{f}'. Choose from: {', '.join(FACTION_CHOICES)}"
                    )
        else:
            faction_list = None

        # Get or create a local user for imported decks
        user, created = User.objects.get_or_create(
            username="imported",
            defaults={"is_active": True},
        )
        if created:
            user.set_password("imported")
            user.save()
            self.stdout.write(f"Created user: {user.username}")

        # Build the URL with filters
        params = {"order": order}
        if faction_list:
            params["faction"] = ",".join(faction_list)

        # Fetch deck URLs from list pages
        deck_urls = []
        page = 1
        while len(deck_urls) < count:
            params["page"] = page
            url = f"{BASE_URL}/en/decks/"
            self.stdout.write(f"Fetching deck list page {page}...")
            response = requests.get(url, params=params, headers=HEADERS)
            if response.status_code != 200:
                self.stderr.write(
                    f"Failed to fetch deck list (status {response.status_code})"
                )
                break

            parser = DeckListParser()
            parser.feed(response.text)

            if not parser.deck_urls:
                self.stdout.write("No more decks found.")
                break

            deck_urls.extend(parser.deck_urls)
            page += 1

        deck_urls = deck_urls[:count]
        self.stdout.write(f"Found {len(deck_urls)} deck(s) to import.")

        # Fetch each deck detail and import
        imported = 0
        for deck_url in deck_urls:
            full_url = f"{BASE_URL}{deck_url}"
            self.stdout.write(f"Fetching {full_url}...")
            response = requests.get(full_url, headers=HEADERS)
            if response.status_code != 200:
                self.stderr.write(
                    f"  Failed to fetch deck (status {response.status_code})"
                )
                continue

            detail_parser = DeckDetailParser()
            detail_parser.feed(response.text)

            if not detail_parser.deck_name or not detail_parser.decklist:
                self.stderr.write(f"  Could not parse deck data from {deck_url}")
                continue

            deck_name = detail_parser.deck_name
            decklist = detail_parser.decklist

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
                imported += 1
                self.stdout.write(f"  Imported: {deck.name} (id={deck.pk})")
            except Exception as e:
                self.stderr.write(f"  Failed to create '{deck_name}': {e}")

        self.stdout.write(f"\nDone. Imported {imported}/{len(deck_urls)} deck(s).")
