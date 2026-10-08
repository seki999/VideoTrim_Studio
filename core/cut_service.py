from models import Segment, OutputOptions
from .merge_service import process_segments

def cut(service, source, output, start, end, precise=True, **kwargs):
    return process_segments(service, [Segment(source, start, end)], output,
                            OutputOptions(mode='crf' if precise else 'copy'), **kwargs)
