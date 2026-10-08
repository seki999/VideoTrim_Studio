from core.output_paths import default_output_path

def test_source_directory_and_timestamp(tmp_path):
    source = tmp_path / '中文 日本語 movie.MOV'; source.write_bytes(b'source')
    output = default_output_path(source, timestamp='20261008_163000')
    assert output == tmp_path / '中文 日本語 movie_20261008_163000.mp4'
    assert source.read_bytes() == b'source'
    output.write_bytes(b'existing')
    assert default_output_path(source, timestamp='20261008_163000').name.endswith('_2.mp4')

def test_batch_name_conflicts_and_custom_directory(tmp_path):
    source = tmp_path / 'movie.mkv'
    output_dir = tmp_path / 'exports'
    first = default_output_path(source, output_dir, '20261008_163000')
    second = default_output_path(tmp_path / 'movie.mov', output_dir, '20261008_163000', [first])
    assert first.parent == output_dir and second.parent == output_dir
    assert second.name == 'movie_20261008_163000_2.mp4'
