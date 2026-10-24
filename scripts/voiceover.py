"""Editable local voiceovers. No third-party imports until real inference."""
import argparse
import contextlib
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import struct
import sys
import tempfile
import time
import uuid
import wave

VERSION = '0.1.0'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def relative_file(root, value):
    root = Path(root).resolve()
    target = (root / value).resolve()
    if not target.is_relative_to(root):
        raise ValueError('File path escapes its project or voice directory')
    return target


@contextlib.contextmanager
def locked(root):
    p = Path(root) / '.lock'
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        yield
    finally:
        p.unlink()


def save_project(root, project):
    old = Path(root) / 'manifest.json'
    if old.exists():
        backups = Path(root) / 'revisions'
        backups.mkdir(exist_ok=True)
        shutil.copyfile(old, backups / (uuid.uuid4().hex + '.json'))
    atomic_json(old, project)


def project_load(root):
    p = load(Path(root) / 'manifest.json')
    if p.get('schema_version') != 1:
        raise ValueError('Unsupported project schema')
    ids = [s['id'] for s in p['segments']]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError('Invalid segment IDs')
    return p


def split_script(text):
    # Preserve ALL original characters; English decimal points are not boundaries.
    pieces = re.findall(r'.+?(?:[。！？!?]+[”’\"\']*|(?<!\d)\.(?=\s|$)|\n+|$)', text, re.S)
    if ''.join(pieces) != text:
        raise ValueError('Splitter did not preserve source text')
    merged = []
    for part in pieces:
        if not part.strip() and merged:
            merged[-1] += part
        else:
            merged.append(part)
    if not text.strip():
        raise ValueError('Script is empty')
    return merged


def wav_read(path):
    with wave.open(str(path), 'rb') as f:
        params = (f.getnchannels(), f.getsampwidth(), f.getframerate())
        if f.getcomptype() != 'NONE' or params[1] != 2:
            raise ValueError('Use uncompressed 16-bit PCM WAV')
        frames = f.readframes(f.getnframes())
    if not frames or len(frames) % (params[0] * 2):
        raise ValueError('Empty or truncated WAV')
    return params, frames


def wav_write(path, params, frames):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(params[0])
        f.setsampwidth(params[1])
        f.setframerate(params[2])
        f.writeframes(frames)


def wav_quality(path):
    params, data = wav_read(path)
    values = [v[0] for v in struct.iter_unpack('<h', data)]
    rms = math.sqrt(sum(v * v for v in values) / len(values)) / 32768
    return dict(channels=params[0], sample_rate=params[2],
                seconds=len(data) / (params[0] * 2 * params[2]),
                peak=max(abs(v) for v in values) / 32768,
                rms_dbfs=20 * math.log10(max(rms, 1e-12)),
                near_clipping_ratio=sum(abs(v) >= 32700 for v in values) / len(values))


def voice_create(directory, audio, transcript, name, consent):
    if not consent:
        raise ValueError('Explicit own-voice / authorized-voice consent is required')
    text = Path(transcript).read_text(encoding='utf-8-sig').strip()
    if not text:
        raise ValueError('Reference transcript is required')
    # Normalize a private COPY of non-16-bit WAV, never alter the user's original.
    normalized = None
    try:
        quality = wav_quality(audio)
    except (ValueError, wave.Error):
        import soundfile as sf
        samples, rate = sf.read(str(audio), dtype='float32', always_2d=True)
        if not len(samples):
            raise ValueError('Empty reference audio')
        fd, name_tmp = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        try:
            sf.write(name_tmp, samples.mean(axis=1), rate, subtype='PCM_16')
            quality = wav_quality(name_tmp)
            normalized = Path(name_tmp).read_bytes()
        finally:
            os.unlink(name_tmp)
    if not 2 <= quality['seconds'] <= 20:
        raise ValueError('Reference must be 2–20 seconds; trim audio AND transcript together')
    if quality['rms_dbfs'] < -50:
        raise ValueError('Reference is silent or too quiet')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    if normalized is not None:
        (directory / 'reference.wav').write_bytes(normalized)
    else:
        shutil.copyfile(audio, directory / 'reference.wav')
    v = dict(name=name, audio='reference.wav', transcript=text, authorized=True,
             consent_at=time.time(), audio_sha256=file_hash(directory / 'reference.wav'),
             source_audio_sha256=file_hash(audio), normalized_copy=normalized is not None,
             quality=quality)
    atomic_json(directory / 'voice.json', v)
    return v


