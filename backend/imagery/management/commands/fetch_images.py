"""Fill the site's image slots with real, openly licensed photography."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from imagery import sources, targets
from imagery.models import SiteImage
from imagery.resolver import invalidate_index


class Command(BaseCommand):
    help = (
        "Fetch openly licensed photographs from Openverse for every image slot "
        "the catalogue defines, and store them as bytes in PostgreSQL."
    )

    def add_arguments(self, parser):
        parser.add_argument("--only", action="append", default=[], metavar="NAME",
                            help="Fetch just these image names (repeatable).")
        parser.add_argument("--group", action="append", default=[], metavar="KEY",
                            help="Fetch just these groups, e.g. product-speckled-breakfast-bowl.")
        parser.add_argument("--limit", type=int, default=0,
                            help="Stop after N images. Useful for a first look.")
        parser.add_argument("--refresh", action="store_true",
                            help="Re-fetch names that already have a stored image.")
        parser.add_argument("--licence", default=sources.DEFAULT_LICENCE_FILTER,
                            help="Licence filter. Usage words go to Openverse's "
                                 "license_type ('commercial,modification', the default, "
                                 "which is what cropping for a shop requires); licence "
                                 "names go to license ('cc0,pdm' for public domain only, "
                                 "which needs no attribution but covers far less).")
        parser.add_argument("--no-cache", action="store_true",
                            help="Ignore cached search responses and spend API quota.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be fetched without downloading or writing.")

    def handle(self, *args, **options):
        groups = targets.build_groups()

        if options["group"]:
            wanted = set(options["group"])
            groups = [g for g in groups if g.key in wanted]
            if not groups:
                raise CommandError(f"No groups match {sorted(wanted)}")
        if options["only"]:
            wanted = set(options["only"])
            groups = [targets.Group(g.key, g.queries,
                                    [s for s in g.slots if s.name in wanted])
                      for g in groups]
            groups = [g for g in groups if g.slots]
            if not groups:
                raise CommandError(f"No image slots match {sorted(wanted)}")

        existing = set(SiteImage.objects.values_list("name", flat=True))
        if not options["refresh"]:
            groups = [targets.Group(g.key, g.queries,
                                    [s for s in g.slots if s.name not in existing])
                      for g in groups]
            groups = [g for g in groups if g.slots]

        pending = sum(len(g.slots) for g in groups)
        if not pending:
            self.stdout.write(self.style.SUCCESS(
                "Every image slot already has a photograph. Use --refresh to replace them."
            ))
            return

        self.stdout.write(
            f"{pending} image(s) across {len(groups)} search group(s)."
            + (" (dry run)" if options["dry_run"] else "")
        )

        if options["dry_run"]:
            for group in groups:
                self.stdout.write(f"\n  {group.key}  →  {' / '.join(group.queries)}")
                for slot in group.slots:
                    self.stdout.write(f"      {slot.name} [{slot.ratio}] {slot.alt}")
            return

        self.verbosity = options["verbosity"]
        client = sources.Openverse(licence_filter=options["licence"],
                                   use_cache=not options["no_cache"])
        stored = failed = 0

        # Avoid reusing photographs anywhere in the catalogue.
        filling = {slot.name for group in groups for slot in group.slots}
        used = self._already_used(exclude=filling)

        for group in groups:
            if options["limit"] and stored >= options["limit"]:
                break
            # Request extra candidates to cover dead links and duplicates.
            needed = max(12, len(group.slots) * 4)
            try:
                candidates = client.search_ladder(group.queries, needed)
            except Exception as exc:  # noqa: BLE001 -- one bad search must not end the run
                self.stderr.write(self.style.ERROR(f"search failed for {group.key}: {exc}"))
                failed += len(group.slots)
                continue

            if not candidates:
                self.stderr.write(self.style.WARNING(
                    f"no results for {group.key} ({' / '.join(group.queries)}) — "
                    "slots keep their placeholder"
                ))
                failed += len(group.slots)
                continue

            unfilled = []
            for slot in group.slots:
                if options["limit"] and stored >= options["limit"]:
                    break
                if self._fill(client, slot, group, candidates, used):
                    stored += 1
                else:
                    unfilled.append(slot)

            if unfilled:
                # Retry every query rung before leaving a slot on its placeholder.
                wider = client.search_ladder(group.queries, needed=10 ** 9)
                for slot in unfilled:
                    if self._fill(client, slot, group, wider, used):
                        stored += 1
                    else:
                        failed += 1

        invalidate_index()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Stored {stored} image(s); {failed} slot(s) left on the generated placeholder."
        ))
        self.stdout.write(
            f"Openverse: {client.requests_made} API request(s), "
            f"{client.cache_hits} served from the local cache"
            + (f", {client.throttled} throttled and retried." if client.throttled else ".")
        )
        if stored:
            self.stdout.write("Attribution for the stored images is published at /credits/.")

    def _already_used(self, exclude: set[str]) -> set[str]:
        """Identities of photographs the catalogue is already showing.

        Rebuilt from the stored provenance so a fresh process knows what earlier
        runs chose. Slots about to be filled are excluded, since their current
        photograph is the one being replaced.
        """
        used: set[str] = set()
        rows = (SiteImage.objects.exclude(name__in=exclude)
                .values_list("source_id", "creator", "source_title"))
        for source_id, creator, title in rows:
            if source_id:
                used.add(source_id)
            used.add(f"{(creator or '').strip().lower()}|{(title or '').strip().lower()[:60]}")
        return used

    def _fill(self, client, slot, group, candidates, used: set[str]) -> bool:
        """Try ranked candidates until one downloads and encodes cleanly."""
        for candidate in sources.rank(candidates, slot.ratio):
            if candidate.source_id in used or candidate.fingerprint in used:
                continue
            try:
                raw = client.download(candidate)
                payload, width, height = sources.to_jpeg(raw, slot.ratio)
            except Exception as exc:  # noqa: BLE001 -- dead links are routine here
                # Skip dead or rate-limited candidates without failing the run.
                if self.verbosity >= 2:
                    self.stderr.write(f"  {slot.name}: skipping a candidate ({exc})")
                continue

            with transaction.atomic():
                SiteImage.objects.update_or_create(
                    name=slot.name,
                    defaults={
                        "ratio": slot.ratio,
                        "alt_text": slot.alt,
                        "search_query": group.query,
                        "data": payload,
                        "content_type": "image/jpeg",
                        "width": width,
                        "height": height,
                        "provider": candidate.provider,
                        "source_id": candidate.source_id,
                        "source_url": candidate.source_url,
                        "source_title": candidate.title,
                        "creator": candidate.creator,
                        "creator_url": candidate.creator_url,
                        "license": candidate.license,
                        "license_version": candidate.license_version,
                        "license_url": candidate.license_url,
                        "attribution": candidate.attribution,
                        "fetched_at": timezone.now(),
                    },
                )
            used.update({candidate.source_id, candidate.fingerprint})
            self.stdout.write(
                f"  {self.style.SUCCESS('✓')} {slot.name} [{slot.ratio}] "
                f"{len(payload) // 1024} KB — {candidate.title[:48] or 'untitled'} "
                f"(CC {candidate.license.upper()})"
            )
            return True

        self.stderr.write(self.style.WARNING(
            f"  ✗ {slot.name}: no usable candidate — keeping the placeholder"
        ))
        return False
