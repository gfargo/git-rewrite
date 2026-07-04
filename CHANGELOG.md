# Changelog

## [0.1.2](https://github.com/gfargo/git-rewrite/compare/v0.1.1...v0.1.2) (2026-07-04)


### Bug Fixes

* rename PyPI package to git-rewrite-history (name was taken) ([331546b](https://github.com/gfargo/git-rewrite/commit/331546be4bea8464f0afd8d2645cef78f4a9a0f4))

## [0.1.1](https://github.com/gfargo/git-rewrite/compare/v0.1.0...v0.1.1) (2026-07-04)


### Bug Fixes

* **backends:** remove duplicate field in RewriteResult namedtuple ([b97d264](https://github.com/gfargo/git-rewrite/commit/b97d2641261232cd3af86a89e5d8650475a59bc3))

## 0.1.0 (2026-07-04)


### Features

* **cli:** add --since / --until / --author scope filters ([#10](https://github.com/gfargo/git-rewrite/issues/10)) ([8f70f86](https://github.com/gfargo/git-rewrite/commit/8f70f863914de7e37d15a20c746f526a75c0806e))
* **cli:** add shell tab-completion via argcomplete ([#16](https://github.com/gfargo/git-rewrite/issues/16)) ([4d2d03e](https://github.com/gfargo/git-rewrite/commit/4d2d03e9e81ac94aed11c5d276f8863ddfd5ff40))
* **config:** repo-level config file and preset subcommand ([540201e](https://github.com/gfargo/git-rewrite/commit/540201ef1e4de5974007538eb3dcc1d4c4cb6986))
* **fields:** add author-date and committer-date to FIELD_ATTR ([04244fa](https://github.com/gfargo/git-rewrite/commit/04244facf77bfa100e64288d028b6b11e6bbcff2))
* **preview:** add --format json and diff-style --preview for strip/replace ([#13](https://github.com/gfargo/git-rewrite/issues/13)) ([181350d](https://github.com/gfargo/git-rewrite/commit/181350dd380c1ad3eafa8b16bdf439e30639808c))
* **rewrite:** print post-rewrite recovery instructions ([#17](https://github.com/gfargo/git-rewrite/issues/17)) ([c4ecba7](https://github.com/gfargo/git-rewrite/commit/c4ecba7ec8b69de2fa3230ed221c74ca508a0d2d))
* **strip:** add --invert flag to keep only matching lines ([#15](https://github.com/gfargo/git-rewrite/issues/15)) ([0be6b0c](https://github.com/gfargo/git-rewrite/commit/0be6b0c0eccdffc877bd421de3380953dfa39e3c))