def voice_info(directory):
    v = load(Path(directory) / 'voice.json')
    if v.get('authorized') is not True or not v.get('transcript', '').strip():
        raise ValueError('Voice consent/transcript missing')
    audio = relative_file(directory, v['audio'])
    actual = file_hash(audio)
    if actual != v['audio_sha256']:
        raise ValueError('Voice reference changed; create a new authorized voice profile')
    return v, audio


def model_fingerprint(directory):
    directory = Path(directory)
    required = ['config.json', 'tokenizer.json', 'tokenizer_config.json']
    if not directory.is_dir() or any(not (directory / f).is_file() for f in required):
        raise ValueError('Incomplete local model: config/tokenizer files missing')
    if not list(directory.glob('*.safetensors')) or not (directory / 'audio_tokenizer').is_dir():
        raise ValueError('Incomplete local model: weights/audio_tokenizer missing')
    entries = []
    for f in sorted(directory.rglob('*')):
        if not f.is_file() or '.cache' in f.parts:
            continue
        stat = f.stat()
        signature = file_hash(f) if stat.st_size < 2_000_000 else str(stat.st_mtime_ns)
        entries.append((f.relative_to(directory).as_posix(), stat.st_size, signature))
    if not any(e[0].startswith('audio_tokenizer/') and e[0].endswith(('.safetensors', '.bin')) for e in entries):
        raise ValueError('Audio tokenizer weights missing')
    return digest(json.dumps(entries).encode())


def environment_id():
    versions = {}
    for name in ('omnivoice', 'torch', 'torchaudio', 'transformers', 'soundfile'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def context(project):
    c = project['config']
    voice, audio = voice_info(c['voice'])
    return dict(voice_sha256=voice['audio_sha256'], transcript=voice['transcript'],
                model=model_fingerprint(c['model']), device=c['device'],
                environment=environment_id(), implementation=VERSION)


def synthesis_settings(s):
    return {k: s[k] for k in ('text', 'spoken_text', 'speed', 'seed')}


def key_for(s, ctx):
    return digest(json.dumps(dict(settings=synthesis_settings(s), context=ctx),
                             sort_keys=True, ensure_ascii=False).encode())


def selected(project, only=None):
    if not only:
        return project['segments']
    ids = [str(int(i)).zfill(3) for i in only.split(',')]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate segment IDs')
    found = [s for s in project['segments'] if s['id'] in ids]
    if len(found) != len(ids):
        raise ValueError('Unknown segment ID')
    return found


def take_valid(root, segment, take, ctx):
    if not take or take['key'] != key_for(segment, ctx):
        return False
    p = relative_file(root, take['file'])
    return p.is_file() and file_hash(p) == take['sha256']


def current_take(s):
    return next((t for t in s['takes'] if t['id'] == s['current']), None)


def project_init(root, script, voice, model, device='auto', seed=42):
    voice_info(voice)
    model_fingerprint(model)
    text = Path(script).read_text(encoding='utf-8-sig')
    segments = [dict(id=f'{i:03d}', text=t, spoken_text=None, pause_ms=250,
                     speed=1.0, seed=seed+i, current=None, takes=[])
                for i, t in enumerate(split_script(text), 1)]
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root / 'source.txt').write_text(text, encoding='utf-8')
    p = dict(schema_version=1, config=dict(voice=str(Path(voice).resolve()),
             model=str(Path(model).resolve()), device=device), segments=segments)
    atomic_json(root / 'manifest.json', p)
    return p


