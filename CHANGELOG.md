# Changelog

All notable changes to the GenUI framework, in [Keep a Changelog](https://keepachangelog.com/) shape: everything lands under **[Unreleased]** until a release exists.

No release has been cut yet - no npm/PyPI publish, no git tag (the Zenodo DOI is a frozen master thesis snapshot, not a package release).

The entire history lives below, newest first.

## [Unreleased]

### A shared model can grow a field that only one of its readers learns about

`StatItem` is the shape of a metric and two types use it. When the metric grid gained a movement, the field went on the shared model and the numeric guard learned to check it in the grid's branch alone. From that moment the other type could carry a delta nobody checked: not visible on a page, because that component draws no movement, and sitting in the payload all the same, absent from the removals the response declares.

- **The field now belongs to the type that draws it.** The shared model is a figure and its label again, and the movement lives on the metric the grid uses. A field no renderer reads is worse than dead code: it reaches the model in the JSON schema, costs tokens in every request, and invites a number that will never be looked at. It is gone from the schema that type receives, which is half the point.
- **The map of grounded fields is no longer maintained by hand alone.** A check walks the component schemas, finds every field whose value is a number shown as content, and builds a payload where that field carries a figure the input never mentioned. The chain has to remove it. The failure message names the type and the field, because it will be read by someone adding a component in a hurry.
- **Proved both ways**: with the fix reverted the check goes red on the exact field, and with a grounding line removed from an unrelated type it goes red there instead. A check nobody has seen fail is a check nobody has tested.

### Questions that open, and the markup that was left out on purpose

`faq` is a new dictionary type: a title, an optional introduction, and 2 to 12 questions that open onto their answers. Answers carry simple markdown and go through the same sanitized renderer as every other piece of model written prose.

- **The browser already had this.** `details` and `summary` give open and close, keyboard operation and the right screen reader announcement, in server rendered HTML, with no script. Grouping them with the `name` attribute gives the exclusive accordion where it is supported, and where it is not, more than one stays open, which for a list of questions is a fine place to land. The shape this came from reached for an accordion library, an icon library, a variant helper and a headless primitive to arrive at the same behaviour.
- **No FAQPage structured data, and the reason is in the component.** The zone already emits a JSON-LD block saying a model wrote this content. A second block telling search engines these are the site's official frequently asked questions would make two opposite claims about the same text, and only one of them is something this framework can stand behind. Someone will want to add it in good faith, so the comment explaining why it is absent sits where they will look.
- **The content is in the HTML before any script runs**, which a test pins with `renderToString`. That is the property the native elements buy, and the one a rebuilt accordion loses.
- Numeric grounding still does not reach into prose, by the decision already documented, so an answer that mentions a figure is not checked. The URL whitelist and the content policy do apply, and a link to an address that was not in the input does not survive an answer.

### A grid of numbers that never said what it was counting

`stats_banner` was two fields, `stats` and `columns`. It rendered a row of figures floating in a page with nothing around them, and no way to say that one of them moved. It now takes an optional eyebrow, title and paragraph, an optional two column layout that puts them beside the grid, and an optional movement per metric. A second stats type would have given the catalog two entries for one intent and the model a coin to flip, so this is the same type with more shape.

- **Direction and sentiment are separate fields, and nothing derives one from the other.** Which way a number moved is a fact. Whether that is good news depends on the metric: cost per acquisition, churn and response time going down is the win. The reference this shape came from colors the down arrow like an error, which paints the best figure of the quarter red. Here sentiment is optional, and without it the movement is shown in a neutral tone that states the direction and claims nothing else.
- **The meaning is not in the color.** The arrow points where the number went and the delta carries its own sign, so the tone is the third carrier rather than the only one. The two tone tokens already in the theme do the coloring, no new knobs.
- **The delta is grounded like the value.** A number displayed beside a figure is a claim like the figure, so an unverifiable one takes its stat out with it. This is exactly the detail that gets missed when a type grows a field: the guarantees stay on, and one invented number sits on the page anyway.
- **Nothing that worked changes.** Every new field is optional, the default layout is the old one, and a test pins the old payload down to the class names it renders.
- Two columns with an empty one is refused at validation, since `split` without a title is the hole this project turns down everywhere else, and the component falls back to the plain grid if a host sends it anyway.

### One section, two rules of truth

`metrics_trend` is a new dictionary type: a title with a quieter second half, 2 to 6 headline figures, and the curve behind them drawn as an area under a line. It says how big and how it is going in one band.

- **The two halves cannot fail the same way, so they do not.** A figure in the grid is a claim on its own: an unverifiable one is removed and the others stay, the way a stat already works. A point on the curve is a claim about a shape: an unverifiable one takes the whole curve, the way a chart point already does, because a line missing a point is a different line and not a rougher one. What is left is a grid of metrics, which is a finished section that tells the scale instead of the growth. Below 2 surviving metrics there is no grid either, and the component goes.
- **The curve is a hand written SVG path, not the chart engine.** The engine sits in a lazy chunk of about 113KB gzipped, which is a lot to load for a shape with no axes, no legend and no tooltip. The path is a dozen lines, renders on the server with no suspense boundary and no loading skeleton, and takes its stroke and its gradient from the accent token rather than from a library prop. No new theme knobs: a curve that is not the accent color is not a need anyone has stated.
- **The points are in the DOM as text**, because a curve is data. The ends of the range sit under the line and the full list is there for assistive technology, so nothing is readable only by looking at the path.
- **A value that is not a number draws nothing.** Dropping the point or placing it at a made-up height would both change the shape of the claim, so the curve goes and the grid stays, which is the same degradation the guard produces.
- A golden fixture falsifies both halves in one recorded response, an invented metric beside an invented point, so a future change that collapses the two rules into one goes red.

### The bento was a grid with a name

3 cards to a row, all the same size, and the fourth alone in a third of the last row with empty space beside it. Cells that are all equal are a table of links. Nothing says which card matters, and the leftover one looks like the layout ran out of content instead of adapting to it.

- **One card leads.** It takes two thirds of the width and 2 rows, and the rest fill around it in threes. That holds at 3 cards and at 12, so the shape says what is important instead of listing everything at the same weight. Order is the default statement of importance, and `featured: true` is how a model names the leading card whatever position it wrote it in. Two claims to it are no claim: the first wins.
- **The last row is always divided between the cards in it.** One left over takes the full width, 2 take half each, 3 take a third. Nothing sits in a fraction of a row with a hole next to it, at any count.
- **Four across stays even**, because that density is something the host asked for explicitly, not an editorial layout to reinterpret.
- **Twelve columns underneath**, since 2, 3 and 4 all divide it, so every arrangement lands on whole tracks. The spans come from one pure function. Its test lays every count from 2 to 14 out the way the browser does, and fails if a single row is left short or if every cell in a layout ends up the same width. Measured in a real browser too: the leading card comes out 656px tall against 320 for the others, and every row covers the full width.
- **Narrow widths still collapse**: half width under the section breakpoint, full width under the small one, with the 2-row lead flattened so it cannot outrun the column it lives in.

### A pinned photo is not a card, and a card that goes nowhere is not clickable

Both came out of one real render. 10 stock photos were pinned so the components would have images to use, and the zone came back with a bento full of cards titled "Portrait, neutral background" that opened a raw JPEG when clicked. The ones that were not links still showed a pointer cursor and grew on hover. They promised a destination that did not exist.

- **Pinned images are material, not content.** An image URL can only reach a render by being pinned, because the whitelist refuses everything the input did not carry. So pinning a photo means "you may use this" and never "put this on the page", and its title and description are notes for whoever composes the zone, not copy for the visitor. Unused image items are no longer appended as cards, on the generated path and on the pinned-only fallback alike, and one the model does use still counts as included. The rule lives in one predicate both paths call.
- **The clickable affordance belongs to the anchor.** The pointer cursor and the hover lift moved from every bento card to the linked ones, so a card with no destination stops looking like a link.
- **A plain string inside a list is content too.** Already fixed in the guard this week, and this render is what it looks like when it is not: the pinned descriptions came back verbatim in the cards.

### The Segment Preview asks for a config nobody wants to write by hand

Rendering an audience against a realistic zone means inventing a business, a visitor mid-trial and a dozen image URLs that resolve, before seeing anything at all. So the page hands that job out. "Draft with an AI assistant" opens a brief, and a click sends it to ChatGPT, Claude or Perplexity with the text already in the box (Gemini, Grok and Copilot have no prompt parameter, so they open on their own page with the brief on the clipboard).

- **The brief asks before it invents.** Its first instruction is a question to the operator: build this around your real site, with the URL, or an invented scenario for testing. Nothing is produced until that is answered, so the output is either grounded in something real or clearly a fixture.
- **It carries the rules the render will enforce**, which is what makes the answer usable: no URL that was not supplied, no figure that does not appear verbatim in the input, and image variants only for components that have an image in the pinned array. A config written without those rules produces a half-empty render and looks like the framework failed.
- **The component vocabulary is passed in, not written into the brief.** It comes from the same `BUILTIN_TYPES` the renderer uses, so the brief cannot drift from the types the library can actually draw.
- **A prompt too long for a URL degrades to the plain chat** instead of being silently truncated by the target, and the clipboard is written either way.
- No vendor logos ship with this. Each product is a colored tile and its name, because approximating someone's brand mark from memory is worse than not drawing it.

### Two columns, and the empty one that would have been a claim

`pros_cons` is a new dictionary type: an optional title and two columns, advantages on one side and limits on the other, each with its own heading and a list of items that may carry simple markdown. Both sides come from the input, the zone context or the retrieved documents. The type description says so to the model, because this is the shape that most invites one to invent balance where there is none.

- **The degraded form is the work.** A column with nothing in it is not rendered as half a grid with a hole: whatever side has content becomes one full-width column, which reads as a decision. With nothing on either side the component is refused at validation and renders nothing at all. Blank entries are dropped before they can become empty bullets, because an empty bullet in a cons column reads as an item withheld.
- **Item text goes through the one markdown renderer that sanitizes.** The library now has a single markdown component, used by the text block and by these items, so the rules that make it safe (URL transform on links and images, links that cannot reach their opener) live in one place instead of being configured twice by hand.
- **Plain strings inside lists were never sanitized, and now are.** The URL guard walked dictionaries and nested structures but skipped string entries in a list, so a markdown link to an address that was never in the input survived inside them. That covers this type's items and, already today, the feature bullets of `pricing_cards`. Fixed in the shared walk, where every type routes through, and the entry keeps the name of the list it lives in so a list of image URLs is still checked as images.
- **Tone is not carried by color alone.** Green against red is exactly the pair a share of readers cannot tell apart, so the heading text and the icon shape carry the same meaning, on every row and not only in the header.
- **Both tones are tokens** (`successColor`, `errorColor`, with controls in the Playground), and the shape follows the corner radius and the spacing scale already there. Measured rather than eyeballed in both themes: the heading tints and their text clear 4.5:1 in light and dark. They did not at first, because a green that reads on a dark surface loses against a pale tint on white.

### One failed read at mount decided the theme for the whole session

The Segment Preview reads the theme saved for the tenant and renders every audience with it, so what you see is what that tenant is served. It read it once, when the page mounted, and threw the error away. A backend still booting, a reload in flight, a theme saved in the Playground a minute later: any of them left the page rendering library defaults for every run after that, until a navigation happened to remount it. The note under the button said "No theme saved for this tenant", a statement about the tenant standing in for a failed request. Reproduced end to end: backend down at mount, up at render time, and the page never recovered on its own.

- **The saved theme is read again before every run**, alongside the renders, so a run costs the same wall clock and always paints with the theme stored right now. The read is tied to the action that needs it instead of to the lifetime of a component, so a transient failure costs one run and heals on the next. Verified against a real backend twice: a theme changed from outside lands on the next run with no navigation, and a read that failed while the backend was down recovers as soon as it answers again.
- **A failed read no longer reports itself as "nothing saved".** Three states, three sentences: applied, nothing saved yet, or could not be read, with the reason. A swallowed error that reads as a fact about your tenant is worse than an error.
- **An empty audience says why it is empty.** It used to offer both explanations at once ("nothing generated, or everything was removed"), while the payload already knows which one it was: nothing removed by the chain means the model returned an empty zone, and the model's own reasoning is printed under it. A zone with no pinned content and nothing retrieved has nothing to curate, and this system does not invent content to fill it.

### Bars that compare, and the one guard that had to be extended by hand

`comparison_bars` is a new dictionary type: a title, an optional subtitle, and 2 to 6 vertical bars, at most one of them highlighted as the page's own. It is the most persuasive thing the model can put on a page, so it was worth checking what protects it before drawing it. The URL whitelist, the content policy and the provenance walk any string on their own. Numeric grounding is the one guarantee with a hand-written map per type, so a numeric component that is not added to that map ships with every guard apparently on and none of them looking at its numbers.

- **A bar value is content, so it is in the grounding map.** A value survives only if its digits exist in the input, like a stat or a price.
- **Nothing is removed: the whole component falls.** The rule the chart already had, and it is stronger here. Dropping the one bar whose figure could not be verified produces a comparison more flattering than the truth, so an untraceable value takes the component with it, and so does anything that would leave fewer than 2 bars. The prompt tells the model to copy figures from the data rather than estimate them: the instruction is the quality lever, the guard is the guarantee.
- **A recorded adversarial response defends it over time.** `backend/tests/golden/comparison_grounding.json` holds two comparisons, one with an invented competitor figure beside two real ones. The invented one has to disappear whole and the grounded one has to survive intact, so a future change that quietly starts trimming bars goes red.
- **Heights are relative to the tallest bar, never to a hundred**, so percentages and absolute figures render with the same shape. Labels and values stay in the DOM as text, the highlighted bar is marked by `aria-current`, weight and a pointer as well as by color, and the callout is optional: without it the chart closes back up instead of keeping an empty band where a bubble would have been.
- **No theme knobs of its own.** The highlighted bar takes the accent color, the others the surface-3 token, and every bar the corner radius. Three dedicated tokens would have been three more names to keep in sync for a result the existing ones already give, and a control that repeats a control is a control nobody trusts.
- **The type is offered on both surfaces.** A comparison presents content rather than opening a page, and "how does this compare" is a question a chat answer gets asked directly.

### A component type described twice, in two prompts that had already drifted

The name of a type lived in a tuple, its shape in a Pydantic model, and the description the model actually reads was written by hand inside two different prompts. They had drifted by three types: the zone catalog listed fourteen, the chat catalog eleven, and `case_studies`, `quote` and `logo_wall` had been added to one and not the other. The structured mechanism for describing a type already existed and was used for the components a customer registers, so the only types described twice were the ones this project controls.

- **The description sits next to the declaration.** `BUILTIN_TYPE_DOCS` in `backend/schemas/registry.py` is the dictionary, and `BUILTIN_TYPES` is derived from it, so a type is named once and described once. The entries stay hand written: printing the generated JSON schema of fourteen types into every request, the way an unknown custom type needs, would cost more prompt than it buys.
- **Each surface declares what it exposes.** `EXPOSED_TYPES` on `ZoneAgent` and on `ResponseAgent`, which feeds both the catalog and the type union in the JSON the model must return. A surface is now a list of names rather than a wall of prose.
- **Facts moved, advice stayed.** "PREFERRED for content zones" and "use sparingly in zones" describe the zone, not the component, so they travel as surface notes and remain in the zone prompt, which lost nothing. The dictionary carries only what holds wherever a component renders: the shape of its data, and the rules that hold everywhere, like an image variant needing its image.
- **A chat answer can now produce `case_studies`, `quote` and `logo_wall`, and is no longer offered `hero_banner`.** The test is what a component is for, not taste. A hero is the device that opens and frames a page, so in a conversational answer it is a banner dropped mid-sentence, while every other type presents content and content reads well on both surfaces: a wall of logos answers "who are your investors" better than a bullet list. `quote` is the case that shows how to apply the rule. As an editorial device it is a full page pull quote, close to a hero, but in a chat backed by a document base it is the natural way to show a verbatim passage. When a component has two jobs, the one it does on that surface decides.
- **Two real differences between the surfaces, neither of them about the list.** A chat catalog now says to leave autoplay off, because a transcript scrolls while the reader is still reading, and to prefer compact shapes, because an answer is read inside a column that can be narrow.
- **`backend/tests/test_type_catalogs.py` makes it a rule instead of a habit.** It checks both directions: every type a surface declares exists in the dictionary, and every type in the dictionary is exposed by some surface, so a component added and wired nowhere goes red instead of shipping unreachable. The failure message names the type and the surface. It reads the declarations out of the agent sources so it runs in a bare shell as well as in a full environment, and a second check compares the composed prompts against the same declarations wherever the application configuration is installed.

### A registration that looked like it worked and never rendered

`registry.ts` reserved 4 names while `ComponentRenderer` had explicit cases for 14, and the registry lookup sat in the switch's `default` branch. So `registerGenUIComponent('hero_banner', AcmeHero)` was accepted, stored, and then never reached: the `case 'hero_banner'` above it drew the framework's own component instead. The backend refused the same name in `custom_components` at the other end. Both halves failed silently, in opposite directions, and the README documented `hero_banner` as the example custom component, so the one snippet most likely to be copied was the one guaranteed not to work.

- **The lookup runs before the switch, so a registration always wins.** The alternative was to reserve the 10 missing names and throw, which turns a dead registration into a clear error. It also throws at module scope, where hosts are told to register, so a name collision would stop the app from booting instead of dropping one component. The permissive direction is the useful one anyway, because overriding a built-in is a feature people want.
- **Re-skinning a built-in is now the supported path.** Register under `hero_banner` and the model keeps generating `hero_banner` with the schema, the grounding and the layout coherence it already had, while your component draws it. No schema to write, no `customComponents` prop, no backend change.
- **An override inherits the data shape of the component it replaces.** Built-in types get the camelCase payload their own component would have received, so `primary_cta` arrives as `data.primaryCta` and the override is a drop-in. Custom types still get their payload exactly as their JSON Schema declared it. Replacing a framework component means inheriting its shape, declaring your own means owning it.
- **The name still cannot be redefined.** `custom_components` keeps refusing built-in names, because the schema is what the prompt teaches the model and what the guards validate against. A page can change the markup and never the contract.
- **`BUILTIN_TYPES` is exported and is the single source of truth.** It drives the camelCase decision, so a section component added to the renderer and not to the list would silently start handing snake_case to its overrides. A test asserts the length.
- **`frontend/tests/component-override.test.tsx`** covers the override winning, both payload shapes, and the list. Verified failing without the fix, so it guards the behaviour rather than restating it.

### The health probe was the most expensive route in the process

The search path was already asynchronous, so the RAG the product actually runs was never the problem. The problem was `/health` and `/ready`. Both rebuilt an entire vector store per call, and building one means collection bring-up, dimension validation and an embedding client, all over the synchronous Qdrant client, all on the event loop. Three to four blocking round-trips per probe, on every replica, every few seconds. A slow Qdrant did not degrade the service: it stalled the workers through the very probes meant to notice, and an orchestrator then killed processes that were serving fine. That is the exact inverse of what a probe is for.

- **The store is built once per process.** Same shape as the orchestrator singleton and the embedding client: the expensive, stateful part is constructed on first use and reused. The agents share it too, so a zone render, a chat and a document listing now talk to one connection instead of three.
- **A failed first construction is not remembered.** A Qdrant that is not up yet raises, the caller reports the dependency as down, and the next call tries again. Caching that failure would pin the process to a lie for its whole lifetime, which is how a five minute outage becomes a permanent one.
- **The connection is reused, the answer is not.** `/health` still makes a live round-trip on every call, because that is the only thing that can tell a healthy dependency from a dead one. A reused handle must never be able to report health it did not verify. With Qdrant unreachable the body still says `qdrant_connected: false` and `degraded`, and the health, ready and live contract is unchanged: Qdrant down is degradation, not unreadiness, so the replica stays in rotation and keeps serving from cache.
- **Nothing synchronous is left on the event loop.** The probe offloads explicitly. The document routes that had nothing to await are simply declared synchronous and the framework runs them in its threadpool, which is the shorter diff and the same result. The file upload route keeps its `await` and hands off the blocking half. Admin routes are lower frequency, not lower risk: one slow listing on the loop stalls every render the worker is serving beside it.
- **`QDRANT_TIMEOUT_SECONDS`, default 2**, matching the cap already on the Redis handle. A hung vector database costs one slow operation instead of a stuck worker. Raise it for bulk indexing into a remote Qdrant; the upload response reports `chunks_indexed`, so a cap set too tight is visible rather than silent.
- **One ingest path instead of three.** Chunking and indexing lived copied in the two upload routes and the background task, each free to drift on how it stays off the loop. It is one function now, and the background task is synchronous so it runs in the threadpool like the rest.
- **The proof is a test, not a claim.** A fake that sleeps synchronously while another coroutine has to keep advancing: 26 ticks with the offload, zero without it. Plus the store built once, the failure not cached, and health still truthful with Qdrant refusing connections.
- **The unused synchronous `search()` wrapper is gone.** No caller, and with a shared store its `asyncio.run` would have handed the async client a second event loop. Dead code whose only remaining job was to be a trap.

### The chat was outside the cap that was supposed to cover it

The cost controls protected the zone path and stopped at its edge. Every chat message starts two model calls, three when the request carries behavior data, and not one of them touched the per-tenant budget. With the default limit of 120 requests a minute and a `pk_` key that ships inside the page, that was room for roughly 21,600 generations an hour on the operator's key, counted nowhere. The README promised that a public credential cannot convert traffic into spend, so either the chat came under the promise or the promise had to be rewritten.

- **A chat message is charged for the generations it makes.** `POST /query` now spends 2 units of `LLM_BUDGET_PER_HOUR`, or 3 when it carries behavior data, because that is how many agents run. A cap that counts one where the system spends three is worse than no cap: it reads as protection and is not.
- **The count lives next to the fan-out that produces it**, in the orchestrator, so an agent added to the parallel run cannot be spent without being counted. A test runs the real agents against a counting client and fails if the declared number and the calls made ever disagree.
- **The budget moved into `api/deps.py`**, next to the other shared singletons, and both routers read it from there. It used to live inside the zone router, and the alternative was one router importing another to reach it. Behavior on the zone path is unchanged, one unit per generation, admin exempt, cache hits free.
- **Over the cap, chat answers stop.** A zone render degrades invisibly because a cached copy exists. The chat has none, and the answer itself is the expensive call of the three, so dropping the accessory analyses would save the small half and still spend the large one. The request returns 429 and names the knob to turn.
- **Admin keys stay exempt on both surfaces**, so an operator's own traffic never competes with the cap protecting them.
- **The three agent fan-out stays as it is.** The profile analysis is what makes a profile progressive rather than a form someone fills in, the behavior agent already runs only when the page sends behavior data, and cutting either per message would trade a visible cost for an invisible loss of the thing the product sells. What was missing was not restraint, it was the meter.

### The compliance story gets a public URL

The four statements in `deploy/` are written for a legal team and read by whoever already cloned the repository. The person deciding whether this project is worth an hour lands on the Studio instead, and left without knowing any of it exists.

- **`#/compliance` in the Studio**, public like `#/about`: no key, no gate, no backend, in the GitHub Pages build. It answers in order what gets generated and how the system says so, what is touched on a visitor's device and what happens when consent is refused, where the data goes and the configuration where none of it leaves, and which rights are endpoints rather than intentions.
- **The half a compliance page usually omits is a section of its own.** What stays with the operator: the lawful basis, the consent platform, the impact assessment, and the two sentences that are easiest to fudge, that configuration approval is not editorial review of generated text, and that the use boundaries are documentation with no code path enforcing them. Mechanism and responsibility are told apart by a label and by layout, never by color alone.
- **The disclaimer sits on the page**, at the top and at reading size, because "engineering documentation, not legal advice" is part of the argument rather than a footnote to hide. Nothing not implemented is described as active: there is no signature claim, no human review claim, no claim of conformity anywhere, and `studio/tests/compliance.test.cjs` fails if one appears or if a linked document is renamed out from under the page.
- **The footer moved under every page** and now opens with that link, ahead of the two external ones. It is not navigation: it is where the project says who built it and what it answers for.

### The compliance statements a regulated buyer asks for first

`deploy/` already held the two documents nobody else in this category writes: the tenant isolation statement and the output guarantees, both shaped to be attached to a contract, both naming the code behind every row. The third and fourth were missing, and they are the ones a DPO and an in-house lawyer open before anything else.

- **`deploy/AI-ACT.md`**, for the legal team. The role map for an on-prem deployment (the customer is provider and deployer, the framework author is neither), with the note that the open source exception of Art. 2(12) explicitly does not reach Art. 50. One table row per obligation (50(1), 50(2), 50(4), 50(5), plus the default posture) with the mechanism, the symbol and the test.
- **The two sections it would have been easy to fudge.** What the `verbatim-from-input` evidence is actually worth against the Art. 50(2) exemption: a fact for your counsel, computed strictly, defaulting to `generated` whenever the comparison is uncertain, and never an exemption the system grants itself. And what the zone registry's approve covers: the configuration, not the generated text. Approving a prompt is not reviewing an output, so the document says there is no human-in-the-loop review of generated text here, rather than letting a reader assume there is.
- **Use boundaries, written to protect both sides.** GenUI curates presentation and decides no price, no eligibility, no coverage, no hiring, no creditworthiness. Wiring it into one of those moves the system into Annex III and changes the whole regime. The points the target verticals actually come near are named (4(a) targeted job ads, 5(b) credit scoring, 5(c) life and health insurance pricing), each with what helps here and what is simply absent. Same for Art. 5: the segmentation dimensions are fixed and inspectable, and the values inside them are host-supplied free text that no code inspects, which is stated instead of implied.
- **`deploy/GDPR.md`**, for the DPO. A pre-filled records-of-processing table, lawful basis mapped to what is actually touched (with the ePrivacy Art. 5(3) and CJEU reasoning), a request runbook with the real endpoints and real commands for access, rectification, erasure and objection, the retention matrix with the real env vars and defaults, and a DPIA input sheet listing this system's genuine risk factors beside the measures already in the code.
- **A transfers table that reads every relevant setting**, including the parts that are inconvenient: what a prompt carries to the LLM provider (a shared render sends the segment archetype, a live render sends the profile), that the chat question reaches the embedding endpoint too, that `GLMOCR_API_KEY` sends whole documents to a third party, that OTel spans carry no content but FastAPI instrumentation records the request path and the per-user routes carry the user id in the URL, and that the default audit sink ships user identifiers to whatever log pipeline you run. The configuration where nothing leaves the perimeter is written out in full.
- **`deploy/posture.sh`**, new. Reads `customer.env` and checks the deployment against what those documents describe: disclosure on, dev-open off, keys and user-token secrets declared, retention set, audit configured. Then it prints the egress map for the configuration in front of it and exits non-zero on a mismatch. Kept separate from `smoke.sh` deliberately: that one needs a running stack and stops at the first failure, this one needs nothing running and must report every finding in one pass.
- **The documents cannot rot in silence.** `backend/tests/test_deploy_docs.py` extracts every `file:symbol` reference from `deploy/*.md`, checks the file exists and the symbol is still in it, and covers all four statements. A rename now turns the suite red instead of leaving a false claim attached to a contract.

### Consent decides, and without it the page is still personalized

`consent` existed on `useGenUI` and nowhere else. `GenUIZone` and `useZone`, the path the Quick Start puts in front of every new integrator, had no consent prop at all and read and wrote the profile in IndexedDB regardless. Storing or reading information on someone's terminal equipment is the thing consent is required for, and it is required as consent given, not consent assumed.

- **BREAKING, and the point of the change: no consent, no device access.** Without an explicit `consent={true}`, the library writes nothing to and reads nothing from IndexedDB, sends no `userId` in render, chat or event requests, and starts no behavior tracker. It used to do all three on its own. **Migration**: pass `consent={true}` (from your CMP, or unconditionally where your own lawful basis says you may) to `GenUIZone`, `useZone` or `useGenUI` to get the previous behavior back. Nothing else changes.
- **The zone still renders, and is still curated.** An anonymous request lands on the path the backend already runs for every unidentified visitor and for the control arm of a holdout: segment `anon`, render generated from the segment archetype. So the degraded mode is a declared product level, personalization that needs no consent banner, not an outage.
- **One gate, three consequences.** `consentGranted()` in `utils/privacy` is the single definition; the hooks apply it once and derive the profile read, the behavior payload and the identifier from it, instead of three guards drifting apart.
- **`privacy` and `consent` are now on `GenUIZone` and `useZone`** with the same meaning they have on `useGenUI`.
- **A zone starts the page tracker itself once consent is granted.** Behavior capture used to start only from `useGenUI`, so a page built out of zones alone collected nothing and never said so. One tracker per page: a second zone leaves the running one alone rather than resetting the session's signals.
- **The Do Not Track and Global Privacy Control checks are gone**, because they can no longer change an outcome: nothing runs without an explicit grant, and an explicit grant already outranked the ambient signal. The behavior is strictly more protective than before, never less.
- **No identity, no per-user state, server-side.** A request whose `user_id` is blank, whitespace or a client-side placeholder (`anonymous`, `undefined`, `null`, ...) creates no profile: renders and chat degrade to the anonymous path, and `POST /profile/sync`, whose entire purpose is to store one, answers `400` instead of quietly writing a profile every anonymous visitor would share. The refusal lives in `ProfileStore.set`, the one place per-user state is born, so no caller can route around it.
- **`GET /api/v1/profile/{user_id}/export`** returns everything the deployment holds about one person: the stored profile plus the audit entries naming them (renders, queries, impressions, clicks, syncs, updates, erasures). It reuses the audit read path, so tenant scoping and filtering cannot drift from the audit viewer's, and it carries the same signed-identity guard as the other per-user routes. When the trail goes to your log pipeline it reports `queryable: false` with a pointer, never an empty history.
- **Erasure now states what it does not erase.** `DELETE /profile/{user_id}` removes the profile and answers `profile_erased` / `audit_retained` with a note. The audit trail is append-only accountability evidence, and in the production sink it has already left the process for your log pipeline; it is bounded by retention rather than edited, and the erasure is recorded in it, so a later export shows when the right was exercised.
- **`PROFILE_TTL_SECONDS` now defaults to 90 days** of inactivity instead of keeping profiles forever (`0` still means forever, as your own storage-limitation policy to justify). Every retention default is written down in one place, the Retention table in the README.

### Generated content says so, to a machine and to a person

A response carried `confidence`, `reasoning`, `cache`, `render_id` and `sanitization`. Nowhere in it, in the DOM, or on the page did it say that a model had written the words. There was not even a setting to get wrong. That is the gap this closes, and the marking is on by default because a default that under-discloses sends the bill to whoever trusted it.

- **Every served payload carries `meta.disclosure`**: whether a model wrote the content, when it was generated, the system that produced it, and the provenance of the visible text. Sync render, SSE `complete`, batch, warmup, every cache hit, and the `/query` answer. One test per path.
- **Computed into the cached payload, never when serving.** A cache entry goes to a whole segment for up to the stale window, so a serve-time timestamp would date the content by the moment it was copied out of the cache instead of the moment the model wrote it. The block is built where the payload is born (`_payload_from_result`, the single constructor for every non-streaming path and for the stream's `complete`), so every later hit repeats the generation timestamp unchanged.
- **A fallback render is marked as not generated.** When generation fails, ordinary code assembles the zone from your own pinned content, and that payload is cached and served like any other. Calling it AI-written is a lie in precisely the direction the marking exists to prevent, so it says `ai_generated: false`. Same for the chat fallback, whose two sentences are written in the source file.
- **`provenance` is computed from the real input corpus**, the one the URL whitelist and numeric grounding already read: `generated`, `verbatim-from-input` (every visible string appears word for word in your input) or `not-generated`. It is evidence for your own assessment and exempts nothing on its own. A zone can take every URL and every number from your input and still be prose a model wrote. So `generated` is the default, and anything unprovable stays `generated`.
- **One setting, safe by default**: `GENUI_DISCLOSURE_OFF` removes the block, the markup and the notice, declares that you inform users elsewhere, and logs a warning at every startup. `DISCLOSURE_EXPOSE_MODEL` (off) adds the model name: the reader needs to know the content is AI-generated, not which model wrote it, and naming it publishes an attack target and your vendor choice at once.
- **Machine-readable in the served HTML**: `GenUIZone` emits JSON-LD with `digitalSourceType` from the IPTC vocabulary, the one C2PA uses (`trainedAlgorithmicMedia`, `compositeWithTrainedAlgorithmicMedia`, `algorithmicMedia`), plus `data-ai-generated` and `data-ai-provenance` on the zone root. Inline, not from an effect, so it lands in `renderToString` output and in the first paint of a streamed render, with a `renderToString` test to keep it that way. The JSON escapes `<`, so content can never close the script element.
- **Readable by a person**: a visible line of text, on by default while a zone shows generated content, styled with the existing `--genui-*` tokens (readable in both color modes, nothing carried by color alone, no aria trickery). `disclosure={{ text, position }}` sets the wording, which is a legal choice, and where it sits. `disclosure={false}` drops the visible line and keeps the markup. It removes itself when a render turns out not to be generated.
- **The notice is tenant configuration, so it lives in the theme**: `disclosureEnabled` (on by default), `disclosurePosition` (above or below the content, aligned left, centered or right: six placements), `disclosureText`, `disclosureFontSize`, `disclosureOpacity` join `GenUITheme` and the per-tenant theme store, edited in a new "AI Act & GDPR" section of the Theme Playground and previewed on a stand-in zone: the library's own loading skeleton stands in for a generated component, so the notice is the only thing to look at, and the wrapper classes are the library's own, which means the six placements behave there exactly as they do on a real zone. Wording and placement are one decision for a whole brand, not a prop to repeat on every zone, and the store already had the whitelist, the audit event and the Studio save/load. A `disclosure` prop on a zone still wins: it is the more specific statement. Only the two visual knobs become CSS custom properties; wording is text, rendered by React, and never reaches a stylesheet.
- **The size knobs have a floor** (11px to 24px, opacity 0.6 to 1), enforced in the library, in the Playground sliders and in the stored contract, so a hand-written `PUT` cannot go under them either. The notice can be made discreet and cannot be made invisible: styling a transparency obligation into a 4px ghost is the one outcome the whole mechanism exists to prevent. Color is deliberately not configurable: it follows `--genui-text-secondary`, which already has a value per color mode.
- **`GenUIDisclosureNotice` is exported**, because `GenUIZone` is not the only way generated content reaches a page: a host driving `useZone` with its own rendering, and the Studio previews, show the same content and owe the same line. One component, one class, one set of tokens, so the notice cannot grow a second look. The Segment Preview and the zone draft preview now render it from each render's own marking (a pinned-only fallback correctly shows none) and list the marking in the per-audience meta; the Theme Playground previews it on its own stand-in zone.
- **For the chat**, where the information is due at the latest at the first interaction, `useGenUI` returns `disclosure.notice` before anything has been sent (`disclosureText` overrides it), plus `disclosure.lastResponse` for hosts that also label each message.
- **No C2PA signature, on purpose.** C2PA 2.4 carries manifests in HTML and defines a `c2pa.ai-disclosure` assertion, and it would be the stronger answer. A manifest is worth what its certificate chain is worth, though: signing identity, key custody and revocation belong to the deployment, not to a package that ships as source. What GenUI emits is a declaration that whoever controls the response can strip, and it is shaped so a signature can be bolted on later without moving it. The verbatim check states its own ceiling too: substring matching on lowercased, whitespace-collapsed text, so reflowed or re-punctuated text reads as generated, the only direction this check is allowed to be wrong in.

### The component budget reaches the library, and the docs reach the code

The zone component budget was enforced server-side and invisible everywhere else: no React prop, and not one line of documentation, even though it decides what a visitor actually sees (a zone renders at most 2 components).

- **`maxComponents` prop** on `GenUIZone` / `useZone` (1..10), sent as `max_components` and **omitted when unset**, so the backend still falls back to the zone's approved registry config and then to `ZONE_MAX_COMPONENTS`. It is a reactive prop like the others (changing it refetches), with a test that asserts both halves: the key is absent when unset, and the value travels when set.
- **README**: a "Component budget" section (the three levels, the pinned exemption, the ceiling-not-target rule), the budget in the Quick Start env block, `meta.behavior` documented on `useGenUI` (with the honest note that `userType` is a segment factor while `engagementScore`, model-estimated, is not: the `eng=` bucket comes from scroll depth so a segment stays reproducible), and the separate link/image whitelist stated in guarantee 3.
- **Studio Content Policy had no section at all** (its screenshot was the only unreferenced one, and `/api/v1/content-policy` the only endpoint absent from the README), plus a new table indexing every endpoint with the key it needs and the section documenting it: the API reference covered only RAG, `/query` and `/zone/render`, so the whole control plane was undiscoverable.
- Structure and data flow caught up: the four new routers and `zones/registry.py` in the tree, the registry resolution step in the render pipeline (it is the first one and was missing), the segment cache in the diagram (it read as "every render calls the LLM"), 10 section components instead of 7, "Config as Data" in the feature list.

### A zone no longer says the same thing twice

The components of a zone are read top to bottom as one band, but the model writes them in one shot, and it showed: a hero with two CTAs pointing at the same URL, followed by a full-width card whose entire content was that same link under the same label. Three elements, one piece of information. The prompt already asked for restraint, which is exactly why this needed enforcing.

- **Redundancy guard** (`utils/redundancy_guard.py`), a new deterministic step in the guarantee chain (`validate -> URL guard -> numeric grounding -> content policy -> redundancy -> pinned`), on both zone paths: the same link target twice inside one component loses the repeat; an element with the same target AND the same wording as an earlier component is removed; a component emptied that way is dropped whole. Removals are reported in the existing `meta.sanitization.dropped_components`, so the Studio preview and the audit trail show them with no new field. One guard instance per render, which is what makes the streaming path see what the visitor has already been shown. `DEDUP_COMPONENTS_ENABLED=false` opts out.
- **Prompt rule 11**: each component must earn its place given the ones before it. Two CTAs are for two different destinations; a single leftover action is a `buttons` component, not a full-width card; the same content restated as a different component type is still the same content; and when nothing new is left, emit fewer components.
- **Pinned presence was reading half the page**: `_enforce_pinned` looked for a pinned item in bento cards and buttons only, so a pinned link the model used as the hero's single CTA (which is exactly what the prompt asks for) looked missing and was appended again as a card with the same label and the same link. The model was punished for doing the right thing. Presence is now read from the whole component tree by field name (`_collect_shown` + `is_url_field`, shared with the URL guard), so it cannot go stale the next time a component type is added, the way the per-type scan did after the enterprise components landed. The other half of the guarantee is unchanged and tested: a pinned item the output really ignores is still appended.
- **Honest limit, stated in the code and in `deploy/OUTPUT-GUARANTEES.md`**: redundancy is judged on link targets and wording, never on meaning. A component repeating an earlier link under genuinely different wording survives, because whether it adds something is an editorial call a comparison cannot make. Pinned content is exempt by construction (it runs after).

### A tenant's theme has a home

The Theme Playground edited a real theme but its only exits were copy-paste (TS/CSS/JSON/share link), so an operator who rebranded a customer's portal had nowhere to put the result except the host codebase. A theme is config like any other: now it can be stored, reviewed and served per tenant.

- **Per-tenant theme store** (`utils/theme_store.py`): one theme per tenant, Redis-or-memory fail-open. Accepted tokens mirror the Playground whitelist (`studio/src/lib/theme.ts`) token by token, each bound to a closed shape (px sizes, 6-digit hex, a font-stack charset that cannot close a declaration or reach `url()`), so a stored theme can restyle a page but never inject CSS. Out-of-contract values are refused on write and re-checked on read, since Redis is shared infrastructure and the value crosses back into a browser. Unset tokens stay absent, so the library defaults still win.
- **`GET` / `PUT /api/v1/theme`**: the tenant always comes from the key, never the request. `GET` accepts a client key on purpose (a theme is public branding, already visible in the page as CSS custom properties); only admin keys write, and a write is audit-logged as `theme_change` with the admin key fingerprint.
- **Playground: tenant bar in the sidebar**, not behind the Save dialog: pick any tenant already connected in this browser session, see whether it has a saved theme and when, load it, or save the current one. Loading a tenant's theme is the first thing you do on arriving, so it is one click away rather than two dialogs deep. Local-only and tree-shaken from the public build like every admin tool; the exports and the share link are untouched.
- **Segment Preview renders with the tenant's saved theme**: a theme saved in the Playground is what that tenant's pages look like, so previewing a render under the studio's own default theme showed a page nobody is served. Zone governance previews inherit it too (both use the same audience matrix). No saved theme means library defaults, and a theme fetch that fails costs the preview its brand colors, never its render.
- **Honest about the model**: saving stores config that the endpoint serves. It does not make the library fetch or apply anything. `GenUIZone` / `GenUISection` still take the theme as a prop, and a host that wants runtime theming reads the endpoint once at boot and passes the JSON through (the README shows the four lines). Build-time theming via the exports remains fully supported.
- **One tenant-keyed store implementation** (`utils/tenant_json_store.py`): the theme store is the third instance of the same shape (zone registry, content policy, theme), so the Redis-or-memory fallback and the corrupt-entry rule are now decided once. The content policy store was moved onto it with no behavior change.
- Audit viewer: `content_policy_change` and `theme_change` added to the known-event filter.

### Homepage: the console gets its own entry

The second homepage card pointed at the Content Studio, one of the six console tools, which stopped being true the moment the console existed. It is now the console's own card, as a semantic zoom rather than a menu: closed it is a poster with exactly the density of the other card (badge, title, one line, arrow); opening it keeps the card the same size while the title travels up into a header and a typographic index of the six tools takes its place. The title is never unmounted, so it really moves rather than crossfading between two copies: each word is its own element, which keeps a single line of the same text in both states, so shrinking it is a uniform scale with no glyph distortion while the two words travel from stacked to side by side. Closed, the title is two lines at exactly the type scale of the other card. The index only fades in once the title has nearly arrived. Descriptions never appear six at once: one fixed zone at the bottom shows the tool under the pointer or keyboard focus. Escape or the back arrow returns to the poster, and clicking a tool marks that row while the route transition runs.

The tool list lives in one place (`studio/src/lib/console.ts`) and feeds both the nav dropdown and the card, so the two can never drift.

### Tenant switcher in the console

The console showed the active tenant but could only ever work on one: a second tenant meant disconnecting and reconnecting, and nothing stopped a page left open on the previous tenant from writing to it. The scoping is now explicit and switchable, without inventing an auth model.

- **One session per tenant, in the browser session**: the studio holds a connected session for each tenant (URL, admin key, tenant from `/whoami`) instead of a single one, with the active session as the thing that scopes every call. Same tenant name on two backends stays two sessions.
- **Tenant picker in every console page header**: switch between connected tenants, or connect another tenant's key to add it. Switching remounts the page, so one tenant's zones, audit trail, policy or knowledge base never sit under another tenant's name.
- **A stale view cannot write to the tenant you just left**: every console call goes through the active session, and a call made with a session that is no longer active is refused client-side with a clear message. The backend still derives the tenant from the key alone, so this is the only place the drift can be caught.
- **Not an operator login, on purpose**: one admin key resolves to one tenant, so switching tenant is switching key. Accounts, roles, SSO and key issuing arrive with user auth, and are not simulated with a key list in the meantime. The connect gate says so, and the README documents the boundary.

### Content policy write path + Studio editor

The per-tenant banned-term policy was enforce-only from an env var: a compliance owner could not edit it without infra access and a redeploy, so the guarantee was real but the governance was not. Now the policy is live per-tenant data with a face.

- **Per-tenant store** (`utils/content_policy_store.py`): banned terms keyed by tenant, Redis-or-memory fail-open (the S1 registry pattern, reused rather than reinvented; not the registry keyspace, since the policy is tenant-scoped and not zone-scoped). `content_policy.py` and its `policy_for` reader are untouched: `effective_policy` = env policy (`policy_for`, unchanged) plus the tenant's stored terms, so an empty store behaves exactly as before. The global `"*"` stays env-only, so a tenant admin can never escalate a term to every tenant.
- **`GET` / `PUT /api/v1/content-policy`** (admin key): read/replace this tenant's banned terms; the tenant always comes from the key, never the request. A change applies to the next render of every zone and every `/query` with no redeploy, and is audit-logged as `content_policy_change` with the admin key fingerprint. The env terms are surfaced read-only so the owner sees what is enforced deployment-wide but not editable here.
- **Studio "Content Policy" page**, in the console nav: edit the tenant's banned terms (one per line), with the enforce-vs-best-effort split stated in the UI itself: terms are a lexical, word-boundary, case-insensitive match (drop the component, redact chat text); tone, semantics and synonyms are best-effort and never claimed as guaranteed. A pill by the editor opens the read-only deployment-wide env terms. Warns when Redis is down (an edit could be lost on restart). Local-only and tree-shaken from the public build like the other admin tools.

### Console shows the active tenant

The whole studio console is tenant-scoped by the admin key (the tenant comes from the key, never the request), but nothing on screen said which tenant. Now it does, and the connect gate explains it.

- **`GET /api/v1/whoami`** (admin key) returns the tenant the key resolves to. The connect gate calls it to verify the session (replacing the heavier `/documents/stats` probe) and stores the tenant in the browser session.
- **Every console page header** now reads `Connected to <url> · tenant <name>`, so an operator sees on every page (Content Studio, Zones, Audit, Content Policy, Measurement, Preview) which tenant they are editing.
- **Connect gate mini-guide**: a short disclosure explains that keys are configured as `key:tenant`, that connecting scopes the whole console to that tenant, that a bare key maps to `default`, and that another tenant means reconnecting with its key. The explicit in-session tenant switcher remains a separate planned step.

### Audit read path + Studio Audit Viewer

The audit trail was write-only: the backend recorded "what was shown to whom" but answering the DPO question ("what did user X see on day Z?") meant grepping JSONL files or the log pipeline by hand. Now it is queryable.

- **`GET /api/v1/audit`** (admin key): always scoped to the key's tenant, filters for `user_id`, `zone_id`, `event` and `date_from`/`date_to` (YYYY-MM-DD), newest first, paginated (`limit` max 200, `offset`, `has_more`). Cross-tenant reads are impossible by construction: the tenant filter comes from the key, never from the query.
- **Abstracted source** (`utils/audit.AuditReader`): the file sink (rotated backups included) is queryable in place; the production logger sink lives in the host's log pipeline, and the endpoint reports `queryable: false` with a note saying where the events are, instead of a silent empty result. A pipeline-backed reader can implement the same interface.
- **`zone_render` audit events now record `sanitization`**: what the guarantee chain removed before serving (stripped URLs, dropped components, ungrounded numbers, policy violations). The trail claimed to be the compliance artifact; now it actually carries the removals.
- **Studio "Audit" page**, in the console nav: searchable table (user, zone, event, date range) with pagination, and a row detail showing what was served (titles, links, segment, cache state) and what the chain removed. Shows the backend's own "not queryable here" note verbatim when the sink is external. Local-only and tree-shaken from the public build like the other admin tools.

### Zone governance: draft, preview, approve (backend + Studio)

The S1 registry made zone config server data, but only Python could touch it: governance existed in theory. Now it has a workflow and a face.

- **Draft beside approved, not instead of it.** Each `(tenant, zone_id)` now has two slots: the approved record production serves, and a draft slot for edits. Saving a draft never changes what renders serve (before this, an edit overwrote the approved record and silently un-served it). `POST .../approve` is the single transition that changes production, and the cache invalidates itself because the config feeds the cache key. One version counter spans both slots; `expected_version` gives optimistic concurrency (409 on a stale edit).
- **Admin CRUD endpoints** under `/api/v1/zone/config`: list, get, save draft, approve, discard draft, delete. Tenant always from the admin key. Write responses report `storage: "memory"` when Redis is unreachable, so a governance write is never lost in silence.
- **Draft preview.** `preview_draft: true` on `/zone/render` (admin only) resolves the draft slot and forces a live bypass: a draft can be previewed but never cached. Warmup strips the flag, so a draft can never be warmed into the cache real traffic reads.
- **Observed zone catalog.** The backend records `(tenant, zone_id)` in a per-tenant set at every cached render (bounded and deduped: zone_id is logical identity, not per-mount). The list endpoint returns the union of registry and observed zones tagged `ungoverned` / `draft` / `approved`, so a fresh integration sees its real zones with zero setup and the operator adopts them from there.
- **Studio "Zones" page**, in the console nav: zone list with status and traffic flag, editor for the governed block (prompts, pinned JSON, preferred type, max items, component budget), save draft, preview through the audience matrix (extracted into a shared `AudienceMatrix` component rather than duplicated), approve with confirmation, discard, delete. Local-only and tree-shaken from the public build like the other admin tools.
- **Audit.** Every transition (`draft_saved`, `approved`, `draft_discarded`, `deleted`) is a `zone_config_change` event with the admin key fingerprint, on the same trail as renders.

### Three editorial components: case studies, quote, logo wall

Added for studio / agency / editorial zones, where the existing catalog leaned SaaS. Same token system, same validation and guarantee pipeline, no new dependencies (the shadcn/lucide/react-countup/framer references in the design inspiration were re-implemented with CSS tokens, emoji/SVG, and a vanilla count-up).

- **`case_studies`**: projects with an optional image, an optional named reference, and optional result metrics, in an editorial layout: [media + body] divided from the figures by a vertical rule, alternating sides case by case, generous spacing. Metric values are numeric-grounded like `stats_banner` (an invented figure is dropped, the case survives on its text); they count up on scroll into view, static under SSR or `prefers-reduced-motion`, and the settle value is the input string verbatim (no locale reformatting). No image → the case is text-first and the grid reflows (`:has()`), no metrics → the rule and figures column are dropped.
- **`quote`**: a single large editorial quote / manifesto. Author, role, avatar and the top logo are each optional and simply omitted when absent — no initials fallback, the statement is the point. The logo label is never printed beside a logo image (most logo files are already wordmarks); it becomes the image alt, and renders as a text wordmark only on its own.
- **`logo_wall`**: a grid of logos (clients, technologies, partners — the heading names what it shows, it is not client-specific). A logo with no usable image is dropped; the grid centers and wraps; the hover reveal appears only when a real overall cta link is given, otherwise it is a plain static wall.

All three are exported from the package, registered in `ComponentRenderer`, in `BUILTIN_TYPES`, and in the zone prompt catalog. The URL guard now also classifies `logo_url` / `*_logo` as image fields (a link can't fill a logo). The Theme Playground shows each with a full and a degraded example.

### Zone component budget (enforced, default 2)

A zone is one band of a host page — typically sitting between CMS-built sections — not a page. Left unbounded, the model would happily emit five or six components per zone (bento + text + buttons + quote + tabs + steps), wrecking the host page's rhythm. Now every zone render has a component budget:

- **`ZONE_MAX_COMPONENTS`** (default **2**) is the deployment default; `max_components` on the request or in the zone config registry overrides it per zone (1-10). The budget is part of the zone cache config, so changing it invalidates cached renders.
- The model is told the budget (and the "one band, not a page" principle) in the prompt; `apply_component_budget` then **enforces** it after validation on both the sync and SSE paths — extra components are cut in order (first ones win) and reported in `meta.sanitization.dropped_components` as "over the zone component budget".
- Pinned enforcement runs after the budget on purpose: the pinned-content guarantee may exceed the budget rather than be silently dropped.

**Behavior change**: zones that previously rendered 3+ components now render at most 2 by default. Raise `ZONE_MAX_COMPONENTS` or set `max_components` per zone to opt out. Cached renders are invalidated once on deploy (config hash change).

### Degradation audit: every component renders only what it has

Systematic pass over all 14 components for every optional-field subset and cardinality (0/1/2/N items). Most already degraded by design (hero CTAs are conditional, a single tab drops the tab bar, autoplay needs 2+ steps, single testimonial drops arrows/dots, grids cap columns by item count). Three gaps fixed:

- **`pricing_cards`**: a plan with no features no longer renders an empty list; `variant: "detailed"` with a single plan degrades to plain cards (a comparison table of one compares nothing).
- **`quote`**: an avatar without an author is not rendered — an anonymous face attributes nothing.
- **Prompt rule 10 "omit what you do not have"**: the model is told every optional field is genuinely optional (one CTA or none, no figures, no author, two stats instead of four) and that components are designed to degrade — padding a component to look complete is worse than leaving fields out.

Pinned by a dedicated degradation test suite (hero 0/1 CTA, pricing empty features and single-plan detailed, orphan avatar, single tab).

### Images can no longer come from link URLs (enforced)

A zone rendered with a single pinned link would reuse that link everywhere it needed a URL, including as an `<img src>` — a page URL pointed at by an `<img>` renders as a broken image. Root cause: the URL guard kept one whitelist for every URL field, so a link URL satisfied an image `src` just as well as an `href`. Now:

- **Separate image and link whitelists** (`utils/url_guard.py`): image fields (`src`, `image`, `image_url`, `avatar_url`, …) accept only URLs that genuinely came from an image source — a pinned item declared `type: "image"`, RAG `metadata.image`, an image-named page-metadata key, or any URL with an image file extension. A plain link never satisfies an `<img src>` and is stripped. Link fields (`href`, `url`, `link`) are unchanged. The image whitelist is a strict subset of the link whitelist (an image can also be a link, not vice versa).
- **Variant re-coherence after stripping** (`schemas/components.py` `downgrade_image_variants`): when an image is removed from a component that required one, the component degrades to its text-only form instead of leaving an image-shaped hole — hero `split` → `centered`, and `with-image` → `text-only` for steps, tabs and content-grid (per item/tab). Runs after the guard on both the sync and SSE paths. This also fixes a latent bug where an _invented_ image URL was stripped and left the same hole.
- **Prompt reinforcement**: rules that a link is never an image (choose an image variant only when the input has an image URL), and that not every card/CTA needs a link — with one link, use it once where it matters rather than pointing every element at the same URL. Best-effort, the guard is the guarantee.

### Text component no longer invited to explain itself

The `text` component was described in the prompt as "Introductory or explanatory text", which contradicted the rule against page meta-commentary (added the day before) and led the model to emit reasoning as content ("Simple, focused, and easy to scan"). Its description is now "short body copy the visitor reads … never a description of the page, the audience, or your choices", and the style enum is clarified as purely visual. Prompt-level and best-effort — natural-language meta-commentary is a judgment call, not mechanically enforceable like URLs or numbers.

### Container-responsive zones

Every component breakpoint was viewport-based (`@media`), so a zone embedded in a narrow container of a wide page (sidebar, column, preview panel) laid out as if it owned the whole viewport: 3-column bento grids squeezed into 400px, hero headlines at 52px inside a card. Zones are embeddable fragments, so they now respond to their own width:

- `.genui-section` (the wrapper every `GenUIZone`/`GenUISection` renders) is a size container (`container-type: inline-size`), and the viewport grid rules gained `@container` mirrors at the same thresholds, measured on the zone instead of the window. The `@media` rules remain as the fallback for browsers without container queries. `.genui-layout-complex` (host opt-in class, never emitted by a zone render) is deliberately not mirrored.
- In narrow containers the hero headline scales with the zone (`cqw`), bento cards drop the 320px forced min-height to 220px, and long single words in bento titles/hero headlines wrap instead of clipping.
- **Fixed (grid columns, all sibling components)**: a grid with more columns than items squeezed each card into a fraction of the zone. `BentoComponent` emitted the LLM-requested column count even with fewer cards (`genui-bento--cols-1` now styled explicitly); `ContentGrid` did the same with its default of 3; `StatsBanner` capped only when no column count was given, so an explicit model-sent `columns: 4` with 2 stats left empty cells. All three now cap columns by item count (as `PricingCards` already did).
- **Fixed (title clipping, all headings)**: `overflow-wrap: anywhere` now applies to every heading a zone renders (bento, hero, content grid, pricing, stats, testimonials, tabs, steps, chart), so a long single word wraps instead of clipping or overflowing in a narrow column, not just on the two headings where it first surfaced.

Additive: full-width zones on wide viewports render identically to before.

### Zone copy voice and bento caption polish

- **Prompt rule (backend, quality lever)**: the ZoneAgent was free to emit meta-commentary as visible content ("Built for a developer audience...", cards badged "Pinned"): a description of the curation instead of page copy. New system rule 8 "write as the page, not about the page": audience/layout/strategy talk and internal labels are banned from components; selection logic goes only in the `reasoning` field. Prompt-level (best effort, like tone), not mechanically enforceable.
- **Fixed (CSS)**: `.genui-bento-card__content` carried the photo-caption scrim (dark background, blur, top border) into text-only cards, painting a visible box whose backdrop-filter layer ignored the card's border radius (WebKit/Blink compositing). Text-only content is now transparent; the with-image caption bar rounds its own bottom corners (`border-bottom-*-radius: inherit`) so the blur layer follows the card shape.

### Frontend/Backend contract fidelity

Cross-cutting audit of the FE/BE contract: three cases where the backend produced data the frontend type declared but the runtime silently dropped, never rendered, or mutated.

#### Fixed: `useGenUI` no longer discards `meta.behavior`

The backend orchestrator attaches behavior analysis to `/query` responses (`engagement_score`, `user_type`, `session_summary`, `insights_count`, `ui_adjustments`) and `ResponseMeta.behavior` declared it, but the hand-built meta mapping skipped it, so it was always `undefined`. It is now mapped to typed camelCase `BehaviorMeta` at the same choke point as `meta.sanitization`. Additive: still `undefined` when the backend omits it.

#### Fixed: `BentoCard.action` renders

The backend schema emits an optional per-card action button (`CardAction`: `label` + `url`) and the CSS for `.genui-bento-card__action` already existed, but `BentoComponent` never rendered it: a card action disappeared silently. It now renders as a link button (URL through `sanitizeUrl`; an action whose URL is dropped as unsafe renders nothing rather than a dead button). When both `link` and `action` are present the action wins and the card-level link wrapper is skipped, because nested anchors are invalid HTML and SSR parsers split them.

#### Fixed: card `metadata` is no longer camelized

`normalizeData` recursively camelized every nested key, including `BentoCard.metadata`, which the contract declares as opaque pass-through: a host key like `external_id` arrived mutated to `externalId`. `metadata` values are now copied verbatim (same reasoning as custom components, which already skip normalization entirely). The FE `BentoCard` type now also declares `metadata`.

### Output guarantees: numeric grounding & content policy

#### Added: numeric grounding (enforced, on by default)

"Never invent numbers" was a prompt instruction; now it is enforced like the URL whitelist. A number displayed _as_ the content (a `stats_banner` value, a `pricing_cards` price, a `chart` data point) survives only if its digits trace to a number present in the input (pinned content, prompts, RAG documents, page context; verbatim modulo formatting, no magnitude conversion). Ungrounded stats/plans are removed and reported in `meta.sanitization.removed_numbers`; one ungrounded chart point drops the whole chart. Applies on sync, SSE and `/query`, always before caching. **Behavior change**: zones whose stats/prices/charts relied on model-known numbers not present in any input will lose those items. Put real figures in the prompt/pinned/RAG (where they should have come from), or set `NUMERIC_GROUNDING_ENABLED=false` to opt out. Numbers inside prose are deliberately not checked.

#### Added: per-tenant content policy (banned terms)

`CONTENT_POLICY` (JSON env, per tenant plus `"*"`) declares banned terms enforced post-generation: a component containing one is dropped, chat `text_response` is redacted, hits land in `meta.sanitization.policy_violations`. Matching is lexical (case-insensitive, word-boundary, phrase-aware); tone stays prompt-level best-effort and is documented as such. Invalid policy JSON fails loudly instead of silently disabling. Off when unset.

#### Fixed: `/query` chat prose was never link-stripped

The URL whitelist covered components but not the chat `text_response`: an invented markdown link in the prose reached the client intact. The chat text now gets the same treatment as text components (non-input links collapse to their text). `/query` responses also gained `meta.sanitization` (same shape as zone renders).

#### Added: the guarantees as a contract document

`deploy/OUTPUT-GUARANTEES.md`: every output guarantee with its enforcing code reference, its test, and its honest limits (enforce vs best-effort), written for a customer's legal/compliance team. The golden harness now also asserts numeric grounding (invariant + adversarial invented-price fixture).

#### Added: frontend: `meta.sanitization` exposed by the hooks

`useZone` and `useGenUI` previously discarded the backend's sanitization report while mapping `meta`; it is now exposed as typed camelCase `meta.sanitization` (`SanitizationReport`: `removedUrls`, `droppedComponents`, `removedNumbers`, `policyViolations`) on both zone renders and `/query` responses. Additive: `undefined` on older backends.

### Deployment & tenant topology

#### Added: reproducible per-customer deployment (`deploy/`)

One GenUI deployment per customer is now a product artifact instead of a manual procedure: `deploy/docker-compose.yml` brings up the backend (multi-worker uvicorn, `backend/Dockerfile`, non-root, stateless) + Redis (AOF) + Qdrant (pinned) with one command, parametrized by a single per-customer `customer.env` (engine BYOK, tenant declaration, budgets, CORS, retention). Redis and Qdrant are not published on the host; the backend is the single entry point. `deploy/smoke.sh` is the post-bring-up acceptance check (liveness, healthy status, fail-closed auth, per-tenant scoping of every declared admin key). Docs: `deploy/README.md` (bring-up, tenant declaration model, engine/embedding BYOK matrix, ops notes) and `deploy/TENANT-ISOLATION.md`, the per-data-type isolation statement with code references, for the customer's security team. New `tests/test_kb_tenant_filter.py` pins the Qdrant tenant filter shape the isolation document cites. `backend/docker-compose.yml` stays as the dev helper.

#### Fixed: multi-worker boot race creating the Qdrant collection

On a fresh Qdrant, several uvicorn workers booting together all saw the collection as absent and all tried to create it: one won, the others got a 409 and failed their vector-store/orchestrator init (health reported `qdrant_connected: false` until those workers were recycled). Losing the create race is now treated as "collection exists" and validated like any other boot (`rag/vector_store.py::_ensure_collection`). Single-worker dev setups never hit this.

### Zone config registry

#### Added: config as data (server-side zone config registry)

Zone configuration (prompts, pinned content, rendering constraints) can now live server-side as a versioned, per-`(tenant, zone_id)` registry entry (`zones.ZoneConfigStore`, Redis or in-memory like the other stores). When an **approved** entry exists, every render path (sync, streaming, batch, warmup) serves exactly that config and ignores the host props for the governed fields; without an entry, props work exactly as before: no behavior change for existing integrations. Entries carry `version` and `status` (`draft` entries are stored but never served), and approving a new version invalidates cached renders automatically.

### Frontend distribution

#### Fixed: `require('genui-framework')` no longer throws ERR_REQUIRE_ESM

`package.json` now has a proper `exports` map with dual builds: `import` resolves the ESM entry (`dist/index.esm.js`), `require` resolves a real CJS entry (`dist/index.cjs`, new extension because the package is `"type": "module"`). Jest, Next.js pages router and other CJS toolchains can now load the package. If you deep-imported `genui-framework/dist/index.js`, switch to the package root (the old path no longer exists); `genui-framework/dist/styles.css` keeps working (also available as `genui-framework/styles.css`). `sideEffects` is declared so the CSS import survives tree-shaking.

#### Changed: bundle: charts lazy, framer-motion removed

- **recharts moved to a lazy chunk** loaded on first chart render. Entry bundle (ESM, gzip): **460 KB → ~134 KB (-71%)**; the chart chunk (~232 KB) is only downloaded by pages that actually render a chart. `<ChartComponent />` API is unchanged (built-in Suspense boundary; a skeleton shows while the chunk loads).
- **framer-motion is no longer a dependency**: the bento hover scale is now plain CSS (visually identical, and it finally respects `prefers-reduced-motion`).

#### Changed: SSR renders the loading skeleton

`renderToString` of a zone with `loadOnMount` (the default) now emits the loading skeleton instead of **empty HTML**: stable server markup, no CLS, hydration-consistent. With `loadOnMount={false}` the server still renders nothing.

#### Changed: zone props are reactive

Changing `zoneId`/`userId`/`basePrompt`/any request-shaping prop on a mounted zone now **refetches automatically**, aborting the inflight request (last issued wins). Previously the zone fetched only on mount and went stale across SPA route reuse. Props are compared by value, so inline object literals don't cause fetch loops. If you relied on the old "fetch once, ignore prop changes" behavior, mount the zone with a stable `key` and fixed props.

#### Changed: unknown component types degrade silently in production

An unknown component type (typically an old bundle talking to a newer backend) renders **nothing** in production builds (`console.warn` only) instead of printing "Unknown component type" into the end user's page. Dev builds still show the inline error box. Same rule for unknown chart types.

#### Added

- **`contract_version`** field on zone render and `/query` responses (exposed as `meta.contractVersion` / `contractVersion`), so deployed bundles can detect a newer backend contract.
- **Accessibility**: tabs follow the WAI-ARIA pattern (roving tabindex, arrow/Home/End keys, `aria-controls`/`aria-labelledby`); the testimonial carousel pauses autoplay on hover/focus and announces quote changes (`aria-live`); a global `prefers-reduced-motion` CSS block stops all infinite genui animations.
- **Frontend test suite on vitest** (`cd frontend && npm test`): packaging boundary (real-Node `require`/`import` subprocesses), SSR skeleton, reactive-props refetch/abort, plus the privacy filter contract migrated from node:test (same 18 tests, no tsc pre-build step).

#### Changed: observability: /health no longer exposes collection internals

- **`GET /health` returns dependency statuses only** (`status`, `qdrant_connected`, `redis`, and the new `llm: "configured" | "unconfigured"`). The unauthenticated `collection_stats` payload is gone; point counts and index state live behind the admin key at `GET /api/v1/documents/stats`. Update anything that parsed `collection_stats` from `/health`.
- The audit file sink (`AUDIT_LOG_PATH`) now **rotates by size** (`AUDIT_LOG_MAX_BYTES`, default 50 MB, `AUDIT_LOG_BACKUP_COUNT`, default 5) instead of growing unbounded. Set `AUDIT_LOG_MAX_BYTES=0` for the old append-forever behavior.

#### Added: observability

- `GET /ready` (load balancers: 503 only when the LLM provider is unconfigured and nothing can be served) and `GET /live` (process liveness).
- `GET /metrics` (admin key): Prometheus text format with HTTP request counts/latency per route, zone renders per cache outcome (`fresh|stale|miss|coalesced|bypass`), LLM generations and latency per tenant/op/outcome, and dependency gauges. Counters are shared across workers via Redis, so any worker serves a truthful scrape.
- `genui.query` tracing span on `/api/v1/query`, tying the existing `genui.llm.*` client spans to the chat path.
- README "Observability" section: production configuration for health, metrics scraping, the audit sink and tracing.

#### Changed: cost controls: public keys can no longer trigger unbounded LLM spend

With BYOK the LLM bill is on the operator's key, and the client `pk_` key is public. Three request-side amplifiers are closed (backend only, no frontend API change):

- **`cache_strategy: "live"` now requires an admin key.** Client keys sending it receive a **403** and should use the segment cache. If your integration set `cacheStrategy="live"` on a browser zone, remove the prop or move that render behind a server-side proxy with an admin key.
- **`/zone/batch-render` is capped** at `ZONE_BATCH_MAX` zones (default 10, 413 above) and a batch of N zones now consumes N rate-limit slots instead of 1.
- **Cold cache misses are single-flight**: concurrent requests for the same (zone, config, segment) coalesce on one generation and report `meta.cache.status: "coalesced"`. Previously each concurrent request paid its own identical LLM call.

#### Added

- `LLM_BUDGET_PER_HOUR`: per-tenant hourly cap on LLM generations, consistent across workers (shares the rate-limit Redis store). Over the cap, cached renders keep being served (stale entries stop refreshing) and new generations return 429. Disabled by default; set it in production.
- `LLM_TIMEOUT_SECONDS` (default 60): explicit timeout on every LLM and embedding provider call, replacing the SDK default of 10 minutes.
- `ZONE_BATCH_MAX` (default 10): batch-render size cap.

### Behavior tracking privacy

#### Changed: behavior tracker default is no longer "capture everything"

The frontend behavior tracker now has a **privacy filter with a safe default** (`privacy: 'balanced'`). This changes what leaves the browser for existing integrations, without changing the API shape:

- Clicked element text, page titles, referrers, link hrefs and navigation paths are **PII-redacted** (emails, IBANs, Italian codici fiscali, 8+ digit runs) before being stored or sent.
- Form field content (`<input>`, `<textarea>`, `<select>`, contenteditable) is **never captured**, at any level.
- `navigator.doNotTrack` and Global Privacy Control are **honored** (tracker does not start), unless `privacy: 'off'`.
- `enableBehaviorTracking` still defaults to `true`.

To restore the previous raw capture, opt out explicitly: `useGenUI({ privacy: 'off' })`.

#### Added

- `data-genui-private` (never record the subtree) and `data-genui-redact` (record shape, never content) DOM attributes, respected at every privacy level.
- `privacy: 'strict' | 'balanced' | 'off'` and `consent: boolean` options on `useGenUI` and `BehaviorTrackerOptions` (exported `PrivacyLevel` type). `consent: false` blocks tracking entirely; `consent: true` records the host CMP's explicit grant and overrides DNT/GPC.
- The auto-captured `current_page` sent by `useZone` follows the tracker's privacy level.
- Capture contract documented per level in the README ("Behavior Tracking & Privacy") for DPO sign-off.
- Frontend test harness seed: `cd frontend && npm test` (node:test + tsc, no new dependencies) covering the privacy filter contract.
