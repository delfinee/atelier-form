# Jun Jie Localisation Code Review & Handover

**Project:** Atelier Form — NTU EE3180 DIP E006  
**Workstream:** Simplified Chinese localisation / China-market UX  
**Prepared:** 3 October 2026  
**Reviewed against:** live `delfinee/dip-new-repo-test` repository, current `main`, Jun Jie's localisation commits, and the initial DIP baseline commit `5c9dc303`

---

## 1. Purpose of this handover

This review is intended to help finish the Simplified Chinese localisation **without rebuilding the translation system**.

The project already had Django internationalisation infrastructure in the initial baseline. The useful translation work already completed should be preserved, but the newer hardcoded Chinese dictionaries should be migrated back into the existing Django i18n workflow so that the project has one consistent translation mechanism.

This is **not** a request to restart the localisation work. The goal is:

1. keep the good translations already written;
2. correct the inaccurate ones;
3. remove the parallel hardcoded translation mechanism;
4. finish the missing dynamic/seed content;
5. add localisation tests;
6. keep future translation work inside Django's normal workflow.

---

## 2. Current repository status checked

At the time of this review:

- live `main` is at commit `7f0a6ad`;
- the supplied 30 September repository snapshot ended at `39d26bf`;
- the only commits after that snapshot are documentation edits to `SELLER_FRONTEND_REVIEW.md`, so the translation implementation itself has not materially changed since the snapshot;
- Jun Jie's GitHub account is `caijunix-droid`;
- the localisation branch is `feature/junjie-zh-localisation`;
- that branch is currently **0 commits ahead and 26 commits behind `main`**;
- the latest localisation work is already represented on `main`.

### Before making more localisation changes

Start from the latest `main`, rather than continuing from the stale branch.

Suggested safe workflow:

```bash
git fetch origin
git switch main
git pull origin main
git switch -c feature/junjie-zh-localisation-finish
```

Keep the finishing PR tightly scoped to localisation. Avoid unrelated edits to shared account, seller, order or deployment files.

---

## 3. Django localisation infrastructure already present in the initial baseline

The project already had the main Django i18n components before the later localisation work.

### `backend/config/settings.py`

The existing configuration includes:

```python
"django.middleware.locale.LocaleMiddleware"
```

and:

```python
LANGUAGE_CODE = env.str("DJANGO_LANGUAGE_CODE")
LANGUAGES = [("en", "English"), ("zh-hans", "简体中文")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
```

### `backend/config/urls.py`

The built-in Django language endpoint is already wired:

```python
path("i18n/", include("django.conf.urls.i18n")),
```

### Templates

The project already uses Django template i18n, for example:

```django
{% load i18n %}
{% translate "Skip to content" %}
```

Use `{% blocktranslate %}` where the sentence contains variables or needs a larger translation block.

### Python/static site copy

`frontend/mockdata/content.py` already demonstrates the intended pattern:

```python
from django.utils.translation import gettext_lazy as _, pgettext_lazy

SITE = {
    "tagline": _("Handmade for everyday moments."),
}
```

It also demonstrates `pgettext_lazy` for strings whose meaning depends on context, such as **Home** as a product category rather than the homepage.

### Translation catalogue

The existing translation source is:

```text
locale/zh_Hans/LC_MESSAGES/django.po
```

The compiled file is:

```text
locale/zh_Hans/LC_MESSAGES/django.mo
```

The `.po` file should be the main editable Chinese translation catalogue. The `.mo` file should be regenerated from it, not edited manually.

---

## 4. Code review: what should be kept

Several parts of the later localisation work follow the right approach and should remain.

### Keep template translation tags

Changes that add:

```django
{% load i18n %}
{% translate "..." %}
{% blocktranslate %}...{% endblocktranslate %}
```

are aligned with the existing architecture.

### Keep Python strings wrapped with Django translation functions

For example:

```python
from django.utils.translation import gettext_lazy as _
```

or, for runtime strings:

```python
from django.utils.translation import gettext
```

