from datetime import datetime
from pathlib import Path

def default_output_path(source, directory=None, timestamp=None, reserved=()):
    source = Path(source).resolve()
    directory = Path(directory).resolve() if directory is not None else source.parent
    timestamp = timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    stem = f'{source.stem}_{timestamp}'
    path = directory / f'{stem}.mp4'
    reserved = {Path(p).resolve() for p in reserved}
    index = 2
    while path.exists() or path in reserved or path == source:
        path = directory / f'{stem}_{index}.mp4'
        index += 1
    return path
