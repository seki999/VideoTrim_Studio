from pathlib import Path
from models import OutputOptions
from .ffprobe_service import probe

def compatible(infos):
    return bool(infos) and all(i.signature == infos[0].signature for i in infos)

def concat_quote(path):
    return "'" + Path(path).resolve().as_posix().replace("'", "'\\''") + "'"

def encoding_args(options, duration):
    codec = options.encoder
    args = ['-c:v', codec, '-pix_fmt', 'yuv420p']
    bitrate = options.bitrate_kbps
    if options.mode == 'size':
        bitrate = int(options.target_mb * 1024 * 1024 * 8 / duration / 1000 * .97 - 128)
        if bitrate < 50: raise ValueError('目标大小过小，无法容纳音频及视频')
    if options.mode in ('bitrate', 'size'):
        args += ['-b:v', f'{bitrate}k']
    elif codec in ('libx264', 'libx265'):
        args += ['-crf', str(options.crf), '-preset', 'medium']
    elif 'nvenc' in codec:
        args += ['-rc', 'vbr', '-cq', str(options.crf), '-b:v', '0']
    elif 'qsv' in codec:
        args += ['-global_quality', str(options.crf)]
    else:
        args += ['-rc', 'cqp', '-qp_i', str(options.crf), '-qp_p', str(options.crf)]
    return args + ['-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart']

def process_segments(service, segments, output, options=None, progress=lambda *a: None, overwrite=False):
    options = options or OutputOptions()
    if not segments: raise ValueError('请先添加视频或片段')
    infos = [probe(s.path) for s in segments]
    lengths = []
    for s, info in zip(segments, infos):
        end = info.duration if s.end is None else s.end
        if not 0 <= s.start < end <= info.duration + .05: raise ValueError('片段时间超出视频范围')
        lengths.append(end - s.start)
    duration = sum(lengths)
    copy = options.mode == 'copy'
    if copy and (options.width or options.height or options.fps):
        raise ValueError('流复制不能改变分辨率或帧率')
    # MP4 supports these common codecs. Other containers are normalized.
    copy = copy and compatible(infos) and infos[0].codec in ('h264', 'hevc', 'mpeg4', 'av1')
    copy = copy and all(not i.audio or i.audio['codec_name'] in ('aac', 'mp3', 'alac') for i in infos)
    def operation(temp, folder):
        if copy:
            listing = folder / 'concat.txt'
            lines = ['ffconcat version 1.0']
            for s, length in zip(segments, lengths):
                lines += ['file ' + concat_quote(s.path), f'inpoint {s.start:.6f}', f'outpoint {s.start + length:.6f}']
            listing.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            service.run(['-fflags', '+genpts', '-f', 'concat', '-safe', '0', '-i', str(listing),
                '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', '-avoid_negative_ts', 'make_zero',
                '-movflags', '+faststart', str(temp)], duration, progress)
            return
        width = options.width or infos[0].width
        height = options.height or infos[0].height
        width, height = max(2, width // 2 * 2), max(2, height // 2 * 2)
        fps = options.fps or infos[0].fps or 30
        if not 1 <= fps <= 240: raise ValueError('帧率必须在 1–240 之间')
        inputs, filters, labels = [], [], []
        for index, (s, info, length) in enumerate(zip(segments, infos, lengths)):
            inputs += ['-i', str(info.path)]
            scale = (f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                     f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2') if options.pad else f'scale={width}:{height}'
            filters.append(f'[{index}:v:0]trim=start={s.start:.6f}:duration={length:.6f},setpts=PTS-STARTPTS,'
                           f'{scale},setsar=1,fps={fps},format=yuv420p[v{index}]')
            if info.audio:
                filters.append(f'[{index}:a:0]atrim=start={s.start:.6f}:duration={length:.6f},asetpts=PTS-{s.start:.6f}/TB,'
                               f'aresample=48000:async=1:first_pts=0,aformat=channel_layouts=stereo,'
                               f'apad,atrim=duration={length:.6f}[a{index}]')
            else:
                filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length:.6f},asetpts=PTS-STARTPTS[a{index}]')
            labels += [f'[v{index}][a{index}]']
        filters.append(''.join(labels) + f'concat=n={len(segments)}:v=1:a=1[v][a]')
        base = inputs + ['-filter_complex_threads', '1', '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]']
        encoding = encoding_args(options, duration)
        if options.two_pass:
            if options.encoder != 'libx264' or options.mode not in ('size', 'bitrate'):
                raise ValueError('双遍编码仅支持 libx264 的目标大小或码率模式')
            passlog = str(folder / 'pass')
            service.run(base + encoding + ['-pass', '1', '-passlogfile', passlog, '-f', 'mp4', os_null()],
                        duration, lambda p, eta: progress(p / 2, None))
            service.run(base + encoding + ['-pass', '2', '-passlogfile', passlog, str(temp)],
                        duration, lambda p, eta: progress(.5 + p / 2, eta))
        else:
            service.run(base + encoding + [str(temp)], duration, progress)
    result = service.transactional(output, [s.path for s in segments], operation, overwrite)
    progress(1, 0)
    return result

def os_null():
    import os
    return os.devnull
