"""Attach/detach the Training entry in a local Studio checkout."""
import argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('checkout');parser.add_argument('--detach',action='store_true');args=parser.parse_args()
path=Path(args.checkout)/'index.html';text=path.read_text()
link='<a href="training.html" id="training-menu">Training</a>'
anchor='<a href="#reports" data-page="reports">Reports</a>'
if args.detach:text=text.replace(link,'')
elif link not in text:
    if text.count(anchor)!=1:raise SystemExit('Navigation differs; review before attaching Training')
    text=text.replace(anchor,anchor+link)
path.write_text(text)
