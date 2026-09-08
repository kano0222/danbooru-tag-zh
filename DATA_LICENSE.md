# Data licensing and provenance

The converter source code in this repository is MIT licensed. That license does not apply to the
upstream translation data.

All generated translations come unchanged from
`ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table/tag.sqlite`. The converter records the
upstream commit, download URL, retrieval time, SQLite SHA-256, and artifact hashes in its manifest.

The upstream repository currently has no explicit data license. Generated files therefore use the
manifest status `unconfirmed-local-only`, are written to the ignored `local-dist/` directory, and
must not be committed or redistributed until permission and attribution terms are confirmed.
