"""Populate the database with the launch catalogue.

Run with `python manage.py seed`. Idempotent: every object is keyed on its
natural key (slug, email, order number), so running it twice updates rather
than duplicates. `--flush` clears commerce data first for a clean rebuild.

Content is imported from `frontend.mockdata`, which is where the catalogue was
authored while the frontend was built. That module stays as the seed source --
it is the fixture, not a runtime dependency; nothing serves requests from it any
more.
"""

import random
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Address, WishlistItem
from content.models import FAQ, Article, FAQGroup, NewsletterSubscriber
from orders.models import (
    DeliveryMethod, FulfillmentStatus, Order, OrderItem, OrderNumberSequence,
    OrderStatus, PaymentStatus,
)
from products.models import (
    Category, Collection, Maker, Product, ProductImage, ProductVariant, StockStatus,
)
from reviews.models import Review

from frontend.mockdata.collections import COLLECTIONS
from frontend.mockdata.faqs import FAQ_GROUPS
from frontend.mockdata.journal import ARTICLES
from frontend.mockdata.makers import MAKERS
from frontend.mockdata.orders import ADDRESSES, ORDERS
from frontend.mockdata.products import PRODUCTS

User = get_user_model()

# Development-only credentials. Documented in the README and safe to publish
# precisely because they only ever exist in a seeded local database.
DEMO_CUSTOMER = {"email": "customer@atelierform.test", "password": "demo-customer-2026",
                 "first_name": "Demo", "last_name": "User", "phone": "+65 8123 4567"}
DEMO_ADMIN = {"email": "admin@atelierform.test", "password": "demo-admin-2026",
              "first_name": "Studio", "last_name": "Admin"}
DEMO_SELLER = {"email": "seller@atelierform.test", "password": "demo-seller-2026",
               "first_name": "Meilin", "last_name": "Chen"}

# Editorial groupings beyond the four browsing categories.
EXTRA_COLLECTIONS = [
    {"slug": "quiet-mornings", "name": "Quiet Mornings",
     "tagline": "For the first hour of the day.",
     "description": "Cups, drippers and a candle for the part of the morning before anything "
                    "has been asked of you. Chosen so the pieces sit together on a small table.",
     "hero": "collection-ceramics", "tile": "category-ceramics", "featured": True,
     "members": ["hand-thrown-stoneware-mug", "ceramic-pour-over-dripper",
                 "speckled-breakfast-bowl", "tea-cup-set-of-two", "soy-wax-studio-candle"]},
    {"slug": "studio-essentials", "name": "Studio Essentials",
     "tagline": "The pieces we use ourselves.",
     "description": "What is actually in daily use in the studio: an apron that has been "
                    "washed a hundred times, boards that get cut on, towels that get used.",
     "hero": "collection-home", "tile": "category-home", "featured": False,
     "members": ["quilted-linen-apron", "olive-wood-serving-board", "hand-loomed-tea-towel",
                 "linen-market-tote", "brass-oak-candle-snuffer"]},
]

STOCK_BY_STATUS = {"in-stock": (14, 46), "low-stock": (2, 4)}


