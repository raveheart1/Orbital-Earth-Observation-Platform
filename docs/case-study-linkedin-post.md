# LinkedIn feed post

A LinkedIn feed post is capped at 3,000 characters, so
[`case-study-linkedin.md`](case-study-linkedin.md) (~7,400) has to be published
as an *Article*. Articles get very little reach on their own — this is the feed
post that links to it. Replace `<article-url>` after publishing.

---

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
