# LinkedIn feed posts

Three versions. All are plain text on purpose — LinkedIn renders neither
Markdown nor LaTeX, so each can be pasted as-is.

The feed cap is 3,000 characters, and only the first ~200 show before "see
more". Every version opens on a concrete detail rather than on the project,
because "I built a satellite platform" is a line people scroll past and "one
line changes this measurement by 40%" is not.

**Which to use.** The first standalone post is the default. It leads with the
baseline-offset measurement, which lands the whole point — a plausible-looking
answer that is wrong — in two sentences, and its central figures are
reproducible with `scripts/measure_processing_effects.py`. The tile-boundary
alternative tells a better story but needs three paragraphs to get there; it is
the stronger choice if the audience will read past the fold. Use the article
version only if [`case-study-linkedin.md`](case-study-linkedin.md) is actually
published as a LinkedIn Article, since Articles get almost no reach without a
post pointing at them.

What the post is *not* claiming matters as much as what it is. NDVI from
Sentinel-2 is textbook, and a remote-sensing specialist reading this will know
that. The claim is about knowing whether a computed number is real — which is
defensible, and which most side-project posts cannot make.

---

## Standalone (1,861 characters)

One line in the Sentinel-2 documentation changes this measurement by 40%. Miss
it, and your chart still looks completely reasonable.

I built the Orbital Earth Observation Platform to find out what happens when
you point an Azure and infrastructure skill set at scientific data. You pick an
area and a date range; it pulls Copernicus Sentinel-2 imagery, masks the
clouds, and measures vegetation greenness over time.

Vegetation greenness is NDVI, a ratio of near-infrared to red light. The
satellite doesn't ship you reflectance, though — it ships integers you have to
decode. And in January 2022, ESA changed that encoding, adding a constant to
every stored value.

Here is why that is easy to get wrong. NDVI is a ratio, so any multiplicative
scale factor cancels out — which makes it tempting to skip the decoding step
entirely. A constant offset does not cancel. It survives in the denominator.

I measured it on real imagery over southeast Michigan rather than trusting the
reasoning. Same pixels, same masking, only the offset removed:

0.4443 handled correctly
0.2738 with the offset ignored

That is the difference between reporting an area as healthily vegetated and
reporting it as sparse. Both numbers plot as a perfectly sensible seasonal
curve. Nothing crashes. No test fails.

NDVI from Sentinel-2 is textbook — a dozen tools will compute it for you. What
is not textbook is knowing whether the number your system just produced is
real, and being able to prove it. That turned out to be most of the work: not
the satellites, not the cloud infrastructure, but the unglamorous business of
verifying that a plausible-looking answer is an answer at all.

Three other bugs in the project had exactly that shape. Only one was loud
enough to announce itself.

Live: https://oeop.net
Code: https://github.com/raveheart1/Orbital-Earth-Observation-Platform

## Alternative standalone — the tile-boundary angle (1,647 characters)

Two preview images were slightly different sizes. That was the only visible
clue that my satellite platform had been measuring the wrong thing.

I built the Orbital Earth Observation Platform to find out what happens when
you point an Azure and infrastructure skill set at scientific data. You pick an
area and a date range; it pulls Copernicus Sentinel-2 imagery, masks the
clouds, and measures vegetation greenness over time.

The area I was testing sits on the boundary between two Sentinel-2 tiles. A
single satellite pass is published as one file per tile, so my pipeline had
several files representing the same moment — and it picked one of them,
requiring only 25% overlap with the requested area.

So some dates measured 56% of the area. Others measured 100%. Both were plotted
on the same chart as though they were the same place.

Nothing crashed. No test failed. The curve looked like a normal growing season.

That is the part I keep coming back to. NDVI from Sentinel-2 is textbook — a
dozen existing tools will compute it for you. What is not textbook is knowing
whether the number your system just produced is real, and being able to prove
it.

The fix reprocesses every observation onto one fixed grid, so all dates measure
identical ground by construction. A date that already had full coverage
reproduced to four decimal places afterwards — which is how I know the fix was
surgical rather than a quiet change to the science itself.

Three other bugs in the project had the same shape. Only one was loud enough to
announce itself.

Live: https://oeop.net
Code: https://github.com/raveheart1/Orbital-Earth-Observation-Platform

---

## Article version (1,567 characters)

Use only if the long write-up is published as a LinkedIn Article. Replace
`<article-url>`.

I built a satellite vegetation-monitoring platform on Azure. The most valuable
thing I found was a bug that produced perfectly reasonable-looking charts.

An analysis over central Detroit rendered before/after previews with different
extents. The earlier image covered the northern part of the area; the later one
reached the Detroit River.

It looked like a CSS problem. It wasn't.

Detroit's area of interest straddles the boundary between two Sentinel-2 tiles.
A single satellite acquisition is published as one file per tile, so an area
crossing that line matches several files representing the same moment. My
pipeline picked one of them and required only 25% overlap with the requested
area. Dates backed by the smaller tile covered 56% of it — and the raster read
silently clipped to whatever the tile contained instead of failing.

NDVI statistics computed over 751,081 pixels on some dates and 1,372,771 on
others. Different ground, plotted on the same chart as though it were the same
place. The change that analysis reported wasn't a measurement; it was an
artifact of which pixels happened to be included.

Nothing crashed. No exception, no alert, no failed test. The curve looked
seasonal and sat in a sensible range. If those two preview images had happened
to be the same size, I would never have looked.

Three other bugs in the project had exactly that character — including a
catalog query that quietly analysed four years of a request for eight.

Full write-up: what the other three were, and the three unglamorous things that
actually caught them.

<article-url>
