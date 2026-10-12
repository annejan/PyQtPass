<!-- SPDX-License-Identifier: WTFPL -->

# Icon 

The icon is a heart-shaped padlock holding the two Python snakes, drawn as
plain vector shapes in `icon.svg` (gradients only, no filters, so Qt draws
it the same way as other SVG viewers). Every other icon file is made from it.

## Making the icon files

With PyQt6 and Pillow (both in `requirements-dev.txt`), from the repository
root:

```bash
python scripts/update_icons.py
```

It writes `icon.png` (512), `icon@2x.png` (1024), `doc-icon.png` (55),
`icon.ico` (16 to 256) and `icon.icns`.

`./updateicons.sh` in this folder does the same with
[Inkscape](https://inkscape.org/), [SVGO](https://github.com/svg/svgo),
[OptiPNG](http://optipng.sourceforge.net/),
[ImageMagick](https://imagemagick.org/) and
[libicns](https://icns.sourceforge.io/).

## Contributions
Feel free to fork this repository and contribute by submitting a pull request.

## License

The PyQtPass logo is licensed under the WTFPL

The Lato font by Lukasz Dziedzic is released under the SIL Open Font License

The ./updateicons.sh script is EUPL 1.2 Licensed
