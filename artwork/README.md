<!-- SPDX-License-Identifier: WTFPL -->

# Icon 

## Processing Script

### Overview
This repository contains a Bash script for converting and resizing an SVG image into various PNG formats and icon files. It is designed to generate icons suitable for different platforms and resolutions, including Windows and macOS.

### Prerequisites
- [Inkscape](https://inkscape.org/)
- [SVGO (SVG Optimizer)](https://github.com/svg/svgo)
- [OptiPNG](http://optipng.sourceforge.net/)
- [ImageMagick](https://imagemagick.org/)

Ensure these tools are installed on your system before running the script.

### Usage
1. Place your SVG file named `icon.svg` in the same directory as the script.
2. Run the script with:
   ```bash
   ./updateicons.sh
   ```
3. The script will generate various PNG files, an ICO file for Windows, and an ICNS file for macOS.

## Contributions
Feel free to fork this repository and contribute by submitting a pull request.

## License

The PyQtPass logo currently in flux and licensed under the WTFPL

The ./updateicons.sh script is EUPL 1.2 Licensed
