from models import Segment
from .merge_service import process_segments

def compress(service, source, output, options, **kwargs):
    return process_segments(service, [Segment(source)], output, options, **kwargs)
