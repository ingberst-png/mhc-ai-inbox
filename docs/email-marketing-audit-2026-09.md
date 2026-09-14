# MileHighCook Email Audit — September 2026

A deep audit of every client-facing email MileHighCook currently sends, measured
against how the best luxury food and hospitality brands run email, with ranked
fixes and ready-to-ship copy.

Scope: the ~21 automated and semi-automated emails deployed out of
`mhc-inbox.vercel.app` and sent through the Gmail API from
`steve@milehighcook.net`, sampled from live sends between 2026-08-14 and
2026-09-14.

---

## 0. The one-paragraph version

The emails are good. The writing is genuinely better than almost every private
chef in the country — specific, warm, no filler, no emoji, no hype. The
lifecycle from inquiry to invoice is more complete than most catering companies
twice this size. But three things are costing real money: **there is no email
after the plate is cleared**, **there is no measurement of any kind**, and
**the beautiful template is applied to the wrong emails**. Fix those three and
the program goes from "good notes" to a compounding asset.

---

## 1. Inventory: what is actually deployed

Two distinct visual systems are in production, and the assignment between them
is accidental rather than designed.

### System A — "The Card"

Cream `#f4f1ea` canvas, 600px white card with 14px radius, navy `#002854`
header, white logo, gold `#E2BB46` letterspaced eyebrow, 3px gold rule, full-
bleed hero photo, Georgia 16px/1.7 body, gold diamond divider, circular chef
portrait in the footer, service-area line, `milehighcook.net`.

Currently used on:

| Email | Trigger |
|---|---|
| Your intake form, how I build your menu | Booking created |
| Your menu is ready to review | Menu published |
| Your invoice, reserve your date | Invoice issued |
| MHC AI Inbox daily digest | 8am MT (internal) |
| Job / decision alerts | Event driven (internal) |

### System B — "The Note"

A bare `<div>`, Arial 14px, `#222` on white, 1.5 line height, a horizontal rule,
`logo-navy.png` at 110px, name, "MileHighCook · Private Chef Dining", phone,
site.

Currently used on:

| Email | Trigger |
|---|---|
| Your MileHighCook inquiry: I'm on it | **First impression — form submit** |
| Your MileHighCook inquiry, quick call? | Manual, same day |
| Your MileHighCook service agreement | Agreement issued |
| One signature and you're set | Signature nudge |
| Your fully executed agreement | Countersigned |
| Your payment is recorded, receipt inside | Payment reconciled |
| Still need your intake form to start planning | Intake nudge |
| How the night runs, [date] | Pre-event brief |
| In N days: [service], [date] | Client + chef reminders |
| Your MileHighCook Job Packet | Chef staffing |
| Quick form to get you set up | Chef onboarding |
| Wednesday: your pay and our service standards | Chef pay |
| Your MileHighCook gift card for [name] | Gift purchase |
| You've received a MileHighCook gift card | Gift recipient |
| Your receipt for the MileHighCook gift card | Gift buyer |
| Menus and pricing for your event | Manual, PDF attached |
| All 1:1 sales follow-ups and negotiation | Manual |

### What does not exist

Nothing runs after the event. There is no thank-you, no photo delivery, no
review request, no referral ask, no rebooking prompt, no seasonal broadcast, no
newsletter, no opt-in list, no lost-lead nurture, no gift-card redemption
nurture, and no partner/venue sequence. The booking funnel is well built and
then it simply stops.

---

## 2. Metrics: there are none

Every client-facing email goes out through the Gmail API. That means:

- **No open tracking.** No pixel, no ESP.
- **No click tracking.** Links are raw destination URLs — no redirect domain, no
  UTM parameters on a single link sampled.
- **No bounce, complaint, or suppression handling.**
- **No A/B capability.** No subject-line testing, no send-time testing.
- **No attribution.** There is no way to answer "did the invoice email get
  opened before they paid" or "which follow-up wording books more calls."

Resend is already in the stack for the internal 8am digest and now exposes a
metrics API and suppression-list control. Moving client-facing sends onto it
(sending as `steve@milehighcook.net` via an authenticated subdomain) is the
lowest-effort path to real numbers.

**Everything below is a hypothesis until this is instrumented.** That is the
single most important sentence in this document.

