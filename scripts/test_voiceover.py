"""Behavioral tests use synthetic tones, NOT cloned speech."""
import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import importlib.util
import contextlib
from types import SimpleNamespace
import voiceover as v


class FakeEngine:
    calls = []

    def __init__(self, project):
        pass

    def generate(self, segment, path):
        self.calls.append(segment['id'])
        size = 2400 + len(segment['text'])*100
        # deterministic audible tone, never advertised as speech
        samples = [int(5000*math.sin(i*0.1)) for i in range(size)]
        v.wav_write(path, (1, 2, 24000), struct.pack('<'+'h'*size, *samples))


class VoiceoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root/'model'
        (self.model/'audio_tokenizer').mkdir(parents=True)
        for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json'):
            (self.model/name).write_text('{}')
        (self.model/'model.safetensors').write_bytes(b'test weights')
        (self.model/'audio_tokenizer'/'model.safetensors').write_bytes(b'test codec')
        reference = self.root/'ref.wav'
        v.wav_write(reference, (1, 2, 24000), struct.pack('<h', 1000)*72000)
        transcript = self.root/'ref.txt'
        transcript.write_text('这是参考录音。', encoding='utf-8')
        self.voice = self.root/'voice'
        v.voice_create(self.voice, reference, transcript, 'test', True)
        self.script = self.root/'script.txt'
        self.source = '第一句。第二句！第三句？'
        self.script.write_text(self.source, encoding='utf-8')
        self.project = self.root/'project'
        v.project_init(self.project, self.script, self.voice, self.model)
        FakeEngine.calls = []

    def render(self, **kwargs):
        return v.render(self.project, approved=True, engine_factory=FakeEngine, **kwargs)

    def state(self):
        return v.project_load(self.project)

    def test_split_preserves_original(self):
        for text in ('Hello world. Next!\n中文。', '\n开头空行。\n\n第二段', '版本3.14正常。', '末尾无标点', '他说：“好的！”随后离开。'):
            self.assertEqual(''.join(v.split_script(text)), text)

    def test_consent_required(self):
        with self.assertRaises(ValueError):
            v.voice_create(self.root/'no', self.root/'ref.wav', self.root/'ref.txt', 'test', False)

    def test_source_immutable(self):
        v.edit(self.project, '2', text='新的第二句。')
        self.assertEqual((self.project/'source.txt').read_text(encoding='utf-8'), self.source)

    def test_preview_then_continue_and_cache(self):
        self.render(only='1')
        self.assertEqual(FakeEngine.calls, ['001'])
        self.render()
        self.assertEqual(FakeEngine.calls, ['001', '002', '003'])
        self.assertTrue(all(x['reused'] for x in self.render()))

    def test_only_changed_sentence_rerenders(self):
        self.render()
        before = self.state()
        v.edit(self.project, '2', text='第二句改了。')
        result = self.render()
        self.assertEqual([r['reused'] for r in result], [True, False, True])
        after = self.state()
        for i in (0, 2):
            self.assertEqual(before['segments'][i]['takes'], after['segments'][i]['takes'])

    def test_pause_does_not_synthesize_and_timeline_matches_frames(self):
        self.render()
        old = v.export(self.project)
        v.edit(self.project, '1', pause_ms=731)
        new = v.export(self.project)
        self.assertEqual(len(FakeEngine.calls), 3)
        self.assertAlmostEqual(new['total_seconds']-old['total_seconds'], .481)
        timeline = v.load(Path(new['directory'])/'timeline.json')
        params, data = v.wav_read(new['audio'])
        self.assertEqual(len(data)/(params[0]*2*params[2]), timeline['total_seconds'])

    def test_retake_and_rollback_restore_content(self):
        self.render()
        original = copy.deepcopy(self.state()['segments'][1])
        v.edit(self.project, '2', text='替换文字。', speed=1.2)
        self.render(only='2', retake=True)
        v.rollback(self.project, '2', original['current'])
        restored = self.state()['segments'][1]
        self.assertEqual(restored['text'], original['text'])
        self.assertEqual(restored['speed'], 1)
        v.export(self.project)
        self.assertEqual(len(restored['takes']), 2)

    def test_stale_audio_not_exported(self):
        self.render()
        v.edit(self.project, '2', speed=1.2)
        with self.assertRaises(ValueError):
            v.export(self.project)

    def test_damaged_audio_not_reused(self):
        self.render()
        s = self.state()['segments'][1]
        v.relative_file(self.project, v.current_take(s)['file']).write_bytes(b'broken')
        with self.assertRaises(ValueError):
            v.export(self.project)
        result = self.render()
        self.assertFalse(result[1]['reused'])

    def test_voice_tamper_detected(self):
        (self.voice/'reference.wav').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.render()

    def test_model_change_invalidates_cache(self):
        self.render()
        (self.model/'config.json').write_text('{"updated":true}')
        with self.assertRaises(ValueError):
            v.export(self.project)
        self.assertTrue(all(not x['reused'] for x in self.render()))

    def test_spoken_override_cleared_when_text_changes(self):
        v.edit(self.project, '2', spoken_text='读音专用。')
        v.edit(self.project, '2', text='新正文。')
        self.assertIsNone(self.state()['segments'][1]['spoken_text'])

    def test_preview_export_refuses_missing_segment(self):
        self.render(only='1')
        v.export(self.project, only='1')
        with self.assertRaises(ValueError):
            v.export(self.project)

    def test_no_render_without_approval(self):
        with self.assertRaises(ValueError):
            v.render(self.project, engine_factory=FakeEngine)
        self.assertEqual(FakeEngine.calls, [])

    def test_bad_edits_and_ids(self):
        for changes in ({'text':''}, {'speed':float('nan')}, {'pause_ms':-1}, {'speed':3}):
            with self.assertRaises(ValueError):
                v.edit(self.project, '1', **changes)
        for only in ('999', '1,1'):
            with self.assertRaises(ValueError):
                self.render(only=only)

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            v.relative_file(self.project, '../ref.wav')

    def test_lock_and_fail_recovery(self):
        with v.locked(self.project):
            with self.assertRaises(FileExistsError):
                v.edit(self.project, '1', pause_ms=100)
        self.assertFalse((self.project/'.lock').exists())

    def test_partial_progress_saved_after_failure(self):
        class Fails(FakeEngine):
            def generate(inner, segment, path):
                if segment['id'] == '002':
                    raise RuntimeError('simulation')
                super().generate(segment, path)
        with self.assertRaises(RuntimeError):
            v.render(self.project, approved=True, engine_factory=Fails)
        self.assertIsNotNone(self.state()['segments'][0]['current'])
        self.assertIsNone(self.state()['segments'][1]['current'])
        self.assertFalse((self.project/'.lock').exists())

    def test_invalid_model_and_empty_script(self):
        (self.model/'audio_tokenizer'/'model.safetensors').unlink()
        with self.assertRaises(ValueError):
            v.model_fingerprint(self.model)
        with self.assertRaises(ValueError):
            v.split_script('   ')

    def test_different_formats_cannot_be_joined(self):
        self.render()
        p = self.state()
        s = p['segments'][1]
        t = v.current_take(s)
        path = v.relative_file(self.project, t['file'])
        v.wav_write(path, (1, 2, 16000), struct.pack('<h', 1000)*1600)
        t['sha256'] = v.file_hash(path)
        v.save_project(self.project, p)
        with self.assertRaisesRegex(ValueError, 'Incompatible'):
            v.export(self.project)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'numpy is inference-only dependency')
    def test_engine_singleton_channel_dimension(self):
        import numpy as np
        received = []
        engine = v.OmniEngine.__new__(v.OmniEngine)
        engine.torch = SimpleNamespace(manual_seed=lambda s:None,
                                      inference_mode=contextlib.nullcontext)
        engine.sf = SimpleNamespace(write=lambda path, audio, rate, **kw: received.append(audio.shape))
        engine.model = SimpleNamespace(generate=lambda **kw:[np.zeros((1, 2400))], sampling_rate=24000)
        engine.reference = self.root/'ref.wav'
        engine.voice = {'transcript':'参考'}
        engine.generate(self.state()['segments'][0], self.root/'out.wav')
        self.assertEqual(received, [(2400,)])

    @unittest.skipUnless(importlib.util.find_spec('soundfile'), 'soundfile is inference-only dependency')
    def test_24bit_reference_is_normalized_without_changing_source(self):
        import soundfile as sf
        import numpy as np
        source = self.root/'24bit.wav'
        sf.write(source, np.ones(72000)*.1, 24000, subtype='PCM_24')
        before = v.file_hash(source)
        voice = v.voice_create(self.root/'voice24', source, self.root/'ref.txt', '24bit', True)
        self.assertTrue(voice['normalized_copy'])
        self.assertEqual(v.file_hash(source), before)
        self.assertEqual(v.wav_read(self.root/'voice24/reference.wav')[0][1], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
