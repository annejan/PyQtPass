"""
Render the PyQtPass icon files from pyqtpass/artwork/icon.svg.

    pip install PyQt6 pillow
    python scripts/update_icons.py

Writes icon.png (512), icon@2x.png (1024), doc-icon.png (55), icon.ico
(16 to 256) and icon.icns (16 to 1024) next to the SVG. Qt renders the
SVG, so the files look like the icon the program shows; Pillow writes the
Windows and macOS formats. artwork/updateicons.sh does the same with
Inkscape, ImageMagick and libicns.
"""

import io
import os
import sys

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QRectF
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

ARTWORK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyqtpass", "artwork"
)


def render(renderer, size):
    """
    :param renderer: The QSvgRenderer of the icon.
    :param size: Width and height in pixels.
    :return: The icon as a Pillow image.
    """
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def main():
    """Write the icon files."""
    app = QGuiApplication(sys.argv[:1])  # pylint: disable=unused-variable
    renderer = QSvgRenderer(os.path.join(ARTWORK, "icon.svg"))
    if not renderer.isValid():
        sys.exit("icon.svg could not be read")
    sizes = {size: render(renderer, size) for size in (16, 32, 48, 64, 128, 256)}
    big = {size: render(renderer, size) for size in (55, 512, 1024)}
    big[1024].save(os.path.join(ARTWORK, "icon@2x.png"), optimize=True)
    big[512].save(os.path.join(ARTWORK, "icon.png"), optimize=True)
    big[55].save(os.path.join(ARTWORK, "doc-icon.png"), optimize=True)
    # Pillow picks each size from the largest image it is given.
    sizes[256].save(
        os.path.join(ARTWORK, "icon.ico"),
        sizes=[(size, size) for size in sorted(sizes)],
        append_images=[sizes[size] for size in sorted(sizes) if size != 256],
    )
    big[1024].save(
        os.path.join(ARTWORK, "icon.icns"),
        append_images=[
            sizes[16],
            sizes[32],
            sizes[64],
            sizes[128],
            sizes[256],
            big[512],
        ],
    )


if __name__ == "__main__":
    main()