---

## 3. Who to study, and the exact move to steal

These are public programs studied from the outside — their published emails,
site capture, and cadence — not their dashboards. The value is the *mechanic*,
not the aesthetic.

### Blackberry Farm / Blackberry Mountain — the journal, not the promo
Their email reads like a dispatch from a working farm: what is coming out of the
garden, what the cheesemaker is doing, which preserves just got jarred. Booking
is the byproduct of wanting to be there. **Steal:** MileHighCook's product is
Steve, not a menu PDF. A quarterly note about what is actually good in September
in the Rockies — the last of the Palisade peaches, elk season, why he stopped
doing a certain dish — outperforms any promotion, because it is the only email
a past client will forward.

### Auberge Resorts Collection — sense of place, per property
Auberge never sells "luxury." It sells one specific valley, one specific
canyon. **Steal:** the current footer says "Colorado · Arizona · Utah ·
Wyoming." That is a coverage map, not a place. Vail, Park City, Jackson,
Scottsdale and Deer Valley are five different customers with five different
seasons. Segment by market the moment there is a list.

### Aman — restraint as the luxury signal
Very low frequency, enormous white space, one photograph, almost no copy. The
scarcity of contact *is* the positioning. **Steal:** do not build a weekly
newsletter. Build four sends a year that people genuinely open. At this price
point, frequency reads as desperation.

### The Little Nell (Aspen) — the expert is the draw
The wine program, the sommelier's notes, the dinners. People subscribe for a
point of view. **Steal:** Steve already has this voice in his 1:1 email and
throws it away. "We never mark up wine" (sent to Matt Brewer, Sep 5) is a better
brand line than anything currently in a template.

### Eleven Madison Park / Alinea Group — the dated release
Reservation drops are treated as events with a time and a date. **Steal:** the
single highest-performing broadcast a private chef can send is
*"Holiday dates open Monday at 9am MT — 11 nights, first come."* It has a
deadline, real scarcity, and it is true.

### Airbnb and Resy — the pre-arrival sequence
Not luxury, but the best-engineered lifecycle in hospitality: confirmation,
anticipation, logistics, day-of, post-stay review. **Steal:** the post-stay half.
MileHighCook has built the first half beautifully and none of the second.

### Graza / Fishwife — subject-line craft
Not the right aesthetic, but the right discipline: every subject sounds like a
person wrote it to one person. **Steal:** the standard. Compare
"In 3 days: Cooking Class, Sep 16, 2026" (calendar app) with Steve's own
hand-written "October 2 at Groom Creek" (a person). The second is better and it
already exists in the sent folder.

### Ongoing swipe file
Really Good Emails, hotels & resorts category — for structure and layout
patterns worth copying, not wording.

---

## 4. Head to head: their move vs. the email deployed today

| The move | Best-in-class | MileHighCook today | Gap |
|---|---|---|---|
| First impression | Sets a tone, and the design carries it | Auto-reply is a bare Arial `<div>` | The one email guaranteed to be opened is the least designed |
| CTA | Tap-target button, one per email | Raw `https://mhc-inbox.vercel.app/invoice/e5eed60c…` as link text | Every conversion click is a wrapping URL on a phone |
| Domain | Own domain on every link | `mhc-inbox.vercel.app` on invoices, agreements, menus | An $11,000 invoice links to a vercel.app project |
| Preheader | 90 chars of persuasion | None — Gmail shows the eyebrow repeated back | Free open-rate lever, unused on every send |
| Post-experience | Review + photos + rebook | Nothing | The highest-trust moment in the business is silent |
| List | Opt-in, segmented, owned | No list exists | Every client is a one-off |
| Measurement | Open, click, revenue per recipient | None | Cannot improve what is not counted |
| Cadence | Deliberate, seasonal | Purely reactive to bookings | No presence between jobs |

---

## 5. Findings, ranked by money

### F1 — Nothing happens after the event *(highest impact)*
The night after a dinner that landed is the single highest-trust moment
MileHighCook will ever have with a customer, and the system sends nothing.
Post-purchase flows convert around 3.8%, roughly 3x promotional email. Review
requests perform best 24–48 hours after the experience, and a second ask about
seven days later measurably lifts response.