### Keep the approach of passing translated UI strings to JavaScript

Do not hardcode separate English/Chinese branches inside `site.js`. Where JavaScript needs a user-facing message, pass it from a translated template or translated JSON configuration.

### Keep stable internal values separate from translated labels

For filters and API/query values:

```text
value = "in-stock"       # stable internal value
label = "现货"            # translated display label
```

Do not translate slugs, URL names, SKU values, enum values or query parameter values.

---

## 5. Main implementation problem: parallel hardcoded translation system

The current code introduces a second translation mechanism in:

```text
frontend/catalogue_i18n.py
```

with dictionaries such as:

```python
COLLECTION_TRANSLATIONS = {
    "ceramics": {
        "name": "陶器",
        ...
    }
}
```

and:

```python
PRODUCT_TRANSLATIONS = {
    "hand-thrown-stoneware-mug": ("手拉炻器马克杯", "炻器 · 陈梅琳"),
}
```

`frontend/services.py` then adds more language-specific dictionaries and `is_chinese()` branches.

This works for some screens, but it duplicates Django's existing i18n system and creates several maintenance problems:

- Chinese copy exists in both Python dictionaries and `django.po`;
- adding another language would require more Python branches;
- some service functions localise objects while others return the original English objects;
- only selected fields are translated;
- translations are harder to extract, review and QA as one catalogue;
- presentation logic becomes coupled to a specific language.

### Target state

After migration, the project should not need language-specific dictionaries such as:

```python
if is_chinese():
    return "精选"
```

or slug-to-Chinese tables for seeded content.

The Chinese strings should live in `django.po`, and normal Django translation lookup should decide what is displayed.

---

## 6. Important completeness issue in the hardcoded implementation

The current hardcoded layer does **not** cover all content.

### Products

`localize_product()` currently changes only:

- `name`
- `short_description`

It does not translate all of these seeded fields:

- `description`
- `story`
- `materials`
- `dimensions`
- `care_instructions`
- `shipping_information`

Some service functions also return raw English products without going through the localisation function.

### Makers

`MAKER_TRANSLATIONS` contains Chinese biography/process content, but maker retrieval paths need to be checked to ensure the translated object is actually used everywhere.

### FAQ

The hardcoded dictionary translates FAQ **group title/blurb**, but not every FAQ:

- question
- answer

### Journal

The hardcoded dictionary translates article **title/standfirst**, but not the full article body blocks.

### Validation and feedback

Custom messages in views/forms/backend code still need to be wrapped in Django translation functions, for example success/error messages and project-specific validation errors.

---

## 7. Translation-quality issues found in the hardcoded Chinese

Most of the hardcoded Chinese is understandable, and a large amount can be reused. However, it should not be treated as fully reviewed.

The following examples need correction or fluent-speaker review:

| English source | Current hardcoded Chinese | Review | Suggested Chinese |
|---|---|---|---|
| Ceramics | `陶器` | Too narrow because the category contains stoneware and porcelain | `陶瓷` |
| Porcelain thrown thin enough to hold the light. | `薄到足以承托光线的瓷器。` | Unnatural / changes the meaning | `薄得足以透光的瓷器。` |
| boards that get cut on | `反复切割使用的木板` | Sounds like the board itself is repeatedly cut | `反复用来切东西的木板` |
| Hand-thrown Stoneware Mug | `手拉炻器马克杯` | Understandable, but the pottery process can be clearer | `手工拉坯炻器马克杯` |
| Stoneware Serving Platter | `炻器餐盘` | Loses “serving platter” | `炻器上菜盘` / `炻器大餐盘` |
| Tea Cup Set of Two | `双人茶杯套装` | Sounds like a set for two people | `茶杯两件套` |
| Olive Wood Serving Board | `橄榄木餐板` | Awkward wording | `橄榄木上菜板` |
| Brass & Oak Candle Snuffer | `黄铜橡木烛剪` | **Wrong object**: `烛剪` is a wick trimmer | `黄铜橡木灭烛器` |
| Ash (colour) | `灰烬` | Literal noun; awkward colour label | `灰烬色` |
| Clay (colour) | `泥土` | Literal soil; poor colour label | `陶土色` |
| A wood-ash glaze is a record of the firing that made it. | `手工灰釉记录着烧制它的过程。` | **Wrong**: “wood-ash” became “handmade” | `木灰釉记录着烧制它的过程。` / `草木灰釉…` |
| Made to order | `订制生产` | Sounds industrial | `按单制作` / `定制制作` |
| wooden floor loom | `木质地织机` | Unnatural terminology | `木制落地织机` |
| converted ground-floor workshop | `改造的底层工作室` | Literal / unnatural | `改造后的一楼工作室` |

