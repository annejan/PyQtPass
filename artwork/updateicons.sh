svgo icon.svg
inkscape -z -o icon.png -w 512 -h 512 icon.svg
inkscape -z -o icon@2x.png -w 1024 -h 1024 icon.svg
inkscape -z -o doc-icon.png -w 55 -h 55 icon.svg
for size in 16 32 48 128 256; do     inkscape -z -o $size.png -w $size -h $size icon.svg ; done
optipng *.png
convert 16.png 32.png 48.png 128.png 256.png -colors 256 icon.ico
rm 16.png 32.png 48.png 128.png 256.png