This also fixes a live problem. The Take a Chef score sits at 3.57, below what
the public reviews suggest, and the 2026-09-13 note from Megan Shoflick ("some
of the food was not great") arrived as a surprise. Owning the post-event ask
means happy clients get routed to Google and unhappy ones get routed to Steve's
inbox *first* — before they post.

**Build:** a four-email sequence (copy in §7).

### F2 — There is no list, and nothing collects one
Repeat and referral is the entire economics of a private chef business, and
there is no mechanism to build an audience. Every client already fills out the
intake form; that is the natural consent point.

**Build:** an unchecked opt-in on the intake form — *"Send me a note when
seasonal dates open. Four times a year, never more."* Auto-enroll gift-card
recipients. Nothing else changes today; the list just starts existing.

### F3 — Zero instrumentation
Covered in §2. Move client sends to Resend on an authenticated subdomain, tag
every link with UTMs, and get opens, clicks, bounces and suppressions.

### F4 — `mhc-inbox.vercel.app` on every client-facing link
This one leaks money quietly. At the luxury tier the URL is part of the product.
A client forwarding a $1,681 invoice to their spouse is forwarding a link to
what reads as somebody's side project. It also splits domain reputation and
hosts every brand image off-brand.

**Fix:** CNAME to `book.milehighcook.net`. Move `/brand/opt/*` images with it.

### F5 — Two design systems, applied backwards
The card template — genuinely well built, correct 600px table structure, good
type, good gold-on-white contrast at `#B8912F` — is on the intake form and the
menu. The plain note is on the first impression, the agreement, and the receipt.

Do **not** simply convert everything to the card. The evidence cuts the other
way for trust-and-reply emails: in a documented high-ticket test a designed HTML
email drew 1.2% CTR against 4.5% for the plain-text version, and plain text
generally out-clicks image-heavy HTML by roughly 42–51%. Plain wins when the
goal is a human reply. Design wins when the goal is to be admired or shown to
someone else.

**Fix — make the two lanes deliberate:**

| Lane | Use for | Rule |
|---|---|---|
| **The Note** (plain, from Steve) | Auto-reply, agreement, signature nudge, follow-ups, negotiation, intake nudge | No hero image, no card. One idea, one ask, reply-friendly |
| **The Card** (branded) | Menu, invoice, gift card, post-event photos, seasonal broadcast | Hero image, button, footer. Made to be looked at and forwarded |

The auto-reply and the receipt move *into* the Note lane deliberately (they are
already there by accident, which is fine — but they need a preheader and a
button). The gift card moves *up* into the Card lane. Nothing else changes lane.

### F6 — Every CTA is a naked URL
`https://mhc-inbox.vercel.app/sign/rxsXFje6N7MzByMthl9mgjZ0R1bD5BDo` is the
clickable text on the signature email. On a phone that wraps across three lines
and is a poor tap target.

**Fix:** a bulletproof table/VML button, gold `#E2BB46` on navy `#002854`, at
least 44px tall, one per email, with the plain URL beneath in 11px grey as a
fallback.

### F7 — No preheader text anywhere
Gmail currently previews the intake email as: *"Private Chef Dining YOUR INTAKE
FORM, HOW I BUILD YOUR MENU Hi Sydney,"* — the eyebrow and the subject, read
back. That is roughly 90 characters of the most valuable space in the inbox
spent saying nothing new.

**Fix:** a hidden preheader div immediately after `<body>`:

```html
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
  Two minutes, and I read every word before I write a single course.
</div>
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
  &#8199;&#65279;&nbsp;&#8199;&#65279;&nbsp;&#8199;&#65279;&nbsp;
</div>
```

Cheapest open-rate lever available. Do it on all 21 emails.

### F8 — Subject lines are operational, not human
"In 3 days: Cooking Class, Sep 16, 2026" reads like a calendar notification.
Steve's own hand-written subjects are far better — "October 2 at Groom Creek",
"Your Deer Valley dinner, January 10", "Locking in the 12th". Place and date,
specific, no service-type jargon.

**Rule:** name the place and the date. Never name the SKU.

### F9 — Dark mode breaks the signature
`logo-navy.png` is a navy mark on transparency, placed on white. In dark-mode
Gmail and Apple Mail the surrounding block inverts and the logo either vanishes
into the dark background or gets an ugly forced white plate. The card template's
white-on-navy header is safe; the Note lane is not.

**Fix:** ship a light logo variant and swap it under
`@media (prefers-color-scheme: dark)`, or place the navy mark on an explicit
white padded plate so the plate travels with it.

### F10 — No CAN-SPAM footer or unsubscribe mechanism
Correct today — everything sent is transactional or genuine 1:1. But the first
broadcast makes a physical mailing address and a working one-click unsubscribe
a legal requirement and a deliverability requirement. Build it before it is
needed, not after.

### F11 — The gift card is the best untapped acquisition channel, and it dead-ends
Jameson Olsen received a $250 card on 2026-09-10. He is a pre-paid, warm,
brand-new prospect who has likely never heard of MileHighCook. He got one plain
email with a code and nothing else. No story, no sense of what an evening is
like, no nudge if he does not redeem, no expiry reminder.

**Build:** a three-email recipient sequence (copy in §7).

### F12 — Lost leads have no path back
Jenny Facer walked on budget on 2026-09-13 and the counter-offer ($4k, sign
today) was improvised live in the thread. Good instinct, no system. Price
objections are the most recoverable loss there is, because the want is already
established.

**Build:** a "budget" bucket. Thirty days later, offer the smaller format —
a hands-on class, an off-peak date, a four-course instead of seven.

### F13 — Market expansion is being done by hand, one email at a time
Nova Guides (Camp Hale weddings), Park City Film, Garden Creek Vineyards,
Colterris, Gemini Event Planning, Orangetheory — all cold-emailed individually,
several admitted to having been dropped for months. This is exactly the
brand-growth motion in the goal, and it is the least systematised thing in the
business: no sequence, no tracking, no follow-up cadence, no list of target
venues per market.

**Build:** a three-touch venue/planner sequence per market (copy in §7), tracked,
with a standing target list for Vail, Park City, Jackson, Aspen and Scottsdale.

---

## 6. Build order

**Phase 1 — Instrument and repair (this week).** These are cheap and they gate
everything else.
1. Client sends move to Resend on an authenticated subdomain.
2. `book.milehighcook.net` CNAME; move brand images.
3. Preheader on all 21 emails.
4. Button component replaces every naked URL.
5. UTMs on every link.
6. Dark-mode logo fix.

**Phase 2 — Capture the money already on the table.**
7. Post-event four-email sequence.
8. Review routing (happy → Google, unhappy → Steve).
9. Intake-form opt-in checkbox.

**Phase 3 — Recover what leaks.**
10. Gift-card recipient sequence.
11. Lost-lead budget sequence.
12. CAN-SPAM footer + unsubscribe infrastructure.

**Phase 4 — Grow.**
13. Quarterly seasonal broadcast, segmented by market.
14. Venue and planner partner sequence per market.
15. Dated release ("holiday dates open Monday 9am MT").

---

## 7. Ready-to-ship copy

Written in the MHC voice: warm, authentic, confident, never pushy, no emoji.

### 7.1 Post-event sequence

**#1 — next morning, ~9am local. Lane: Note. No card, no images.**

> **Subject:** Last night at [venue/town]
> **Preheader:** One thing I'd change, and one thing I'd cook again.
>
> Hi [Name],
>
> Thank you for last night. [One true, specific sentence about the actual
> evening — the toast, the kid who ate three servings of the short rib, the
> snow starting halfway through the second course.]
>
> If I cooked for you again I'd make [dish] the same way and rethink [dish].
> That's the honest read.
>
> Your kitchen was left the way I found it. If anything turns up that shouldn't
> have, tell me and I'll sort it.
>
> Much thanks,
> Steve

**#2 — +2 days, ~10am local. Lane: Note.**

> **Subject:** A quick favour, if it was worth it
> **Preheader:** Sixty seconds, and it genuinely decides who finds us.
>
> Hi [Name],
>
> If [date] was worth it, a short review is the single most useful thing you
> could do for us. Word of mouth is how nearly every night on my calendar got
> booked.
>
> [ Leave a review ]  ← button
>
> And if any part of it fell short, reply here instead and tell me straight. I
> would much rather hear it from you than read it later.
>
> Much thanks,
> Steve

*Routing: the button goes to a two-choice page. "It was great" → Google review.
"Something was off" → a form that lands in Steve's inbox and never posts
publicly.*

**#3 — +10 days. Lane: Card.**

> **Subject:** Photos from [date]
> **Preheader:** Yours to keep, and to send to whoever asks who cooked.
>
> A handful of shots from the night. Yours to use however you like.
>
> [ See the photos ]  ← button
>
> If someone at that table asks who cooked, sending them this is the whole
> referral. I keep [month] open for exactly that reason.

**#4 — +90 days, or the week before their season. Lane: Card.**

> **Subject:** [Town] in [season]
> **Preheader:** What's good right now, and what's still open.
>
> [Two or three sentences about what is actually in season and what he is
> cooking with it — real, not filler.]
>
> [Dates] are still open in [town].
>
> [ Hold a date ]  ← button

### 7.2 Rewritten inquiry auto-reply

Same excellent copy, plus the two things it is missing.

> **Subject:** Your MileHighCook inquiry: I'm on it
> **Preheader:** I read every one myself, usually within the hour.
>
> Hi [Name],
>
> Thanks for reaching out. I just saw your inquiry come in, and I'm glad you
> found us. I'll personally reach out shortly, usually the same day, to hear the
> full picture: the occasion, the people at the table, the food you love.
>
> A great meal starts long before anyone sits down, and it starts here.
>
> If it's easier, reply to this email with anything you'd like me to know before
> we talk.
>
> Much thanks,
> Steve Ingber
> Chef & Owner · MileHighCook

Changes: preheader added, dark-mode-safe logo, and — if a sample menu PDF is
ever linked here — one button, never a raw URL.

### 7.3 Gift-card recipient sequence

**#1 — on issue. Lane: Card.**

> **Subject:** [Buyer] bought you dinner
> **Preheader:** A chef in your kitchen, and a code that doesn't expire on you.
>
> [Buyer] has given you an evening with MileHighCook — $[amount], code
> [CODE].
>
> Here's what that actually looks like: I come to your kitchen, cook a menu
> built around your table, and leave it spotless. You sit down with your people
> the entire time.
>
> [ Pick your date ]  ← button

**#2 — +21 days if unredeemed. Lane: Note.**

> **Subject:** Your card from [Buyer]
> **Preheader:** No expiry. But the good dates go early.
>
> Hi [Name], your $[amount] from [Buyer] is still sitting here. There's no
> expiry on it — but [month] and [month] fill up first, so it's worth picking a
> date even if it's a long way out.
>
> Reply with a rough window and I'll tell you what's open.

**#3 — +75 days if unredeemed. Lane: Note.** A single short line offering to
just talk it through, plus the two or three date windows still open.

### 7.4 Lost lead — budget

**+30 days after a price walk-away. Lane: Note.**

> **Subject:** A smaller version of the same night
> **Preheader:** Same cooking, different shape.
>
> Hi [Name],
>
> You stepped back on [event] because of budget, and that was the right call at
> the number I gave you. But the number isn't the only shape this takes.
>
> A hands-on class runs a fraction of a full service and people remember it
> longer. A four-course instead of seven. A weeknight instead of a Saturday.
> Any of those get you the same food and the same night.
>
> If you tell me the number you can actually do, I'll tell you honestly whether
> I can build something good inside it.
>
> Much thanks,
> Steve

### 7.5 Venue and planner partner sequence

Three touches, 6 days apart, per market. Lane: Note, always.

**Touch 1 — the specific reason.**
> **Subject:** [Venue name] and a chef who travels
>
> One sentence naming something specific and true about their venue. One
> sentence on what MileHighCook does for a venue with no kitchen. One question
> that is easy to answer.

**Touch 2 — the proof.**
> **Subject:** What a night at [comparable venue] looked like
>
> One real event, real numbers, real outcome. A photo link. No ask beyond a
> reply.

**Touch 3 — the close, or the clean exit.**
> **Subject:** Last note from me on [venue]
>
> Say plainly that this is the last one, leave the door open, and mean it. This
> is the highest-response email in almost every cold sequence.

### 7.6 Subject-line bank

Place and date, never SKU.

- October 2 at Groom Creek
- Your Deer Valley dinner, January 10
- Locking in the 12th
- Holiday dates open Monday, 9am
- Last night at [venue]
- Peaches are done, elk is on
- Three nights left in [month]
- A smaller version of the same night

Retire: "In 3 days: Cooking Class, Sep 16, 2026", "Your intake form, how I
build your menu" (→ "Two minutes, and I start building your menu").

---

## 8. What to measure, and the number to beat

Once Phase 1 lands, these are the targets. Industry floors are cited so it is
clear what "good" means; a list made entirely of past private-chef clients
should beat every campaign floor comfortably.

| Metric | Target | Industry reference |
|---|---|---|
| Lifecycle / transactional open | 60–80% | Transactional email typically 80–85% |
| Lifecycle click-through | 15%+ | Transactional CTR ~4.8%, ~2x average |
| Post-event review request — open | 50%+ | Post-purchase flows convert ~3.8%, ~3x promo |
| Post-event review request — click | 20%+ | — |
| Review conversion (click → posted) | 30%+ | — |
| Gift-card recipient email 1 — open | 45–65% | Welcome-flow email 1 benchmark |
| Quarterly broadcast — open | 40%+ | F&B campaigns typically 38–48% |
| Quarterly broadcast — click | 2.5–3% | Strong F&B programs reach 2.5–3% |
| Unsubscribe per send | under 0.15% | Restaurant benchmark 0.15% |
| Spam complaint rate | under 0.1% | Deliverability hard floor |

Weakest campaign floors, for context: restaurant industry sits around 21–25%
open, ~1.1% CTR, ~3.3% click-to-open. A list of people who have already paid
for a private chef should not be anywhere near those numbers.

Review quarterly. The only metric that ultimately matters is bookings
attributable to email — which is why UTMs in Phase 1 are not optional.

---

## Sources

- [Restaurant Benchmarks 2026 — Bloom Intelligence](https://bloomintelligence.com/blog/restaurant-benchmarks/)
- [Email Marketing Benchmarks 2026 — Klaviyo](https://www.klaviyo.com/uk/blog/email-marketing-benchmarks-open-click-and-conversion-rates)
- [Klaviyo Benchmarks by Industry 2026 — GOSH Digital](https://www.goshdigital.co/blog/klaviyo-benchmarks-by-industry)
- [Klaviyo Flow Benchmarks — BS&Co](https://bsandco.us/blog-post/klaviyo-flow-benchmarks)
- [Email Marketing Benchmarks 2025 — MailerLite](https://www.mailerlite.com/blog/compare-your-email-performance-metrics-industry-benchmarks)
- [Restaurant email marketing statistics — Stripo](https://stripo.email/blog/restaurant-email-marketing-statistics-how-emails-drive-reservations-loyalty-and-revenue/)
- [Transactional Email Open Rates 2025 — Mailer To Go](https://resources.mailertogo.com/statistics/transactional-email-open-rates-benchmarks-statistics-2025)
- [Transactional Email for Marketers — Campaign Monitor](https://www.campaignmonitor.com/resources/guides/transactional-email/)
- [Plain-Text vs HTML Emails — Moosend](https://moosend.com/blog/html-vs-plain-text-email/)
- [The surprising truth about plain-text vs branded emails in 2026](https://business-image.co.uk/plain-text-vs-branded-emails/)
- [HTML vs Text Email: A 2026 Deliverability Guide — MailGenius](https://www.mailgenius.com/html-vs-text-email/)
- [When To Ask for Reviews — PowerReviews](https://www.powerreviews.com/when-to-ask-for-reviews-best-practice-guide/)
- [Review request timing by industry — Widewail](https://www.widewail.com/blog/when-to-request-reviews-and-videos-the-ultimate-guide-to-review-request-timing-by-industry)
- [Hotel & Hospitality email examples — Really Good Emails](https://reallygoodemails.com/categories/hotels-and-resorts)
- [Email Design Best Practices for Luxury Hotels](https://www.americasgreatresorts.net/email-design-best-practices-for-luxury-hotels-creating-visual-masterpieces/)