### Maker names

The repository source provides the maker names in Roman letters. The Chinese character versions such as `陈梅琳`, `陆文静`, etc. are editorial character choices rather than translations that can be proven from the English source. Keep them only after the team/fluent reviewer agrees on those Chinese names.

---

## 8. Existing fuzzy `.po` entries: review them instead of only removing flags

The initial repository already contained some incorrect translations marked with gettext's `fuzzy` flag. These were explicitly unfinished and needed review.

Examples included:

```po
#, fuzzy
#| msgid "Place order"
msgid "All orders"
msgstr "提交订单"
```

and:

```po
#, fuzzy
#| msgid "Search the site"
msgid "Read the piece"
msgstr "站内搜索"
```

The current catalogue removed many fuzzy flags while leaving the same Chinese text unchanged.

Examples that still require correction include:

| English | Current Chinese | Better translation |
|---|---|---|
| All orders | `提交订单` | `全部订单` |
| Read the piece | `站内搜索` | `阅读全文` / `阅读文章` |
| Details & materials | `资料与配送` | `详情与材质` |
| Reviews | `概览` | `评价` / `评论` |
| Review | `概览` | `评价` / `评论` |

**Rule:** only remove `#, fuzzy` after checking the translation against the exact current `msgid`.

---

## 9. Recommended Django workflow for ordinary UI strings

### In templates

Use:

```django
{% load i18n %}

{% translate "Reviews" %}
```

For sentences containing variables:

```django
{% blocktranslate with name=maker.name %}
Made by {{ name }}
{% endblocktranslate %}
```

Use context where one English word has different meanings:

```django
{% translate "Home" context "category" %}
```

### In Python

For module-level/static definitions:

```python
from django.utils.translation import gettext_lazy as _

SORT_OPTIONS = [
    ("featured", _("Featured")),
    ("newest", _("Newest")),
    ("price-asc", _("Price: Low to High")),
    ("price-desc", _("Price: High to Low")),
]
```

For strings produced during a request:

```python
from django.utils.translation import gettext

messages.success(request, gettext("Your details have been saved."))
```

For validation/form strings defined at import time, prefer `gettext_lazy`.

---

## 10. Recommended workflow for seeded/database-backed catalogue content

This is the main area that needs a small amount of extra handling because the English source is stored in the database.

The project does **not** need a second slug-to-Chinese dictionary for fixed seed content.

### Step A — mark the English seed source for extraction

For seeded/static catalogue text in files such as:

```text
frontend/mockdata/collections.py
frontend/mockdata/makers.py
frontend/mockdata/products.py
frontend/mockdata/faqs.py
frontend/mockdata/journal.py
```

use Django's `gettext_noop()` to mark English strings for the catalogue **without translating them at seed time**.

Example:

```python
from django.utils.translation import gettext_noop

_p(
    slug="hand-thrown-stoneware-mug",
    name=gettext_noop("Hand-thrown Stoneware Mug"),
    short_description=gettext_noop("Stoneware · Chen Meilin"),
    description=gettext_noop(
        "A mug with a little weight to it, thrown to sit low in the hand. ..."
    ),
)
```

`gettext_noop()` returns the original English text, so the database still stores the canonical English seed value.

### Step B — translate that stored seed value at presentation time

In the presentation/service layer:

```python
from copy import copy
from django.utils.translation import gettext


def localize_seeded_product(product):
    localized = copy(product)
    localized.name = gettext(product.name)
    localized.short_description = gettext(product.short_description)
    localized.description = gettext(product.description)
    localized.story = gettext(product.story)
    localized.materials = [gettext(item) for item in product.materials]
    localized.dimensions = gettext(product.dimensions)
    localized.care_instructions = gettext(product.care_instructions)
    localized.shipping_information = gettext(product.shipping_information)
    return localized
```

The important change is that the service function no longer knows anything about Chinese. It simply asks Django for the translation in the currently active language.

Use the same principle for:

- maker biography/process lines;
- collection name/tagline/description;
- FAQ group title/blurb/question/answer;
- article title/standfirst/body text.

### Scope warning

This approach is for **fixed seeded/static content** whose English source is committed in the repository.

Do not assume future seller-authored/free-text product descriptions can be translated through `.po`. If the project later supports independently authored bilingual seller content, that should use explicit multilingual fields/content management rather than pretending arbitrary user text is a gettext source string.

---

## 11. Replace manual `is_chinese()` label branches

Current patterns such as:

```python
labels = {
    "Featured": "精选",
    "Newest": "最新上架",
}

if is_chinese():
    ...
```

should become normal gettext lookups.

Example:

```python
from django.utils.translation import gettext_lazy as _

SORT_OPTIONS = [
    ("featured", _("Featured")),
    ("newest", _("Newest")),
    ("price-asc", _("Price: Low to High")),
    ("price-desc", _("Price: High to Low")),
]
```

For filter objects, keep the internal value unchanged and translate only the label:

```python
{
    "value": "in-stock",
    "label": gettext("In stock"),
}
```

Do the same for colour/material display labels.

---

## 12. Migration plan for `frontend/catalogue_i18n.py`

Do not delete the file first, because it currently contains translation work worth preserving.

### Recommended order

1. **Copy/review the Chinese text** from `catalogue_i18n.py` into the matching `msgstr` entries in `django.po`.
2. Correct the known translation problems listed above.
3. Mark the canonical English seed strings with `gettext_noop()` so `makemessages` can extract them.
4. Update the service/presentation layer to call Django `gettext()` on seeded DB fields.
5. Replace the manual `is_chinese()` mappings in `frontend/services.py` with normal gettext labels.
6. Run the localisation tests in both English and `zh-hans`.
7. Only after the translated pages are verified, remove `catalogue_i18n.py` and its imports.

This preserves the translation effort while removing the duplicate architecture.

---

## 13. Generate and compile the catalogue

After source strings are correctly marked:

```bash
python manage.py makemessages -l zh_Hans
```

Review:

```text
locale/zh_Hans/LC_MESSAGES/django.po
```

Fill or correct the `msgstr` values, then compile:

```bash
python manage.py compilemessages
```

Do not hand-edit `django.mo`.

`makemessages` / `compilemessages` require GNU gettext to be available in the development environment. If the command reports that gettext tools are missing, install those tools rather than replacing this workflow with Python dictionaries.

---

## 14. Localisation tests to add

There are currently no dedicated tests using `translation.override("zh-hans")` in the areas reviewed.

Add regression coverage for the Chinese storefront.

Example pattern:

```python
from django.test import TestCase
from django.urls import reverse
from django.utils import translation


class SimplifiedChineseLocalisationTests(TestCase):
    def test_homepage_uses_chinese_copy(self):
        with translation.override("zh-hans"):
            response = self.client.get(reverse("home"))

        self.assertContains(response, "简体中文 expected text here")
```

### Minimum browser/server-rendered coverage

Test at least:

- Home
- Shop/filter labels
- Collection page
- Product detail
- Maker index/detail
- FAQ group + question/answer
- Journal index + article body
- Account/login/profile
- Checkout
- validation/error feedback
- language switch back to English

### Important acceptance checks

For Chinese mode:

- key headings render in Chinese;
- seeded product description/story/material/care text renders in Chinese;
- maker biography/process renders in Chinese;
- FAQ questions and answers render in Chinese;
- journal article body renders in Chinese;
- validation and success/error messages render in Chinese;
- filter/query values still work because only display labels were translated;
- no Chinese punctuation/text leaks into English mode.

For English mode:

- the same pages remain unchanged;
- no Chinese hardcoded text appears when English is active.

---

## 15. Specific files to focus on

### Keep / extend

```text
backend/config/settings.py
backend/config/urls.py
locale/zh_Hans/LC_MESSAGES/django.po
frontend/templates/**
frontend/mockdata/content.py
```

### Refactor

```text
frontend/catalogue_i18n.py
frontend/services.py
frontend/mockdata/collections.py
frontend/mockdata/makers.py
frontend/mockdata/products.py
frontend/mockdata/faqs.py
frontend/mockdata/journal.py
```

### Audit for untranslated custom messages

```text
frontend/views.py
frontend/*forms.py
backend/accounts/
backend/reviews/
backend/orders/
backend/payments/
```

Only user-facing strings need translation. Internal log messages, identifiers, status codes, slugs, database keys and developer-only text should remain stable.

---

## 16. Recommended PR structure

Keep the finishing PR easy to review.

Suggested commit sequence:

```text
1. fix(i18n): correct Simplified Chinese catalogue translations
2. refactor(i18n): mark seeded content for Django gettext
3. refactor(i18n): remove language-specific service mappings
4. feat(i18n): translate remaining FAQ, journal and catalogue content
5. feat(i18n): translate custom validation and feedback messages
6. test(i18n): add zh-hans localisation regression coverage
7. chore(i18n): regenerate compiled Django messages
```

Avoid mixing seller-dashboard, review, fulfilment, recommendation or deployment work into this PR unless a localisation change genuinely requires it.

---

## 17. Definition of done

The localisation work can be considered complete when all of the following are true:

- [ ] `main` is the starting baseline for the work.
- [ ] No new Chinese strings are added through `if is_chinese()` branches or slug-to-Chinese dictionaries.
- [ ] Existing useful Chinese from `catalogue_i18n.py` has been migrated into `django.po`.
- [ ] Known mistranslations have been corrected.
- [ ] Previously fuzzy translations have been individually reviewed before removing the fuzzy marker.
- [ ] Static/template strings use `{% translate %}`, `{% blocktranslate %}`, `gettext_lazy`, `gettext` or contextual gettext as appropriate.
- [ ] Fixed seeded DB content is marked for gettext extraction and translated at presentation time.
- [ ] Product detail fields are fully covered, not only name/short description.
- [ ] Maker biographies/processes are translated and actually rendered through the localisation path.
- [ ] FAQ questions/answers are translated.
- [ ] Journal body content is translated.
- [ ] Custom validation/error/success messages are translated.
- [ ] `python manage.py makemessages -l zh_Hans` completes successfully.
- [ ] `python manage.py compilemessages` completes successfully.
- [ ] dedicated `zh-hans` tests pass.
- [ ] relevant existing frontend/account/review tests still pass.
- [ ] full test suite passes before merge where practical.
- [ ] English pages are unchanged and do not contain Chinese hardcoded text.
- [ ] Chinese pages have been manually reviewed by a fluent speaker.

---

## 18. Short summary for Jun Jie

The translation work already completed does not need to be thrown away. Most of the Chinese copy in the hardcoded catalogue is usable and can be moved into the existing `.po` catalogue after review.

The main technical change is to **stop maintaining Chinese as a second Python data layer**. The project already has Django i18n configured, so the finishing work should use that system consistently:

```text
English source in templates/Python/seed fixture
            ↓
Django makemessages
            ↓
locale/zh_Hans/LC_MESSAGES/django.po
            ↓
Django gettext / template translation at request time
            ↓
English or Simplified Chinese according to active language
```

That keeps the implementation smaller, makes translation QA easier, avoids duplicate language logic, and gives the project one maintainable localisation workflow.