class OmniEngine:
    def __init__(self, project):
        # Set offline flags BEFORE importing model libraries. No implicit downloads.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import torch
        import soundfile
        from omnivoice import OmniVoice
        self.torch, self.sf = torch, soundfile
        self.voice, self.reference = voice_info(project['config']['voice'])
        device = project['config']['device']
        if device == 'auto':
            device = 'cuda:0' if torch.cuda.is_available() else (
                'mps' if torch.backends.mps.is_available() else 'cpu')
        dtype = torch.float32 if device == 'cpu' else torch.float16
        self.model = OmniVoice.from_pretrained(project['config']['model'],
                     device_map=device, dtype=dtype, local_files_only=True)

    def generate(self, segment, path):
        self.torch.manual_seed(segment['seed'])
        with self.torch.inference_mode():
            result = self.model.generate(text=(segment['spoken_text'] or segment['text']).strip(),
                     language='Chinese', ref_audio=str(self.reference),
                     ref_text=self.voice['transcript'], speed=segment['speed'],
                     num_step=32)
        audio = result[0]
        if hasattr(audio, 'detach'):
            audio = audio.detach().float().cpu().numpy()
        # Upstream releases return (T,), some bundled versions return (1,T).
        import numpy as np
        audio = np.asarray(audio).squeeze()
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError('Engine returned invalid mono waveform')
        self.sf.write(str(path), audio, self.model.sampling_rate, subtype='PCM_16')


def render(root, only=None, retake=False, approved=False, engine_factory=OmniEngine):
    if not approved:
        raise ValueError('Confirm voice, segmentation and render plan with user first')
    root = Path(root)
    with locked(root):
        p = project_load(root)
        ctx = context(p)
        engine = None
        report = []
        for s in selected(p, only):
            if retake:
                s['seed'] = random.SystemRandom().randint(0, 2**31-1)
            cached = next((t for t in reversed(s['takes']) if take_valid(root, s, t, ctx)), None)
            if cached and not retake:
                s['current'] = cached['id']
                save_project(root, p)
                report.append(dict(segment=s['id'], reused=True, file=cached['file']))
                continue
            if engine is None:
                engine = engine_factory(p)
            take_id = uuid.uuid4().hex[:12]
            folder = root / 'audio' / s['id']
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / (take_id + '.wav')
            engine.generate(s, output)
            quality = wav_quality(output)
            take = dict(id=take_id, file=output.relative_to(root).as_posix(),
                        key=key_for(s, ctx), sha256=file_hash(output),
                        settings=synthesis_settings(s), context=ctx,
                        quality=quality, created_at=time.time())
            s['takes'].append(take)
            s['current'] = take_id
            save_project(root, p)
            report.append(dict(segment=s['id'], reused=False, file=take['file']))
        return report


def edit(root, segment, **changes):
    allowed = {'text', 'spoken_text', 'pause_ms', 'speed'}
    if set(changes) - allowed:
        raise ValueError('Unknown edit field')
    if 'text' in changes and not changes['text'].strip():
        raise ValueError('Empty text')
    if 'spoken_text' in changes and changes['spoken_text'] is not None and not changes['spoken_text'].strip():
        raise ValueError('Empty spoken text; use clear-spoken instead')
    if 'pause_ms' in changes and not 0 <= changes['pause_ms'] <= 10000:
        raise ValueError('pause_ms must be 0..10000')
    if 'speed' in changes and not 0.5 <= changes['speed'] <= 2:
        raise ValueError('speed must be 0.5..2')
    with locked(root):
        p = project_load(root)
        s = selected(p, segment)[0]
        if 'text' in changes:
            s['spoken_text'] = None
        s.update(changes)
        save_project(root, p)
        return s


def rollback(root, segment, take_id):
    with locked(root):
        p = project_load(root)
        s = selected(p, segment)[0]
        take = next((t for t in s['takes'] if t['id'] == take_id), None)
        if not take:
            raise ValueError('Unknown take ID')
        s.update(copy.deepcopy(take['settings']))
        s['current'] = take_id
        save_project(root, p)
        return s


