# Cisco Network Topology Icons

Source: https://www.cisco.com/c/en/us/about/brand-center/network-topology-icons.html
(EPS, PMS 3015 colour set: `/c/dam/en_us/about/ac50/ac47/3015_eps.zip`, downloaded 2026-09-25)

Terms (verbatim): **"You may use them freely, but you may not alter them."**

So these icons are:
- only **format-converted** (EPS → PDF → SVG; shapes and colours unchanged):
  `gs -dEPSCrop -sDEVICE=pdfwrite -o x.pdf x.eps && pdftocairo -svg x.pdf x.svg`
- inlined with their internal `id`s (clipPaths) prefixed to avoid collisions; no path or colour is changed;
- rendered with **proportional scaling only** — never recoloured, stretched or cropped.

| file | original |
|---|---|
| router.svg | router.eps |
| cloud.svg | cloud.eps |
| pc.svg | pc.eps |
