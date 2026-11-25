# Leaflet runtime

Leaflet 1.9.4 is distributed under the BSD 2-Clause license in this directory.
The CSS comes from the Leaflet npm package. The JavaScript is an ES module
bundle of `map`, `tileLayer`, `polyline` and `featureGroup` from
`dist/leaflet-src.esm.js`, built with esbuild 0.25.12 using
`--bundle --format=esm --minify --legal-comments=inline`.