class Command(BaseCommand):
    help = "Seed the database with categories, collections, makers, products, content and demo accounts."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true",
                            help="Delete existing catalogue, orders and demo accounts first.")
        parser.add_argument(
            "--public-only",
            action="store_true",
            help="Seed public catalogue and editorial content without demo users or private data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # Deterministic, so a reseed produces the same stock levels.
        self.rng = random.Random(20260905)

        if options["flush"]:
            self._flush()

        categories = self._seed_categories()
        collections = self._seed_collections()
        makers = self._seed_makers()
        products = self._seed_products(categories, collections, makers)
        self._seed_collection_membership(products, collections)
        self._seed_articles()
        self._seed_faqs()

        if options["public_only"]:
            self.stdout.write(self.style.SUCCESS(
                f"\nSeeded public content: {Category.objects.count()} categories · "
                f"{Collection.objects.count()} collections · {Maker.objects.count()} makers · "
                f"{Product.objects.count()} products · {ProductVariant.objects.count()} variants · "
                f"{ProductImage.objects.count()} images · {Article.objects.count()} articles · "
                f"{FAQ.objects.count()} FAQs"
            ))
            return

        customer, admin = self._seed_users(makers)
        self._seed_addresses(customer)
        self._seed_orders(customer, products)
        self._seed_wishlist_and_reviews(customer, products)
        self._seed_newsletter()

        self.stdout.write(self.style.SUCCESS(
            f"\nSeeded: {Category.objects.count()} categories · "
            f"{Collection.objects.count()} collections · {Maker.objects.count()} makers · "
            f"{Product.objects.count()} products · {ProductVariant.objects.count()} variants · "
            f"{ProductImage.objects.count()} images · {Article.objects.count()} articles · "
            f"{FAQ.objects.count()} FAQs · {Order.objects.count()} orders · "
            f"{User.objects.count()} users"
        ))
        self.stdout.write(
            "\nDevelopment accounts (local only):\n"
            f"  customer  {DEMO_CUSTOMER['email']}  /  {DEMO_CUSTOMER['password']}\n"
            f"  seller    {DEMO_SELLER['email']}  /  {DEMO_SELLER['password']}\n"
            f"  admin     {DEMO_ADMIN['email']}  /  {DEMO_ADMIN['password']}\n"
        )

    # -- flush ------------------------------------------------------------
    def _flush(self):
        self.stdout.write("Flushing existing data…")
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        OrderNumberSequence.objects.all().delete()
        Review.objects.all().delete()
        WishlistItem.objects.all().delete()
        ProductVariant.objects.all().delete()
        ProductImage.objects.all().delete()
        Product.objects.all().delete()
        Collection.objects.all().delete()
        Category.objects.all().delete()
        Maker.objects.all().delete()
        Article.objects.all().delete()
        FAQ.objects.all().delete()
        FAQGroup.objects.all().delete()
        NewsletterSubscriber.objects.all().delete()
        Address.objects.all().delete()
        User.objects.filter(email__in=[DEMO_CUSTOMER["email"], DEMO_SELLER["email"],
                                       DEMO_ADMIN["email"]]).delete()

    # -- catalogue --------------------------------------------------------
    def _seed_categories(self) -> dict:
        out = {}
        for order, entry in enumerate(c for c in COLLECTIONS if c["kind"] == "category"):
            category, _ = Category.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["title"], "tagline": entry["tagline"],
                    "description": entry["description"], "hero_image": entry["hero"],
                    "tile_image": entry["tile"], "sort_order": order, "is_active": True,
                },
            )
            out[entry["slug"]] = category
        self.stdout.write(f"  categories: {len(out)}")
        return out

    def _seed_collections(self) -> dict:
        out = {}
        for order, entry in enumerate(c for c in COLLECTIONS if c["kind"] == "editorial"):
            collection, _ = Collection.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["title"], "tagline": entry["tagline"],
                    "description": entry["description"], "hero_image": entry["hero"],
                    "tile_image": entry["tile"], "is_featured": entry["featured"],
                    "sort_order": order, "is_active": True,
                },
            )
            out[entry["slug"]] = collection

        for order, entry in enumerate(EXTRA_COLLECTIONS, start=len(out)):
            collection, _ = Collection.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["name"], "tagline": entry["tagline"],
                    "description": entry["description"], "hero_image": entry["hero"],
                    "tile_image": entry["tile"], "is_featured": entry["featured"],
                    "sort_order": order, "is_active": True,
                },
            )
            out[entry["slug"]] = collection
        self.stdout.write(f"  collections: {len(out)}")
        return out

    def _seed_makers(self) -> dict:
        out = {}
        for entry in MAKERS:
            maker, _ = Maker.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["name"], "discipline": entry["discipline"],
                    "location": entry["location"], "since": entry["since"],
                    "tagline": entry["tagline"],
                    "short_bio": entry["biography"][0] if entry["biography"] else "",
                    "biography": list(entry["biography"]), "process": list(entry["process"]),
                    "portrait": entry["portrait"], "studio_images": list(entry["images"]),
                    "is_featured": True, "is_active": True,
                },
            )
            out[entry["slug"]] = maker
        self.stdout.write(f"  makers: {len(out)}")
        return out

    def _seed_products(self, categories, collections, makers) -> dict:
        out = {}
        for entry in PRODUCTS:
            made_to_order = entry["stock_status"] == "made-to-order"
            low, high = STOCK_BY_STATUS.get(entry["stock_status"], (14, 46))
            quantity = 0 if made_to_order else self.rng.randint(low, high)

            product, _ = Product.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "name": entry["name"],
                    "short_description": entry["short_description"],
                    "description": entry["description"],
                    "story": entry["story"],
                    "price": Decimal(str(entry["price"])),
                    "currency": settings.COMMERCE["CURRENCY"],
                    "category": categories[entry["category"]],
                    "maker": makers[entry["maker"]],
                    "materials": list(entry["materials"]),
                    "dimensions": entry["dimensions"],
                    "care_instructions": entry["care"],
                    "shipping_information": entry["dispatch"],
                    "is_active": True,
                    "is_featured": entry["featured"],
                    "is_new_arrival": entry["new_arrival"],
                    "is_made_to_order": made_to_order,
                    "stock_quantity": quantity,
                    "sort_weight": entry["added"],
                },
            )

            product.product_images.all().delete()
            ProductImage.objects.bulk_create([
                ProductImage(product=product, image=name, sort_order=i, is_primary=(i == 0),
                             alt_text=f"{product.name}, view {i + 1}")
                for i, name in enumerate(entry["images"])
            ])

            # Spread the product's stock across its variants so per-variant
            # inventory adds up to the product-level figure.
            variant_entries = entry["variants"]
            product.product_variants.all().delete()
            if variant_entries:
                per_variant = max(1, quantity // len(variant_entries)) if quantity else 0
                for i, variant in enumerate(variant_entries):
                    ProductVariant.objects.create(
                        product=product,
                        group=variant["group"],
                        label=variant["label"],
                        sku=f"{product.slug[:28].upper().replace('-', '')}-{variant['group'][:3].upper()}-{i + 1:02d}",
                        swatch=variant["swatch"] or "",
                        stock_quantity=0 if not variant["available"] else per_variant,
                        is_active=True,
                        sort_order=i,
                    )

            # Collections: the mock catalogue tags each product with one.
            slug = entry.get("collection")
            if slug and slug in collections:
                product.collections.set([collections[slug]])
            else:
                product.collections.clear()

            product.refresh_from_db()
            product.refresh_stock_status()
            out[entry["slug"]] = product

        self.stdout.write(f"  products: {len(out)} "
                          f"({ProductVariant.objects.count()} variants, "
                          f"{ProductImage.objects.count()} images)")
        return out

    def _seed_collection_membership(self, products, collections):
        """Add the curated editorial groupings on top of the catalogue tags."""
        for entry in EXTRA_COLLECTIONS:
            collection = collections[entry["slug"]]
            for slug in entry["members"]:
                product = products.get(slug)
                if product:
                    product.collections.add(collection)

    # -- editorial --------------------------------------------------------
    def _seed_articles(self):
        for entry in ARTICLES:
            published = timezone.make_aware(datetime.strptime(entry["date"], "%d %B %Y"))
            Article.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "title": entry["title"], "standfirst": entry["standfirst"],
                    "category": entry["category"], "author": entry["author"],
                    "cover_image": entry["image"], "read_time": entry["read_time"],
                    "body": entry["body"], "is_featured": entry["featured"],
                    "is_published": True, "published_at": published,
                },
            )
        self.stdout.write(f"  articles: {Article.objects.count()}")

    def _seed_faqs(self):
        for order, group_entry in enumerate(FAQ_GROUPS):
            group, _ = FAQGroup.objects.update_or_create(
                slug=group_entry["slug"],
                defaults={"title": group_entry["title"], "blurb": group_entry["blurb"],
                          "sort_order": order, "is_active": True},
            )
            group.faqs.all().delete()
            FAQ.objects.bulk_create([
                FAQ(group=group, question=item["q"], answer=item["a"], sort_order=i)
                for i, item in enumerate(group_entry["items"])
            ])
        self.stdout.write(f"  FAQs: {FAQ.objects.count()} in {FAQGroup.objects.count()} groups")

    # -- accounts ---------------------------------------------------------
    def _seed_users(self, makers):
        customer = User.objects.filter(email=DEMO_CUSTOMER["email"]).first()
        if customer is None:
            customer = User.objects.create_user(
                email=DEMO_CUSTOMER["email"], password=DEMO_CUSTOMER["password"],
                first_name=DEMO_CUSTOMER["first_name"], last_name=DEMO_CUSTOMER["last_name"],
                phone=DEMO_CUSTOMER["phone"], accepts_marketing=True,
            )
        else:
            customer.set_password(DEMO_CUSTOMER["password"])
            customer.save()

        admin = User.objects.filter(email=DEMO_ADMIN["email"]).first()
        if admin is None:
            admin = User.objects.create_superuser(
                email=DEMO_ADMIN["email"], password=DEMO_ADMIN["password"],
                first_name=DEMO_ADMIN["first_name"], last_name=DEMO_ADMIN["last_name"],
            )
        else:
            admin.set_password(DEMO_ADMIN["password"])
            admin.is_staff = admin.is_superuser = admin.is_admin = True
            admin.save()

        seller = User.objects.filter(email=DEMO_SELLER["email"]).first()
        if seller is None:
            seller = User.objects.create_user(
                email=DEMO_SELLER["email"], password=DEMO_SELLER["password"],
                first_name=DEMO_SELLER["first_name"], last_name=DEMO_SELLER["last_name"],
                is_seller=True,
            )
        else:
            seller.set_password(DEMO_SELLER["password"])
            seller.is_seller = True
            seller.save()
        makers["chen-meilin"].owner = seller
        makers["chen-meilin"].save(update_fields=["owner", "updated_at"])

        self.stdout.write("  users: 1 customer, 1 seller, 1 admin")
        return customer, admin

    def _seed_addresses(self, customer):
        customer.addresses.all().delete()
        for entry in ADDRESSES:
            first, _, last = entry["name"].partition(" ")
            Address.objects.create(
                user=customer, label=entry["label"], first_name=first, last_name=last,
                address_line_1=entry["line1"], address_line_2=entry["line2"],
                city=entry["city"], postal_code=entry["postcode"], country=entry["country"],
                phone=entry["phone"], is_default=entry["default"],
            )
        self.stdout.write(f"  addresses: {customer.addresses.count()}")

    def _seed_orders(self, customer, products):
        """Historic orders so the account pages have something to show.

        Written directly rather than through `orders.services.create_order`,
        which would decrement today's stock for a purchase made months ago.
        """
        Order.objects.filter(user=customer).delete()
        status_map = {
            "dispatched": (OrderStatus.SHIPPED, FulfillmentStatus.FULFILLED),
            "delivered": (OrderStatus.DELIVERED, FulfillmentStatus.FULFILLED),
            "in-production": (OrderStatus.PROCESSING, FulfillmentStatus.UNFULFILLED),
            "placed": (OrderStatus.CONFIRMED, FulfillmentStatus.UNFULFILLED),
        }
        default_address = customer.addresses.filter(is_default=True).first()

        for entry in ORDERS:
            status, fulfillment = status_map.get(entry["status"],
                                                 (OrderStatus.CONFIRMED, FulfillmentStatus.UNFULFILLED))
            placed = timezone.make_aware(datetime.strptime(entry["date"], "%d %B %Y"))
            address = default_address.snapshot() if default_address else {}

            order = Order.objects.create(
                order_number=OrderNumberSequence.next_number(placed.year),
                user=customer,
                status=status,
                payment_status=PaymentStatus.PAID,
                fulfillment_status=fulfillment,
                subtotal=Decimal(str(entry["subtotal"])),
                shipping_amount=Decimal(str(entry["shipping"])),
                total=Decimal(str(entry["total"])),
                customer_email=customer.email,
                customer_phone=customer.phone,
                shipping_address_snapshot=address,
                billing_address_snapshot=address,
                delivery_method=DeliveryMethod.STANDARD,
                carrier=entry["carrier"],
                tracking_number=entry["tracking"],
                placed_at=placed,
            )
            for item in entry["items"]:
                product = products.get(item["slug"])
                variant = None
                if product and item.get("variant"):
                    variant = product.product_variants.filter(label=item["variant"]).first()
                OrderItem.objects.create(
                    order=order, product=product, variant=variant,
                    maker=product.maker if product else None,
                    sku=variant.sku if variant else "",
                    product_slug=item["slug"], product_name=item["name"],
                    maker_name=product.maker.name if product else "",
                    variant_name=item.get("variant") or "",
                    image=product.primary_image() if product else "",
                    unit_price=Decimal(str(item["price"])), quantity=item["qty"],
                    line_total=Decimal(str(item["price"])) * item["qty"],
                )
        self.stdout.write(f"  orders: {Order.objects.filter(user=customer).count()}")

    def _seed_wishlist_and_reviews(self, customer, products):
        WishlistItem.objects.filter(user=customer).delete()
        for slug in ["matte-ceramic-vase", "woven-cotton-throw", "olive-wood-serving-board"]:
            if slug in products:
                WishlistItem.objects.get_or_create(user=customer, product=products[slug])

        Review.objects.filter(user=customer).delete()
        seeded_reviews = [
            ("hand-thrown-stoneware-mug", 5, "Exactly as described",
             "The weight is the thing. It has become the only mug I reach for."),
            ("olive-wood-serving-board", 4, "Lovely, needs oiling",
             "Beautiful grain. Wants re-oiling more often than I expected, which is fine."),
        ]
        for slug, rating, title, body in seeded_reviews:
            if slug in products:
                Review.objects.get_or_create(
                    product=products[slug], user=customer,
                    defaults={"rating": rating, "title": title, "body": body},
                )
        self.stdout.write(f"  wishlist: {WishlistItem.objects.filter(user=customer).count()}, "
                          f"reviews: {Review.objects.count()}")

    def _seed_newsletter(self):
        for email in ["reader@example.com", "studio.friend@example.com"]:
            NewsletterSubscriber.objects.get_or_create(email=email, defaults={"source": "seed"})