def export(root, only=None):
    root = Path(root)
    with locked(root):
        p = project_load(root)
        ctx = context(p)
        items = selected(p, only)
        parts, timeline = [], []
        params = None
        frame_count = 0
        for i, s in enumerate(items):
            take = current_take(s)
            if not take_valid(root, s, take, ctx):
                raise ValueError(f"Segment {s['id']}: missing, stale or damaged take; render it first")
            fmt, data = wav_read(relative_file(root, take['file']))
            if params is not None and fmt != params:
                raise ValueError('Incompatible WAV formats; regenerate with same engine')
            params = fmt
            frames = len(data) // (fmt[0] * 2)
            pause = round(s['pause_ms'] * fmt[2] / 1000) if i < len(items)-1 else 0
            timeline.append(dict(id=s['id'], text=s['text'],
                spoken_text=s['spoken_text'] or s['text'], take=take['id'],
                start=frame_count/fmt[2], end=(frame_count+frames)/fmt[2],
                pause_after_seconds=pause/fmt[2]))
            frame_count += frames + pause
            parts.append((s, take, data, pause))
        output = root / 'exports' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        (output / 'segments').mkdir(parents=True)
        for s, take, data, pause in parts:
            shutil.copyfile(relative_file(root, take['file']), output / 'segments' / (s['id']+'.wav'))
        combined = b''.join(data + bytes(pause*params[0]*2) for _, _, data, pause in parts)
        wav_write(output / 'full.wav', params, combined)
        atomic_json(output / 'timeline.json', dict(type='segment-boundaries-not-word-subtitles',
                    sample_rate=params[2], total_seconds=frame_count/params[2], segments=timeline))
        (output / 'script.txt').write_text(''.join(s['text'] for s in items), encoding='utf-8')
        return dict(directory=str(output.resolve()), audio=str((output/'full.wav').resolve()),
                    total_seconds=frame_count/params[2])


def doctor(model=None, probe=False):
    report = dict(version=VERSION, python=sys.version.split()[0], executable=sys.executable,
                  dependencies=environment_id(), model_ready=False,
                  voice_synthesis_tested=False)
    if model:
        report['model_fingerprint'] = model_fingerprint(model)
        report['model_ready'] = True
    if probe:
        import torch
        from omnivoice import OmniVoice
        report.update(cuda=torch.cuda.is_available(), model_class_importable=OmniVoice is not None)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    d = sub.add_parser('doctor')
    d.add_argument('--model')
    d.add_argument('--probe-runtime', action='store_true')
    v = sub.add_parser('voice')
    for flag in ('directory', 'audio', 'transcript', 'name'):
        v.add_argument('--'+flag, required=True)
    v.add_argument('--consent', action='store_true')
    init = sub.add_parser('init')
    for flag in ('project', 'script', 'voice', 'model'):
        init.add_argument('--'+flag, required=True)
    init.add_argument('--device', default='auto')
    init.add_argument('--seed', type=int, default=42)
    for name in ('show', 'configure', 'edit', 'render', 'rollback', 'export'):
        q = sub.add_parser(name)
        q.add_argument('--project', required=True)
        if name in ('edit', 'rollback'):
            q.add_argument('--segment', required=True)
        if name in ('render', 'export'):
            q.add_argument('--only')
        if name == 'render':
            q.add_argument('--retake', action='store_true')
            q.add_argument('--approved', action='store_true')
        if name == 'rollback':
            q.add_argument('--take', required=True)
        if name == 'configure':
            for field in ('voice', 'model', 'device'):
                q.add_argument('--'+field)
        if name == 'edit':
            q.add_argument('--text')
            spoken = q.add_mutually_exclusive_group()
            spoken.add_argument('--spoken-text')
            spoken.add_argument('--clear-spoken', action='store_true')
            q.add_argument('--pause-ms', type=int)
            q.add_argument('--speed', type=float)
    a = parser.parse_args()
    if a.command == 'doctor':
        result = doctor(a.model, a.probe_runtime)
    elif a.command == 'voice':
        result = voice_create(a.directory, a.audio, a.transcript, a.name, a.consent)
    elif a.command == 'init':
        result = project_init(a.project, a.script, a.voice, a.model, a.device, a.seed)
    elif a.command == 'render':
        result = render(a.project, a.only, a.retake, a.approved)
    elif a.command == 'export':
        result = export(a.project, a.only)
    elif a.command == 'rollback':
        result = rollback(a.project, a.segment, a.take)
    elif a.command == 'edit':
        changes = {k: getattr(a, k) for k in ('text', 'spoken_text', 'pause_ms', 'speed') if getattr(a, k) is not None}
        if a.clear_spoken:
            changes['spoken_text'] = None
        result = edit(a.project, a.segment, **changes)
    elif a.command == 'configure':
        with locked(a.project):
            result = project_load(a.project)
            for field in ('voice', 'model', 'device'):
                value = getattr(a, field)
                if value is not None:
                    result['config'][field] = value if field == 'device' else str(Path(value).resolve())
            context(result)
            save_project(a.project, result)
    else:
        result = project_load(a.project)
        ctx = context(result)
        for s in result['segments']:
            s['needs_render'] = not take_valid(a.project, s, current_take(s), ctx)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc), 'type': type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
