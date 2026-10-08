import hashlib
import threading
from pathlib import Path
import pytest
from models import Segment, OutputOptions
from core.ffmpeg_service import FFmpegService, Cancelled
from core.ffprobe_service import probe
from core.cut_service import cut
from core.compress_service import compress
from core.merge_service import process_segments, compatible

pytestmark = pytest.mark.integration

def service(tmp_path): return FFmpegService(tmp_path / 'logs')

def validate(path, duration, size=(320, 240), audio=True):
    info = probe(path)
    assert abs(info.duration - duration) < .15
    assert (info.width, info.height) == size
    assert info.codec == 'h264'
    assert bool(info.audio) == audio
    if audio:
        video = next(s for s in info.streams if s['codec_type'] == 'video')
        assert abs(float(video.get('start_time', 0)) - float(info.audio.get('start_time', 0))) < .1
        assert abs(float(video['duration']) - float(info.audio['duration'])) < .15
    return info

def test_fast_cut(media, tmp_path):
    out = tmp_path / 'fast.mp4'
    cut(service(tmp_path), media[0], out, 0, 1, precise=False)
    validate(out, 1)

def test_precise_cut_and_special_path(media, tmp_path):
    out = tmp_path / "日本語 中文 ' & output.mp4"
    cut(service(tmp_path), media[0], out, .237, 1.237)
    validate(out, 1)

def test_same_encoding_merge(media, tmp_path):
    assert compatible([probe(media[0]), probe(media[1])])
    out = tmp_path / 'merge.mp4'
    process_segments(service(tmp_path), [Segment(p) for p in media[:2]], out, OutputOptions(mode='copy'))
    validate(out, 4)

def test_mixed_resolution_audio_and_silence(media, tmp_path):
    out = tmp_path / 'mixed.mp4'
    process_segments(service(tmp_path), [Segment(media[0]), Segment(media[2]), Segment(media[3])], out,
                     OutputOptions(mode='copy'))
    info = validate(out, 6)
    assert info.audio['channels'] == 2
    assert info.audio['sample_rate'] == '48000'

def test_compression(media, tmp_path):
    out = tmp_path / 'compressed.mp4'
    compress(service(tmp_path), media[0], out, OutputOptions(crf=28, width=160, height=120, fps=20))
    info = validate(out, 2, (160, 120))
    assert info.fps == 20
    assert info.size < media[0].stat().st_size

def test_single_encode_workflow(media, tmp_path):
    out = tmp_path / 'workflow.mp4'
    process_segments(service(tmp_path), [Segment(media[2], .2, 1.2), Segment(media[0], .3, 1.3)], out,
                     OutputOptions(width=640, height=360))
    validate(out, 2, (640, 360))

def test_two_pass_target_size(media, tmp_path):
    out = tmp_path / 'two-pass.mp4'
    compress(service(tmp_path), media[0], out, OutputOptions(mode='size', target_mb=.12, two_pass=True))
    info = validate(out, 2)
    assert info.size < .16 * 1024**2

def test_cancel_running_ffmpeg(media, tmp_path):
    runner = service(tmp_path); output = tmp_path / 'cancel.mp4'; errors = []
    def work():
        try:
            def operation(temp, folder):
                runner.run(['-re', '-stream_loop', '-1', '-i', str(media[0]), '-t', '60',
                    '-c:v', 'libx264', '-c:a', 'aac', str(temp)], 60,
                    lambda p, eta: runner.cancel() if p > .001 else None)
            runner.transactional(output, [media[0]], operation)
        except Exception as exc: errors.append(exc)
    worker = threading.Thread(target=work); worker.start(); worker.join(15)
    if worker.is_alive(): runner.cancel(); worker.join(5)
    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], Cancelled)
    assert not output.exists()
    assert not list(tmp_path.glob('.videotrim-*'))

def test_source_protection(media, tmp_path):
    before = hashlib.sha256(media[0].read_bytes()).hexdigest()
    with pytest.raises(ValueError): cut(service(tmp_path), media[0], media[0], 0, 1)
    assert hashlib.sha256(media[0].read_bytes()).hexdigest() == before
    existing = tmp_path / 'existing.mp4'; existing.write_bytes(b'keep')
    with pytest.raises(FileExistsError): cut(service(tmp_path), media[0], existing, 0, 1)
    assert existing.read_bytes() == b'keep'

def test_failed_output_cleanup(media, tmp_path):
    out = tmp_path / 'failed.mp4'
    with pytest.raises(RuntimeError):
        service(tmp_path).transactional(out, [media[0]],
            lambda temp, folder: service(tmp_path).run(['-i', str(media[0]), '-c:v', 'invalid_encoder', str(temp)], 2))
    assert not out.exists()
    assert list((tmp_path / 'logs').glob('*.log'))

def test_hevc(media, tmp_path):
    out = tmp_path / 'hevc.mp4'
    compress(service(tmp_path), media[0], out, OutputOptions(encoder='libx265', crf=28))
    assert probe(out).codec == 'hevc'

def test_delayed_audio_sync(media, tmp_path):
    import subprocess
    import array
    from core.ffprobe_service import locate
    delayed = tmp_path / 'delayed.mp4'
    subprocess.run([locate('ffmpeg'), '-v', 'error', '-y', '-i', str(media[0]),
        '-itsoffset', '0.5', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
        '-map', '0:v:0', '-map', '1:a:0', '-t', '2', '-c:v', 'copy', '-c:a', 'aac', str(delayed)],
        check=True, capture_output=True)
    out = tmp_path / 'sync.mp4'
    compress(service(tmp_path), delayed, out, OutputOptions())
    validate(out, 2)
    pcm = subprocess.run([locate('ffmpeg'), '-v', 'error', '-i', str(out), '-map', '0:a:0',
        '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1'], check=True, capture_output=True).stdout
    samples = array.array('h'); samples.frombytes(pcm)
    early = samples[:int(.3 * 48000)]; later = samples[int(.7*48000):int(1*48000)]
    assert sum(abs(x) for x in early) / len(early) < 30
    assert sum(abs(x) for x in later) / len(later) > 1000
