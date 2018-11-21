# open_nsfw-warc

Fork of Yahoo's [open_nsfw](https://github.com/yahoo/open_nsfw) classifier with a script for classifying images in WARC files.

[Original README](README.orig.md)

## Run

Available as [nlagovau/open_nsfw-warc:master](https://hub.docker.com/r/nlagovau/open_nsfw-warc) on Docker Hub.

    docker run -it --rm nlagovau/open_nsfw-warc:master ./classify_warc.py /tmp/example.warc.gz

## Build

    docker build -t open_nsfw .
